#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""网页套牌工作台 hub（MtgWorkbenchPlan Phase 0 hub + Phase 1 限制赛组牌）。

分层（决策 B：引擎先行，UI 最薄）：
  引擎纯函数    build_snapshot / serialize_deck / build_stats /
                hydrate_pool / apply_add|remove|move —— 可独立单测
  权威状态      WorkbenchState —— 持锁；牌表 + 水合牌池 + 卡片库 + 最近 seed
  HTTP 层       make_handler —— 解析请求 → 调引擎 → 序列化，不含任何牌规则

端点：
  GET  /                    内嵌工作台页面（fetch 轮询 /api/snapshot，3s）
  GET  /api/snapshot        牌表 + 牌池 + 统计 + 最近 seed 的全量快照
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

错误信封与 mtg_rules_tool 同构：
  {"status": "error", "error": {"type": ..., "message": ...}}
未知路径 404；handler 未捕获异常 500（traceback 只进 stderr，不回浏览器）；
完全解析不出任何条目的导入是业务错误（400），与"成功但带 skipped 警告"
明确分离。Ctrl+C 干净退出；CLI 出口接 runlog 留痕。
"""
import argparse
import json
import sys
import threading
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import deck_core
import deck_model
import deck_pooper
import limited_strategy as LS
import mtg_tool
import mtga_draft_tool
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
<h1>MTG 套牌工作台（Phase 1 限制赛）</h1>
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
