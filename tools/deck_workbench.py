#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""网页套牌工作台 hub（MtgWorkbenchPlan Phase 0 hub + Phase 1 限制赛 +
Phase 2 构筑模式与核验接入 + Phase 3 Agent 桥与双 LLM 通道）。

分层（决策 B：引擎先行，UI 最薄）：
  引擎纯函数    build_snapshot / serialize_deck / build_stats /
                hydrate_pool / apply_add|remove|move /
                build_roles / parse_cost_output / parse_rotation_output /
                AgentBridge（请求队列+认领+结果槽位）/ avenues / find / advice
                —— 可独立单测
  权威状态      WorkbenchState —— 持锁；牌表 + 水合牌池 + 卡片库 + 最近 seed
                + 核验缓存槽位（roles/combos/cost/audit/constructed）
                + Agent 桥 + avenues 持久列表
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
  POST /api/agent/request   body {"kind", "payload", "timeout_sec"}；kind 限定
                            next_move/explain/novel_synergies/handoff 四种，
                            未知 kind → 400；入队返回 {"request_id", "queued_at"}
  GET  /api/agent/next?agent=<name>&wait=1   Agent 侧长轮询（认领语义，同一
                            请求同一时间只派给一个 agent）；队空挂起最长 60s
                            返回 {"status":"wait"} 心跳；wait=0 立即返回（测试用）
  POST /api/agent/result    body {"request_id", "status": "ok"|"error",
                            "result", "message"}；未认领/重复提交 → 409，
                            未知 id → 404，已过 TTL 清理 → 410
  GET  /api/agent/result/{id}  网页侧轮询：未就绪 202 {"status":"pending"}，
                            就绪 200，TTL 过期 410，未知 404
  POST /api/agent/heartbeat body {"request_id", "agent"}；认领后 60s 内无
                            结果且无心跳 → 请求重新入队可再认领（防 Agent
                            崩溃挂死请求）
  GET  /api/agent/status    桥诊断：队列深度/在途/就绪结果数/kind 集合
  GET  /api/find?q=...&limit=20   包装 mtg_tool.scryfall_search（进程内，
                            磁盘缓存，oracle 去重）；铁律契约落地端点——
                            LLM 提案的一切卡牌必须来自这里的实际结果；
                            语法错误 400，网络失败 500，零命中 = ok + 空列表
  POST /api/avenues         body {"title", "note", "candidates":[{name,reason}]}
                            反向通路：Agent 写入探索方向（服务端不联网验证
                            候选牌名，响应标 unverified_card_names 明示铁律
                            责任在写入方）；GET 列表；DELETE /api/avenues/{id}；
                            POST /api/avenues/{id}/focus 单焦点高亮
  POST /api/advice          嵌入式 LLM 轴（决策 D 辅助通道）：读
                            tools/llm_config.json（DEEPSEEK_API_KEY 可覆盖
                            api_key），OpenAI 兼容 chat；配置缺失/请求失败/
                            超时 → 显式 offline + machine_fallback（stats 与
                            已缓存 roles 缺口的确定性结论）；LLM 输出原文
                            展示并标 verified=false（未经工具核验）；不重试

错误信封与 mtg_rules_tool 同构：
  {"status": "error", "error": {"type": ..., "message": ...}}
未知路径 404；handler 未捕获异常 500（traceback 只进 stderr，不回浏览器）；
完全解析不出任何条目的导入是业务错误（400），与"成功但带 skipped 警告"
明确分离。Ctrl+C 干净退出；CLI 出口接 runlog 留痕。
"""
import argparse
import collections
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
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
import mtga_auto_tool as AUTO
import mtga_draft_tool
import roles as role_tags
import runlog
import workbench_jobs
import workbench_agent
import deck_evaluate
import workbench_evaluation

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8644
MAX_BODY_BYTES = 1024 * 1024
POLL_INTERVAL_MS = 3000

MAX_COPIES = 4                      # 构筑默认上限；限制赛依据导入牌池数量
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
IMAGE_TOOL_SCRIPT = TOOL_DIR / "deck_image.py"
SUBPROCESS_TIMEOUT = 180            # cost/audit 单个子进程的上限秒数
# 角色缺口基准：constructed_strategy 的 M1-M9 模块配额（deck_config 的
# STRATEGY_TARGETS 骨架只服务限制赛深度检查，不作构筑基准；basis 字段明说）
GAP_MODULES = tuple(CS.REQUIRED_MODULES)    # ("M1", "M2", "M3", "M5", "M8")

# ---- Phase 3 Agent 桥与双 LLM 通道 ----
AGENT_KINDS = ("next_move", "explain", "novel_synergies", "handoff")
AGENT_RESULT_TTL = 300.0            # 结果槽位 TTL（秒）：浏览器放弃的结果被清理
AGENT_CLAIM_LEASE = 60.0            # 认领租约（秒）：无结果且无心跳则重新入队
AGENT_POLL_MAX = 60.0               # next 长轮询单次挂起上限（wait 心跳周期）
FIND_DEFAULT_LIMIT = 20
FIND_MAX_LIMIT = 100                # 铁律契约的搜索包装：单页上限，防巨量响应
ADVICE_LLM_TIMEOUT = 60             # advice 嵌入式 LLM 调用超时（不重试）
LLM_CONFIG_JSON = TOOL_DIR / "llm_config.json"

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
    cards, unresolved, cache, merged = [], {}, {}, {}
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
            canonical = str(cache[key].get("name") or name).casefold()
            if canonical not in merged:
                item = dict(cache[key])
                item["count"] = 0
                merged[canonical] = item
                cards.append(item)
            merged[canonical]["count"] += qty
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


def apply_add(deck, name, section, qty, max_copies=MAX_COPIES):
    """纯函数：加牌，返回新 Deck。非豁免同名超 4 张抛 DeckEditError。"""
    _check_edit_args(name, section, qty)
    rows = [[card.qty, card.name] for card in getattr(deck, section)]
    have = sum(row[0] for row in rows if row[1] == name)
    if max_copies is not None and not _copy_limit_exempt(name) and have + qty > max_copies:
        raise DeckEditError(
            "'{}' 在 {} 已有 {} 张，再加 {} 张超过同名 {} 张上限"
            .format(name, section, have, qty, max_copies))
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


def apply_move(deck, name, from_section, to_section, qty, max_copies=MAX_COPIES):
    """纯函数：main↔sideboard 搬移（守恒），返回新 Deck。"""
    if from_section == to_section:
        raise DeckEditError("from/to 分区不能相同: {!r}".format(from_section))
    moved = apply_remove(deck, name, from_section, qty)
    return apply_add(moved, name, to_section, qty, max_copies=max_copies)


def build_limited_audit(deck, pool, unresolved=(), skipped=()):
    """Pure limited gates: delivery count and copies from the imported pool."""
    main = sum(card.qty for card in deck.main)
    violations = [] if main in ALLOWED_DECK_SIZES else ["主牌 {} 张，限制赛交付应为 40 或 41".format(main)]
    validate = {"status": "fail" if violations else "pass", "ok": not violations,
                "violations": violations, "main": main,
                "sideboard": sum(card.qty for card in deck.sideboard)}
    available = collections.Counter()
    for card in pool:
        available[deck_model.front_name(card["name"]).casefold()] += int(card.get("count") or 1)
    unknown_names = {deck_model.front_name(card["name"]).casefold() for card in unresolved}
    used, labels = collections.Counter(), {}
    for _qty, name, _section in deck.entries():
        if name in deck_model.BASIC_LANDS:
            continue
        key = deck_model.front_name(name).casefold()
        used[key] += _qty
        labels[key] = name
    pool_violations, unknown = [], []
    if pool or unresolved:
        for key, count in used.items():
            if key in unknown_names:
                unknown.append(labels[key])
            elif count > available[key]:
                pool_violations.append("{}：主备合计 {} 张，导入牌池只有 {} 张".format(labels[key], count, available[key]))
        if skipped:
            unknown.append("导入牌池存在无法解析的行")
    else:
        unknown.append("未导入完整牌池，只能检查牌表张数")
    pool_ok = False if pool_violations else None if unknown else True
    pool_gate = {"status": "fail" if pool_ok is False else "unknown" if pool_ok is None else "pass",
                 "ok": pool_ok, "violations": pool_violations, "unknown": unknown,
                 "basis": "以本次导入牌池为依据；主备合计不得超过池内数量，基本地按内核规则补充。"}
    overall = False if not validate["ok"] or pool_ok is False else None if pool_ok is None else True
    return {"status": "ok", "scope": "limited", "format": None, "limited": True,
            "validate": validate, "pool": pool_gate,
            "rotation": {"status": "not_applicable", "ok": None,
                         "detail": "限制赛不采用构筑赛合法性和 Standard 轮替门禁。"}, "ok": overall}


def summarize_ratings(pool, table, set_code=None):
    names = sorted({_name for _name in (str(card.get("name") or "") for card in pool)
                    if _name not in deck_model.BASIC_LANDS})
    covered = [name for name in names if table and table.lookup(name) and table.lookup(name).get("grade")]
    meta = {}
    if set_code:
        path = mtga_draft_tool.card_table_path(str(set_code).upper())
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    if not isinstance(meta, dict):
        meta = {}
    return {"set": set_code, "covered": len(covered), "total": len(names),
            "missing": [name for name in names if name not in covered],
            "source": meta.get("source"), "generated": meta.get("generated"),
            "preview_count": sum(table.lookup(name).get("source") == "preview" or
                                 table.lookup(name).get("confidence") == "C0" for name in covered),
            "basis": "评分用于机器选牌排序、色组深度和曲线/角色取舍；缺失评分使用默认值，不能据此证明强度。"}


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
    seed_text = body.get("seed_text")
    if seed_text is not None:
        if not isinstance(seed_text, str) or not seed_text.strip():
            raise ValueError("seed_text 必须是非空牌表文本")
        seed_names = CS.parse_seed_lines(seed_text.splitlines())
    else:
        seed_names = []
    seeds = body.get("seeds")
    if seed_text is None and (not isinstance(seeds, list) or not seeds):
        raise ValueError("seeds 必须是非空牌名数组，如 [\"牌名A\", \"牌名B\"]")
    for item in (seeds if seed_text is None else []):
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


def _clip_detail(text, limit=500):
    """子进程错误细节收敛：压成单行并按 limit 截断，截断处标注 …[截断]。

    rot_audit/deck_cost 的 stderr 可能整段倾倒（含 URL 与重试噪音，
    如 "! FAIL https://… 429"），直接进 JSON 会把页面淹没；截断保信息
    密度且明示发生了截断。短文本原样返回。
    """
    flat = " ".join(str(text).split())
    if len(flat) <= limit:
        return flat
    return flat[:limit] + "…[截断]"


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


# ------------------------------------------------------------------ Agent 桥（Phase 3）

class AgentBridge:
    """进程内请求/结果队列：网页（人）出题，交互式 Agent 会话答题。

    借鉴上游 deck-forge AgentBridge 的协议语义（0BSD），asyncio.Future
    改为 Condition + dict 以适配 ThreadingHTTPServer 的多线程模型：

    - submit 入队；next_request 是认领语义——同一请求同一时间只派给
      一个 agent，拿到即 in_flight；
    - 认领后 claim_lease（60s）内未提交结果且无心跳 → 重新入队可再认领
      （防 Agent 崩溃把请求挂死）；
    - 结果槽位 TTL（300s）后清理：迟到的 result → 410，未取的 GET → 410，
      tombstone 再保留一个 TTL 周期以区分"从未存在"（404）；
    - 时间一律走注入的 clock（缺省 time.monotonic），测试用假时钟驱动
      租约/TTL 过期；对外时间戳仍是 ISO。
    """

    def __init__(self, result_ttl=AGENT_RESULT_TTL,
                 claim_lease=AGENT_CLAIM_LEASE, clock=None):
        self._cond = threading.Condition()
        self._result_ttl = float(result_ttl)
        self._claim_lease = float(claim_lease)
        self._clock = clock or time.monotonic
        self._counter = 0
        self._queue = collections.deque()      # 待认领 request_id（FIFO）
        self._records = {}                     # request_id → record
        self._gone = {}                        # 已清理 id → 清理时刻（410 tombstone）

    def _sweep_locked(self):
        """锁内清理：过期结果 → tombstone；过期 tombstone 遗忘；在途认领
        租约过期 → 重新入队。"""
        now = self._clock()
        for rid in [rid for rid, rec in self._records.items()
                    if rec["state"] == "done"
                    and now - rec["completed_at"] > self._result_ttl]:
            self._records.pop(rid)
            self._gone[rid] = now
        for rid in [rid for rid, t in self._gone.items()
                    if now - t > self._result_ttl]:
            self._gone.pop(rid)
        for rec in self._records.values():
            if rec["state"] == "in_flight" \
                    and now - rec["claimed_at"] > self._claim_lease:
                rec["state"] = "queued"
                rec["claimed_by"] = None
                rec["claimed_at"] = None
                self._queue.append(rec["id"])

    def submit(self, kind, payload, timeout_sec=None):
        """入队一个 reasoning 请求，返回 {"request_id", "queued_at"}。"""
        with self._cond:
            self._sweep_locked()
            self._counter += 1
            rid = "req-{}".format(self._counter)
            self._records[rid] = {
                "id": rid, "kind": kind, "payload": payload,
                "timeout_sec": timeout_sec,
                "queued_at": _now_iso(),
                "state": "queued",
                "claimed_by": None, "claimed_at": None,
                "claim_token": None,
                "completed_iso": None, "completed_at": None,
                "result_status": None, "result": None, "message": None,
            }
            self._queue.append(rid)
            self._cond.notify()
            return {"request_id": rid,
                    "queued_at": self._records[rid]["queued_at"]}

    @staticmethod
    def _request_view(rec):
        return {"request_id": rec["id"], "kind": rec["kind"],
                "payload": rec["payload"], "queued_at": rec["queued_at"],
                "timeout_sec": rec["timeout_sec"], "claim_token": rec["claim_token"]}

    def next_request(self, agent, wait=True, poll_max=AGENT_POLL_MAX):
        """Agent 侧长轮询：拿到请求返回 {"status":"ok","request":{...}}；
        队空返回 {"status":"wait"}（wait=True 时最多挂起 poll_max 秒）。"""
        deadline = self._clock() + poll_max
        with self._cond:
            while True:
                self._sweep_locked()
                if self._queue:
                    rid = self._queue.popleft()
                    rec = self._records.get(rid)
                    if rec is None or rec["state"] != "queued":
                        continue            # 已被认领/清理（防御，跳过）
                    rec["state"] = "in_flight"
                    rec["claimed_by"] = agent
                    rec["claim_token"] = uuid.uuid4().hex
                    rec["claimed_at"] = self._clock()
                    return {"status": "ok", "request": self._request_view(rec)}
                if not wait:
                    return {"status": "wait"}
                remaining = deadline - self._clock()
                if remaining <= 0:
                    return {"status": "wait"}
                self._cond.wait(timeout=remaining)

    def complete(self, request_id, status, result, message, agent=None, claim_token=None):
        """Agent 提交结果。返回 "ok" / "missing"（未知 id）/ "gone"（已
        过 TTL 清理）/ "not_claimed"（未在认领态）/ "done"（重复提交）。"""
        with self._cond:
            self._sweep_locked()
            rec = self._records.get(request_id)
            if rec is None:
                return "gone" if request_id in self._gone else "missing"
            if rec["state"] == "done":
                return "done"
            if rec["state"] != "in_flight":
                return "not_claimed"
            if (agent is not None and rec["claimed_by"] != agent) or \
                    (claim_token is not None and rec["claim_token"] != claim_token):
                return "not_claimed"
            rec["state"] = "done"
            rec["completed_at"] = self._clock()
            rec["completed_iso"] = _now_iso()
            rec["result_status"] = status
            rec["result"] = result
            rec["message"] = message
            self._cond.notify()
            return "ok"

    def get_result(self, request_id):
        """网页侧取结果：返回 ("ok", view) / ("pending", view) /
        ("missing", None) / ("gone", None)。

        ok 与 pending 两种 view 顶层都带 claimed_by（未认领 None）——
        页面据此显示"等待 Agent 认领…"还是"[agent] 处理中…"。
        """
        with self._cond:
            self._sweep_locked()
            rec = self._records.get(request_id)
            if rec is None:
                return ("gone", None) if request_id in self._gone \
                    else ("missing", None)
            if rec["state"] != "done":
                return "pending", {"request_id": rec["id"],
                                   "kind": rec["kind"],
                                   "claimed_by": rec["claimed_by"]}
            return "ok", {"request_id": rec["id"], "kind": rec["kind"],
                          "status": rec["result_status"],
                          "result": rec["result"], "message": rec["message"],
                          "agent": rec["claimed_by"],
                          "claimed_by": rec["claimed_by"],
                          "completed_at": rec["completed_iso"]}

    def heartbeat(self, request_id, agent, claim_token=None):
        """认领方续租：返回 "ok" / "missing" / "gone" / "not_claimed"。"""
        with self._cond:
            self._sweep_locked()
            rec = self._records.get(request_id)
            if rec is None:
                return "gone" if request_id in self._gone else "missing"
            if rec["state"] != "in_flight" or rec["claimed_by"] != agent or \
                    (claim_token is not None and rec["claim_token"] != claim_token):
                return "not_claimed"
            rec["claimed_at"] = self._clock()
            return "ok"

    def status(self):
        """桥诊断：队列深度、在途请求数与认领明细、就绪结果数、kind 集合。

        in_flight 保持计数（旧消费方兼容），in_flight_requests 新带
        [{request_id, claimed_by}] 明细供页面判断"处理中/待认领"。
        """
        with self._cond:
            self._sweep_locked()
            states = [rec["state"] for rec in self._records.values()]
            in_flight = [{"request_id": rec["id"],
                          "claimed_by": rec["claimed_by"]}
                         for rec in self._records.values()
                         if rec["state"] == "in_flight"]
            return {"status": "ok",
                    "queue_depth": len(self._queue),
                    "in_flight": states.count("in_flight"),
                    "in_flight_requests": in_flight,
                    "results_ready": states.count("done"),
                    "tracked_requests": len(self._records),
                    "recent_requests": [{"request_id": rec["id"], "kind": rec["kind"],
                                         "state": rec["state"], "claimed_by": rec["claimed_by"],
                                         "queued_at": rec["queued_at"]}
                                        for rec in list(self._records.values())[-10:]],
                    "kinds": list(AGENT_KINDS)}


def parse_agent_request_body(body):
    """POST /api/agent/request 请求体校验 → (kind, payload, timeout_sec)。"""
    kind = body.get("kind")
    if kind not in AGENT_KINDS:
        raise ValueError("kind 只支持 {}，收到: {!r}".format(
            "/".join(AGENT_KINDS), kind))
    payload = body.get("payload")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("payload 必须是 JSON 对象，收到: {!r}".format(payload))
    timeout_sec = body.get("timeout_sec")
    if timeout_sec is not None:
        if not isinstance(timeout_sec, (int, float)) \
                or isinstance(timeout_sec, bool) or timeout_sec <= 0:
            raise ValueError("timeout_sec 必须是正数（秒），收到: {!r}"
                             .format(timeout_sec))
        timeout_sec = float(timeout_sec)
    return kind, payload, timeout_sec


def parse_agent_result_body(body):
    """POST /api/agent/result 请求体校验 → (request_id, status, result, msg)。"""
    request_id = body.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request_id 必须是非空字符串，收到: {!r}"
                         .format(request_id))
    status = body.get("status")
    if status not in ("ok", "error"):
        raise ValueError("status 必须是 'ok' 或 'error'，收到: {!r}"
                         .format(status))
    result = body.get("result")
    if result is None:
        result = {}
    if not isinstance(result, dict):
        raise ValueError("result 必须是 JSON 对象，收到: {!r}".format(result))
    message = body.get("message", "")
    if not isinstance(message, str):
        raise ValueError("message 必须是字符串，收到: {!r}".format(message))
    return request_id.strip(), status, result, message


def parse_agent_heartbeat_body(body):
    """POST /api/agent/heartbeat 请求体校验 → (request_id, agent)。"""
    request_id = body.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request_id 必须是非空字符串，收到: {!r}"
                         .format(request_id))
    agent = body.get("agent")
    if not isinstance(agent, str) or not agent.strip():
        raise ValueError("agent 必须是非空字符串，收到: {!r}".format(agent))
    return request_id.strip(), agent.strip()


# ------------------------------------------------------------------ avenues（Phase 3 反向通路）

def parse_avenue_body(body):
    """POST /api/avenues 请求体校验 → (title, note, candidates)。

    candidates[].name 必须是非空字符串；服务端不联网验证牌名（铁律责任
    在写入方，响应以 unverified_card_names 明示）。输入错误抛 ValueError。"""
    title = body.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title 必须是非空字符串，收到: {!r}".format(title))
    note = body.get("note", "")
    if not isinstance(note, str):
        raise ValueError("note 必须是字符串，收到: {!r}".format(note))
    raw_candidates = body.get("candidates")
    if raw_candidates is None:
        raw_candidates = []
    if not isinstance(raw_candidates, list):
        raise ValueError("candidates 必须是数组，收到: {!r}"
                         .format(raw_candidates))
    candidates = []
    for item in raw_candidates:
        if not isinstance(item, Mapping):
            raise ValueError("candidates 只接受对象记录，收到: {!r}".format(item))
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("候选 name 必须是非空字符串，收到: {!r}"
                             .format(name))
        reason = item.get("reason", "")
        if not isinstance(reason, str):
            raise ValueError("候选 reason 必须是字符串，收到: {!r}"
                             .format(reason))
        candidates.append({"name": name.strip(), "reason": reason})
    return title.strip(), note, candidates


# ------------------------------------------------------------------ find（铁律契约落地端点）

def find_cards(query, limit):
    """包装 mtg_tool.scryfall_search（进程内调用 + 磁盘缓存，不走子进程）。

    铁律契约：LLM 提案的一切卡牌必须来自这里（或 mtg_tool CLI）的实际
    结果。oracle 去重（与 CLI search 默认一致），截断到 limit。
    QuerySyntaxError 由 HTTP 层映射 400；其余 MtgToolError 映射 500；
    真实零命中是空列表而非异常。
    """
    cards, total, warnings = mtg_tool.scryfall_search(query, unique="oracle")
    records = [mtg_tool.normalize_card(card) for card in cards[:limit]]
    return {"status": "ok", "query": query, "total_cards": total,
            "returned": len(records), "cards": records,
            "warnings": list(warnings)}


# ------------------------------------------------------------------ advice（决策 D 嵌入式 LLM 轴）

ADVICE_SYSTEM = (
    "你是万智牌套牌构筑顾问。根据用户给出的牌表与确定性统计，给出下一步"
    "构筑/微调建议。纪律：点名具体卡牌时必须来自牌表本身或用户明确给出"
    "的检索证据，不得凭记忆编造牌名；建议要具体、可执行，用中文，3-5 条。")

# 重试策略：不重试（0 次）。advice 是网页按钮触发的辅助通道，失败语义是
# 显式 offline + machine_fallback 兜底——用户立刻拿到确定性结论；一次重试
# 对超时/网络类瞬态故障收益边际，却双倍延迟与计费，且违背"禁止静默重试
# 风暴"的红线。需要更健壮、可核验的 LLM 驱动请走 Agent 桥主通道。


def build_machine_fallback(state):
    """纯机器兜底：stats + 已缓存 roles 缺口的确定性结论（无任何网络）。

    roles 只读缓存槽位（不触发水合）；槽位缺失/失败时 role_gaps=None 明示
    unknown，不编造。
    """
    stats = state.stats()
    fallback = {"main": stats["main"], "lands": stats["lands"],
                "nonlands": stats["nonlands"],
                "average_cmc": stats["average_cmc"],
                "curve_label": stats["curve_label"], "curve": stats["curve"],
                "mana_sources": stats["mana_sources"], "pips": stats["pips"],
                "land_check": stats["land_check"], "role_gaps": None,
                "notes": []}
    if not stats["land_check"]["ok"]:
        fallback["notes"].append(
            "land_check 未通过（{} 张口径，{} 地）：3回合≥2地 {:.0%}，"
            "5回合≥4地 {:.0%}".format(
                stats["land_check"]["deck_size"], stats["lands"],
                stats["land_check"]["p3"] or 0.0,
                stats["land_check"]["p5"] or 0.0))
    if stats["unknown"]:
        fallback["notes"].append("以下牌未水合，曲线/配比未计入: "
                                 + "、".join(stats["unknown"]))
    roles_slot = state.slot("roles")
    if roles_slot and roles_slot.get("status") == "ok":
        fallback["role_gaps"] = roles_slot["result"].get("gaps") or []
    return fallback


def build_advice_prompt(state):
    """当前牌表的紧凑 prompt：牌表行 + stats 摘要 + 已缓存 roles 缺口。

    只塞确定性结论，不塞原始大数据；roles 缺口只来自缓存槽位（不触发
    网络水合），槽位缺失就如实不写。
    """
    lines = []
    text = state.export_text().strip()
    lines.append("当前牌表：\n" + text if text else "当前牌表为空。")
    stats = state.stats()
    lines.append(
        "统计（deck_core 口径）：主牌 {main} 张，地 {lands} / 非地 {nonlands}，"
        "平均 CMC {cmc}（{label}）；曲线 {curve}；land_check {lc}".format(
            main=stats["main"], lands=stats["lands"], nonlands=stats["nonlands"],
            cmc=stats["average_cmc"], label=stats["curve_label"],
            curve=json.dumps(stats["curve"], ensure_ascii=False),
            lc=json.dumps(stats["land_check"], ensure_ascii=False)))
    roles_slot = state.slot("roles")
    if roles_slot and roles_slot.get("status") == "ok":
        gaps = roles_slot["result"].get("gaps") or []
        lines.append("角色缺口："
                     + ("；".join("{module} 缺 {deficit}（有 {have} / 目标 {want}）"
                                  .format(**gap) for gap in gaps)
                        if gaps else "无（M1/M2/M3/M5/M8 均达 wanted 配额）"))
    lines.append("请给出下一步构筑/微调建议（3-5 条，每条一句，可执行）。")
    return "\n\n".join(lines)


def build_advice(state):
    """嵌入式 LLM 点评（决策 D 辅助通道）。

    配置缺失/请求失败/超时 → {"status": "offline", "advice": None,
    "offline_reason": ..., "machine_fallback": ...}；成功 → status ok +
    LLM 原文（verified=False 明示未经工具核验）。任何失败路径都带纯机器
    兜底，绝不留空。不重试（见 ADVICE_SYSTEM 上方注释）。
    """
    payload = {"status": "offline", "advice": None, "model": None,
               "verified": False, "offline_reason": None,
               "machine_fallback": build_machine_fallback(state),
               "checked_at": _now_iso()}
    try:
        cfg = AUTO.load_llm_config(LLM_CONFIG_JSON)
    except Exception as exc:
        # 配置缺失/损坏/无 key 一律显式 offline（load_llm_config 自身抛
        # AutoToolError；json 损坏等异常同样吞为 offline 理由，不 500）
        payload["offline_reason"] = str(exc)
        return payload
    messages = [{"role": "system", "content": ADVICE_SYSTEM},
                {"role": "user", "content": build_advice_prompt(state)}]
    try:
        text = AUTO.llm_chat(cfg, messages, timeout=ADVICE_LLM_TIMEOUT)
    except Exception as exc:
        # llm_chat 把 HTTP/网络/超时/解析失败统一抛 AutoToolError；宽捕是
        # 为了让辅助通道任何失败都显式 offline，而不是 500 吓到网页
        payload["offline_reason"] = str(exc)
        return payload
    payload.update({"status": "ok", "advice": text, "model": cfg.get("model")})
    return payload


# ------------------------------------------------------------------ 权威状态

class WorkbenchState:
    """权威状态：当前 Deck + 会话元数据（导入时间/来源/序号）。

    所有读写持锁，import 的纯解析在锁外完成，锁内只做替换 + 快照构造，
    并发导入因此是安全的串行化（最后一次成功写入获胜）。
    """

    def __init__(self, agent_backend=workbench_agent.DEFAULT_BACKEND):
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
                       ("roles", "combos", "cost", "audit", "constructed", "evaluation")}
        # Phase 3：Agent 桥（请求/结果队列）+ avenues 持久列表（反向通路）
        self.bridge = AgentBridge()
        self.receiver = workbench_agent.create_receiver(self, backend=agent_backend)
        self.jobs = workbench_jobs.JobRegistry()
        self._avenues = []
        self._avenue_seq = 0

    def _record_slot(self, name, entry):
        with self._lock:
            self._slots[name] = entry

    def slot(self, name):
        """读取核验槽位的副本（advice 兜底/prompt 用；不触发水合）。"""
        with self._lock:
            entry = self._slots.get(name)
            return dict(entry) if entry else None

    # -------------------------------------------------- Phase 3 avenues

    def avenue_add(self, title, note, candidates):
        """新增探索方向；unverified_card_names 随记录持久化（铁律责任在
        写入方，服务端不联网验证候选牌名）。"""
        with self._lock:
            self._avenue_seq += 1
            avenue = {"id": "av-{}".format(self._avenue_seq),
                      "title": title, "note": note, "candidates": candidates,
                      "unverified_card_names": bool(candidates),
                      "focused": False, "created_at": _now_iso()}
            self._avenues.append(avenue)
            return dict(avenue)

    def avenue_list(self):
        with self._lock:
            return [dict(avenue) for avenue in self._avenues]

    def avenue_delete(self, avenue_id):
        with self._lock:
            for index, avenue in enumerate(self._avenues):
                if avenue["id"] == avenue_id:
                    self._avenues.pop(index)
                    return True
        return False

    def avenue_focus(self, avenue_id):
        """单焦点语义：点亮目标、清除其余。不存在返回 None。"""
        with self._lock:
            target = None
            for avenue in self._avenues:
                if avenue["id"] == avenue_id:
                    target = avenue
                    break
            if target is None:
                return None
            for avenue in self._avenues:
                avenue["focused"] = avenue is target
            return dict(target)

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
            snap["bridges"] = self.bridge.status()
            snap["bridges"]["receiver"] = self.receiver.status()
            snap["bridges"]["receiver"]["backends"] = workbench_agent.backend_options()
            snap["avenues"] = [dict(avenue) for avenue in self._avenues]
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
            self._slots = {name: None for name in self._slots}
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
            self._slots = {name: None for name in self._slots}
            self._last_seed = None
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
                     table=None, table_warnings=(), set_code=None):
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
        seed["ratings"] = summarize_ratings(pool, table, set_code)
        with self._lock:
            self._last_seed = seed
        snapshot["seed"] = seed
        return snapshot

    def _edit(self, func, *args):
        """手动微调：锁内应用纯函数并返回 快照 + 重算 stats。"""
        with self._lock:
            self._deck = func(self._deck, *args)
            self._slots = {name: None for name in self._slots}
            if self._last_seed:
                self._last_seed = dict(self._last_seed, stale=True)
            snap = build_snapshot(self._deck, self._session_locked())
            snap["stats"] = build_stats(self._deck, self._card_db)
            return snap

    def deck_add(self, name, section, qty=1, limited=False):
        if limited:
            _check_edit_args(name, section, qty)
            with self._lock:
                if name not in deck_model.BASIC_LANDS:
                    used = sum(card.qty for sec in SECTIONS for card in getattr(self._deck, sec)
                               if deck_model.front_name(card.name).casefold() == deck_model.front_name(name).casefold())
                    available = sum(int(card.get("count") or 1) for card in self._pool
                                    if deck_model.front_name(card["name"]).casefold() == deck_model.front_name(name).casefold())
                    if used + qty > available:
                        raise DeckEditError("{}：已使用 {} 张，牌池只有 {} 张；可将已有备牌移入主牌。".format(name, used, available))
                self._deck = apply_add(self._deck, name, section, qty, max_copies=None)
                self._slots = {key: None for key in self._slots}
                if self._last_seed:
                    self._last_seed = dict(self._last_seed, stale=True)
            return self.snapshot()
        return self._edit(apply_add, name, section, qty)

    def deck_remove(self, name, section, qty=1):
        return self._edit(apply_remove, name, section, qty)

    def deck_move(self, name, from_section, to_section, qty=1, limited=False):
        return self._edit(apply_move, name, from_section, to_section, qty,
                          None if limited else MAX_COPIES)

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
        seed = seed_names if isinstance(seed_names, CS.SeedSet) else CS.SeedSet(main=tuple((1, name) for name in seed_names))
        built = CS.build_constructed_deck(candidates, seed, fmt, bo3=bo3,
                                          strategy=strategy, platform=platform)
        snapshot = self.import_text(
            deck_pooper.render_constructed_deck(built),
            source_name="seed-constructed")
        summary = summarize_constructed(built)
        summary["selections"] = [{"name": item.card["name"], "qty": item.count,
                                  "module": item.module, "reason": item.reason} for item in built.main]
        with self._lock:
            for card in candidates:
                self._card_db[card["name"]] = dict(card)
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
                    completed.returncode, _clip_detail(stderr)
                    or _clip_detail(stdout) or "无输出"))
            self._record_slot("cost", {"status": "error",
                                       "checked_at": checked_at,
                                       "error": envelope["error"]})
            return envelope, False
        result = parse_cost_output(stdout)
        result.update({"status": "ok", "checked_at": checked_at})
        self._record_slot("cost", {"status": "ok", "checked_at": checked_at,
                                   "result": result})
        return result, True

    def _audit_context(self):
        with self._lock:
            return (self._deck, list(self._pool), list(self._pool_unresolved), list(self._pool_skipped))

    @staticmethod
    def _context_signature(context):
        deck, pool, unresolved, skipped = context
        data = [serialize_deck(deck), [(card.get("name"), card.get("count")) for card in pool],
                unresolved, skipped]
        return hashlib.sha256(_json_bytes(data)).hexdigest()

    def start_audit(self, fmt, limited, bo3):
        context = self._audit_context()
        source = self._context_signature(context) + ":{}:{}:{}".format(fmt, limited, bo3)

        def worker(progress, _key):
            result, http_ok = self.audit(fmt, limited, bo3, progress=progress, context=context)
            if not http_ok:
                raise WorkbenchError(result["error"]["message"])
            return result

        return self.jobs.start("audit", source, worker)

    def start_evaluation(self, body, fetch_card=None):
        fmt, options, supplied, baseline = workbench_evaluation.parse_request(body)
        with self._lock:
            deck = self._deck
            cached = json.loads(json.dumps(list(self._card_db.values())))
            context = [serialize_deck(deck), cached]
        if not deck.main:
            raise ValueError("请先导入或生成牌表")
        if deck.skipped:
            raise ValueError("当前牌表含跳过的行，请修正后评测")
        decks = [deck] + ([baseline] if baseline is not None else [])
        for item in decks:
            if not 7 <= sum(c.qty for c in item.main) <= 250:
                raise ValueError("评测牌库需为7至250张")
            if any(type(qty) is not int or qty < 1 for qty, _, _ in item.entries()):
                raise ValueError("牌张数量必须为正整数")
        context_hash = deck_evaluate.digest(context)
        source = deck_evaluate.digest([context_hash, fmt, options, supplied,
                                       serialize_deck(baseline) if baseline is not None else None])
        if len({name for item in decks for _, name, _ in item.entries()}) > workbench_evaluation.MAX_NAMES:
            raise ValueError("单次评测最多150个不同牌名")

        def worker(progress, _key):
            with self._lock:
                self._slots["evaluation"] = None
            cards = workbench_evaluation.prepare_cards(
                decks, supplied if supplied is not None else cached,
                None if supplied is not None else (fetch_card or default_fetch_card), progress)
            if baseline is not None:
                progress("正在评测对照牌表", 0, 2)
                before = deck_evaluate.evaluate(baseline, cards, **options)
            progress("正在评测当前牌表", 1 if baseline is not None else 0, 2 if baseline is not None else 1)
            result = deck_evaluate.evaluate(deck, cards, **options)
            if baseline is not None:
                result = deck_evaluate.comparison(before, result)
            result.update(format_context=fmt, checked_at=_now_iso())
            with self._lock:
                now = [serialize_deck(self._deck), list(self._card_db.values())]
                result["stale"] = deck_evaluate.digest(now) != context_hash
                if not result["stale"]:
                    self._slots["evaluation"] = {"status": "ok", "checked_at": result["checked_at"], "result": result}
            progress("评测完成（" + ("有未覆盖项" if result["status"] == "partial" else "模型范围内完成") + "）", 1, 1)
            return result

        return self.jobs.start("evaluation", source, worker)

    def start_image(self, title="当前套牌"):
        deck = self._deck_copy()
        text = serialize_deck(deck)
        if not text.strip():
            raise ValueError("请先导入或生成牌表")
        source = hashlib.sha256(text.encode("utf-8")).hexdigest()

        def worker(progress, key):
            names = sorted({name for _qty, name, _sec in deck.entries()})
            missing = []
            for i, name in enumerate(names):
                progress("准备卡图：" + name, i, len(names))
                if not workbench_jobs.card_image(name):
                    missing.append(name)
                progress("卡图已处理 {} / {}".format(i + 1, len(names)), i + 1, len(names))
            progress("正在排版并写入 PNG", len(names), len(names))
            with tempfile.TemporaryDirectory(prefix="workbench_image_") as tmp:
                path = Path(tmp) / "deck.txt"
                out = Path(tmp) / "deck.png"
                path.write_text(text, encoding="utf-8")
                completed = _run_tool([sys.executable, "-X", "utf8", str(IMAGE_TOOL_SCRIPT),
                                       str(path), "--out", str(out), "--title", title])
                stdout, stderr = _completed_text(completed)
                if completed.returncode or not out.is_file():
                    raise WorkbenchError("图片输出失败：" + _clip_detail(stderr or stdout or "未生成 PNG"))
                data = out.read_bytes()
            return {"download_url": "/api/jobs/" + key + "/image", "missing_images": missing,
                    "stale": serialize_deck(self._deck_copy()) != text, "_image": data}

        return self.jobs.start("image", source, worker)

    def audit(self, fmt, limited, bo3, progress=None, context=None):
        """聚合 mtg_tool validate 与 rot_audit deck 两个子进程门禁。

        返回 (payload, http_ok)。http_ok 仅表示请求本身可否 200；门禁结果在
        payload.validate/rotation 的 status（pass/fail/unknown）与顶层 ok
        （True/False/None——任何一门 unknown 则整体 None，绝不把失败当通过）。
        """
        checked_at = _now_iso()
        context = context or self._audit_context()
        deck, pool, unresolved, skipped = context
        text = serialize_deck(deck)
        progress = progress or (lambda *args: None)
        if not text.strip():
            envelope = _error_envelope(
                "EmptyDeckError", "当前牌表为空：请先导入牌表再跑门禁")
            self._record_slot("audit", {"status": "error",
                                        "checked_at": checked_at,
                                        "error": envelope["error"]})
            return envelope, False
        if limited:
            progress("检查限制赛张数", 0, 2)
            payload = build_limited_audit(deck, pool, unresolved, skipped)
            progress("核对主备牌与导入牌池数量", 1, 2)
        else:
            standard = fmt.lower() == "standard"
            progress("CLI：检查张数、逐牌合法性与平台可用性（缓存/网络）", 0, 2 if standard else 1)
            validate = self._gate_validate(text, fmt, False, bo3)
            if standard:
                progress("CLI：检查 Standard 轮替存活", 1, 2)
                rotation = self._gate_rotation(text)
            else:
                rotation = {"status": "not_applicable", "ok": None,
                            "detail": "{} 不采用 Standard 轮替门禁。".format(fmt)}
            gates = [validate] + ([rotation] if standard else [])
            overall = False if any(g["ok"] is False for g in gates) else \
                None if any(g["ok"] is None for g in gates) else True
            payload = {"status": "ok", "scope": "constructed", "format": fmt, "limited": False,
                       "validate": validate, "rotation": rotation, "ok": overall}
        payload.update(bo3=bo3, checked_at=checked_at)
        with self._lock:
            current = (self._deck, self._pool, self._pool_unresolved, self._pool_skipped)
            payload["stale"] = self._context_signature(context) != self._context_signature(current)
            if not payload["stale"]:
                self._slots["audit"] = {"status": "ok", "checked_at": checked_at, "result": payload}
        progress("体检完成", 2 if limited or fmt.lower() == "standard" else 1,
                 2 if limited or fmt.lower() == "standard" else 1)
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
                    _clip_detail(stderr + " " + stdout) or "无输出")}

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
                        _clip_detail(stderr) or "无输出")}
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
    的合法降级路径（缺失等级使用默认分，再按曲线/角色计分），但必须明示。
    """
    if not set_code:
        return None, ["未提供 set：无评分表，按默认分与曲线/角色综合选择"
                      "（可在 seed 请求传 {\"set\": \"XXX\"} 启用评分表）"]
    code = str(set_code).upper()
    if not re.fullmatch(r"[A-Z0-9]{2,8}", code):
        raise ValueError("系列代码需为 2–8 位字母或数字")
    table = mtga_draft_tool.load_card_table(code)
    if table is None:
        return None, ["无评分表 tools/cache/draft_ratings/{}.json："
                      "按默认分与曲线/角色综合选择".format(code)]
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
                elif path == "/api/card-image":
                    self._handle_card_image()
                elif path.startswith("/api/jobs/"):
                    self._handle_job_get(path)
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
                elif path == "/api/agent/next":
                    self._handle_agent_next()
                elif path == "/api/agent/status":
                    payload = state.bridge.status()
                    payload["receiver"] = state.receiver.status()
                    self._send_json(200, payload)
                elif path == "/api/agent/connection":
                    payload = state.receiver.status()
                    payload["backends"] = workbench_agent.backend_options()
                    self._send_json(200, payload)
                elif path.startswith("/api/agent/result/"):
                    self._handle_agent_result_get(path.rsplit("/", 1)[1])
                elif path == "/api/find":
                    self._handle_find()
                elif path == "/api/avenues":
                    self._send_json(200, {"status": "ok",
                                          "avenues": state.avenue_list()})
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
                elif path == "/api/audit/start":
                    self._handle_audit(async_start=True)
                elif path == "/api/evaluation/start":
                    self._handle_evaluation_start()
                elif path == "/api/export-image":
                    self._handle_image_start()
                elif path in ("/api/deck/add", "/api/deck/remove", "/api/deck/move"):
                    self._handle_deck_edit(path.rsplit("/", 1)[1])
                elif path == "/api/agent/request":
                    self._handle_agent_request()
                elif path == "/api/agent/connect":
                    self._handle_agent_connection("connect")
                elif path == "/api/agent/disconnect":
                    self._handle_agent_connection("disconnect")
                elif path == "/api/agent/approval":
                    self._handle_agent_connection("approval")
                elif path == "/api/agent/result":
                    self._handle_agent_result()
                elif path == "/api/agent/heartbeat":
                    self._handle_agent_heartbeat()
                elif path == "/api/avenues":
                    self._handle_avenue_add()
                elif path.startswith("/api/avenues/") and path.endswith("/focus"):
                    self._handle_avenue_focus(path[len("/api/avenues/"):
                                                   -len("/focus")])
                elif path == "/api/advice":
                    self._send_json(200, build_advice(state))
                else:
                    self._send_json(404, _error_envelope(
                        "NotFoundError", "未知路径: {}".format(path)))
            except Exception as exc:
                self._unhandled(exc)

        def do_DELETE(self):
            try:
                path = urlsplit(self.path).path
                if path.startswith("/api/avenues/"):
                    self._handle_avenue_delete(path[len("/api/avenues/"):])
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
                                              table_warnings=table_warnings,
                                              set_code=body.get("set"))
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

        def _handle_card_image(self):
            name = (parse_qs(urlsplit(self.path).query).get("name") or [""])[0]
            snap = state.snapshot()
            allowed = {card["name"] for cards in snap["sections"].values() for card in cards}
            allowed.update(card["name"] for card in snap["pool"]["entries"])
            if name not in allowed:
                self._send_json(404, _error_envelope("NotFoundError", "该牌不在当前牌表或牌池中"))
                return
            path = workbench_jobs.card_image(name)
            if path is None:
                self._send_json(404, _error_envelope("ImageUnavailable", "没有可用卡图"))
                return
            self._send(200, path.read_bytes(), workbench_jobs.image_content_type(path))

        def _handle_job_get(self, path):
            parts = path.strip("/").split("/")
            job = state.jobs.get(parts[2]) if len(parts) in (3, 4) else None
            if job is None:
                self._send_json(404, _error_envelope("NotFoundError", "任务不存在或已过期"))
            elif len(parts) == 4 and parts[3] == "image":
                data = state.jobs.image(parts[2])
                if not data:
                    self._send_json(409, _error_envelope("ImageNotReady", "图片尚未完成或生成失败"))
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Disposition", 'attachment; filename="deck.png"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif len(parts) == 3:
                self._send_json(200, job)
            else:
                self._send_json(404, _error_envelope("NotFoundError", "未知任务路径"))

        def _handle_image_start(self):
            try:
                body = self._read_json_body(allow_empty=True)
                title = body.get("title") or "当前套牌"
                if not isinstance(title, str) or len(title) > 120:
                    raise ValueError("标题需为 120 字以内文本")
                self._send_json(202, state.start_image(title))
            except ValueError as exc:
                self._bad_request(exc)

        def _handle_evaluation_start(self):
            try:
                body = self._read_json_body()
                self._send_json(202, state.start_evaluation(body))
            except (ValueError, TypeError) as exc:
                self._bad_request(exc)

        def _handle_audit(self, async_start=False):
            try:
                body = self._read_json_body()
            except ValueError as exc:
                self._bad_request(exc)
                return
            fmt = body.get("format")
            limited = body.get("limited")
            bo3 = body.get("bo3", False)
            if not limited and (not isinstance(fmt, str) or not fmt.strip()):
                self._bad_request(ValueError(
                    "format 是必填非空字符串（如 \"pioneer\"），收到: {!r}".format(fmt)))
                return
            if not isinstance(limited, bool):
                # limited 必须显式传：不做牌张数静默推断
                self._bad_request(ValueError(
                    "limited 是必填布尔（true=限制赛 40/41 口径，false=构筑口径），"
                    "收到: {!r}".format(limited)))
                return
            fmt = fmt.strip() if isinstance(fmt, str) else ""
            if async_start:
                try:
                    self._send_json(202, state.start_audit(fmt, limited, bool(bo3)))
                except ValueError as exc:
                    self._bad_request(exc)
                return
            payload, ok = state.audit(fmt, limited, bool(bo3))
            self._send_json(200 if ok else 500, payload)

        def _handle_deck_edit(self, op):
            try:
                body = self._read_json_body()
            except ValueError as exc:
                self._bad_request(exc)
                return
            name = body.get("name")
            qty = body.get("qty", 1)
            limited = body.get("limited", False)
            if not isinstance(limited, bool):
                self._bad_request(ValueError("limited 必须是布尔值"))
                return
            try:
                if op == "add":
                    snap = state.deck_add(name, body.get("section"), qty, limited=limited)
                elif op == "remove":
                    snap = state.deck_remove(name, body.get("section"), qty)
                else:
                    snap = state.deck_move(name, body.get("from"),
                                           body.get("to"), qty, limited=limited)
            except DeckEditError as exc:
                self._send_json(400, _error_envelope("DeckEditError", str(exc)))
                return
            self._send_json(200, snap)

        # -------------------------------------------------- Phase 3 Agent 桥

        def _handle_agent_connection(self, operation):
            try:
                self._check_agent_origin()
                body = self._read_json_body(allow_empty=True)
                if operation == "connect":
                    host = self.server.server_address[0]
                    if host not in ("127.0.0.1", "localhost", "::1"):
                        raise ValueError("自动 Agent 接收端仅供本机回环工作台使用")
                    requested = (body.get("backend") or "").strip()
                    if requested and requested != state.receiver.backend_name:
                        if state.receiver.status()["status"] not in ("offline", "error"):
                            raise ValueError("接收端已连接，请先断开再切换后端")
                        replacement = workbench_agent.create_receiver(state, backend=requested)
                        state.receiver.close()
                        state.receiver = replacement
                    url = "http://127.0.0.1:{}".format(self.server.server_address[1])
                    payload = state.receiver.connect(url)
                elif operation == "disconnect":
                    payload = state.receiver.disconnect()
                else:
                    payload = state.receiver.answer_approval(body.get("approval_id"), body.get("decision"))
                self._send_json(200, payload)
            except ValueError as exc:
                self._bad_request(exc)

        def _handle_agent_request(self):
            try:
                self._check_agent_origin()
                body = self._read_json_body()
                kind, payload, timeout_sec = parse_agent_request_body(body)
            except ValueError as exc:
                self._bad_request(exc)
                return
            self._send_json(200, state.bridge.submit(kind, payload, timeout_sec))

        def _check_agent_origin(self):
            origin = self.headers.get("Origin")
            if origin:
                parsed = urlsplit(origin)
                if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or \
                        parsed.port != self.server.server_address[1]:
                    raise ValueError("Agent 控制请求必须来自当前本机工作台")

        def _handle_agent_next(self):
            query = parse_qs(urlsplit(self.path).query)
            agent = (query.get("agent") or ["agent"])[0].strip() or "agent"
            wait = (query.get("wait") or ["1"])[0] != "0"
            payload = state.bridge.next_request(agent, wait=wait)
            self._send_json(200, payload)

        def _handle_agent_result(self):
            try:
                body = self._read_json_body()
                request_id, status, result, message = parse_agent_result_body(body)
            except ValueError as exc:
                self._bad_request(exc)
                return
            outcome = state.bridge.complete(request_id, status, result, message)
            if outcome == "ok":
                self._send_json(200, {"status": "ok",
                                      "request_id": request_id})
                return
            if outcome == "missing":
                self._send_json(404, _error_envelope(
                    "NotFoundError", "未知 request_id: {}".format(request_id)))
            elif outcome == "gone":
                self._send_json(410, _error_envelope(
                    "ResultExpiredError",
                    "请求结果已超过 TTL 被清理: {}".format(request_id)))
            elif outcome == "done":
                self._send_json(409, _error_envelope(
                    "ResultConflictError",
                    "请求已有结果，重复提交: {}".format(request_id)))
            else:  # not_claimed
                self._send_json(409, _error_envelope(
                    "ResultConflictError",
                    "请求未被任何 agent 认领（或认领已过期重派）: {}"
                    .format(request_id)))

        def _handle_agent_result_get(self, request_id):
            outcome, view = state.bridge.get_result(request_id)
            if outcome == "ok":
                self._send_json(200, view)
            elif outcome == "pending":
                self._send_json(202, {"status": "pending",
                                      "request_id": request_id,
                                      "claimed_by": (view or {}).get(
                                          "claimed_by")})
            elif outcome == "gone":
                self._send_json(410, _error_envelope(
                    "ResultExpiredError",
                    "请求结果已超过 TTL 被清理: {}".format(request_id)))
            else:
                self._send_json(404, _error_envelope(
                    "NotFoundError", "未知 request_id: {}".format(request_id)))

        def _handle_agent_heartbeat(self):
            try:
                body = self._read_json_body()
                request_id, agent = parse_agent_heartbeat_body(body)
            except ValueError as exc:
                self._bad_request(exc)
                return
            outcome = state.bridge.heartbeat(request_id, agent)
            if outcome == "ok":
                self._send_json(200, {"status": "ok"})
            elif outcome == "missing":
                self._send_json(404, _error_envelope(
                    "NotFoundError", "未知 request_id: {}".format(request_id)))
            elif outcome == "gone":
                self._send_json(410, _error_envelope(
                    "ResultExpiredError",
                    "请求结果已超过 TTL 被清理: {}".format(request_id)))
            else:
                self._send_json(409, _error_envelope(
                    "HeartbeatConflictError",
                    "请求不在该 agent 的认领之下: {}".format(request_id)))

        # -------------------------------------------------- Phase 3 avenues / find

        def _handle_avenue_add(self):
            try:
                body = self._read_json_body()
                title, note, candidates = parse_avenue_body(body)
            except ValueError as exc:
                self._bad_request(exc)
                return
            self._send_json(200, state.avenue_add(title, note, candidates))

        def _handle_avenue_focus(self, avenue_id):
            avenue = state.avenue_focus(avenue_id)
            if avenue is None:
                self._send_json(404, _error_envelope(
                    "NotFoundError", "未知 avenue id: {}".format(avenue_id)))
                return
            self._send_json(200, avenue)

        def _handle_avenue_delete(self, avenue_id):
            if state.avenue_delete(avenue_id):
                self._send_json(200, {"status": "ok", "id": avenue_id})
            else:
                self._send_json(404, _error_envelope(
                    "NotFoundError", "未知 avenue id: {}".format(avenue_id)))

        def _handle_find(self):
            query = parse_qs(urlsplit(self.path).query)
            q = (query.get("q") or [""])[0].strip()
            raw_limit = (query.get("limit") or [str(FIND_DEFAULT_LIMIT)])[0]
            if not q:
                self._bad_request(ValueError("缺少查询参数 q（Scryfall 查询式）"))
                return
            try:
                limit = int(raw_limit)
                if not 1 <= limit <= FIND_MAX_LIMIT:
                    raise ValueError(
                        "limit 必须在 1..{}，收到: {!r}".format(FIND_MAX_LIMIT,
                                                             raw_limit))
            except ValueError as exc:
                self._bad_request(exc)
                return
            try:
                payload = find_cards(q, limit)
            except mtg_tool.QuerySyntaxError as exc:
                self._send_json(400, _error_envelope("QuerySyntaxError",
                                                     str(exc)))
                return
            except mtg_tool.MtgToolError as exc:
                self._send_json(500, _error_envelope(type(exc).__name__,
                                                     "find 查询失败: {}".format(exc)))
                return
            self._send_json(200, payload)

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
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MTG 套牌工作台</title>
<style>
  :root { color-scheme:dark; --bg:#0d1117; --panel:#161d26; --inset:#10161e;
    --line:#2b3644; --text:#dce3eb; --muted:#95a3b4; --accent:#8bd5bf;
    --gold:#e8bf78; --bad:#ff9691; --radius:12px; }
  * { box-sizing:border-box; }
  [hidden] { display:none !important; }
  body { margin:0; color:var(--text); background:radial-gradient(ellipse at 40% 0%,#1c2c33 0,transparent 55%),var(--bg);
    font:13px/1.6 'Microsoft YaHei UI','Microsoft YaHei',sans-serif; }
  button,input,select,textarea { font:inherit; }
  button,a,summary,input,select,textarea { -webkit-tap-highlight-color:transparent; }
  button { cursor:pointer; border:1px solid var(--line); background:#202b38;
    color:var(--text); border-radius:7px; padding:7px 12px; min-height:36px; }
  button:hover { border-color:var(--accent); background:#263743; }
  button:disabled { opacity:.55; cursor:wait; }
  :focus-visible { outline:2px solid var(--accent); outline-offset:3px; }
  button.primary { background:var(--accent); color:#10231f; border-color:var(--accent); font-weight:700; }
  button.primary:hover { background:#abe7d5; }
  a { color:var(--accent); }
  input:not([type=checkbox]),select,textarea { width:100%; min-width:0; color:var(--text);
    background:var(--inset); border:1px solid var(--line); border-radius:6px; padding:8px 10px; }
  textarea { display:block; min-height:106px; resize:vertical;
    font:12px/1.7 Consolas,'Microsoft YaHei',monospace; }
  input[type=checkbox] { accent-color:var(--accent); margin:0; }
  label.field { display:grid; gap:5px; color:var(--muted); font-size:12px; }
  .check { display:flex; align-items:center; gap:7px; min-height:32px; }
  .form-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin:12px 0; }
  .full { grid-column:1/-1; }
  .actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }
  .topbar { border-bottom:1px solid var(--line); background:#101820e6; }
  .topbar-inner { max-width:1800px; margin:auto; padding:18px 26px; display:flex; align-items:center; gap:26px; flex-wrap:wrap; }
  .brand { display:flex; gap:12px; align-items:center; }
  .brand-mark { font:700 17px Bahnschrift,Consolas,sans-serif; letter-spacing:-1px; color:var(--accent);
    border:1px solid #577c74; border-radius:9px; padding:9px 7px; }
  h1 { font-size:18px; letter-spacing:.5px; margin:0; }
  .eyebrow { font:11px Bahnschrift,Consolas,sans-serif; letter-spacing:2px; color:var(--muted); }
  .tabs { display:flex; gap:4px; padding:4px; background:var(--inset); border:1px solid var(--line); border-radius:9px; }
  .tabbtn { border-color:transparent; background:transparent; color:var(--muted); padding:6px 20px; }
  .tabbtn.active { background:#2b3e42; color:var(--accent); }
  .header-actions { margin-left:auto; display:flex; gap:8px; align-items:center; }
  .connection { color:var(--accent); font-size:12px; }
  .shell { max-width:1800px; margin:auto; padding:20px 26px 32px; }
  .session-row { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:16px; }
  #session { color:var(--muted); font-size:12px; overflow-wrap:anywhere; }
  .mode-hint { color:var(--muted); font-size:12px; }
  .overview { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin-bottom:20px; }
  .metric { padding:12px 18px; border:1px solid var(--line); border-radius:var(--radius);
    background:linear-gradient(120deg,#1c2932,#161d26); display:flex; justify-content:space-between; align-items:center; gap:8px; }
  .metric span { color:var(--muted); font-size:12px; }
  .metric strong { font:28px Bahnschrift,Consolas,sans-serif; color:var(--text); }
  .workspace { display:grid; grid-template-columns:minmax(250px,.82fr) minmax(340px,1.55fr) minmax(300px,1fr); gap:18px; align-items:start; }
  .column { min-width:0; }
  .column-label { color:var(--muted); font-size:11px; letter-spacing:1px; margin:0 0 10px; }
  .column-label b { color:var(--accent); font-family:Bahnschrift,Consolas,sans-serif; margin-right:8px; }
  .panel { background:var(--panel); border:1px solid var(--line); border-radius:var(--radius);
    padding:16px; margin-bottom:14px; min-width:0; overflow-wrap:anywhere; }
  .panel h2 { font-size:14px; margin:0; font-weight:600; }
  .panel h3 { font-size:13px; margin:0 0 8px; }
  .panel-head { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:12px; }
  .panel-head .tag { background:var(--inset); border:1px solid var(--line); border-radius:5px; padding:2px 7px; }
  .editor { border-top:2px solid var(--accent); }
  .editor .panel-head h2 { font-size:18px; }
  .editor-note { color:var(--muted); font-size:12px; margin:0 0 14px; }
  #zones { max-height:calc(100vh - 350px); min-height:320px; overflow:auto; scrollbar-gutter:stable; }
  .zone { margin-bottom:16px; }
  .zone-head { display:flex; align-items:center; gap:8px; padding:8px 0; border-bottom:1px solid var(--line); margin-bottom:5px; }
  .zone-head b { color:var(--accent); }
  .zone ul { margin:8px 0; padding-left:20px; }
  .row { display:flex; align-items:center; gap:8px; padding:7px 0; min-width:0; font-size:12px; }
  .row + .row { border-top:1px solid #25303d; }
  .row .nm { flex:1; min-width:0; overflow-wrap:anywhere; }
  .row .tag { min-width:25px; text-align:center; font-family:Bahnschrift,Consolas,sans-serif; }
  .row button { flex-shrink:0; margin:0; padding:4px 7px; font-size:11px; min-height:30px; }
  .row .card-actions { display:flex; gap:4px; }
  .ts,.tag,.note { color:var(--muted); }
  .tag,.note { font-size:12px; }
  .note { line-height:1.7; }
  .empty-state { display:grid; place-content:center; text-align:center; min-height:230px; padding:24px 12px; gap:12px; }
  .empty-state strong { font-size:16px; font-weight:500; }
  .empty-glyph { font:36px Bahnschrift,Consolas,sans-serif; color:#557367; }
  .empty-state .actions { justify-content:center; }
  #poolList { max-height:360px; overflow:auto; margin-top:8px; scrollbar-gutter:stable; }
  #poolCount { margin-top:8px; }
  .pool-toolbar { display:flex; gap:8px; }
  .pool-toolbar input { flex:1; }
  .pool-toolbar select { width:110px; }
  details > summary { cursor:pointer; color:var(--text); font-size:12px; }
  details[open] > summary { margin-bottom:12px; }
  .fold { margin:12px 0; padding-top:12px; border-top:1px solid var(--line); }
  .fold > summary { color:var(--muted); }
  .inspector-tabs { display:flex; gap:2px; margin-bottom:14px; padding-bottom:10px; border-bottom:1px solid var(--line); }
  .inspectbtn { flex:1; border-color:transparent; background:transparent; color:var(--muted); padding:6px; }
  .inspectbtn.active { background:#2b3e42; color:var(--accent); }
  .tool-section + .tool-section { margin-top:20px; padding-top:18px; border-top:1px solid var(--line); }
  .statline { font-size:12px; line-height:1.8; overflow-wrap:anywhere; }
  .ok { color:var(--accent); } .bad { color:var(--bad); } .warn { color:var(--gold); }
  .bar { background:var(--accent); height:8px; border-radius:3px; display:inline-block; max-width:100%; }
  .curve { display:flex; gap:8px; height:100px; align-items:end; margin:14px 0; }
  .curve-col { flex:1; text-align:center; color:var(--muted); min-width:0; font-size:11px; }
  .curve-col b { display:block; color:var(--text); font:13px Bahnschrift,Consolas,sans-serif; }
  .curve-bar { display:block; width:100%; max-width:32px; margin:4px auto; border-radius:4px 4px 0 0; background:linear-gradient(var(--accent),#3e8174); }
  .mana-row { display:flex; align-items:center; gap:8px; padding:4px 0; }
  .mana-symbol { display:inline-grid; place-content:center; width:22px; height:22px;
    border-radius:50%; border:1px solid var(--line); font:12px Bahnschrift,Consolas,sans-serif; }
  .mana-W { background:#e4d8b6; color:#282722; } .mana-U { background:#769fb8; color:#132431; }
  .mana-B { background:#4a4651; color:#e3dbe9; } .mana-R { background:#c57e68; color:#31180f; }
  .mana-G { background:#83a787; color:#102e17; }
  .card { background:var(--inset); border:1px solid var(--line); border-radius:8px;
    padding:10px 12px; margin:10px 0; font-size:12px; line-height:1.7; }
  .card h3 { color:var(--accent); margin:0 0 6px; }
  .verdict { font-weight:600; background:var(--inset); border-left:3px solid var(--accent); padding:10px 12px; margin:10px 0; }
  table.kv { width:100%; border-collapse:collapse; table-layout:fixed; font-size:12px; margin:6px 0; }
  table.kv td { border:1px solid var(--line); padding:4px 8px; vertical-align:top; overflow-wrap:anywhere; }
  .table-wrap { max-width:100%; overflow-x:auto; }
  .table-wrap table { width:100%; border-collapse:collapse; font-size:12px; }
  .table-wrap th,.table-wrap td { text-align:left; border-bottom:1px solid var(--line); padding:6px; }
  td.kvkey { color:var(--muted); width:32%; }
  ul.kvlist { margin:4px 0; padding-left:18px; }
  .feedback { margin-bottom:16px; padding:10px 14px; border:1px solid #7b514c; border-radius:8px;
    background:#32201f; color:var(--bad); display:flex; align-items:start; gap:10px; }
  #errors { flex:1; white-space:pre-wrap; overflow-wrap:anywhere; }
  #dismissError { min-height:28px; padding:2px 8px; }
  #warningPanel { border-color:#64533b; }
  #warnings { color:var(--gold); white-space:pre-wrap; font-size:12px; }
  .status-footer { color:var(--muted); font-size:11px; padding:4px 0; }
  .art-thumb { width:38px; height:53px; padding:0 !important; border:0; overflow:hidden; background:var(--inset); flex-shrink:0; }
  .art-thumb img { width:100%; height:100%; object-fit:cover; display:block; }
  .art-missing::after { content:'无卡图'; color:var(--muted); font-size:10px; }
  .zone-cards .row { position:relative; }
  .viewbtn.active { color:var(--accent); border-color:var(--accent); }
  .deck-grid .zone-cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(125px,1fr)); gap:10px; padding-top:8px; }
  .deck-grid .zone-cards .row { display:flex; flex-direction:column; align-items:stretch; border:1px solid var(--line); padding:8px; border-radius:8px; }
  .deck-grid .art-thumb { width:100%; height:auto; aspect-ratio:244/340; }
  .deck-grid .zone-cards .row > .tag { position:absolute; top:12px; left:12px; background:#10161edb; padding:2px 5px; border-radius:4px; }
  .deck-grid .card-actions { justify-content:space-between; }
  dialog { color:var(--text); background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:18px; max-width:94vw; }
  dialog::backdrop { background:#080b10c9; }
  dialog .panel-head { margin-bottom:12px; }
  #cardPreviewImage { display:block; max-height:75vh; max-width:80vw; }
  #exportPreviewImage { display:block; max-width:85vw; max-height:68vh; object-fit:contain; }
  .job-status { padding:10px 12px; border-left:2px solid var(--accent); background:var(--inset); margin:10px 0; font-size:12px; }
  .job-status:empty { display:none; }
  #taskStatus { color:var(--accent); font-size:12px; margin-bottom:14px; }
  #taskStatus:empty { display:none; }
  .claim-row { border-top:1px solid var(--line); padding:6px 0; margin-top:6px; font-size:12px; }
  @media (min-width:1201px) { .editor-column { position:sticky; top:18px; } }
  @media (max-width:1200px) {
    .workspace { grid-template-columns:minmax(250px,.75fr) minmax(340px,1.25fr); }
    .inspector-column { grid-column:1/-1; }
    .inspector-content { max-width:none; }
    #stats { display:grid; grid-template-columns:1fr 1fr; gap:6px 24px; }
    #zones { max-height:650px; }
  }
  @media (max-width:720px) {
    .topbar-inner { padding:16px; gap:14px; }
    .brand { flex:1; } h1 { font-size:16px; }
    .header-actions { margin:0; } .connection { display:none; }
    .tabs { order:3; width:100%; } .tabbtn { flex:1; }
    .shell { padding:16px; } .session-row { flex-wrap:wrap; }
    .overview { grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin-bottom:16px; }
    .metric { padding:10px 12px; } .metric strong { font-size:24px; }
    .workspace { grid-template-columns:minmax(0,1fr); gap:10px; }
    .editor-column { order:0; } .source-column { order:1; } .inspector-column { order:2; }
    .column-label b { display:none; }
    .inspector-column { grid-column:auto; }
    .panel { padding:14px; } #zones { max-height:520px; min-height:230px; }
    #stats { display:block; } .row button { min-height:36px; }
    .header-actions button { padding:6px 9px; }
    body.busy .connection,.connection.warn { display:block; position:fixed; bottom:16px; left:16px;
      z-index:5; background:var(--panel); padding:8px 12px; border:1px solid var(--line); border-radius:8px; }
  }
  @media (prefers-reduced-motion:no-preference) {
    .workspace { animation:arrive .3s ease-out; }
    @keyframes arrive { from { opacity:0; transform:translateY(6px); } to { opacity:1; transform:translateY(0); } }
  }
</style>
</head>
<body>
<header class="topbar"><div class="topbar-inner">
  <div class="brand"><span class="brand-mark" aria-hidden="true">MTG</span>
    <div><div class="eyebrow">DECK WORKBENCH</div><h1>MTG 套牌工作台</h1></div></div>
  <nav class="tabs" aria-label="组牌模式">
    <button class="tabbtn" data-mode="limited" id="tabLimited" type="button" aria-pressed="true">限制赛</button>
    <button class="tabbtn" data-mode="constructed" id="tabConstructed" type="button" aria-pressed="false">构筑</button>
  </nav>
  <div class="header-actions"><span class="connection" id="connection" role="status" aria-live="polite">正在连接</span>
    <button id="openImport" type="button">导入</button><button id="exportBtn" type="button">导出 TXT</button>
    <button id="imageBtn" type="button">导出图片</button></div>
</div></header>
<main class="shell">
  <div class="session-row"><div id="session">尚未导入牌表</div><div id="modeHint" class="mode-hint"></div></div>
  <div id="errorPanel" class="feedback" hidden><div id="errors" role="alert"></div>
    <button id="dismissError" type="button" aria-label="关闭错误提示">关闭</button></div>
  <div id="taskStatus" role="status" aria-live="polite"></div>
  <div id="imageReady" hidden><button id="showExportPreview">图片已生成，查看 / 下载 PNG</button></div>
  <div class="overview" aria-label="当前套牌概况">
    <div class="metric"><span>主牌 / 张</span><strong id="mainMetric">0</strong></div>
    <div class="metric"><span>备牌 / 张</span><strong id="sideMetric">0</strong></div>
    <div class="metric"><span>地牌 / 张</span><strong id="landMetric">0</strong></div>
    <div class="metric"><span>平均法术力值</span><strong id="cmcMetric">—</strong></div>
  </div>
  <div class="workspace">
    <aside class="column source-column" aria-label="导入与组牌">
      <div class="column-label"><b>01</b>准备与组牌</div>
      <details class="panel" id="deckImport">
        <summary>导入已有牌表</summary>
        <label class="field" for="decktext">牌表文本<textarea id="decktext" placeholder="Deck&#10;4 Card Name&#10;...&#10;&#10;Sideboard&#10;2 Card Name"></textarea></label>
        <div class="note">支持 MTGA 格式与中文分区名称，导入会替换当前牌表。</div>
        <div class="actions"><button id="importBtn" class="primary">导入牌表</button></div>
      </details>
      <section class="mode-panel" data-mode="limited">
        <div class="panel">
          <div class="panel-head"><h2>限制赛牌池</h2><span class="tag">卡牌来源</span></div>
          <details id="poolImport" open><summary>粘贴牌池</summary>
            <label class="field" for="pooltext">每行：数量 牌名<textarea id="pooltext" placeholder="1 Card Name&#10;2 Another Card Name"></textarea></label>
            <div class="form-grid"><label class="field full" for="srcname">来源（可选）<input id="srcname" type="text" placeholder="例如：本轮现开牌池"></label></div>
            <button id="poolBtn">导入牌池</button>
          </details>
          <div class="fold">
            <div class="pool-toolbar"><input id="poolSearch" type="search" placeholder="筛选牌名" aria-label="筛选牌池牌名">
              <select id="poolFilter" aria-label="筛选牌池分区"><option value="all">全部卡牌</option><option value="main">已入主牌</option><option value="sideboard">在备牌</option><option value="out">未入套</option></select></div>
            <div class="tag" id="poolCount"></div><div id="poolList"></div>
          </div>
        </div>
        <div class="panel">
          <div class="panel-head"><h2>自动组牌</h2><span class="tag">纯机器 · 限制赛</span></div>
          <div class="form-grid">
            <label class="field" for="seedColors">色组<select id="seedColors"></select></label>
            <label class="field" for="seedSize">主牌张数<select id="seedSize"><option value="41">41 张</option><option value="40">40 张</option></select></label>
            <label class="field full" for="setcode">系列代码（可选）<input id="setcode" type="text" placeholder="如 FRA，用于加载评分"></label>
          </div>
          <div class="note">只从导入牌池选牌，不调用 LLM。系列代码用于读取本地评分，影响选牌排序；缺失评分使用默认值。通常从 17 地 + 24 张其他牌开始，调整地数和 40/41 张需说明理由。</div>
          <div class="actions"><button id="seedBtn" class="primary">生成套牌</button></div>
          <div id="seedInfo" class="statline"></div>
          <details class="fold"><summary>对比色组与裁剪结果</summary><div id="seedPlans" class="statline"></div><div id="seedCuts" class="note"></div></details>
        </div>
      </section>
      <section class="panel mode-panel" data-mode="constructed" hidden>
        <div class="panel-head"><h2>构筑组牌</h2><span class="tag">候选 → 套牌</span></div>
        <label class="field" for="seednames">核心牌（逗号分隔，也可在下方指定数量）<input id="seednames" type="text" placeholder="输入希望保留的核心牌名"></label>
        <details class="fold"><summary>指定牌张数量与主备分区</summary><label class="field" for="seedConstraints">固定牌张（填写后优先使用此处）<textarea id="seedConstraints" placeholder="Deck&#10;4 Core Card&#10;&#10;Sideboard&#10;2 Side Card"></textarea></label><div class="note">主牌、备牌和行侣均按指定数量保留；其余卡位从候选补齐。</div></details>
        <div class="form-grid">
          <label class="field" for="ccFormat">赛制<input id="ccFormat" type="text" value="pioneer"></label>
          <label class="field" for="ccStrategy">策略<select id="ccStrategy"><option value="mid">中速</option><option value="aggro">快攻</option><option value="control">控制</option></select></label>
          <label class="field" for="ccPlatform">平台<select id="ccPlatform"><option value="arena">MTG Arena</option><option value="paper">实体牌</option><option value="mtgo">MTGO</option><option value="any">不限</option></select></label>
          <label class="check"><input id="ccBo3" type="checkbox">三局两胜（BO3）</label>
        </div>
        <details class="fold" open><summary>导入候选数据</summary>
          <label class="field" for="candtext">检索工具导出的 JSON 数组<textarea id="candtext" placeholder='[{"name":"Card Name",...}]'></textarea></label>
          <div class="note">使用工具检索的完整卡牌数据作为组牌候选。</div>
        </details>
        <button id="ccBtn" class="primary">构筑组牌</button><div id="ccInfo" class="statline"></div>
      </section>
    </aside>
    <section class="column editor-column" aria-label="当前牌表编辑区">
      <div class="column-label"><b>02</b>编辑当前套牌</div>
      <div class="panel editor">
        <div class="panel-head"><h2>当前牌表</h2><span class="tag" id="deckTotal">共 0 张</span></div>
        <div class="actions" style="margin:0 0 12px"><button class="viewbtn active" id="deckListBtn">列表</button><button class="viewbtn" id="deckGridBtn">卡图</button></div>
        <p class="editor-note">调整主备牌，或移除一张；每次操作都会更新统计。</p>
        <div id="zones"></div>
      </div>
      <details class="panel" id="warningPanel" hidden open><summary id="warningSummary">需要留意</summary><div id="warnings"></div></details>
      <div class="status-footer">当前会话保存在内存中；完成调整后请导出牌表。</div>
    </section>
    <aside class="column inspector-column" aria-label="统计、核验与助手">
      <div class="column-label"><b>03</b>检查与探索</div>
      <section class="panel"><div class="panel-head"><h2>曲线与法术力</h2><span class="tag">随牌表更新</span></div><div id="stats"></div></section>
      <section class="panel inspector-content">
        <nav class="inspector-tabs" aria-label="检查与探索工具">
          <button class="inspectbtn active" data-view="checks" aria-pressed="true">核验</button>
          <button class="inspectbtn" data-view="assistant" aria-pressed="false">助手</button>
          <button class="inspectbtn mode-panel" data-mode="constructed" data-view="explore" aria-pressed="false" hidden>候选</button>
        </nav>
        <div class="inspect-view" data-view="checks">
          <div class="tool-section"><h3>门禁体检</h3><div class="note" id="auditBasis">限制赛检查张数与导入牌池，不检查构筑合法性和轮替。</div>
            <div class="form-grid"><label class="field" id="auditFormatField" for="auditFormat">构筑赛制<input id="auditFormat" type="text" value="pioneer"></label>
              <label class="check"><input id="auditBo3" type="checkbox">BO3</label>
              <label class="check full"><input id="auditLimited" type="checkbox">限制赛口径（40 / 41 张）</label></div>
            <button id="auditBtn">运行体检</button><div id="auditProgress" class="job-status" aria-live="polite"></div><div id="auditBox" class="statline"></div>
          </div>
          <div class="tool-section"><h3>展开与版本评测</h3>
            <div class="note">评估起手和土地支付潜力，辅助比较构型。暂不模拟横置时序、加速、对手或胜率；未覆盖项会列出。</div>
            <div class="form-grid"><label class="field" for="evalFormat">评测赛制<select id="evalFormat"><option value="pioneer">Pioneer / Explorer</option><option value="standard">Standard</option><option value="historic">Historic</option><option value="timeless">Timeless</option><option value="limited">限制赛</option><option value="brawl">Brawl</option><option value="standard_brawl">Standard Brawl</option><option value="competitive_brawl">Competitive Brawl</option><option value="commander">Commander</option></select></label>
              <label class="field" for="evalRuns">抽样次数<input id="evalRuns" type="number" value="2000" min="1" max="5000"></label>
              <label class="field" for="evalTurns">观测回合<input id="evalTurns" type="number" value="5" min="1" max="8"></label>
              <label class="check"><input id="evalDraw" type="checkbox">第一回合抓牌</label>
              <label class="field full" for="evalTargets">关键咒语（每行一个英文名，留空自动选取）<textarea id="evalTargets" placeholder="Card Name"></textarea></label></div>
            <details class="fold"><summary>对比另一份牌表</summary><button id="evalBaselineBtn">保存当前牌表作对照</button><label class="field" for="evalBaseline">对照牌表（留空仅评测当前版本）<textarea id="evalBaseline" placeholder="可粘贴以前的完整牌表；不会替换当前牌表"></textarea></label></details>
            <details class="fold"><summary>离线牌面数据（可选）</summary><label class="field" for="evalCards">牌面快照<textarea id="evalCards" placeholder="Scryfall / mtg_tool search 的 JSON 数组"></textarea></label><div class="note">默认复用候选和牌池牌面，缺失时补查。提供快照后只用该数据；缺牌会明确报错。</div></details>
            <div class="actions"><button id="evalBtn">运行评测 / 对照</button><button id="evalDownloadBtn" disabled>下载评测结果</button></div>
            <div id="evalProgress" class="job-status" aria-live="polite"></div><div id="evalBox" class="statline"></div>
          </div>
          <div class="mode-panel" data-mode="constructed" hidden>
            <div class="tool-section"><h3>角色分布与缺口</h3><button id="rolesBtn">刷新角色</button><div id="rolesBox" class="statline"></div></div>
            <details class="fold"><summary>组合技 · Commander Spellbook</summary>
              <div class="form-grid"><label class="field" for="cbFormat">赛制<input id="cbFormat" type="text" value="pioneer"></label>
                <label class="field" for="cbPlatform">平台<select id="cbPlatform"><option value="arena">MTG Arena</option><option value="paper">实体牌</option><option value="mtgo">MTGO</option></select></label>
                <label class="field" for="cbLimit">查询条数<input id="cbLimit" type="number" min="1" value="20"></label></div>
              <div class="note">查询需要等待；主牌、换备与缺组件结果分开显示。</div>
              <div class="actions"><button id="combosBtn">查询组合技</button></div><div id="combosBox" class="statline"></div>
            </details>
            <details class="fold"><summary>套牌造价</summary><button id="costBtn">核算造价</button><div id="costBox" class="statline"></div></details>
          </div>
        </div>
        <div class="inspect-view" data-view="assistant" hidden>
          <div class="tool-section"><h3>Agent 助手</h3>
            <div id="agentConnection" class="job-status" aria-live="polite">接收端未连接</div>
            <div class="actions"><select id="agentBackend" hidden></select><button id="agentConnectBtn">连接 Agent</button><button id="agentDisconnectBtn" hidden>断开</button></div>
            <div class="note">连接一次后持续接收网页任务，自动领取、查证并回执。复用工作台专用会话与本机 Agent CLI 的登录和配置，待机不调用模型。</div>
            <div id="agentApproval" class="card" hidden><strong>Agent 操作需要批准</strong><div id="agentApprovalReason"></div>
              <div id="agentApprovalDetails" class="statline"></div><div class="actions"><button id="agentApproveBtn">允许本次</button><button id="agentDeclineBtn">拒绝</button></div></div>
            <div class="form-grid"><label class="field full" for="agentKind">希望获得什么帮助？<select id="agentKind"><option value="next_move">建议下一步</option><option value="explain">规则与配合解释</option><option value="novel_synergies">协同候选提案</option><option value="handoff">全流程体检</option></select></label>
              <label class="field full" for="agentNote">补充说明（可选）<textarea id="agentNote" placeholder="例如：希望保留核心配合，先改善前期曲线"></textarea></label></div>
            <details class="fold"><summary>高级请求设置</summary>
              <label class="field" for="agentTimeout">超时（秒）<input id="agentTimeout" type="number" min="1" value="300"></label>
              <div class="note">额外参数是交给 Agent 的上下文，不是模型参数或脚本选项。通常留空；上方补充说明会合并到 note。</div>
              <label class="field" for="agentPayload">额外上下文（JSON 对象）<textarea id="agentPayload" placeholder='{"budget":"尽量不消耗稀有野卡","keep_theme":true}'></textarea></label>
            </details>
            <button id="agentReqBtn" class="primary">提交请求</button>
            <div id="agentReqInfo" class="statline" aria-live="polite"></div><div id="agentResult" class="statline"></div><div id="bridgeStatus" class="note"></div><div id="claimList"></div>
          </div>
          <div class="tool-section"><h3>智能点评</h3><div class="note">直连工具：快速点评不调用查证工具；离线时保留机器统计。</div>
            <div class="actions"><button id="adviceBtn">获取点评</button></div><div id="adviceBox" class="statline"></div></div>
        </div>
        <div class="inspect-view" data-view="explore" hidden>
          <div class="tool-section"><h3>卡牌检索</h3>
            <div class="form-grid"><label class="field full" for="findQ">Scryfall 查询式<input id="findQ" type="text" placeholder="f:pioneer t:creature cmc<=2"></label>
              <label class="field" for="findLimit">条数<input id="findLimit" type="number" min="1" value="20"></label></div>
            <button id="findBtn">检索</button><div id="findBox" class="statline"></div>
          </div>
          <div class="tool-section"><h3>Agent 回写候选</h3><div class="note">候选来自实际检索；未核验的牌名会明确标注。</div><div id="avenueList" class="statline"></div>
            <details class="fold"><summary>手动新增探索方向</summary>
              <div class="form-grid"><label class="field full" for="avTitle">标题<input id="avTitle" type="text"></label><label class="field full" for="avNote">备注<input id="avNote" type="text"></label>
                <label class="field full" for="avCands">候选：每行「牌名 | 理由」<textarea id="avCands"></textarea></label></div>
              <button id="avenueBtn">新增候选</button>
            </details>
          </div>
        </div>
      </section>
    </aside>
  </div>
</main>
<dialog id="cardPreview"><div class="panel-head"><strong id="cardPreviewTitle"></strong><button id="closeCardPreview">关闭</button></div><img id="cardPreviewImage" alt="卡牌正面"></dialog>
<dialog id="exportPreview"><div class="panel-head"><strong>牌表图片</strong><button id="closeExportPreview">关闭</button></div>
  <div id="imageProgress" class="job-status" aria-live="polite"></div><img id="exportPreviewImage" alt="当前牌表图片" hidden>
  <div class="actions"><a id="imageDownload" download="deck.png" hidden>下载 PNG</a></div>
</dialog>
<script>
const ZONES = ['commander', 'companion', 'main', 'sideboard'];
const ZH = {commander:'指挥官', companion:'伴侣', main:'主牌', sideboard:'备牌'};
const COLORS = 'WUBRG';
let lastSnap = null;
let ticking = false;
let busy = false;
let agentPending = false;
let lastRender = '';
let currentMode = 'limited';
const runningJobs = {};
let evaluationResult = null;
function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
                                  .replace(/>/g,'&gt;').replace(/"/g,'&quot;')
                                  .replace(/'/g,'&#39;'); }
function formatTime(value) {
  const date = new Date(value);
  return isNaN(date.getTime()) ? String(value || '') : date.toLocaleString('zh-CN',
    {timeZone:'Asia/Hong_Kong', hour12:false});
}
function showErrors(msg) {
  document.getElementById('errors').textContent = msg || '';
  document.getElementById('errorPanel').hidden = !msg;
}
function openImport() {
  const box = document.getElementById('deckImport');
  box.open = true;
  box.scrollIntoView({block:'center'});
  document.getElementById('decktext').focus({preventScroll:true});
}
function setInspector(view) {
  for (const panel of document.querySelectorAll('.inspect-view'))
    panel.hidden = panel.dataset.view !== view;
  for (const button of document.querySelectorAll('.inspectbtn')) {
    const active = button.dataset.view === view;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  }
}
function cardButton(action, name, section, to, text) {
  return '<button type="button" data-card-action="' + action
    + '" data-name="' + esc(name) + '" data-section="' + section
    + '" data-to="' + (to || '') + '" aria-label="' + esc(name + '：' + text)
    + '">' + text + '</button>';
}
function artThumb(name) {
  return '<button class="art-thumb" type="button" data-card-preview="' + esc(name)
    + '" aria-label="查看 ' + esc(name) + ' 的卡图"><img loading="lazy" alt="" src="/api/card-image?name='
    + encodeURIComponent(name) + '" onerror="this.hidden=true;this.parentElement.classList.add(\\'art-missing\\')"></button>';
}
function setDeckView(view) {
  document.body.classList.toggle('deck-grid', view === 'grid');
  document.getElementById('deckGridBtn').classList.toggle('active', view === 'grid');
  document.getElementById('deckListBtn').classList.toggle('active', view !== 'grid');
  try { localStorage.setItem('workbench-card-view', view); } catch (e) {}
}
function renderJobStatus() {
  document.getElementById('taskStatus').textContent = Object.values(runningJobs)
    .filter(Boolean).map(job => ({audit:'体检', image:'图片输出', evaluation:'展开评测'}[job.kind] || job.kind) + '：' + job.message
      + ' · ' + job.elapsed_sec + ' 秒').join('；');
}
async function followJob(id, kind) {
  const button = document.getElementById({audit:'auditBtn', image:'imageBtn', evaluation:'evalBtn'}[kind]);
  const box = document.getElementById({audit:'auditProgress', image:'imageProgress', evaluation:'evalProgress'}[kind]);
  try {
    for (;;) {
      const job = await fetchJSON('/api/jobs/' + encodeURIComponent(id));
      runningJobs[kind] = job;
      button.disabled = true;
      box.textContent = job.message + (job.total != null ? ' · 已完成 ' + job.current + ' / ' + job.total : '')
        + ' · ' + job.elapsed_sec + ' 秒';
      renderJobStatus();
      if (job.status === 'error') throw new Error((job.error || {}).message || '任务失败');
      if (job.status === 'done') {
        runningJobs[kind] = null;
        await tick();
        if (kind === 'audit') renderAudit({checks:{audit:{status:'ok', result:job.result}}});
        else if (kind === 'evaluation') {
          renderEvaluation({checks:{evaluation:{status:'ok', result:job.result}}});
          box.textContent = job.result.stale ? '任务期间牌表或牌面已变更，此结果仅供历史对照。' : '评测完成';
        }
        else {
          const img = document.getElementById('exportPreviewImage');
          const link = document.getElementById('imageDownload');
          img.src = job.result.download_url; img.hidden = false;
          link.href = job.result.download_url; link.hidden = false;
          document.getElementById('imageReady').hidden = false;
          box.textContent = 'PNG 已生成' + (job.result.stale ? '（生成的是任务开始时的牌表）' : '')
            + ((job.result.missing_images || []).length ? '；缺失卡图将以占位显示：' + job.result.missing_images.join('、') : '');
        }
        showErrors('');
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  } catch (e) { box.textContent = '任务失败：' + e.message; showErrors(e.message); }
  finally {
    runningJobs[kind] = null;
    try { localStorage.removeItem('workbench-job-' + kind); } catch (e) {}
    updateDisabled(); renderJobStatus();
  }
}
async function startJob(kind, url, body) {
  if (runningJobs[kind]) return;
  runningJobs[kind] = {kind:kind, message:'准备任务', elapsed_sec:0};
  updateDisabled(); renderJobStatus();
  try {
    const job = await postJSON(url, body);
    try { localStorage.setItem('workbench-job-' + kind, job.job_id); } catch (e) {}
    await followJob(job.job_id, kind);
  } catch (e) { runningJobs[kind] = null; updateDisabled(); renderJobStatus(); showErrors(e.message); }
}
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
  if (g.status === 'fail') return '<span class="bad">● 未通过</span>';
  return '<span class="warn">● 未知</span>';
}
function pct(v) { return v == null ? '—' : (v * 100).toFixed(1) + '%'; }
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
  const main = (snap.sections.main || []).some(c => c.name === name);
  const side = (snap.sections.sideboard || []).some(c => c.name === name);
  return main && side ? 'both' : main ? 'main' : side ? 'sideboard' : 'out';
}
function renderPool(snap) {
  const filter = document.getElementById('poolFilter').value;
  const search = document.getElementById('poolSearch').value.trim().toLowerCase();
  const entries = (snap.pool && snap.pool.entries) || [];
  let html = '', shown = 0;
  for (const e of entries) {
    const st = cardStatus(e.name, snap);
    if (filter !== 'all' && st !== filter && !(st === 'both' && filter !== 'out')) continue;
    if (search && !e.name.toLowerCase().includes(search)) continue;
    shown++;
    const stTxt = {main:'<span class="ok">主</span>',
                   sideboard:'<span class="warn">备</span>',
                   both:'<span class="ok">主/备</span>',
                   out:'<span class="ts">裁</span>'}[st];
    html += '<div class="row"><span class="tag">' + e.qty + '×</span>'
      + '<span class="nm">' + esc(e.name)
      + ' <span class="ts">' + (e.cmc != null ? e.cmc + '费' : '') + '</span></span>'
      + stTxt
      + '<span class="card-actions">' + cardButton('add', e.name, 'main', '', '主+1')
      + cardButton('add', e.name, 'sideboard', '', '备+1') + '</span></div>';
  }
  document.getElementById('poolList').innerHTML =
    shown ? html : '<div class="note">' + (entries.length ? '没有匹配的卡牌。' : '导入牌池后，可在这里逐张加入主牌或备牌。') + '</div>';
  const c = (snap.pool && snap.pool.counts) || {};
  document.getElementById('poolCount').textContent =
    (c.names || 0) + ' 种 / ' + (c.cards || 0) + ' 张'
    + (c.unresolved_names ? '，缺少数据 ' + c.unresolved_names + ' 种' : '');
}
function renderDeck(snap) {
  document.getElementById('deckTotal').textContent = '共 ' + snap.total + ' 张';
  if (!snap.total) {
    document.getElementById('zones').innerHTML = '<div class="empty-state">'
      + '<span class="empty-glyph" aria-hidden="true">[ + ]</span><strong>从一份牌表开始</strong>'
      + '<span class="note">导入已有牌表，或从牌池生成套牌。<br>主牌和备牌将在这里显示。</span>'
      + '<div class="actions"><button type="button" data-open-import>导入已有牌表</button></div></div>';
    return;
  }
  let html = '';
  for (const z of ZONES) {
    const items = (snap.sections && snap.sections[z]) || [];
    const count = (snap.counts && snap.counts[z]) || 0;
    if (z === 'commander' || z === 'companion') {
      if (!items.length) continue;
      html += '<div class="zone"><div class="zone-head"><b>' + ZH[z] + '</b><span class="tag">' + count + ' 张</span></div><div class="zone-cards">'
        + items.map(c => '<div class="row">' + artThumb(c.name) + '<span class="tag">' + c.qty + '×</span><span class="nm">' + esc(c.name) + '</span></div>').join('')
        + '</div></div>';
      continue;
    }
    const btns = c => '<span class="card-actions">'
      + cardButton('move', c.name, z, z === 'main' ? 'sideboard' : 'main', z === 'main' ? '入备' : '入主')
      + cardButton('remove', c.name, z, '', '-1') + '</span>';
    html += '<div class="zone"><div class="zone-head"><b>' + ZH[z] + '</b><span class="tag">' + count + ' 张</span></div><div class="zone-cards">'
      + items.map(c => '<div class="row">' + artThumb(c.name) + '<span class="tag">' + c.qty + '×</span>'
        + '<span class="nm">' + esc(c.name) + '</span>' + btns(c) + '</div>').join('')
      + (items.length ? '' : '<div class="note">暂无' + ZH[z] + '</div>') + '</div></div>';
  }
  document.getElementById('zones').innerHTML = html;
}
function renderStats(snap) {
  const s = snap.stats || {};
  const counts = snap.counts || {};
  document.getElementById('mainMetric').textContent = counts.main || 0;
  document.getElementById('sideMetric').textContent = counts.sideboard || 0;
  document.getElementById('landMetric').textContent = s.lands || 0;
  const curve = s.curve || {};
  const known = Object.keys(curve).length > 0;
  document.getElementById('cmcMetric').textContent = known ? s.average_cmc : '—';
  if (!s.main) {
    document.getElementById('stats').innerHTML = '<div class="note">加入主牌后显示费用曲线、法术力来源与地数检查。</div>';
    return;
  }
  const lc = s.land_check || {};
  const p3 = (lc.p3 != null) ? (lc.p3 * 100).toFixed(1) + '%' : '—';
  const p5 = (lc.p5 != null) ? (lc.p5 * 100).toFixed(1) + '%' : '—';
  let html = '<div><div class="statline">地 ' + (s.lands || 0) + ' / 非地 ' + (s.nonlands || 0)
    + (known ? ' · ' + esc(s.curve_label || '') : '') + '</div>';
  // deck_core groups costs <=1 and >=5 into the first/last buckets.
  const slots = ['1','2','3','4','5'];
  const max = Math.max(1, ...Object.values(curve));
  html += known ? '<div class="curve" aria-label="法术力曲线">' + slots.map(k =>
    '<div class="curve-col"><b>' + (curve[k] || 0) + '</b><span class="curve-bar" style="height:'
    + Math.max(2, (curve[k] || 0) / max * 60) + 'px"></span>' + (k === '1' ? '0–1' : k === '5' ? '5+' : k) + '费</div>'
    ).join('') + '</div>' : '<div class="note">暂无可统计的费用数据。</div>';
  html += '</div><div>';
  const pips = s.pips || {}, sources = s.mana_sources || {};
  const colors = [...COLORS].filter(c => pips[c] || sources[c]);
  html += colors.length ? '<div class="note">颜色 · 费用符号 / 地牌来源</div>' + colors.map(c =>
    '<div class="mana-row"><span class="mana-symbol mana-' + c + '">' + c
    + '</span><span>' + (pips[c] || 0) + ' 符号 / ' + (sources[c] || 0) + ' 来源</span></div>').join('')
    : '<div class="note">暂无有色法术力数据。</div>';
  html += '<div class="card">地数检查 <span class="' + (lc.ok ? 'ok">通过' : 'warn">需要留意')
    + '</span><br><span class="note">按 ' + (lc.deck_size || 40) + ' 张 / ' + (lc.lands || 0)
    + ' 地计算</span><br>第 3 回合 ≥ 2 地：' + p3 + '<br>第 5 回合 ≥ 4 地：' + p5 + '</div>';
  if (s.warnings && s.warnings.length)
    html += '<div class="note">' + s.warnings.map(esc).join('<br>') + '</div>';
  document.getElementById('stats').innerHTML = html + '</div>';
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
    + (seed.depth_note ? '（' + esc(seed.depth_note) + '，评级深度）' : '')
    + '；平均 CMC ' + seed.average_cmc + '；地 ' + Object.keys(seed.lands).map(c => esc(c) + ' ' + seed.lands[c]).join(' / ')
    + '；' + (seed.valid ? '<span class="ok">门禁通过</span>'
                         : '<span class="bad">门禁失败: ' + esc(seed.violations.join('；')) + '</span>');
  const ratings = seed.ratings || {};
  if (ratings.total != null)
    document.getElementById('seedInfo').innerHTML += '<div class="note">评分覆盖 ' + ratings.covered + ' / ' + ratings.total
      + ' 个非基本地牌名' + (ratings.source ? ' · 来源 ' + esc(ratings.source) : '')
      + (ratings.generated ? ' · ' + esc(ratings.generated) : '') + '</div>'
      + (ratings.preview_count ? '<div class="note">其中 ' + ratings.preview_count + ' 个预览期 / 低置信评分，仅作为选牌参考。</div>' : '')
      + (ratings.missing.length ? '<details class="fold"><summary>缺失评分：' + ratings.missing.length + ' 个牌名使用默认值</summary>'
        + ratings.missing.map(esc).join('、') + '</details>' : '');
  if (seed.stale) document.getElementById('seedInfo').innerHTML += '<div class="warn">此为生成时方案，当前牌表已手动调整。</div>';
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
  if ((r.selections || []).length)
    box.innerHTML += '<details class="fold"><summary>逐牌入选依据（启发式）</summary>'
      + r.selections.map(s => '<div><strong>' + s.qty + ' × ' + esc(s.name) + '</strong> · '
        + esc(s.reason) + '</div>').join('') + '</details>';
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
    box.innerHTML = '<div class="card"><span class="bad">造价不可用: '
      + truncBlock((slot.error && slot.error.message) || '', 120, 5) + '</span></div>';
    return;
  }
  const r = slot.result;
  const b = r.budget || {};
  let html = '<div class="card">签名 <b>' + esc(r.signature || '?') + '</b>　预算 '
    + (b.ok ? '<span class="ok">' : '<span class="bad">') + esc(b.tier || '?')
    + '</span><br>PP核心 ' + (r.packs && r.packs.core != null ? r.packs.core : '?')
    + ' 包；PP全量 ' + (r.packs && r.packs.all != null ? r.packs.all : '?')
    + ' 包；惩罚 ' + (r.packs && r.packs.penalty != null ? r.packs.penalty : '?') + '×';
  if ((r.unrecognized || []).length)
    html += '<br><span class="warn">deck_cost 未识别: '
          + r.unrecognized.map(esc).join('、') + '</span>';
  html += '</div>';
  box.innerHTML = html;
}
// ---------------- 结构化结果渲染器（输入 JSON，输出 HTML 字符串，绝不倾倒原始 JSON） ----------------
const KEY_ZH = {action:'操作', detail:'详情', evidence:'依据', result:'结果',
  message:'结论', candidates:'候选', name:'名称', reason:'理由', how:'做法',
  deck_profile:'牌表概况', roles:'角色分布', recommendation:'主要建议',
  next_moves:'下一步建议', alternatives:'备选方案', colors:'色组',
  strategy:'策略', deck_size:'牌张数', average_cmc:'平均 CMC', lands:'地配置',
  land_check:'地检', ok:'通过', violations:'违规', cuts:'被裁',
  plans:'枚举方案', depth_ok:'深度达标', valid:'合法', warnings:'警告',
  sources:'来源', source_url:'来源链接', module:'模块', deficit:'缺口',
  have:'现有', want:'目标', quantity:'数量', cards:'卡牌', note:'备注',
  title:'标题', agent:'Agent', status:'状态', kind:'类型', request_id:'请求号',
  completed_at:'完成时间', queued_at:'入队时间', payload:'补充说明',
  timeout_sec:'超时(秒)', p3:'3回合≥2地', p5:'5回合≥4地', curve:'曲线',
  curve_label:'曲线评价', mana_sources:'法术力来源', pips:'法术力符号',
  main:'主牌', sideboard:'备牌', total:'合计', cmc:'法术力费用',
  type_line:'类型行', popularity:'人气', produces:'产出', components:'组件',
  description:'描述', overview:'概况', summary:'摘要', advice:'点评',
  model:'模型', offline_reason:'离线原因', machine_fallback:'机器兜底',
  signature:'签名', budget:'预算', packs:'卡包折算', stats:'统计',
  unrecognized:'未识别', group_counts:'分类计数', buckets:'分类',
  rotating_cards:'将退卡牌', basis:'基准', distribution:'分布', gaps:'缺口',
  unknown:'未知', checked_at:'核验时间', format:'赛制', limited:'限制赛',
  bo3:'BO3', platform:'平台', seeds:'种子', query:'查询式',
  returned:'返回条数', total_cards:'总条数', url:'链接', id:'编号',
  focused:'焦点', created_at:'创建时间', unverified_card_names:'候选未核验',
  report:'报告', modules:'模块', commander:'指挥官', nonbasic_lands:'非基本地',
  depth_note:'深度说明', score:'评分', playable_count:'可打张数',
  imported_at:'导入时间', source_name:'来源', import_seq:'导入序号',
  skip:'跳过'};
const VAL_ZH = {pass:'通过', fail:'未通过', unknown:'未知', ok:'正常',
  error:'出错', pending:'等待中', offline:'离线', queued:'已入队',
  done:'已完成', in_flight:'处理中'};
function zhKey(k) { return KEY_ZH[k] || k; }
function toggleLong(a) {
  const s = a.nextElementSibling;
  if (!s) return;
  const show = s.style.display === 'none';
  s.style.display = show ? '' : 'none';
  a.textContent = show ? '收起' : '展开';
}
function truncStr(s, n) {
  s = String(s);
  if (s.length <= n) return esc(s);
  return esc(s.slice(0, n)) + '<span class="tag">…</span>'
    + '<a href="#" onclick="toggleLong(this);return false;">展开</a>'
    + '<span class="long" style="display:none">' + esc(s) + '</span>';
}
function truncBlock(text, perLine, maxLines) {
  const lines = String(text).split(/\\n|；/).map(x => x.trim()).filter(Boolean);
  if (!lines.length) return '<span class="ts">—</span>';
  const shown = lines.slice(0, maxLines).map(x => truncStr(x, perLine));
  let html = shown.join('<br>');
  if (lines.length > maxLines)
    html += ' <a href="#" onclick="toggleLong(this);return false;">展开（共 '
      + lines.length + ' 行）</a><span class="long" style="display:none">'
      + lines.map(esc).join('<br>') + '</span>';
  return html;
}
function renderValue(v, depth) {
  if (v === null || v === undefined) return '<span class="ts">—</span>';
  if (typeof v === 'boolean')
    return v ? '<span class="ok">是</span>' : '<span class="bad">否</span>';
  if (typeof v === 'number') return String(v);
  if (typeof v === 'string') {
    if (VAL_ZH[v]) return VAL_ZH[v];
    return truncStr(v, 200);
  }
  if (Array.isArray(v)) {
    if (!v.length) return '<span class="ts">（空）</span>';
    return '<ul class="kvlist">'
      + v.map(item => '<li>' + renderValue(item, depth + 1) + '</li>').join('')
      + '</ul>';
  }
  const keys = Object.keys(v);
  if (!keys.length) return '<span class="ts">（空）</span>';
  let rows = '';
  for (const k of keys)
    rows += '<tr><td class="kvkey">' + esc(zhKey(k)) + '</td><td>'
          + renderValue(v[k], depth + 1) + '</td></tr>';
  return '<table class="kv">' + rows + '</table>';
}
function renderDeckProfile(p) {
  let html = '<div class="card"><h3>牌表概况</h3><div class="statline">';
  const bits = [];
  if (p.colors) bits.push('色组 <b>' + esc((p.colors || []).join('')) + '</b>');
  if (p.strategy) bits.push('策略 ' + esc(p.strategy));
  if (p.deck_size != null) bits.push(p.deck_size + ' 张');
  if (p.average_cmc != null) bits.push('平均 CMC ' + p.average_cmc);
  if (p.lands) bits.push('地 ' + renderValue(p.lands, 1));
  html += bits.join('　') + '</div>';
  if (p.land_check) {
    const lc = p.land_check;
    html += '<div class="statline">地检（' + (lc.deck_size || '?') + ' 张口径，'
      + (lc.lands != null ? lc.lands : '?') + ' 地）：3回合≥2地 ' + pct(lc.p3)
      + '，5回合≥4地 ' + pct(lc.p5) + '，'
      + (lc.ok ? '<span class="ok">通过</span>'
               : '<span class="bad">未通过</span>') + '</div>';
  }
  const rest = {};
  for (const k in p)
    if (['colors','strategy','deck_size','average_cmc','lands','land_check'].indexOf(k) < 0)
      rest[k] = p[k];
  if (Object.keys(rest).length) html += renderValue(rest, 1);
  return html + '</div>';
}
function renderMoveCard(m, i) {
  if (m === null || m === undefined) return '';
  if (typeof m === 'string')
    return '<div class="card"><b>' + (i + 1) + '.</b> ' + truncStr(m, 300) + '</div>';
  let html = '<div class="card"><h3>建议 ' + (i + 1)
    + (m.action ? '：' + esc(m.action) : '') + '</h3>';
  if (m.how) html += '<div>' + truncStr(m.how, 400) + '</div>';
  if (Array.isArray(m.evidence) && m.evidence.length)
    html += '<div class="note">依据</div><ul class="kvlist">'
      + m.evidence.map(e => '<li>' + renderValue(e, 1) + '</li>').join('')
      + '</ul>';
  const rest = {};
  for (const k in m)
    if (['action','how','evidence'].indexOf(k) < 0) rest[k] = m[k];
  if (Object.keys(rest).length) html += renderValue(rest, 1);
  return html + '</div>';
}
function renderAgentPayload(d) {
  let html = '';
  if (d.message) html += '<div class="verdict">' + truncStr(d.message, 500) + '</div>';
  const r = d.result;
  if (r && typeof r === 'object' && !Array.isArray(r)) {
    const used = {};
    if (r.deck_profile) { html += renderDeckProfile(r.deck_profile); used.deck_profile = 1; }
    if (r.roles) {
      html += '<div class="card"><h3>角色分布</h3>' + renderValue(r.roles, 1) + '</div>';
      used.roles = 1;
    }
    const moves = [];
    if (Array.isArray(r.next_moves)) moves.push.apply(moves, r.next_moves);
    if (r.recommendation) moves.push(r.recommendation);
    if (moves.length)
      html += '<div class="card"><h3>建议</h3>'
            + moves.map(renderMoveCard).join('') + '</div>';
    if (Array.isArray(r.alternatives) && r.alternatives.length)
      html += '<div class="card"><h3>备选方案</h3>'
            + r.alternatives.map(renderMoveCard).join('') + '</div>';
    const rest = {};
    for (const k in r)
      if (!used[k] && ['next_moves','recommendation','alternatives'].indexOf(k) < 0)
        rest[k] = r[k];
    if (Object.keys(rest).length) html += renderValue(rest, 0);
  } else if (r !== null && r !== undefined) {
    html += renderValue(r, 0);
  }
  if (!html) html = '<span class="ts">（无结果内容）</span>';
  return html;
}
function renderAudit(snap) {
  const slot = snap.checks && snap.checks.audit;
  const box = document.getElementById('auditBox');
  if (!slot) { box.textContent = '—'; return; }
  if (slot.status === 'error') {
    box.innerHTML = '<div class="card"><span class="bad">门禁不可用: '
      + truncBlock((slot.error && slot.error.message) || '', 120, 5) + '</span></div>';
    return;
  }
  const r = slot.result;
  if (r.scope === 'limited') {
    let html = '<div class="card">限制赛体检 ' + (r.ok === true ? '<span class="ok">通过</span>'
      : r.ok === false ? '<span class="bad">未通过</span>' : '<span class="warn">待核验</span>')
      + '<br>40/41 张检查 ' + gateHtml(r.validate) + '<br>牌池数量检查 ' + gateHtml(r.pool)
      + '<div class="note">' + esc((r.pool || {}).basis || '') + '</div>';
    for (const gate of [r.validate || {}, r.pool || {}]) {
      html += (gate.violations || []).map(v => '<div class="bad">' + esc(v) + '</div>').join('');
      html += (gate.unknown || []).map(v => '<div class="warn">' + esc(v) + '</div>').join('');
    }
    html += '<div class="note">不检查构筑赛合法性或 Standard 轮替。通过表示张数与当前导入牌池一致，不代表套牌强度。</div>';
    if (r.stale) html += '<div class="warn">牌表或牌池在检查期间已变更，请重新体检。</div>';
    box.innerHTML = html + '</div>';
    return;
  }
  const overall = r.ok === true ? '<span class="ok">● 全部通过</span>'
    : r.ok === false ? '<span class="bad">● 有门禁未通过</span>'
                     : '<span class="warn">● 有门禁未知（≠通过）</span>';
  let html = overall + '　张数与合法性 ' + gateHtml(r.validate);
  if (r.validate && r.validate.violations && r.validate.violations.length)
    html += '<ul class="kvlist">'
      + r.validate.violations.map(v => '<li class="bad">' + truncStr(v, 120) + '</li>').join('')
      + '</ul>';
  html += r.rotation && r.rotation.status === 'not_applicable'
    ? '<div class="note">' + esc(r.rotation.detail) + '</div>' : '<br>轮替存活 ' + gateHtml(r.rotation);
  if (r.rotation && r.rotation.detail) html += '<br>' + truncBlock(r.rotation.detail, 120, 5);
  if (r.rotation && r.rotation.error)
    html += ' <span class="warn">' + truncBlock(r.rotation.error, 120, 5) + '</span>';
  if (r.validate && r.validate.error)
    html += ' <span class="warn">' + truncBlock(r.validate.error, 120, 5) + '</span>';
  if (r.stale) html += '<div class="warn">检查期间牌表已变更，请重新体检。</div>';
  box.innerHTML = html;
}
function renderEvaluation(snap) {
  const slot = snap.checks && snap.checks.evaluation;
  const box = document.getElementById('evalBox');
  evaluationResult = slot && slot.result;
  document.getElementById('evalDownloadBtn').disabled = !evaluationResult;
  if (!evaluationResult) { box.textContent = '尚未评测'; return; }
  const result = evaluationResult;
  const current = result.after || result;
  const pct = v => v == null ? '未知' : (v * 100).toFixed(1) + '%';
  let html = '<div class="card"><strong>' + (result.before ? '版本对照' : '当前牌表评测') + '</strong> · '
    + (result.status === 'partial' ? '<span class="warn">有未覆盖项</span>' : '选定模型范围内完成');
  if (result.stale) html += '<div class="warn">结果已过期，请按当前牌表重新评测。</div>';
  html += '<div>牌库 ' + current.counts.main + ' 张 · 地 ' + current.counts.lands + ' 张 · 策略结束后可留起手 '
    + pct(current.opening.keepable.probability) + '</div><div class="note">'
    + current.settings.runs + ' 次抽样；' + (current.settings.on_draw ? '首回合抓牌' : '首回合不抓牌')
    + '；免费调度 ' + current.settings.free_mulligans + ' 次。区间只描述抽样误差。</div>';
  html += '<div class="table-wrap"><table><thead><tr><th>关键咒语</th><th>回合</th><th>土地支付潜力</th><th>抽到且可支付</th></tr></thead><tbody>';
  for (const goal of current.goals) {
    if (goal.unsupported) html += '<tr><td>' + esc(goal.name) + '</td><td colspan="3">未覆盖：' + esc(goal.unsupported) + '</td></tr>';
    for (const row of goal.by_turn) {
      const interval = row.mana_potential.ci95 || [];
      html += '<tr><td>' + esc(goal.name) + '</td><td>' + row.turn + '</td><td>' + pct(row.mana_potential.probability)
        + '<div class="note">95%区间 ' + interval.map(pct).join('–') + '</div></td><td>' + pct(row.seen_and_mana.probability) + '</td></tr>';
    }
  }
  html += '</tbody></table></div>';
  if (result.before) {
    html += '<h4>当前减去对照（最后观测回合）</h4>';
    for (const row of result.deltas.filter(d => d.turn === current.settings.turns))
      html += '<div>' + esc(row.name) + '：土地支付潜力 ' + (row.mana_potential_delta >= 0 ? '+' : '')
        + (row.mana_potential_delta * 100).toFixed(1) + ' 个百分点</div>';
    html += '<div class="note">描述性差值，不自动判断显著性或哪个版本更强。</div>';
    const only = (result.targets_only_before || []).concat(result.targets_only_after || []);
    if (only.length) html += '<div class="warn">仅一版评测的目标：' + only.map(esc).join('、') + '</div>';
  }
  for (const [label, report] of result.before ? [['对照', result.before], ['当前', current]] : [['当前', current]]) {
    for (const item of report.excluded_sources)
      html += '<div class="warn">' + label + '未覆盖色源：' + esc(item.name) + ' · ' + esc(item.reason) + '</div>';
    if (report.unmodeled_modal_lands.length)
      html += '<div class="warn">' + label + '未覆盖双面地选择：' + report.unmodeled_modal_lands.map(esc).join('、') + '</div>';
  }
  html += '<div class="note">忽略横置时序、下地顺序、生命支付和非地加速。不是准时施放率或胜率，也不复刻BO1起手平滑。</div>';
  box.innerHTML = html + '</div>';
}
function renderBridge(snap) {
  const b = snap.bridges || {};
  const receiver = b.receiver || {status:'offline',message:'接收端未连接'};
  const statesText = {offline:'未连接',connecting:'连接中',idle:'在线 · 等待任务',busy:'在线 · 处理中',approval:'在线 · 等待批准',stopping:'正在断开',error:'连接失败'};
  document.getElementById('agentConnection').textContent = (statesText[receiver.status] || receiver.status)
    + ' · ' + (receiver.message || '') + (receiver.elapsed_sec ? ' · ' + receiver.elapsed_sec + ' 秒' : '')
    + (receiver.thread_id ? ' · 会话 ' + receiver.thread_id : '')
    + (receiver.model ? ' · ' + receiver.model : '');
  const connected = ['connecting','idle','busy','approval','stopping'].includes(receiver.status);
  const connectBtn = document.getElementById('agentConnectBtn');
  connectBtn.hidden = connected;
  connectBtn.textContent = '连接 ' + (receiver.backend_label || 'Agent');
  const backendSel = document.getElementById('agentBackend');
  const backends = receiver.backends || [];
  backendSel.hidden = connected || backends.length < 2;
  if (backends.length > 1) {
    const current = Array.from(backendSel.options).map(o => o.value).join(',');
    const wanted = backends.map(b => b.name).join(',');
    if (current !== wanted) {
      backendSel.innerHTML = '';
      for (const b of backends) backendSel.add(new Option(b.label, b.name));
    }
    backendSel.value = receiver.backend || backends[0].name;
    connectBtn.textContent = '连接 ' + ((backends.find(b => b.name === backendSel.value) || {}).label || 'Agent');
    backendSel.onchange = () => { connectBtn.textContent = '连接 ' +
      ((backends.find(b => b.name === backendSel.value) || {}).label || 'Agent'); };
  }
  document.getElementById('agentDisconnectBtn').hidden = !connected;
  document.getElementById('agentDisconnectBtn').disabled = receiver.status === 'stopping';
  const approval = receiver.approval;
  document.getElementById('agentApproval').hidden = !approval;
  if (approval) {
    document.getElementById('agentApproval').dataset.id = approval.id;
    document.getElementById('agentApprovalReason').textContent = approval.reason;
    document.getElementById('agentApprovalDetails').textContent = approval.detail || '';
  }
  let txt = '等待 ' + (b.queue_depth || 0) + ' / 处理中 '
    + (b.in_flight || 0) + ' / 已完成 ' + (b.results_ready || 0);
  const inflight = b.in_flight_requests || [];
  if (inflight.length)
    txt += '；在途：' + inflight.map(x => x.request_id
      + (x.claimed_by ? '（' + x.claimed_by + ' 处理中）' : '（待认领）')).join('、');
  document.getElementById('bridgeStatus').textContent = txt;
  const states = {queued:'待领取', in_flight:'处理中', done:'已回执'};
  document.getElementById('claimList').innerHTML = (b.recent_requests || []).map(r =>
    '<div class="claim-row"><b>' + esc(r.request_id) + '</b> · ' + (states[r.state] || esc(r.state))
    + ' · ' + (r.claimed_by ? esc(r.claimed_by) + ' 已显式认领' : '尚无 Agent 认领')
    + (r.state === 'done' ? ' <button data-receipt="' + esc(r.request_id) + '">查看回执</button>' : '') + '</div>').join('');
}
function renderAvenues(snap) {
  const list = snap.avenues || [];
  const box = document.getElementById('avenueList');
  if (!list.length) { box.innerHTML = '<div class="note">暂无探索方向。检索卡牌或向助手请求协同候选。</div>'; return; }
  box.innerHTML = list.map(a =>
    '<div class="card"' + (a.focused ? ' style="border-color:var(--accent)"' : '') + '>'
    + '<span class="nm"><b>' + esc(a.title) + '</b>'
    + (a.note ? ' <span class="tag">' + esc(a.note) + '</span>' : '')
    + (a.unverified_card_names ? ' <span class="warn">候选未核验</span>' : '')
    + '<br>' + (a.candidates || []).map(c => esc(c.name)
        + (c.reason ? ' <span class="ts">(' + esc(c.reason) + ')</span>' : ''))
        .join('、')
    + '</span>'
    + '<div class="actions"><button data-avenue-action="focus" data-id="' + esc(a.id) + '">聚焦</button>'
    + '<button data-avenue-action="delete" data-id="' + esc(a.id) + '">删除</button></div></div>'
  ).join('');
}
async function pollAgentResult(rid, timeoutSec=300) {
  const infoBox = document.getElementById('agentReqInfo');
  const box = document.getElementById('agentResult');
  const deadline = Date.now() + timeoutSec * 1000;
  while (Date.now() < deadline) {
    const r = await fetch('/api/agent/result/' + encodeURIComponent(rid));
    if (r.status === 202) {
      let cb = null;
      try { cb = (await r.json()).claimed_by; } catch (e) { cb = null; }
      infoBox.textContent = cb
        ? ('[' + cb + '] 处理中…（入队 ' + rid + '）')
        : ('等待 Agent 认领…（入队 ' + rid + '）');
      await new Promise(res => setTimeout(res, 3000));
      continue;
    }
    const d = await r.json();
    if (!r.ok) throw new Error(d.error ? d.error.type + ': ' + d.error.message
                                       : JSON.stringify(d));
    if (d.status === 'error') {
      infoBox.textContent = '回执完成（' + (d.agent || d.claimed_by || '?') + '）';
      box.innerHTML = '<span class="bad">回执失败：'
        + truncStr(d.message || '未知错误', 300) + '</span>'
        + (d.result && Object.keys(d.result).length
           ? renderValue(d.result, 0) : '');
    } else {
      infoBox.textContent = '回执完成（' + (d.agent || d.claimed_by || '?')
        + (d.completed_at ? '，' + formatTime(d.completed_at) : '') + '）';
      box.innerHTML = renderAgentPayload(d);
    }
    return;
  }
  infoBox.textContent = '等待超时；网页未自动启动 Agent。请求仍在桥中，可由当前 CLI 显式领取。';
  box.textContent = '';
}
function doFocusAvenue(id) {
  run(() => postJSON('/api/avenues/' + encodeURIComponent(id) + '/focus', {}));
}
function doDeleteAvenue(id) {
  run(async () => {
    const r = await fetch('/api/avenues/' + encodeURIComponent(id),
                          {method: 'DELETE'});
    const d = await r.json();
    if (!r.ok) throw new Error(d.error ? d.error.type + ': ' + d.error.message
                                       : JSON.stringify(d));
  });
}
async function tick() {
  if (ticking) return;
  ticking = true;
  try {
    const d = await fetchJSON('/api/snapshot');
    const connection = document.getElementById('connection');
    connection.textContent = busy ? '正在处理…' : '本地已连接';
    connection.className = 'connection';
    lastSnap = d;
    const s = d.session || {};
    document.getElementById('session').textContent = s.import_seq
      ? '导入 #' + s.import_seq + '　' + (s.source_name ? '来源 ' + s.source_name + '　' : '')
        + '时间 ' + formatTime(s.imported_at)
      : '尚未导入牌表';
    const signature = JSON.stringify(Object.assign({}, d, {bridges:null}));
    if (signature !== lastRender) {
      const zones = document.getElementById('zones');
      const pool = document.getElementById('poolList');
      const zoneScroll = zones.scrollTop, poolScroll = pool.scrollTop;
      renderPool(d);
      renderDeck(d);
      renderStats(d);
      renderSeed(d);
      renderConstructed(d);
      renderRoles(d);
      renderCombos(d);
      renderCost(d);
      renderAudit(d);
      renderEvaluation(d);
      renderAvenues(d);
      zones.scrollTop = zoneScroll;
      pool.scrollTop = poolScroll;
      updateDisabled();
      lastRender = signature;
    }
    renderBridge(d);
    const warns = [].concat(d.warnings || [], (d.pool && d.pool.warnings) || []);
    document.getElementById('warnings').textContent =
      warns.join('\\n');
    document.getElementById('warningPanel').hidden = !warns.length;
    document.getElementById('warningSummary').textContent = '需要留意 · ' + warns.length + ' 条';
  } catch (e) {
    const connection = document.getElementById('connection');
    connection.textContent = '连接中断';
    connection.className = 'connection warn';
    connection.title = String(e.message || e);
  } finally { ticking = false; }
}
function updateDisabled() {
  for (const id of ['poolBtn','importBtn','seedBtn','ccBtn','rolesBtn','combosBtn',
                    'costBtn','auditBtn','findBtn','adviceBtn','avenueBtn'])
    document.getElementById(id).disabled = busy;
  document.getElementById('agentReqBtn').disabled = busy || agentPending;
  document.getElementById('auditBtn').disabled = busy || !!runningJobs.audit;
  document.getElementById('imageBtn').disabled = busy || !!runningJobs.image;
  document.getElementById('evalBtn').disabled = busy || !!runningJobs.evaluation;
  document.getElementById('evalBaselineBtn').disabled = busy;
  for (const button of document.querySelectorAll('[data-card-action],[data-avenue-action]'))
    button.disabled = busy;
}
async function run(action) {
  if (busy) return;
  busy = true;
  document.body.classList.add('busy');
  updateDisabled();
  document.getElementById('connection').textContent = '正在处理…';
  let success = false;
  try { await action(); showErrors(''); success = true; }
  catch (e) { showErrors(String(e.message || e)); }
  finally { busy = false; document.body.classList.remove('busy'); updateDisabled(); }
  await tick();
  return success;
}
function doAdd(name, section) {
  const limited = currentMode === 'limited';
  const other = section === 'main' ? 'sideboard' : 'main';
  const poolCard = lastSnap && lastSnap.pool.entries.find(c => c.name === name);
  const used = lastSnap ? ['main','sideboard'].reduce((n,z) => n + (lastSnap.sections[z] || [])
    .filter(c => c.name === name).reduce((s,c) => s + c.qty, 0), 0) : 0;
  if (limited && poolCard && used >= poolCard.qty && lastSnap.sections[other].some(c => c.name === name)) {
    doMove(name, other, section); return;
  }
  run(() => postJSON('/api/deck/add', {name:name, section:section, qty:1, limited:limited}));
}
function doRemove(name, section) { run(() => postJSON('/api/deck/remove', {name:name, section:section, qty:1})); }
function doMove(name, from, to) { run(() => postJSON('/api/deck/move', {name:name, from:from, to:to, qty:1, limited:currentMode === 'limited'})); }
function updateAuditScope() {
  const limited = document.getElementById('auditLimited').checked;
  document.getElementById('auditFormatField').hidden = limited;
  document.getElementById('auditFormat').disabled = limited;
  document.getElementById('auditBasis').textContent = limited
    ? '纯机器检查 40/41 张与导入牌池数量；不检查构筑赛合法性和 Standard 轮替。'
    : '调用 CLI 检查张数、赛制合法性和平台；Standard 才加轮替检查。';
}
function setMode(mode) {
  if (mode !== 'limited' && mode !== 'constructed') mode = 'limited';
  currentMode = mode;
  const evalFormat = document.getElementById('evalFormat');
  if (mode === 'limited') evalFormat.value = 'limited';
  else if (evalFormat.value === 'limited') evalFormat.value = 'pioneer';
  document.getElementById('evalDraw').checked = evalFormat.value === 'commander';
  try { localStorage.setItem('workbench-mode', mode); } catch (e) {}
  const panels = document.querySelectorAll('.mode-panel');
  for (let i = 0; i < panels.length; i++)
    panels[i].hidden = panels[i].getAttribute('data-mode') !== mode;
  const tabs = document.querySelectorAll('.tabbtn');
  for (let i = 0; i < tabs.length; i++) {
    const active = tabs[i].getAttribute('data-mode') === mode;
    tabs[i].classList.toggle('active', active);
    tabs[i].setAttribute('aria-pressed', String(active));
  }
  document.getElementById('modeHint').textContent = mode === 'limited'
    ? '限制赛 · 默认 41 张，可选 40 张' : '构筑 · 从核心牌与候选开始';
  const al = document.getElementById('auditLimited');
  if (al) al.checked = (mode === 'limited');   // 限制赛默认 40/41 口径，构筑默认关闭
  if (mode === 'limited' && !document.querySelector('.inspect-view[data-view="explore"]').hidden)
    setInspector('checks');
  updateAuditScope();
}
function initMode() {
  let mode = 'limited';
  try { mode = localStorage.getItem('workbench-mode') || 'limited'; } catch (e) {}
  setMode(mode);
}
document.getElementById('tabLimited').onclick = () => setMode('limited');
document.getElementById('tabConstructed').onclick = () => setMode('constructed');
document.getElementById('openImport').onclick = openImport;
document.getElementById('dismissError').onclick = () => showErrors('');
document.getElementById('agentConnectBtn').onclick = () => run(() => postJSON('/api/agent/connect', {backend: document.getElementById('agentBackend').value}));
document.getElementById('agentDisconnectBtn').onclick = () => run(() => postJSON('/api/agent/disconnect', {}));
for (const [id, decision] of [['agentApproveBtn','accept'],['agentDeclineBtn','decline']])
  document.getElementById(id).onclick = () => run(() => postJSON('/api/agent/approval', {
    approval_id:document.getElementById('agentApproval').dataset.id, decision:decision}));
document.getElementById('auditLimited').onchange = updateAuditScope;
document.getElementById('deckListBtn').onclick = () => setDeckView('list');
document.getElementById('deckGridBtn').onclick = () => setDeckView('grid');
document.getElementById('closeCardPreview').onclick = () => document.getElementById('cardPreview').close();
document.getElementById('closeExportPreview').onclick = () => document.getElementById('exportPreview').close();
document.getElementById('showExportPreview').onclick = () => document.getElementById('exportPreview').showModal();
for (const button of document.querySelectorAll('.inspectbtn'))
  button.onclick = () => setInspector(button.dataset.view);
document.addEventListener('click', event => {
  const button = event.target.closest('button');
  if (!button || button.disabled) return;
  if (button.hasAttribute('data-open-import')) openImport();
  const d = button.dataset;
  if (d.cardPreview) {
    document.getElementById('cardPreviewTitle').textContent = d.cardPreview;
    document.getElementById('cardPreviewImage').src = '/api/card-image?name=' + encodeURIComponent(d.cardPreview);
    document.getElementById('cardPreview').showModal();
  }
  if (d.receipt) {
    setInspector('assistant');
    pollAgentResult(d.receipt).catch(e => showErrors(e.message));
  }
  if (d.cardAction === 'add') doAdd(d.name, d.section);
  if (d.cardAction === 'remove') doRemove(d.name, d.section);
  if (d.cardAction === 'move') doMove(d.name, d.section, d.to);
  if (d.avenueAction === 'focus') doFocusAvenue(d.id);
  if (d.avenueAction === 'delete') doDeleteAvenue(d.id);
});
document.getElementById('poolBtn').onclick = async () => {
  const ok = await run(() => postText('/api/pool', document.getElementById('pooltext').value, 'srcname'));
  if (ok) document.getElementById('poolImport').open = false;
};
document.getElementById('importBtn').onclick = async () => {
  const ok = await run(() => postText('/api/builds/import', document.getElementById('decktext').value));
  if (ok) document.getElementById('deckImport').open = false;
};
document.getElementById('exportBtn').onclick = () => run(async () => {
  const r = await fetch('/api/export');
  if (!r.ok) throw new Error('牌表导出失败');
  const url = URL.createObjectURL(await r.blob());
  const link = document.createElement('a'); link.href = url; link.download = 'deck.txt';
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
document.getElementById('imageBtn').onclick = () => {
  document.getElementById('exportPreviewImage').hidden = true;
  document.getElementById('imageDownload').hidden = true;
  document.getElementById('imageReady').hidden = true;
  document.getElementById('exportPreview').showModal();
  startJob('image', '/api/export-image', {title:currentMode === 'limited' ? '限制赛套牌' : '构筑套牌'});
};
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
  const fixed = document.getElementById('seedConstraints').value.trim();
  if (fixed) body.seed_text = fixed;
  await postJSON('/api/seed-constructed', body);
});
document.getElementById('evalFormat').onchange = () => {
  document.getElementById('evalDraw').checked = document.getElementById('evalFormat').value === 'commander';
};
document.getElementById('evalBaselineBtn').onclick = () => run(async () => {
  const response = await fetch('/api/export');
  if (!response.ok) throw new Error('无法保存对照牌表');
  document.getElementById('evalBaseline').value = await response.text();
});
document.getElementById('evalBtn').onclick = () => {
  try {
    const body = {format:document.getElementById('evalFormat').value,
      runs:Number(document.getElementById('evalRuns').value), turns:Number(document.getElementById('evalTurns').value),
      on_draw:document.getElementById('evalDraw').checked,
      targets:document.getElementById('evalTargets').value.split(/\\r?\\n/).map(s => s.trim()).filter(Boolean),
      baseline_text:document.getElementById('evalBaseline').value};
    const raw = document.getElementById('evalCards').value.trim();
    if (raw) body.cards = JSON.parse(raw);
    startJob('evaluation', '/api/evaluation/start', body);
  } catch (e) { showErrors(e.message); }
};
document.getElementById('evalDownloadBtn').onclick = () => {
  if (!evaluationResult) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(evaluationResult, null, 2)], {type:'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = 'evaluation.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
document.getElementById('rolesBtn').onclick = () => run(() => fetchJSON('/api/roles'));
document.getElementById('combosBtn').onclick = () => run(() => fetchJSON(
  '/api/combos?format=' + encodeURIComponent(document.getElementById('cbFormat').value.trim() || 'pioneer')
  + '&platform=' + document.getElementById('cbPlatform').value
  + '&limit=' + encodeURIComponent(document.getElementById('cbLimit').value.trim() || '20')));
document.getElementById('costBtn').onclick = () => run(() => fetchJSON('/api/cost'));
document.getElementById('auditBtn').onclick = () => startJob('audit', '/api/audit/start', {
  format: document.getElementById('auditFormat').value.trim() || 'pioneer',
  limited: document.getElementById('auditLimited').checked,
  bo3: document.getElementById('auditBo3').checked});
document.getElementById('agentReqBtn').onclick = () => run(async () => {
  let payload = {};
  const raw = document.getElementById('agentPayload').value.trim();
  if (raw) payload = JSON.parse(raw);
  if (!payload || typeof payload !== 'object' || Array.isArray(payload))
    throw new Error('额外参数需为 JSON 对象。');
  const note = document.getElementById('agentNote').value.trim();
  if (note) payload.note = note;
  const body = {kind: document.getElementById('agentKind').value,
    payload: payload,
    timeout_sec: parseInt(document.getElementById('agentTimeout').value, 10) || 300};
  const d = await postJSON('/api/agent/request', body);
  const t = formatTime(d.queued_at);
  document.getElementById('agentReqInfo').textContent =
    '已入队 ' + d.request_id + '（' + t + '）';
  document.getElementById('agentResult').textContent = '等待回执…';
  agentPending = true;
  pollAgentResult(d.request_id, body.timeout_sec).catch(e => showErrors(String(e.message || e)))
    .finally(() => { agentPending = false; updateDisabled(); });
});
document.getElementById('findBtn').onclick = () => run(async () => {
  const q = document.getElementById('findQ').value.trim();
  const limit = document.getElementById('findLimit').value.trim() || '20';
  const r = await fetch('/api/find?q=' + encodeURIComponent(q)
    + '&limit=' + encodeURIComponent(limit));
  const d = await r.json();
  if (!r.ok) throw new Error(d.error ? d.error.type + ': ' + d.error.message
                                     : JSON.stringify(d));
  document.getElementById('findBox').innerHTML = '命中 ' + d.returned
    + ' / 共 ' + d.total_cards + '：<br>'
    + (d.cards || []).map(c => esc(c.name)).join('、');
});
document.getElementById('adviceBtn').onclick = () => run(async () => {
  const d = await postJSON('/api/advice', {});
  const box = document.getElementById('adviceBox');
  if (d.status === 'offline') {
    box.innerHTML = '<span class="warn">LLM 离线：'
      + esc(d.offline_reason || '未知原因') + '</span><br>'
      + '<span class="note">以下为机器兜底内容（确定性统计，未经 LLM 生成）：</span>'
      + renderValue(d.machine_fallback || {}, 0);
  } else {
    box.innerHTML = '<span class="tag">[' + esc(d.model || 'llm')
      + '，未经工具核验]</span><br>' + esc(d.advice);
  }
});
document.getElementById('avenueBtn').onclick = () => run(async () => {
  const candidates = document.getElementById('avCands').value.split('\\n')
    .map(line => line.split('|').map(s => s.trim()))
    .filter(parts => parts[0])
    .map(parts => ({name: parts[0], reason: parts.slice(1).join('|') || ''}));
  await postJSON('/api/avenues', {
    title: document.getElementById('avTitle').value,
    note: document.getElementById('avNote').value,
    candidates: candidates});
});
document.getElementById('poolFilter').onchange = () => { if (lastSnap) { renderPool(lastSnap); updateDisabled(); } };
document.getElementById('poolSearch').oninput = () => { if (lastSnap) { renderPool(lastSnap); updateDisabled(); } };
buildColorOptions();
initMode();
try { setDeckView(localStorage.getItem('workbench-card-view') || 'list'); } catch (e) {}
for (const kind of ['audit','image','evaluation']) {
  let id = null;
  try { id = localStorage.getItem('workbench-job-' + kind); } catch (e) {}
  if (id) followJob(id, kind);
}
setInterval(tick, """ + str(POLL_INTERVAL_MS) + """); tick();
</script>
</body>
</html>
"""


# ------------------------------------------------------------------ serve/CLI

def serve(host, port, agent_backend=workbench_agent.DEFAULT_BACKEND):
    """启动工作台（前台阻塞）。端口占用等启动失败抛 WorkbenchError。"""
    try:
        state = WorkbenchState(agent_backend=agent_backend)
    except ValueError as exc:
        raise WorkbenchError(str(exc)) from exc
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
        state.receiver.close()
        server.server_close()
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    child = sub.add_parser("serve", help="启动网页工作台 hub（前台阻塞）")
    child.add_argument("--host", default=DEFAULT_HOST)
    child.add_argument("--port", type=int, default=DEFAULT_PORT,
                       help="默认 {}（避开 8642 对局监控 / 8643 轮抓面板）".format(DEFAULT_PORT))
    child.add_argument("--agent-backend", default=workbench_agent.DEFAULT_BACKEND,
                       choices=sorted(workbench_agent.BACKENDS),
                       help="助手持续接收端默认后端（页面连接时可切换）")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return serve(args.host, args.port, agent_backend=args.agent_backend)
    except WorkbenchError as exc:
        print("[error] " + str(exc), file=sys.stderr)
        runlog.log_run("deck_workbench", "error", "serve " + str(exc))
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(runlog.run_logged("deck_workbench", main))
