#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""网页套牌工作台 hub（MtgWorkbenchPlan Phase 0 hub + Phase 1 限制赛 +
Phase 2 构筑模式与核验接入）。

分层（决策 B：引擎先行，UI 最薄）：
  引擎纯函数    build_snapshot / serialize_deck / build_stats /
                hydrate_pool / apply_add|remove|move /
                build_roles / parse_cost_output / parse_rotation_output —— 可独立单测
  权威状态      WorkbenchState —— 持锁；牌表 + 水合牌池 + 卡片库 + 最近 seed
                + 核验缓存槽位（roles/combos/cost/audit/constructed）
  HTTP 层       make_handler —— 解析请求 → 调引擎 → 序列化，不含任何牌规则

端点：
  GET  /                    内嵌工作台页面（fetch 轮询 /api/snapshot，3s）
  GET  /api/snapshot        牌表 + 牌池 + 统计 + 最近 seed + checks 槽位的全量快照
  POST /api/builds/import   请求体为牌表文本；deck_model.parse_text 解析并替换状态
  GET  /api/export          标准导出文本（与 deck_model 解析器可往返解析）
  POST /api/pool            请求体为牌池文本（数量 牌名）；逐名水合（Scryfall），
                            查不到的牌行按名降级进 unresolved 并计数，不使导入失败
  GET  /api/pool            牌池快照：条目、水合/未水合统计、warnings
  POST /api/seed            调 limited_strategy.build_limited_deck；body 可选
                            {"colors": ["W","U"], "deck_size": 41, "set": "FRA"}；
                            结果经 deck_pooper.render_deck → import 路径装回状态；
                            无评分表时 table=None 降级并在 warnings 明示
  GET  /api/stats           当前牌表曲线/地数/land_check/法术力配比（deck_core 口径）；
                            无牌表返回空结构（空不是错误）
  POST /api/deck/add|remove|move  手动微调（main↔sideboard，同名 ≤4，
                            BASIC_LANDS/ANY_NUMBER 豁免），响应带重算 stats
  POST /api/seed-constructed  调 constructed_strategy.build_constructed_deck；
                            body {"candidates": <mtg_tool search --out 同构数组>,
                            "seeds": ["牌名",...], "format": "pioneer"(缺省),
                            "bo3": true, "strategy": "mid"(缺省), "platform":
                            "arena"(缺省)}；结果经 render_constructed_deck →
                            import 路径装回当前牌表；候选空/种子不在候选等
                            输入错误 → 400（与 deck_pooper constructed 口径一致）
  GET  /api/roles           当前牌表角色聚合（roles.classify_card）：各 root
                            张数分布、逐牌主角色、未水合牌名进 unknown 明示；
                            角色缺口对照 constructed_strategy.MODULE_QUOTAS
                            的 M1/M2/M3/M5/M8 wanted 配额（deck_config 的骨架
                            目标只服务限制赛，不作构筑基准——basis 字段明说）
  GET  /api/combos?format=pioneer&platform=arena&limit=20
                            当前牌表跑 mtg_combo_tool.search_deck（进程内，
                            75 请求/分钟节流，可能慢）。六桶原样展示；
                            stale/truncated 透出；查询失败（网络等）与"成功
                            零命中"显式分离（status=error vs 全零桶）
  GET  /api/cost            子进程跑 tools/newbie/deck_cost.py sig（与 CLI 输出
                            天然一致）；快照缺失/子进程失败 → 显式 error，
                            绝不返回零造价
  POST /api/audit           body {"format": "pioneer", "limited": false,
                            "bo3": false}（limited 必传，不做张数静默推断）；
                            聚合 mtg_tool validate（limited=true 带 --limited）与
                            rot_audit deck 两个子进程门禁；交通灯结构
                            {validate, rotation, ok}；子进程失败 = 门禁
                            unknown（null），不是通过

错误信封与 mtg_rules_tool 同构：
  {"status": "error", "error": {"type": ..., "message": ...}}
未知路径 404；handler 未捕获异常 500（traceback 只进 stderr，不回浏览器）；
完全解析不出任何条目的导入是业务错误（400），与"成功但带 skipped 警告"
明确分离。Ctrl+C 干净退出；CLI 出口接 runlog 留痕。
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import threading
import traceback
from collections.abc import Mapping
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import constructed_strategy as CS
import deck_core
import deck_model
import deck_pooper
import limited_strategy as LS
import mtg_combo_tool
import mtg_tool
import mtga_draft_tool
import roles as role_tags
import runlog

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8644
MAX_BODY_BYTES = 1024 * 1024
POLL_INTERVAL_MS = 3000

MAX_COPIES = 4                      # 限制赛同名上限（豁免名单除外）
SEED_PLAN_TOP_N = 5                 # seed 响应携带的枚举方案条数
DEFAULT_DECK_SIZE = 41              # 限制赛交付口径：17 地 + 24 其他
ALLOWED_DECK_SIZES = (40, 41)       # 40 张需在报告注明裁剪理由（draft_methodology §4）
EDIT_SECTIONS = ("main", "sideboard")

# ---- Phase 2 构筑模式缺省与工具路径 ----
DEFAULT_CONSTRUCTED_FORMAT = "pioneer"
DEFAULT_STRATEGY = "mid"            # deck_core.STRATEGY_TARGETS 之一
DEFAULT_PLATFORM = "arena"
DEFAULT_COMBO_LIMIT = 20
# mtg_combo_tool CLI 支持的赛制集合（search 子命令口径，非法值在此 400）
COMBO_FORMATS = ("standard", "pioneer", "explorer", "modern", "legacy",
                 "vintage", "commander", "brawl", "standardbrawl",
                 "historic", "timeless", "alchemy", "pauper")
TOOL_DIR = Path(__file__).resolve().parent
COST_TOOL_SCRIPT = TOOL_DIR / "newbie" / "deck_cost.py"
VALIDATE_TOOL_SCRIPT = TOOL_DIR / "mtg_tool.py"
ROT_TOOL_SCRIPT = TOOL_DIR / "rot_audit.py"
SUBPROCESS_TIMEOUT = 180            # cost/audit 单个子进程的上限秒数
# 角色缺口基准：constructed_strategy 的 M1-M9 模块配额（deck_config 的
# STRATEGY_TARGETS 骨架只服务限制赛深度检查，不作构筑基准；basis 字段明说）
GAP_MODULES = tuple(CS.REQUIRED_MODULES)    # ("M1", "M2", "M3", "M5", "M8")

# 基本地 → 颜色（mana_sources 统计用；Wastes 无色不列入）
_BASIC_LAND_COLORS = {
    "Plains": "W", "Island": "U", "Swamp": "B",
    "Mountain": "R", "Forest": "G",
    "Snow-Covered Plains": "W", "Snow-Covered Island": "U",
    "Snow-Covered Swamp": "B", "Snow-Covered Mountain": "R",
    "Snow-Covered Forest": "G",
}

SECTIONS = deck_model.SECTIONS  # ("commander", "companion", "main", "sideboard")
SECTION_TITLES = {"commander": "Commander", "companion": "Companion",
                  "main": "Deck", "sideboard": "Sideboard"}


class WorkbenchError(Exception):
    """工作台启动/服务级错误（如端口占用），CLI 出口给清晰错误。"""


class EmptyImportError(ValueError):
    """牌表/牌池文本未解析出任何条目（业务错误，区别于带警告的成功）。"""


class PoolEmptyError(ValueError):
    """seed 时无可用牌池（未导入或全部牌名水合失败）。"""


class DeckEditError(ValueError):
    """手动微调违反约束（同名上限、存量不足、分区非法等）。"""


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------ 引擎纯函数

def build_snapshot(deck, session):
    """纯函数：Deck + 会话元数据 → 快照 dict（import 响应与其同构）。"""
    sections, counts = {}, {}
    for sec in SECTIONS:
        cards = getattr(deck, sec)
        sections[sec] = [{"qty": card.qty, "name": card.name} for card in cards]
        counts[sec] = sum(card.qty for card in cards)
    skipped = [{"line_no": item.line_no, "raw": item.raw, "reason": item.reason}
               for item in deck.skipped]
    return {"status": "ok", "sections": sections, "counts": counts,
            "total": sum(counts.values()), "skipped": skipped,
            "warnings": ["第 {} 行已跳过（{}）: {}".format(
                item.line_no, item.reason, item.raw) for item in deck.skipped],
            "session": session}


def serialize_deck(deck):
    """纯函数：Deck → 标准导出文本。分区头部（Deck/Sideboard/Commander/
    Companion）为 deck_model 识别的段头，`数量 牌名` 行可被 _LINE_RE 往返
    解析；空分区不输出段头，blank-line 切备牌规则因此不会干扰再导入。"""
    lines = []
    for sec in SECTIONS:
        cards = getattr(deck, sec)
        if not cards:
            continue
        lines.append(SECTION_TITLES[sec])
        lines.extend("{} {}".format(card.qty, card.name) for card in cards)
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ 限制赛引擎（Phase 1）

def default_fetch_card(name):
    """牌名 → 水合卡片 dict（Scryfall，走 mtg_tool 磁盘缓存）。

    生产路径；测试经 WorkbenchState.import_pool(fetch_card=...) 注入假实现。
    复用 deck_pooper 的既有水合逻辑（含 normalize_card 字段对齐）。
    """
    return deck_pooper._fetch_named(name, use_cache=True)


def parse_pool_entries(text):
    """牌池文本 → ([(qty, name)], [skipped dict])。

    复用 deck_model.parse_text：容忍 Deck/Sideboard 段头与 `(SET) 编号` 后缀；
    主/备两个分区合并计入牌池（牌池没有备牌概念，空行误切无副作用）。
    一个条目都解析不出时抛 EmptyImportError。
    """
    deck = deck_model.parse_text(text)
    entries = [(card.qty, card.name)
               for sec in ("main", "sideboard") for card in getattr(deck, sec)]
    if not entries:
        raise EmptyImportError("牌池文本未解析出任何 '数量 牌名' 条目")
    skipped = [{"line_no": item.line_no, "raw": item.raw, "reason": item.reason}
               for item in deck.skipped]
    return entries, skipped


def hydrate_pool(entries, fetch_card):
    """逐名水合牌池：fetch_card(name) → 卡片 dict。

    查不到/拉取失败（mtg_tool.MtgToolError）按名降级进 unresolved 并累计
    数量——单牌查不到不等于整个导入失败。返回 (cards, unresolved)。
    """
    cards, unresolved, cache = [], {}, {}
    for qty, name in entries:
        key = name.lower()
        if key not in cache:
            try:
                cache[key] = dict(fetch_card(name))
            except mtg_tool.MtgToolError as exc:
                cache[key] = None
                unresolved[key] = {"name": name, "qty": 0, "reason": str(exc)}
        if cache[key] is None:
            unresolved[key]["qty"] += qty
        else:
            item = dict(cache[key])
            item["count"] = qty
            cards.append(item)
    return cards, list(unresolved.values())


def build_pool_snapshot(pool, unresolved, meta, skipped):
    """纯函数：水合牌池 + 元数据 → 快照 dict（POST/GET /api/pool 同构）。"""
    entries = [{"qty": int(card.get("count") or 1),
                "name": str(card.get("name") or ""),
                "cmc": card.get("cmc"),
                "colors": list(card.get("colors") or []),
                "type_line": str(card.get("type_line") or card.get("type") or "")}
               for card in pool]
    warnings = ["第 {} 行已跳过（{}）: {}".format(
        item["line_no"], item["reason"], item["raw"]) for item in skipped]
    warnings.extend("牌名查不到，已按行降级跳过（共 {} 张）: {}（{}）".format(
        item["qty"], item["name"], item["reason"]) for item in unresolved)
    return {"status": "ok",
            "entries": entries,
            "unresolved": unresolved,
            "counts": {"names": len(entries),
                       "cards": sum(item["qty"] for item in entries),
                       "unresolved_names": len(unresolved),
                       "unresolved_qty": sum(item["qty"] for item in unresolved),
                       "skipped_lines": len(skipped)},
            "imported_at": meta.get("imported_at"),
            "source_name": meta.get("source_name"),
            "warnings": warnings}


def _lookup_card(card_db, name):
    """卡片库查找：全名优先，回退 MDFC 正面名。"""
    return card_db.get(name) or card_db.get(deck_model.front_name(name))


def build_stats(deck, card_db):
    """纯函数：牌表统计（deck_core 口径）。无牌表返回空结构（status ok）。

    card_db 未覆盖的牌名进 unknown 并从曲线/法术力配比中排除（明示降级，
    不静默当 0 费）。基本地无需水合即可识别；非基本地依赖 type_line。
    """
    curve, pips, sources, unknown = {}, {}, {}, []
    lands = nonlands = known_nonlands = 0
    cmc_sum = 0.0
    main_qty = sum(card.qty for card in deck.main)
    for ref in deck.main:
        card = _lookup_card(card_db, ref.name)
        type_line = ""
        if card is not None:
            type_line = str(card.get("type_line") or card.get("type") or "")
        is_basic = ref.name in deck_model.BASIC_LANDS
        if is_basic or "land" in type_line.split(" // ", 1)[0].lower():
            lands += ref.qty
            if is_basic:
                colors = [_BASIC_LAND_COLORS[ref.name]] if ref.name in _BASIC_LAND_COLORS else []
            else:
                colors = [c for c in (card.get("colors") or []) if c in LS.COLORS]
            for color in colors:
                sources[color] = sources.get(color, 0) + ref.qty
            continue
        nonlands += ref.qty
        if card is None:
            if ref.name not in unknown:
                unknown.append(ref.name)
            continue
        try:
            cmc = float(card.get("cmc") or 0)
        except (TypeError, ValueError):
            cmc = 0.0
        slot = deck_core.cmc_slot(cmc)
        curve[slot] = curve.get(slot, 0) + ref.qty
        known_nonlands += ref.qty
        cmc_sum += cmc * ref.qty
        cost = str(card.get("mana_cost") or card.get("cost") or "")
        for color, value in deck_core.parse_mana_pips(cost).items():
            pips[color] = pips.get(color, 0) + value * ref.qty
    curve_label, _bonus = deck_core.curve_rating(curve)
    check_size = main_qty if main_qty >= 40 else 40
    p3, p5, ok = deck_core.land_check(lands, check_size)
    warnings = []
    if unknown:
        warnings.append("以下 {} 张牌无卡片数据（未水合），曲线/法术力配比未计入: {}".format(
            sum(ref.qty for ref in deck.main if ref.name in unknown),
            "、".join(unknown)))
    return {"status": "ok",
            "main": main_qty,
            "sideboard": sum(card.qty for card in deck.sideboard),
            "total": main_qty + sum(card.qty for card in deck.sideboard),
            "lands": lands,
            "nonlands": nonlands,
            "curve": {str(slot): curve[slot] for slot in sorted(curve)},
            "curve_label": curve_label,
            "average_cmc": round(cmc_sum / known_nonlands, 2) if known_nonlands else 0.0,
            "pips": {color: round(pips[color], 1) for color in sorted(pips)},
            "mana_sources": {color: sources[color] for color in sorted(sources)},
            "land_check": {"deck_size": check_size, "lands": lands,
                           "p3": p3, "p5": p5, "ok": ok},
            "unknown": unknown,
            "warnings": warnings}


def _copy_limit_exempt(name):
    """同名 ≤4 的豁免：基本地（限制赛无限）与 ANY_NUMBER 名单。"""
    return name in deck_model.BASIC_LANDS or name in deck_model.ANY_NUMBER


def _check_edit_args(name, section, qty):
    if not isinstance(name, str) or not name.strip():
        raise DeckEditError("牌名不能为空")
    if section not in EDIT_SECTIONS:
        raise DeckEditError("只允许操作 main/sideboard 分区，收到: {!r}".format(section))
    if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
        raise DeckEditError("qty 必须是正整数，收到: {!r}".format(qty))


def _rebuild(deck, section, rows):
    """按 [[qty, name], ...] 重建指定分区，返回新 Deck（其余分区原样）。"""
    cards = tuple(deck_model.CardRef(qty, name, section)
                  for qty, name in rows if qty > 0)
    return deck_model.Deck(commander=deck.commander, companion=deck.companion,
                           main=cards if section == "main" else deck.main,
                           sideboard=cards if section == "sideboard" else deck.sideboard,
                           skipped=())


def apply_add(deck, name, section, qty):
    """纯函数：加牌，返回新 Deck。非豁免同名超 4 张抛 DeckEditError。"""
    _check_edit_args(name, section, qty)
    rows = [[card.qty, card.name] for card in getattr(deck, section)]
    have = sum(row[0] for row in rows if row[1] == name)
    if not _copy_limit_exempt(name) and have + qty > MAX_COPIES:
        raise DeckEditError(
            "'{}' 在 {} 已有 {} 张，再加 {} 张超过同名 {} 张上限"
            .format(name, section, have, qty, MAX_COPIES))
    for row in rows:
        if row[1] == name:
            row[0] += qty
            break
    else:
        rows.append([qty, name])
    return _rebuild(deck, section, rows)


def apply_remove(deck, name, section, qty):
    """纯函数：减牌，返回新 Deck。存量不足抛 DeckEditError。"""
    _check_edit_args(name, section, qty)
    rows = [[card.qty, card.name] for card in getattr(deck, section)]
    have = sum(row[0] for row in rows if row[1] == name)
    if have < qty:
        raise DeckEditError("'{}' 在 {} 只有 {} 张，无法移除 {} 张"
                            .format(name, section, have, qty))
    for row in rows:
        if row[1] == name:
            row[0] -= qty
            break
    return _rebuild(deck, section, rows)


def apply_move(deck, name, from_section, to_section, qty):
    """纯函数：main↔sideboard 搬移（守恒），返回新 Deck。"""
    if from_section == to_section:
        raise DeckEditError("from/to 分区不能相同: {!r}".format(from_section))
    moved = apply_remove(deck, name, from_section, qty)
    return apply_add(moved, name, to_section, qty)


def summarize_plans(plans, top_n=SEED_PLAN_TOP_N):
    """ColorPlan 列表 → 页面展示用的摘要 dict（颜色组合 + score 等）。"""
    return [{"colors": list(plan.colors),
             "score": round(plan.score, 3),
             "depth_ok": plan.depth_ok,
             "curve_label": plan.curve_label,
             "playable_count": plan.playable_count}
            for plan in plans[:top_n]]


def summarize_seed(limited, plans, deck_size, table_warnings):
    """LimitedDeck + 枚举方案 → seed 结果摘要（写入快照的 seed 字段）。"""
    return {"colors": list(limited.colors),
            "strategy": limited.strategy,
            "deck_size": deck_size,
            "depth_ok": limited.depth_ok,
            "depth_note": limited.depth_note,
            "average_cmc": round(limited.average_cmc, 2),
            "lands": dict(limited.lands),
            "nonbasic_lands": [{"qty": sel.count, "name": str(sel.card.get("name") or "")}
                               for sel in limited.nonbasic_lands],
            "land_check": {"p3": limited.land_check[0],
                           "p5": limited.land_check[1],
                           "ok": limited.land_check[2]},
            "cuts": list(limited.cuts),
            "valid": limited.valid,
            "violations": list(limited.violations),
            "plans": summarize_plans(plans),
            "warnings": list(table_warnings)}


# ------------------------------------------------------------------ 构筑引擎（Phase 2）

def parse_constructed_body(body):
    """seed-constructed 请求体校验 → (candidates, seed_names, fmt, bo3, strategy, platform)。

    与 deck_pooper constructed 同一输入口径：candidates 是 mtg_tool search
    --out 的同构非空数组；seeds 是非空牌名数组（各按 1 张必留种子处理）。
    输入错误抛 ValueError（HTTP 400）；strategy 合法性由
    build_constructed_deck 复核（非法 strategy 同样 ValueError → 400）。
    """
    candidates = body.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError(
            "candidates 必须是非空 JSON 数组（mtg_tool search --out 的同构产物）")
    if any(not isinstance(item, Mapping) for item in candidates):
        raise ValueError("candidates 包含非对象记录")
    seeds = body.get("seeds")
    if not isinstance(seeds, list) or not seeds:
        raise ValueError("seeds 必须是非空牌名数组，如 [\"牌名A\", \"牌名B\"]")
    seed_names = []
    for item in seeds:
        name = item.strip() if isinstance(item, str) else ""
        if not name:
            raise ValueError("seeds 只接受非空牌名字符串，收到: {!r}".format(item))
        seed_names.append(name)
    fmt = body.get("format") or DEFAULT_CONSTRUCTED_FORMAT
    if not isinstance(fmt, str) or not fmt.strip():
        raise ValueError("format 必须是非空字符串，收到: {!r}".format(fmt))
    strategy = body.get("strategy") or DEFAULT_STRATEGY
    if not isinstance(strategy, str):
        raise ValueError("strategy 必须是字符串，收到: {!r}".format(strategy))
    platform = body.get("platform") or DEFAULT_PLATFORM
    if not isinstance(platform, str):
        raise ValueError("platform 必须是字符串，收到: {!r}".format(platform))
    return candidates, seed_names, fmt.strip(), bool(body.get("bo3")), \
        strategy.strip().lower(), platform.strip().lower()


def summarize_constructed(built):
    """ConstructedDeck → seed-constructed 响应摘要（同时写入 checks.constructed）。"""
    return {"format": built.format,
            "colors": list(built.colors),
            "valid": built.valid,
            "violations": list(built.violations),
            "report": list(built.report),
            "modules": dict(built.modules),
            "main": sum(item.count for item in built.main),
            "sideboard": sum(item.count for item in built.sideboard),
            "commander": sum(item.count for item in built.commander)}


def build_roles(deck, card_db, fetch_card):
    """纯函数：牌表角色聚合（roles.classify_card 口径）。

    水合顺序：卡片库（牌池导入的缓存）→ fetch_card（缺省 Scryfall）；
    查不到的牌名按名聚合并量进 unknown（带原因），不静默跳过也不失败。
    distribution 按"命中即计"统计（一张牌可贡献多个 root）；cards 给逐牌
    主角色（primary_role 口径）与模块归属（constructed_strategy._module）。
    gaps 对照 constructed_strategy.MODULE_QUOTAS 的 REQUIRED_MODULES wanted
    配额；deck_config 的骨架目标是限制赛口径，不作构筑基准（basis 明说）。
    """
    distribution = {root: 0 for root in role_tags.ROOTS}
    modules = {}
    cards = []
    failures = {}
    cache = {}
    total_qty = 0
    refs = [ref for sec in SECTIONS for ref in getattr(deck, sec)]
    for ref in refs:
        total_qty += ref.qty
        card = _lookup_card(card_db, ref.name)
        if card is None:
            key = ref.name.lower()
            if key in failures:
                failures[key]["qty"] += ref.qty
                continue
            if key not in cache:
                try:
                    cache[key] = dict(fetch_card(ref.name))
                except mtg_tool.MtgToolError as exc:
                    cache[key] = None
                    failures[key] = {"name": ref.name, "qty": 0,
                                     "reason": str(exc)}
            card = cache[key]
            if card is None:
                failures[key]["qty"] += ref.qty    # 首次失败即计入张数
                continue
        tags = role_tags.classify_card(card)
        roots = [root for root in role_tags.ROOTS if role_tags.has_root(tags, root)]
        for root in roots:
            distribution[root] += ref.qty
        module = CS._module(card) or "other"
        modules[module] = modules.get(module, 0) + ref.qty
        cards.append({"name": ref.name, "qty": ref.qty,
                      "primary": role_tags.primary_role(tags, card),
                      "roots": roots, "module": module})
    gaps = []
    for module in GAP_MODULES:
        have = modules.get(module, 0)
        want = CS.MODULE_QUOTAS[module][1]
        if have < want:
            gaps.append({"module": module, "have": have, "want": want,
                         "deficit": want - have})
    return {"status": "ok",
            "main": sum(card.qty for card in deck.main),
            "sideboard": sum(card.qty for card in deck.sideboard),
            "total": total_qty,
            "distribution": distribution,
            "cards": cards,
            "modules": modules,
            "gaps": gaps,
            "basis": "constructed_strategy.MODULE_QUOTAS 的 M1/M2/M3/M5/M8 "
                     "wanted 配额（deck_config 骨架目标仅服务限制赛，"
                     "不作构筑基准）",
            "unknown": sorted(failures.values(), key=lambda item: item["name"])}


def summarize_combo(combo):
    """analyze 产出的单个组合技 → 面板展示摘要（保留状态字段，不丢信息）。"""
    components = [{"name": item.get("name"), "quantity": item.get("quantity", 1)}
                  for item in combo.get("components") or []]
    availability = combo.get("combined") or {}
    return {"id": combo.get("id"),
            "url": combo.get("source_url"),
            "popularity": combo.get("popularity") or 0,
            "cards": " + ".join("{}×{}".format(item["quantity"], item["name"])
                                for item in components),
            "components": components,
            "produces": list(combo.get("results") or []),
            "legality": (combo.get("legality") or {}).get("status"),
            "missing": list(availability.get("missing_cards") or []),
            "unverified_templates": list(availability.get("unverified_templates") or []),
            "description": (combo.get("description") or "")[:300]}


def summarize_combos(result, format_name, platform):
    """mtg_combo_tool.search_deck 的结果 dict → 面板/快照序列化。

    六桶、stale、truncated、warnings 原样透出；成功零命中 = 全零桶 +
    status ok，与查询失败（status error）显式分离。
    """
    buckets = {}
    group_counts = {}
    for key in mtg_combo_tool.OUTPUT_BUCKETS:
        combos = result.get(key) or []
        buckets[key] = [summarize_combo(item) for item in combos]
        group_counts[key] = len(buckets[key])
    return {"status": "ok",
            "format": format_name,
            "platform": platform,
            "buckets": buckets,
            "group_counts": group_counts,
            "variant_count": result.get("variant_count"),
            "analyzed_variant_count": result.get("analyzed_variant_count"),
            "unexamined_variant_count": result.get("unexamined_variant_count"),
            "stale": bool(result.get("stale")),
            "truncated": bool(result.get("truncated")),
            "warnings": list(result.get("warnings") or [])}


# ------------------------------------------------------------------ 外部工具输出解析（Phase 2）

def _run_tool(argv):
    """跑外部工具子进程（字节捕获，自行按 UTF-8 解码；OSError/超时向上抛）。"""
    return subprocess.run(argv, capture_output=True, timeout=SUBPROCESS_TIMEOUT)


def _completed_text(completed):
    stdout = (completed.stdout or b"").decode("utf-8", "replace")
    stderr = (completed.stderr or b"").decode("utf-8", "replace")
    return stdout, stderr


def parse_cost_output(text):
    """deck_cost.py sig 的文本输出 → 结构化 dict。

    deck_cost 只有文本输出（无 --json），按行锚解析；缺行字段给 None，
    不编造。预算档位以 ✗ 前缀判定失败。
    """
    signature = None
    budget = None
    packs = {"core": None, "all": None, "penalty": None}
    stats = None
    unrecognized = []
    match = re.search(r"造价签名\s+(\S+)", text)
    if match:
        signature = match.group(1)
    match = re.search(r"物质点预算\s+(.*?)\s*｜\s*(.*)", text)
    if match:
        tier = match.group(1).strip()
        budget = {"ok": not tier.startswith("✗"),
                  "tier": tier.lstrip("✅ ").strip(),
                  "detail": match.group(2).strip()}
    match = re.search(r"PP核心[^=]*=\s*([\d.]+)", text)
    if match:
        packs["core"] = float(match.group(1))
    match = re.search(r"PP全量[^=]*=\s*([\d.]+)", text)
    if match:
        packs["all"] = float(match.group(1))
    match = re.search(r"惩罚系数\s*=\s*([\d.]+)", text)
    if match:
        packs["penalty"] = float(match.group(1))
    match = re.search(r"非基本地\s*(\d+)\s*张\s*｜\s*生物\s*(\d+)\s*张\s*｜\s*"
                      r"主牌合计\s*(\d+)\s*张", text)
    if match:
        stats = {"nonbasic_lands": int(match.group(1)),
                 "creatures": int(match.group(2)),
                 "main_total": int(match.group(3))}
    match = re.search(r"未识别[:：]\s*(.+)", text)
    if match:
        unrecognized = [name.strip() for name in match.group(1).split(",")
                        if name.strip()]
    return {"signature": signature, "budget": budget, "packs": packs,
            "stats": stats, "unrecognized": unrecognized}


def parse_validate_output(stdout):
    """mtg_tool validate 的 stdout → 违规列表（'[违规]' 行）。"""
    violations = []
    for line in stdout.splitlines():
        if "[违规]" in line:
            violations.append(line.split("[违规]", 1)[1].strip())
    return violations


_ROT_CARD_RE = re.compile(r"^\s*(✅存活|❌将退)\s+(\d+)\s+(.+?)\s+存活印刷")
_ROT_TOTAL_RE = re.compile(r"^(主牌|备牌)：(\d+)/(\d+) 张轮替后存活（将退 (\d+) 张）")


def parse_rotation_output(stdout):
    """rot_audit deck 的 stdout → 结构化轮替审计。

    ok = 主备两区都没有"将退"牌；网络失败时 rot_audit 仍 exit 0 但 stderr
    带 '! FAIL' 行——由调用方结合 returncode/stderr 判定 unknown，这里只
    负责忠实解析 stdout。
    """
    section = None
    rotating = []
    totals = {}
    for line in stdout.splitlines():
        if line.startswith("== "):
            section = line[3:].strip()
            continue
        match = _ROT_CARD_RE.match(line)
        if match:
            if match.group(1) == "❌将退":
                rotating.append({"name": match.group(3).strip(),
                                 "qty": int(match.group(2)),
                                 "section": section or "?"})
            continue
        match = _ROT_TOTAL_RE.match(line.strip())
        if match:
            totals[match.group(1)] = {"survive": int(match.group(2)),
                                      "total": int(match.group(3)),
                                      "rotating": int(match.group(4))}
    main = totals.get("主牌", {"survive": 0, "total": 0, "rotating": 0})
    side = totals.get("备牌", {"survive": 0, "total": 0, "rotating": 0})
    return {"main": main, "sideboard": side,
            "rotating_cards": rotating,
            "ok": main["rotating"] == 0 and side["rotating"] == 0}


# ------------------------------------------------------------------ 权威状态

class WorkbenchState:
    """权威状态：当前 Deck + 会话元数据（导入时间/来源/序号）。

    所有读写持锁，import 的纯解析在锁外完成，锁内只做替换 + 快照构造，
    并发导入因此是安全的串行化（最后一次成功写入获胜）。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._deck = deck_model.Deck()
        self._imported_at = None
        self._source_name = None
        self._import_seq = 0
        self._pool = []
        self._pool_unresolved = []
        self._pool_skipped = []
        self._pool_meta = {"imported_at": None, "source_name": None}
        self._card_db = {}
        self._last_seed = None
        # Phase 2 核验缓存槽位：roles/combos/cost/audit/constructed，
        # 每项 {"status": "ok"/"error", "checked_at": iso, "result"/"error": ...}
        self._slots = {name: None for name in
                       ("roles", "combos", "cost", "audit", "constructed")}

    def _record_slot(self, name, entry):
        with self._lock:
            self._slots[name] = entry

    def _session_locked(self):
        return {"imported_at": self._imported_at,
                "source_name": self._source_name, "import_seq": self._import_seq}

    def _pool_locked(self):
        return build_pool_snapshot(self._pool, self._pool_unresolved,
                                   self._pool_meta, self._pool_skipped)

    def snapshot(self):
        with self._lock:
            snap = build_snapshot(self._deck, self._session_locked())
            snap["pool"] = self._pool_locked()
            snap["stats"] = build_stats(self._deck, self._card_db)
            snap["seed"] = self._last_seed
            snap["checks"] = {name: (dict(entry) if entry else None)
                              for name, entry in self._slots.items()}
            return snap

    def export_text(self):
        with self._lock:
            return serialize_deck(self._deck)

    def import_text(self, text, source_name=None):
        """解析并替换当前牌表，返回新快照 dict。

        完全解析不出任何条目时抛 EmptyImportError（失败），有 skipped
        行但仍有个体条目时正常返回（成功但带 warnings，见快照）。
        """
        deck = deck_model.parse_text(text)
        if not any(getattr(deck, sec) for sec in SECTIONS):
            raise EmptyImportError(
                "牌表文本未解析出任何条目；期望 '数量 英文名' 行或分区段头")
        with self._lock:
            self._deck = deck
            self._imported_at = _now_iso()
            self._source_name = source_name or None
            self._import_seq += 1
            return build_snapshot(deck, self._session_locked())

    def import_pool(self, text, source_name=None, fetch_card=None):
        """解析并水合牌池，替换池状态，返回牌池快照。

        fetch_card 可注入（测试用假实现）；缺省走 default_fetch_card
        （Scryfall 网络 + mtg_tool 缓存）。水合失败的牌名按行降级进
        unresolved——只要文本解析出条目就返回成功（带 warnings）。
        """
        entries, skipped = parse_pool_entries(text)
        pool, unresolved = hydrate_pool(entries, fetch_card or default_fetch_card)
        with self._lock:
            self._pool = pool
            self._pool_unresolved = unresolved
            self._pool_skipped = skipped
            self._pool_meta = {"imported_at": _now_iso(),
                               "source_name": source_name or None}
            for card in pool:
                self._card_db[str(card.get("name") or "")] = card
            return self._pool_locked()

    def pool_snapshot(self):
        with self._lock:
            return self._pool_locked()

    def stats(self):
        with self._lock:
            return build_stats(self._deck, self._card_db)

    def seed_limited(self, colors=None, deck_size=DEFAULT_DECK_SIZE,
                     table=None, table_warnings=()):
        """调 limited_strategy 组牌，结果经 render_deck → import_text 装回
        当前牌表（复用 Phase 0 导入路径，不另起状态）。返回带 seed 摘要的
        快照。无可用牌池抛 PoolEmptyError；非法色组/deck_size 抛 ValueError。
        """
        with self._lock:
            pool = list(self._pool)
        if not pool:
            raise PoolEmptyError(
                "没有可用牌池：请先 POST /api/pool 导入（全部牌名水合失败同样视为空池）")
        plans = LS.enumerate_color_plans(pool, table)
        limited = LS.build_limited_deck(pool, table=table,
                                        forced_colors=colors, deck_size=deck_size)
        snapshot = self.import_text(deck_pooper.render_deck(limited),
                                    source_name="seed")
        seed = summarize_seed(limited, plans, deck_size, table_warnings)
        with self._lock:
            self._last_seed = seed
        snapshot["seed"] = seed
        return snapshot

    def _edit(self, func, *args):
        """手动微调：锁内应用纯函数并返回 快照 + 重算 stats。"""
        with self._lock:
            self._deck = func(self._deck, *args)
            snap = build_snapshot(self._deck, self._session_locked())
            snap["stats"] = build_stats(self._deck, self._card_db)
            return snap

    def deck_add(self, name, section, qty=1):
        return self._edit(apply_add, name, section, qty)

    def deck_remove(self, name, section, qty=1):
        return self._edit(apply_remove, name, section, qty)

    def deck_move(self, name, from_section, to_section, qty=1):
        return self._edit(apply_move, name, from_section, to_section, qty)

    # -------------------------------------------------- Phase 2 构筑模式

    def _deck_copy(self):
        with self._lock:
            deck = self._deck
            return deck_model.Deck(commander=deck.commander,
                                   companion=deck.companion,
                                   main=deck.main, sideboard=deck.sideboard,
                                   skipped=())

    def seed_constructed(self, candidates, seed_names, fmt, bo3,
                         strategy, platform):
        """调 constructed_strategy 组构筑牌并装回当前牌表（import 路径复用）。

        引擎的 ValueError（种子不在候选池、strategy 非法、候选记录缺 name
        等）原样向上抛，由 HTTP 层映射 400——与 deck_pooper constructed
        的报错口径一致。返回带 constructed 摘要的快照。
        """
        seed = CS.SeedSet(main=tuple((1, name) for name in seed_names))
        built = CS.build_constructed_deck(candidates, seed, fmt, bo3=bo3,
                                          strategy=strategy, platform=platform)
        snapshot = self.import_text(
            deck_pooper.render_constructed_deck(built),
            source_name="seed-constructed")
        summary = summarize_constructed(built)
        snapshot["constructed"] = summary
        self._record_slot("constructed", {"status": "ok" if built.valid else "error",
                                          "checked_at": _now_iso(),
                                          "result": summary})
        return snapshot

    def roles(self, fetch_card=None):
        """当前牌表角色聚合；未水合牌名进 unknown 明示（不失败）。"""
        with self._lock:
            deck = self._deck
            card_db = dict(self._card_db)
        result = build_roles(deck, card_db, fetch_card or default_fetch_card)
        result["checked_at"] = _now_iso()
        self._record_slot("roles", {"status": "ok",
                                    "checked_at": result["checked_at"],
                                    "result": result})
        return result

    def combos(self, format_name, platform, limit):
        """当前牌表跑 mtg_combo_tool.search_deck（进程内，可能慢）。

        返回 (payload, ok)。查询失败（网络/Spellbook/数据错误）→
        (error 信封, False)；成功（含零命中、stale、truncated）→
        (序列化结果, True)。stale/truncated/warnings 原样透出。
        """
        deck = self._deck_copy()
        if not deck.main and not deck.commander:
            raise ValueError("当前牌表为空：请先导入牌表再查询组合技")
        checked_at = _now_iso()
        try:
            raw = mtg_combo_tool.search_deck(deck, format_name, platform,
                                             limit=limit)
        except (mtg_tool.MtgToolError, ValueError, OSError) as exc:
            envelope = _error_envelope(type(exc).__name__, str(exc))
            envelope["source"] = "commander-spellbook"
            envelope["checked_at"] = checked_at
            self._record_slot("combos", {"status": "error",
                                         "checked_at": checked_at,
                                         "error": envelope["error"]})
            return envelope, False
        result = summarize_combos(raw, format_name, platform)
        result["checked_at"] = checked_at
        self._record_slot("combos", {"status": "ok", "checked_at": checked_at,
                                     "result": result})
        return result, True

    def cost(self):
        """子进程跑 deck_cost.py sig（与 CLI 天然一致）。

        返回 (payload, ok)。子进程失败/超时/快照缺失 → (error 信封, False)，
        绝不返回零造价；空牌表同样显式报错。
        """
        checked_at = _now_iso()
        text = self.export_text()
        if not text.strip():
            envelope = _error_envelope(
                "EmptyDeckError", "当前牌表为空：请先导入牌表再核算造价")
            self._record_slot("cost", {"status": "error",
                                       "checked_at": checked_at,
                                       "error": envelope["error"]})
            return envelope, False
        try:
            with tempfile.TemporaryDirectory(prefix="workbench_cost_") as tmp:
                deck_path = Path(tmp) / "deck.txt"
                deck_path.write_text(text, encoding="utf-8")
                completed = _run_tool([sys.executable, "-X", "utf8",
                                       str(COST_TOOL_SCRIPT), "sig",
                                       str(deck_path)])
        except (OSError, subprocess.TimeoutExpired) as exc:
            envelope = _error_envelope(type(exc).__name__,
                                       "造价工具子进程失败: {}".format(exc))
            self._record_slot("cost", {"status": "error",
                                       "checked_at": checked_at,
                                       "error": envelope["error"]})
            return envelope, False
        stdout, stderr = _completed_text(completed)
        if completed.returncode != 0:
            envelope = _error_envelope(
                "CostToolError",
                "deck_cost sig 退出码 {}：{}".format(
                    completed.returncode, " ".join(stderr.split())[:500] or
                    " ".join(stdout.split())[:500] or "无输出"))
            self._record_slot("cost", {"status": "error",
                                       "checked_at": checked_at,
                                       "error": envelope["error"]})
            return envelope, False
        result = parse_cost_output(stdout)
        result.update({"status": "ok", "checked_at": checked_at})
        self._record_slot("cost", {"status": "ok", "checked_at": checked_at,
                                   "result": result})
        return result, True

    def audit(self, fmt, limited, bo3):
        """聚合 mtg_tool validate 与 rot_audit deck 两个子进程门禁。

        返回 (payload, http_ok)。http_ok 仅表示请求本身可否 200；门禁结果在
        payload.validate/rotation 的 status（pass/fail/unknown）与顶层 ok
        （True/False/None——任何一门 unknown 则整体 None，绝不把失败当通过）。
        """
        checked_at = _now_iso()
        text = self.export_text()
        if not text.strip():
            envelope = _error_envelope(
                "EmptyDeckError", "当前牌表为空：请先导入牌表再跑门禁")
            self._record_slot("audit", {"status": "error",
                                        "checked_at": checked_at,
                                        "error": envelope["error"]})
            return envelope, False
        validate = self._gate_validate(text, fmt, limited, bo3)
        rotation = self._gate_rotation(text)
        if validate["ok"] is False or rotation["ok"] is False:
            overall = False
        elif validate["ok"] is True and rotation["ok"] is True:
            overall = True
        else:
            overall = None     # 有门禁 unknown：整体未知，不是通过
        payload = {"status": "ok", "format": fmt, "limited": limited,
                   "bo3": bo3, "validate": validate, "rotation": rotation,
                   "ok": overall, "checked_at": checked_at}
        self._record_slot("audit", {"status": "ok", "checked_at": checked_at,
                                    "result": payload})
        return payload, True

    def _gate_validate(self, deck_text, fmt, limited, bo3):
        """mtg_tool validate 子进程门禁：0=pass，4=fail（违规模块），
        其余（含 2 牌表解析失败、OSError、超时）= unknown。"""
        argv = [sys.executable, "-X", "utf8", str(VALIDATE_TOOL_SCRIPT),
                "validate"]
        try:
            with tempfile.TemporaryDirectory(prefix="workbench_validate_") as tmp:
                deck_path = Path(tmp) / "deck.txt"
                deck_path.write_text(deck_text, encoding="utf-8")
                argv.append(str(deck_path))
                argv.extend(["--format", fmt])
                if limited:
                    argv.append("--limited")
                if bo3:
                    argv.append("--bo3")
                completed = _run_tool(argv)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"status": "unknown", "ok": None, "violations": [],
                    "error": "validate 子进程失败: {}".format(exc)}
        stdout, stderr = _completed_text(completed)
        if completed.returncode == 0:
            return {"status": "pass", "ok": True,
                    "violations": parse_validate_output(stdout)}
        if completed.returncode == 4:
            return {"status": "fail", "ok": False,
                    "violations": parse_validate_output(stdout)}
        return {"status": "unknown", "ok": None,
                "violations": parse_validate_output(stdout),
                "error": "validate 退出码 {}：{}".format(
                    completed.returncode,
                    " ".join((stderr + " " + stdout).split())[:500] or "无输出")}

    def _gate_rotation(self, deck_text):
        """rot_audit deck 子进程门禁。rot_audit 网络失败仍 exit 0 但 stderr
        带 '! FAIL'——此时结果不可信，标 unknown 而不是按 stdout 判存活。"""
        try:
            with tempfile.TemporaryDirectory(prefix="workbench_rot_") as tmp:
                deck_path = Path(tmp) / "deck.txt"
                deck_path.write_text(deck_text, encoding="utf-8")
                completed = _run_tool([sys.executable, "-X", "utf8",
                                       str(ROT_TOOL_SCRIPT), "deck",
                                       str(deck_path)])
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"status": "unknown", "ok": None,
                    "error": "rot_audit 子进程失败: {}".format(exc)}
        stdout, stderr = _completed_text(completed)
        if completed.returncode != 0 or "! FAIL" in stderr:
            return {"status": "unknown", "ok": None,
                    "error": "rot_audit 退出码 {}：{}".format(
                        completed.returncode,
                        " ".join(stderr.split())[:500] or "无输出")}
        parsed = parse_rotation_output(stdout)
        if not parsed["main"]["total"] and not parsed["sideboard"]["total"]:
            return {"status": "unknown", "ok": None,
                    "error": "rot_audit 输出不可解析（无牌表总计行）"}
        rotating = parsed["rotating_cards"]
        detail = "主牌 {survive}/{total} 张存活（将退 {rotating} 张）；备牌 " \
                 "{s_survive}/{s_total} 张存活（将退 {s_rotating} 张）".format(
                     survive=parsed["main"]["survive"],
                     total=parsed["main"]["total"],
                     rotating=parsed["main"]["rotating"],
                     s_survive=parsed["sideboard"]["survive"],
                     s_total=parsed["sideboard"]["total"],
                     s_rotating=parsed["sideboard"]["rotating"])
        if rotating:
            detail += "；将退：" + "、".join(
                "{}{}×{}".format(item["name"], item["qty"], item["section"])
                for item in rotating)
        return {"status": "pass" if parsed["ok"] else "fail",
                "ok": parsed["ok"],
                "main": parsed["main"], "sideboard": parsed["sideboard"],
                "rotating_cards": rotating, "detail": detail}


# ------------------------------------------------------------------ HTTP 层

def _error_envelope(exc_type, message):
    return {"status": "error", "error": {"type": exc_type, "message": message}}


def _json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _parse_colors(raw):
    """seed body 的 colors 校验：None 或 1-2 个不重复的 WUBRG 字母。"""
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)):
        raise ValueError("colors 必须是颜色字母数组，如 [\"W\", \"U\"]")
    colors = []
    for item in raw:
        color = str(item).upper()
        if color not in LS.COLORS:
            raise ValueError("非法颜色: {!r}（只支持 W/U/B/R/G）".format(item))
        colors.append(color)
    if len(set(colors)) != len(colors):
        raise ValueError("colors 不能重复: {!r}".format(raw))
    if not 1 <= len(colors) <= 2:
        raise ValueError("colors 只支持 1-2 个颜色（限制赛单色/双色）: {!r}".format(raw))
    return colors


def _parse_deck_size(raw):
    """seed body 的 deck_size 校验：缺省 41，只接受 40/41。"""
    if raw is None:
        return DEFAULT_DECK_SIZE
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise ValueError("deck_size 必须是整数，收到: {!r}".format(raw))
    if raw not in ALLOWED_DECK_SIZES:
        raise ValueError("deck_size 只支持 {}，收到: {}（41 = 通常 17 地 + 24 其他；"
                         "40 张需在报告注明裁剪理由）".format(
                             "/".join(map(str, ALLOWED_DECK_SIZES)), raw))
    return raw


def _resolve_table(set_code):
    """seed 的评分表解析：显式 set → mtga_draft_tool.load_card_table。

    缺失/未提供都返回 (None, [warning])——table=None 是 limited_strategy
    的合法降级路径（按稀有度/结构计分），但必须在响应里明示。
    """
    if not set_code:
        return None, ["未提供 set：无评分表，按稀有度/结构降级计分"
                      "（可在 seed 请求传 {\"set\": \"XXX\"} 启用评分表）"]
    code = str(set_code).upper()
    table = mtga_draft_tool.load_card_table(code)
    if table is None:
        return None, ["无评分表 tools/cache/draft_ratings/{}.json："
                      "按稀有度/结构降级计分".format(code)]
    return table, []


def make_handler(state):
    """构造绑定给定状态的 Handler 类。只做请求解析→引擎调用→序列化。"""
    class Handler(BaseHTTPRequestHandler):
        server_version = "DeckWorkbench/1"

        def _send(self, status, body, ctype):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status, payload):
            self._send(status, _json_bytes(payload),
                       "application/json; charset=utf-8")

        def _read_body(self):
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise ValueError("缺少 Content-Length 请求头")
            try:
                length = int(raw_length)
            except ValueError:
                raise ValueError("Content-Length 非法: {!r}".format(raw_length))
            if length < 0 or length > MAX_BODY_BYTES:
                raise ValueError("请求体长度越界: {}".format(length))
            body = self.rfile.read(length)
            try:
                return body.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ValueError("请求体不是合法 UTF-8: {}".format(exc))

        def _read_json_body(self, allow_empty=False):
            text = self._read_body()
            if not text.strip():
                if allow_empty:
                    return {}
                raise ValueError("请求体必须是 JSON 对象")
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("请求体不是合法 JSON: {}".format(exc))
            if not isinstance(data, dict):
                raise ValueError("请求体必须是 JSON 对象")
            return data

        def _bad_request(self, exc):
            self._send_json(400, _error_envelope("BadRequest", str(exc)))

        def do_GET(self):
            try:
                path = urlsplit(self.path).path
                if path == "/":
                    self._send(200, PAGE_HTML.encode("utf-8"),
                               "text/html; charset=utf-8")
                elif path == "/api/snapshot":
                    self._send_json(200, state.snapshot())
                elif path == "/api/export":
                    self._send(200, state.export_text().encode("utf-8"),
                               "text/plain; charset=utf-8")
                elif path == "/api/pool":
                    self._send_json(200, state.pool_snapshot())
                elif path == "/api/stats":
                    self._send_json(200, state.stats())
                elif path == "/api/roles":
                    self._send_json(200, state.roles())
                elif path == "/api/combos":
                    self._handle_combos()
                elif path == "/api/cost":
                    self._handle_cost()
                else:
                    self._send_json(404, _error_envelope(
                        "NotFoundError", "未知路径: {}".format(path)))
            except Exception as exc:
                self._unhandled(exc)

        def do_POST(self):
            try:
                path = urlsplit(self.path).path
                if path == "/api/builds/import":
                    self._handle_import()
                elif path == "/api/pool":
                    self._handle_pool_import()
                elif path == "/api/seed":
                    self._handle_seed()
                elif path == "/api/seed-constructed":
                    self._handle_seed_constructed()
                elif path == "/api/audit":
                    self._handle_audit()
                elif path in ("/api/deck/add", "/api/deck/remove", "/api/deck/move"):
                    self._handle_deck_edit(path.rsplit("/", 1)[1])
                else:
                    self._send_json(404, _error_envelope(
                        "NotFoundError", "未知路径: {}".format(path)))
            except Exception as exc:
                self._unhandled(exc)

        def _handle_import(self):
            try:
                text = self._read_body()
            except ValueError as exc:
                self._bad_request(exc)
                return
            source_name = self.headers.get("X-Source-Name")
            try:
                snapshot = state.import_text(text, source_name=source_name)
            except EmptyImportError as exc:
                envelope = _error_envelope(type(exc).__name__, str(exc))
                envelope["skipped"] = []   # 无状态可回读，保持信封最小
                envelope["warnings"] = []
                self._send_json(400, envelope)
                return
            self._send_json(200, snapshot)

        def _handle_pool_import(self):
            try:
                text = self._read_body()
            except ValueError as exc:
                self._bad_request(exc)
                return
            try:
                snapshot = state.import_pool(text,
                                             source_name=self.headers.get("X-Source-Name"))
            except EmptyImportError as exc:
                self._send_json(400, _error_envelope(type(exc).__name__, str(exc)))
                return
            self._send_json(200, snapshot)

        def _handle_seed(self):
            try:
                body = self._read_json_body(allow_empty=True)
                colors = _parse_colors(body.get("colors"))
                deck_size = _parse_deck_size(body.get("deck_size"))
                table, table_warnings = _resolve_table(body.get("set"))
            except ValueError as exc:
                self._bad_request(exc)
                return
            try:
                snapshot = state.seed_limited(colors=colors, deck_size=deck_size,
                                              table=table,
                                              table_warnings=table_warnings)
            except (PoolEmptyError, ValueError) as exc:
                self._send_json(400, _error_envelope(type(exc).__name__, str(exc)))
                return
            self._send_json(200, snapshot)

        def _handle_seed_constructed(self):
            try:
                body = self._read_json_body()
                args = parse_constructed_body(body)
            except ValueError as exc:
                self._bad_request(exc)
                return
            try:
                snapshot = state.seed_constructed(*args)
            except (ValueError, TypeError) as exc:
                # 与 deck_pooper constructed 同一报错口径（exit 2 → 400）
                self._send_json(400, _error_envelope(type(exc).__name__,
                                                     str(exc)))
                return
            self._send_json(200, snapshot)

        def _handle_combos(self):
            query = parse_qs(urlsplit(self.path).query)
            fmt = (query.get("format") or [DEFAULT_CONSTRUCTED_FORMAT])[0]
            platform = (query.get("platform") or [DEFAULT_PLATFORM])[0]
            raw_limit = (query.get("limit") or [str(DEFAULT_COMBO_LIMIT)])[0]
            try:
                if fmt not in COMBO_FORMATS:
                    raise ValueError(
                        "format 只支持 {}，收到: {!r}".format(
                            "/".join(COMBO_FORMATS), fmt))
                limit = int(raw_limit)
                if limit < 1:
                    raise ValueError("limit 必须是正整数，收到: {!r}".format(raw_limit))
            except ValueError as exc:
                self._bad_request(exc)
                return
            try:
                payload, ok = state.combos(fmt, platform, limit)
            except ValueError as exc:
                self._bad_request(exc)
                return
            self._send_json(200 if ok else 500, payload)

        def _handle_cost(self):
            payload, ok = state.cost()
            self._send_json(200 if ok else 500, payload)

        def _handle_audit(self):
            try:
                body = self._read_json_body()
            except ValueError as exc:
                self._bad_request(exc)
                return
            fmt = body.get("format")
            limited = body.get("limited")
            bo3 = body.get("bo3", False)
            if not isinstance(fmt, str) or not fmt.strip():
                self._bad_request(ValueError(
                    "format 是必填非空字符串（如 \"pioneer\"），收到: {!r}".format(fmt)))
                return
            if not isinstance(limited, bool):
                # limited 必须显式传：不做牌张数静默推断
                self._bad_request(ValueError(
                    "limited 是必填布尔（true=限制赛 40/41 口径，false=构筑口径），"
                    "收到: {!r}".format(limited)))
                return
            payload, ok = state.audit(fmt.strip(), limited, bool(bo3))
            self._send_json(200 if ok else 500, payload)

        def _handle_deck_edit(self, op):
            try:
                body = self._read_json_body()
            except ValueError as exc:
                self._bad_request(exc)
                return
            name = body.get("name")
            qty = body.get("qty", 1)
            try:
                if op == "add":
                    snap = state.deck_add(name, body.get("section"), qty)
                elif op == "remove":
                    snap = state.deck_remove(name, body.get("section"), qty)
                else:
                    snap = state.deck_move(name, body.get("from"),
                                           body.get("to"), qty)
            except DeckEditError as exc:
                self._send_json(400, _error_envelope("DeckEditError", str(exc)))
                return
            self._send_json(200, snap)

        def _unhandled(self, exc):
            traceback.print_exc()   # traceback 进 stderr，不回浏览器
            try:
                self._send_json(500, _error_envelope(
                    type(exc).__name__, "工作台内部错误: {}".format(exc)))
            except OSError:
                pass                # 连接已断，无法回写

        def log_message(self, *args):
            pass                    # 静音访问日志

    return Handler


# ------------------------------------------------------------------ 内嵌页面

PAGE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>MTG 套牌工作台</title>
<style>
  body { background:#0d1117; color:#c9d1d9; font-family:Consolas,'Microsoft YaHei',monospace;
         margin:0; padding:16px; }
  h1 { font-size:18px; color:#58a6ff; margin:0 0 12px; }
  .panel { background:#161b22; border:1px solid #30363d; border-radius:6px;
           padding:12px 16px; margin-bottom:12px; }
  .panel h2 { font-size:13px; color:#8b949e; margin:0 0 8px; font-weight:normal; }
  #session { font-size:13px; color:#8b949e; }
  .cols { display:flex; gap:12px; align-items:flex-start; }
  .col { flex:1; min-width:0; }
  .zone { margin-bottom:10px; }
  .zone b { color:#3fb950; }
  .zone ul { margin:4px 0 0; padding-left:20px; line-height:1.7; font-size:14px; }
  .row { display:flex; align-items:center; gap:8px; padding:2px 0; font-size:13px; }
  .row .nm { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .row button { margin:0; padding:1px 8px; font-size:12px; }
  .ts { color:#484f58; }
  .tag { color:#8b949e; font-size:12px; }
  #pooltext { width:100%; height:120px; background:#0d1117; color:#c9d1d9;
              border:1px solid #30363d; border-radius:4px; font-family:inherit; }
  #decktext { width:100%; height:90px; background:#0d1117; color:#c9d1d9;
              border:1px solid #30363d; border-radius:4px; font-family:inherit; }
  #srcname, #setcode { width:160px; background:#0d1117; color:#c9d1d9;
             border:1px solid #30363d; border-radius:4px; font-family:inherit; }
  select { background:#0d1117; color:#c9d1d9; border:1px solid #30363d;
           border-radius:4px; font-family:inherit; padding:3px; }
  button { background:#21262d; color:#c9d1d9; border:1px solid #30363d;
           border-radius:6px; padding:5px 14px; margin-top:8px; cursor:pointer; }
  button:hover { border-color:#58a6ff; }
  #warnings { color:#e3b341; white-space:pre-wrap; font-size:13px; }
  #errors { color:#f85149; white-space:pre-wrap; font-size:13px; }
  .bar { background:#1f6feb; height:12px; border-radius:2px; display:inline-block; }
  .statline { font-size:13px; line-height:1.8; }
  .ok { color:#3fb950; } .bad { color:#f85149; } .warn { color:#e3b341; }
  .note { color:#8b949e; font-size:12px; line-height:1.6; }
</style>
</head>
<body>
<h1>MTG 套牌工作台（Phase 2 构筑模式）</h1>
<div class="panel"><h2>会话</h2><div id="session">尚未导入牌表</div></div>
<div class="cols">
  <div class="col">
    <div class="panel"><h2>牌池</h2>
      <div class="row">筛选：<select id="poolFilter">
        <option value="all">全部</option>
        <option value="main">已入主牌</option>
        <option value="sideboard">在备牌</option>
        <option value="out">未入套（被裁）</option>
      </select><span class="tag" id="poolCount"></span></div>
      <div id="poolList">—</div>
    </div>
    <div class="panel"><h2>导入牌池（数量 牌名，每行一张）</h2>
      <textarea id="pooltext" placeholder="粘贴牌池文本（容忍 Deck 段头与 (SET) 编号后缀）"></textarea>
      <div>来源（可选）：<input id="srcname" type="text"></div>
      <button id="poolBtn">导入牌池</button>
    </div>
    <div class="panel"><h2>导入/导出牌表</h2>
      <textarea id="decktext" placeholder="粘贴牌表文本（Deck/Sideboard 段头）"></textarea>
      <button id="importBtn">导入牌表</button>
      <button id="exportBtn">导出当前牌表</button>
    </div>
  </div>
  <div class="col">
    <div class="panel"><h2>Seed（limited_strategy）</h2>
      <div class="row">色组：<select id="seedColors"></select>
          张数：<select id="seedSize">
            <option value="41">41</option>
            <option value="40">40</option>
          </select>
          系列：<input id="setcode" type="text" placeholder="如 FRA（评分表）"></div>
      <div class="note">通常 17 地 + 24 其他 = 41；选 40 张需在报告注明裁剪理由
        （draft_methodology §4）。无评分表时按稀有度/结构降级计分并在警告中明示。</div>
      <button id="seedBtn">Seed</button>
      <div id="seedInfo" class="statline"></div>
      <div id="seedPlans" class="statline"></div>
      <div id="seedCuts" class="note"></div>
    </div>
    <div class="panel"><h2>统计（deck_core 口径）</h2><div id="stats">—</div></div>
    <div class="panel"><h2>当前牌表</h2><div id="zones">—</div></div>
    <div class="panel"><h2>警告</h2><div id="warnings">—</div></div>
    <div class="panel"><h2>错误</h2><div id="errors">—</div></div>
  </div>
</div>
<div class="panel"><h2>Seed 构筑（constructed_strategy，候选 = mtg_tool search --out 同构 JSON）</h2>
  <textarea id="candtext" style="width:100%;height:80px;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;font-family:inherit;" placeholder='粘贴候选 JSON 数组，如 [{"name":"Lightning Bolt",...},...]'></textarea>
  <div class="row">种子（逗号分隔牌名）：<input id="seednames" type="text" style="width:280px;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;font-family:inherit;">
    赛制：<input id="ccFormat" type="text" value="pioneer" style="width:80px;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;font-family:inherit;">
    策略：<select id="ccStrategy"><option value="mid">mid</option><option value="aggro">aggro</option><option value="control">control</option></select>
    平台：<select id="ccPlatform"><option value="arena">arena</option><option value="paper">paper</option><option value="mtgo">mtgo</option><option value="any">any</option></select>
    <label><input id="ccBo3" type="checkbox">BO3</label></div>
  <button id="ccBtn">Seed 构筑</button>
  <div id="ccInfo" class="statline"></div>
</div>
<div class="cols">
  <div class="col">
    <div class="panel"><h2>角色分布与缺口（roles.py）</h2>
      <button id="rolesBtn">刷新角色</button>
      <div id="rolesBox" class="statline">—</div>
    </div>
    <div class="panel"><h2>组合技（Commander Spellbook，可能慢，75 请求/分钟节流）</h2>
      <div class="row">赛制：<input id="cbFormat" type="text" value="pioneer" style="width:80px;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;font-family:inherit;">
        平台：<select id="cbPlatform"><option value="arena">arena</option><option value="paper">paper</option><option value="mtgo">mtgo</option></select>
        条数：<input id="cbLimit" type="text" value="20" style="width:50px;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;font-family:inherit;"></div>
      <button id="combosBtn">查询组合技</button>
      <div id="combosBox" class="statline">—</div>
    </div>
  </div>
  <div class="col">
    <div class="panel"><h2>造价（deck_cost sig，子进程 = CLI 口径）</h2>
      <button id="costBtn">核算造价</button>
      <div id="costBox" class="statline">—</div>
    </div>
    <div class="panel"><h2>门禁（mtg_tool validate + rot_audit，交通灯）</h2>
      <div class="row">赛制：<input id="auditFormat" type="text" value="pioneer" style="width:80px;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;font-family:inherit;">
        <label><input id="auditLimited" type="checkbox">limited（40/41 口径）</label>
        <label><input id="auditBo3" type="checkbox">BO3</label></div>
      <button id="auditBtn">跑门禁</button>
      <div id="auditBox" class="statline">—</div>
    </div>
  </div>
</div>
<script>
const ZONES = ['commander', 'companion', 'main', 'sideboard'];
const ZH = {commander:'指挥官', companion:'伴侣', main:'主牌', sideboard:'备牌'};
const COLORS = 'WUBRG';
let lastSnap = null;
function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
                                  .replace(/>/g,'&gt;'); }
function showErrors(msg) { document.getElementById('errors').textContent = msg || '—'; }
async function postJSON(url, obj) {
  const r = await fetch(url, {method:'POST',
    headers:{'Content-Type':'application/json; charset=utf-8'},
    body: JSON.stringify(obj || {})});
  const d = await r.json();
  if (!r.ok) throw new Error(d.error ? d.error.type + ': ' + d.error.message
                                    : JSON.stringify(d));
  return d;
}
async function postText(url, text, srcId) {
  const headers = {'Content-Type':'text/plain; charset=utf-8'};
  if (srcId) headers['X-Source-Name'] = document.getElementById(srcId).value;
  const r = await fetch(url, {method:'POST', headers: headers, body: text});
  const d = await r.json();
  if (!r.ok) throw new Error(d.error ? d.error.type + ': ' + d.error.message
                                    : JSON.stringify(d));
  return d;
}
async function fetchJSON(url) {
  const r = await fetch(url);
  const d = await r.json();
  if (!r.ok) throw new Error(d.error ? d.error.type + ': ' + d.error.message
                                     : JSON.stringify(d));
  return d;
}
function gateHtml(g) {
  if (!g) return '<span class="ts">—</span>';
  if (g.status === 'pass') return '<span class="ok">● 通过</span>';
  if (g.status === 'fail') return '<span class="bad">● 失败</span>';
  return '<span class="warn">● 未知</span>';
}
function buildColorOptions() {
  const sel = document.getElementById('seedColors');
  let html = '<option value="">自动（枚举选最优）</option>';
  for (let i = 0; i < COLORS.length; i++) {
    html += '<option value="' + COLORS[i] + '">' + COLORS[i] + '</option>';
  }
  for (let i = 0; i < COLORS.length; i++) for (let j = i + 1; j < COLORS.length; j++) {
    html += '<option value="' + COLORS[i] + COLORS[j] + '">'
          + COLORS[i] + '+' + COLORS[j] + '</option>';
  }
  sel.innerHTML = html;
}
function cardStatus(name, snap) {
  for (const z of ['main', 'sideboard']) {
    const hit = (snap.sections[z] || []).find(c => c.name === name);
    if (hit) return z;
  }
  return 'out';
}
function renderPool(snap) {
  const filter = document.getElementById('poolFilter').value;
  const entries = (snap.pool && snap.pool.entries) || [];
  let html = '', shown = 0;
  for (const e of entries) {
    const st = cardStatus(e.name, snap);
    if (filter !== 'all' && st !== filter) continue;
    shown++;
    const stTxt = {main:'<span class="ok">主</span>',
                   sideboard:'<span class="warn">备</span>',
                   out:'<span class="ts">裁</span>'}[st];
    html += '<div class="row"><span class="tag">' + e.qty + '×</span>'
      + '<span class="nm">' + esc(e.name)
      + ' <span class="ts">' + (e.cmc != null ? e.cmc + '费' : '') + '</span></span>'
      + stTxt
      + '<button onclick="doAdd(\\'' + esc(e.name).replace(/'/g, '') + '\\',\\'main\\')">主+1</button>'
      + '<button onclick="doAdd(\\'' + esc(e.name).replace(/'/g, '') + '\\',\\'sideboard\\')">备+1</button></div>';
  }
  document.getElementById('poolList').innerHTML =
    shown ? html : '<div class="ts">（无匹配条目）</div>';
  const c = (snap.pool && snap.pool.counts) || {};
  document.getElementById('poolCount').textContent =
    (c.names || 0) + ' 种 / ' + (c.cards || 0) + ' 张'
    + (c.unresolved_names ? '，未水合 ' + c.unresolved_names + ' 种' : '');
}
function renderDeck(snap) {
  let html = '';
  for (const z of ZONES) {
    const items = (snap.sections && snap.sections[z]) || [];
    const count = (snap.counts && snap.counts[z]) || 0;
    if (z === 'commander' || z === 'companion') {
      html += '<div class="zone"><b>' + ZH[z] + '</b>（' + count + ' 张）<ul>'
        + items.map(c => '<li>' + c.qty + ' × ' + esc(c.name) + '</li>').join('')
        + (items.length ? '' : '<li class="ts">（空）</li>') + '</ul></div>';
      continue;
    }
    const btns = z === 'main'
      ? c => '<button onclick="doMove(\\'' + esc(c.name).replace(/'/g,'') + '\\',\\'main\\',\\'sideboard\\')">→备</button>'
           + '<button onclick="doRemove(\\'' + esc(c.name).replace(/'/g,'') + '\\',\\'main\\')">−1</button>'
      : c => '<button onclick="doMove(\\'' + esc(c.name).replace(/'/g,'') + '\\',\\'sideboard\\',\\'main\\')">→主</button>'
           + '<button onclick="doRemove(\\'' + esc(c.name).replace(/'/g,'') + '\\',\\'sideboard\\')">−1</button>';
    html += '<div class="zone"><b>' + ZH[z] + '</b>（' + count + ' 张）'
      + items.map(c => '<div class="row"><span class="tag">' + c.qty + '×</span>'
        + '<span class="nm">' + esc(c.name) + '</span>' + btns(c) + '</div>').join('')
      + (items.length ? '' : '<div class="ts">（空）</div>') + '</div>';
  }
  html += '<div class="zone"><b>合计</b>：' + snap.total + ' 张</div>';
  document.getElementById('zones').innerHTML = html;
}
function renderStats(snap) {
  const s = snap.stats || {};
  const lc = s.land_check || {};
  const p3 = (lc.p3 != null) ? (lc.p3 * 100).toFixed(1) + '%' : '—';
  const p5 = (lc.p5 != null) ? (lc.p5 * 100).toFixed(1) + '%' : '—';
  let html = '<div class="statline">主牌 ' + (s.main || 0) + ' 张：地 '
    + (s.lands || 0) + ' / 非地 ' + (s.nonlands || 0)
    + '；平均 CMC ' + (s.average_cmc || 0) + '（' + esc(s.curve_label || '') + '）</div>';
  html += '<div class="statline">曲线：';
  const curve = s.curve || {};
  const keys = Object.keys(curve);
  html += keys.length
    ? keys.map(k => k + '费×' + curve[k]
        + ' <span class="bar" style="width:' + (curve[k] * 10) + 'px"></span>').join('　')
    : '<span class="ts">（空）</span>';
  html += '</div><div class="statline">法术力：pips '
    + esc(JSON.stringify(s.pips || {})) + '；来源 '
    + esc(JSON.stringify(s.mana_sources || {})) + '</div>';
  html += '<div class="statline">land_check（' + (lc.deck_size || 40) + ' 张口径，'
    + (lc.lands || 0) + ' 地）：3回合≥2地 ' + p3 + '，5回合≥4地 ' + p5
    + '，<span class="' + (lc.ok ? 'ok">通过' : 'bad">未通过') + '</span></div>';
  if (s.warnings && s.warnings.length)
    html += '<div class="note">' + s.warnings.map(esc).join('<br>') + '</div>';
  document.getElementById('stats').innerHTML = html;
}
function renderSeed(snap) {
  const seed = snap.seed;
  if (!seed) { document.getElementById('seedInfo').textContent = '—';
    document.getElementById('seedPlans').innerHTML = '';
    document.getElementById('seedCuts').textContent = ''; return; }
  document.getElementById('seedInfo').innerHTML =
    '色组 <b>' + esc(seed.colors.join('+')) + '</b>（' + esc(seed.strategy)
    + '，' + seed.deck_size + ' 张）深度'
    + (seed.depth_ok ? '<span class="ok">通过</span>' : '<span class="bad">不足</span>')
    + '；平均 CMC ' + seed.average_cmc + '；地 ' + esc(JSON.stringify(seed.lands))
    + '；' + (seed.valid ? '<span class="ok">门禁通过</span>'
                         : '<span class="bad">门禁失败: ' + esc(seed.violations.join('；')) + '</span>');
  document.getElementById('seedPlans').innerHTML = '枚举方案 top '
    + (seed.plans || []).length + '：' + (seed.plans || []).map(p =>
      esc(p.colors.join('+')) + ' = ' + p.score
      + (p.depth_ok ? '' : '（深度不足）')).join('；');
  document.getElementById('seedCuts').textContent =
    (seed.cuts && seed.cuts.length) ? '被裁：' + seed.cuts.join('；') : '被裁：无';
}
const BUCKET_ZH = {main_available:'主牌可打', postboard_available:'换备后可打',
  sideboard_candidates:'备牌候选', missing_components:'缺组件',
  needs_verification:'待核验', excluded:'已排除'};
function renderConstructed(snap) {
  const c = snap.checks && snap.checks.constructed;
  const box = document.getElementById('ccInfo');
  if (!c) { box.textContent = '—'; return; }
  if (c.status === 'error' && c.error && !c.result) {
    box.innerHTML = '<span class="bad">查询失败: ' + esc(c.error.message || '') + '</span>';
    return;
  }
  const r = c.result;
  box.innerHTML = (r.valid ? '<span class="ok">门禁通过</span>'
                           : '<span class="bad">门禁失败: '
                             + esc(r.violations.join('；')) + '</span>')
    + '；颜色 ' + esc((r.colors || []).join('') || '无色')
    + '；主牌 ' + r.main + ' 张，备牌 ' + r.sideboard + ' 张'
    + '<br>' + (r.report || []).map(esc).join('<br>');
}
function renderRoles(snap) {
  const slot = snap.checks && snap.checks.roles;
  const box = document.getElementById('rolesBox');
  if (!slot) { box.textContent = '—'; return; }
  const r = slot.result;
  let html = '<div class="note">' + esc(r.basis) + '</div>';
  const dist = r.distribution || {};
  const keys = Object.keys(dist).filter(k => dist[k] > 0);
  html += '<div>' + (keys.length
    ? keys.map(k => esc(k) + '×' + dist[k]
        + ' <span class="bar" style="width:' + (dist[k] * 4) + 'px"></span>').join('　')
    : '<span class="ts">（无可分类牌）</span>') + '</div>';
  if ((r.gaps || []).length)
    html += '<div class="warn">缺口：' + r.gaps.map(g =>
      esc(g.module) + ' 缺 ' + g.deficit + '（有 ' + g.have + ' / 目标 ' + g.want + '）'
      ).join('；') + '</div>';
  else html += '<div class="ok">缺口：无（M1/M2/M3/M5/M8 均达 wanted 配额）</div>';
  if ((r.unknown || []).length)
    html += '<div class="bad">未水合（角色未知）: ' + r.unknown.map(u =>
      esc(u.name) + '×' + u.qty).join('、') + '</div>';
  box.innerHTML = html;
}
function renderCombos(snap) {
  const slot = snap.checks && snap.checks.combos;
  const box = document.getElementById('combosBox');
  if (!slot) { box.textContent = '—'; return; }
  if (slot.status === 'error') {
    box.innerHTML = '<span class="bad">查询失败（≠零命中）: '
      + esc((slot.error && slot.error.message) || '') + '</span>';
    return;
  }
  const r = slot.result;
  const counts = r.group_counts || {};
  let html = '<div>' + Object.keys(BUCKET_ZH).map(k =>
    esc(BUCKET_ZH[k]) + ' <b>' + (counts[k] || 0) + '</b>').join('　') + '</div>';
  if (r.stale) html += '<div class="warn">stale：缓存结果， freshness 不保证</div>';
  if (r.truncated) html += '<div class="warn">truncated：只分析 ' + r.analyzed_variant_count
    + ' / ' + r.variant_count + '，调大 limit</div>';
  const hits = (r.buckets && r.buckets.main_available || []).slice(0, 5);
  for (const c of hits)
    html += '<div class="row"><span class="nm">' + esc(c.cards) + '</span>'
      + '<a class="tag" href="' + esc(c.url) + '" target="_blank">#' + esc(c.id) + '</a></div>';
  for (const w of (r.warnings || []))
    html += '<div class="warn">' + esc(w) + '</div>';
  box.innerHTML = html;
}
function renderCost(snap) {
  const slot = snap.checks && snap.checks.cost;
  const box = document.getElementById('costBox');
  if (!slot) { box.textContent = '—'; return; }
  if (slot.status === 'error') {
    box.innerHTML = '<span class="bad">造价不可用: '
      + esc((slot.error && slot.error.message) || '') + '</span>';
    return;
  }
  const r = slot.result;
  const b = r.budget || {};
  let html = '签名 <b>' + esc(r.signature || '?') + '</b>　预算 '
    + (b.ok ? '<span class="ok">' : '<span class="bad">') + esc(b.tier || '?')
    + '</span><br>PP核心 ' + (r.packs && r.packs.core != null ? r.packs.core : '?')
    + ' 包；PP全量 ' + (r.packs && r.packs.all != null ? r.packs.all : '?')
    + ' 包；惩罚 ' + (r.packs && r.packs.penalty != null ? r.packs.penalty : '?') + '×';
  if ((r.unrecognized || []).length)
    html += '<br><span class="warn">deck_cost 未识别: '
          + r.unrecognized.map(esc).join('、') + '</span>';
  box.innerHTML = html;
}
function renderAudit(snap) {
  const slot = snap.checks && snap.checks.audit;
  const box = document.getElementById('auditBox');
  if (!slot) { box.textContent = '—'; return; }
  if (slot.status === 'error') {
    box.innerHTML = '<span class="bad">门禁不可用: '
      + esc((slot.error && slot.error.message) || '') + '</span>';
    return;
  }
  const r = slot.result;
  const overall = r.ok === true ? '<span class="ok">● 全部通过</span>'
    : r.ok === false ? '<span class="bad">● 有门禁失败</span>'
                     : '<span class="warn">● 有门禁未知（≠通过）</span>';
  let html = overall + '　validate ' + gateHtml(r.validate)
    + (r.validate && r.validate.violations && r.validate.violations.length
       ? '：<span class="bad">' + r.validate.violations.map(esc).join('；') + '</span>' : '')
    + '<br>轮替 ' + gateHtml(r.rotation);
  if (r.rotation && r.rotation.detail) html += '：' + esc(r.rotation.detail);
  if (r.rotation && r.rotation.error) html += ' <span class="warn">'
    + esc(r.rotation.error) + '</span>';
  if (r.validate && r.validate.error) html += ' <span class="warn">'
    + esc(r.validate.error) + '</span>';
  box.innerHTML = html;
}
async function tick() {
  try {
    const r = await fetch('/api/snapshot');
    const d = await r.json();
    showErrors('');
    lastSnap = d;
    const s = d.session || {};
    document.getElementById('session').textContent = s.import_seq
      ? '导入 #' + s.import_seq + '　' + (s.source_name ? '来源 ' + s.source_name + '　' : '')
        + '时间 ' + s.imported_at
      : '尚未导入牌表';
    renderPool(d);
    renderDeck(d);
    renderStats(d);
    renderSeed(d);
    renderConstructed(d);
    renderRoles(d);
    renderCombos(d);
    renderCost(d);
    renderAudit(d);
    const warns = [].concat(d.warnings || [], (d.pool && d.pool.warnings) || []);
    document.getElementById('warnings').textContent =
      warns.length ? warns.join('\\n') : '—';
  } catch (e) { showErrors('轮询失败: ' + e); }
}
async function run(action) {
  try { await action(); showErrors(''); } catch (e) { showErrors(String(e.message || e)); }
  tick();
}
function doAdd(name, section) { run(() => postJSON('/api/deck/add', {name:name, section:section, qty:1})); }
function doRemove(name, section) { run(() => postJSON('/api/deck/remove', {name:name, section:section, qty:1})); }
function doMove(name, from, to) { run(() => postJSON('/api/deck/move', {name:name, from:from, to:to, qty:1})); }
document.getElementById('poolBtn').onclick = () => run(
  () => postText('/api/pool', document.getElementById('pooltext').value, 'srcname'));
document.getElementById('importBtn').onclick = () => run(
  () => postText('/api/builds/import', document.getElementById('decktext').value));
document.getElementById('exportBtn').onclick = () => { window.open('/api/export'); };
document.getElementById('seedBtn').onclick = () => run(async () => {
  const raw = document.getElementById('seedColors').value;
  const body = {};
  if (raw) body.colors = raw.length === 1 ? [raw] : [raw[0], raw[1]];
  body.deck_size = parseInt(document.getElementById('seedSize').value, 10);
  const set = document.getElementById('setcode').value.trim();
  if (set) body.set = set;
  await postJSON('/api/seed', body);
});
document.getElementById('ccBtn').onclick = () => run(async () => {
  const raw = document.getElementById('candtext').value.trim();
  const candidates = JSON.parse(raw || 'null');
  const body = {candidates: candidates,
    seeds: document.getElementById('seednames').value.split(/[,，]/).map(s => s.trim()).filter(Boolean),
    format: document.getElementById('ccFormat').value.trim() || 'pioneer',
    strategy: document.getElementById('ccStrategy').value,
    platform: document.getElementById('ccPlatform').value,
    bo3: document.getElementById('ccBo3').checked};
  await postJSON('/api/seed-constructed', body);
});
document.getElementById('rolesBtn').onclick = () => run(() => fetchJSON('/api/roles'));
document.getElementById('combosBtn').onclick = () => run(() => fetchJSON(
  '/api/combos?format=' + encodeURIComponent(document.getElementById('cbFormat').value.trim() || 'pioneer')
  + '&platform=' + document.getElementById('cbPlatform').value
  + '&limit=' + encodeURIComponent(document.getElementById('cbLimit').value.trim() || '20')));
document.getElementById('costBtn').onclick = () => run(() => fetchJSON('/api/cost'));
document.getElementById('auditBtn').onclick = () => run(() => postJSON('/api/audit', {
  format: document.getElementById('auditFormat').value.trim() || 'pioneer',
  limited: document.getElementById('auditLimited').checked,
  bo3: document.getElementById('auditBo3').checked}));
document.getElementById('poolFilter').onchange = () => { if (lastSnap) renderPool(lastSnap); };
buildColorOptions();
setInterval(tick, """ + str(POLL_INTERVAL_MS) + """); tick();
</script>
</body>
</html>
"""


# ------------------------------------------------------------------ serve/CLI

def serve(host, port):
    """启动工作台（前台阻塞）。端口占用等启动失败抛 WorkbenchError。"""
    state = WorkbenchState()
    try:
        server = ThreadingHTTPServer((host, port), make_handler(state))
    except OSError as exc:
        raise WorkbenchError(
            "无法在 {}:{} 启动工作台（端口被占用或地址非法）: {}".format(
                host, port, exc)) from exc
    actual_port = server.server_address[1]
    print("MTG 套牌工作台: http://{}:{}/  （Ctrl+C 退出）".format(host, actual_port),
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    child = sub.add_parser("serve", help="启动网页工作台 hub（前台阻塞）")
    child.add_argument("--host", default=DEFAULT_HOST)
    child.add_argument("--port", type=int, default=DEFAULT_PORT,
                       help="默认 {}（避开 8642 对局监控 / 8643 轮抓面板）".format(DEFAULT_PORT))
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return serve(args.host, args.port)
    except WorkbenchError as exc:
        print("[error] " + str(exc), file=sys.stderr)
        runlog.log_run("deck_workbench", "error", "serve " + str(exc))
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(runlog.run_logged("deck_workbench", main))
