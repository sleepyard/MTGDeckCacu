#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mtg_tool.py — MTG 套牌构筑工作流 CLI（Scryfall + mtgch.com，仅标准库）

Subcommands:
  search    按 Scryfall 查询枚举候选牌（全分页 / oracle 去重 / MDFC 展开）
  check     逐牌三重核对：赛制合法性 + 平台可用性 + 中文名
  validate  牌表机器门禁（张数 / 同名上限 / 赛制 / 平台 / 颜色身份）
  baseline  环境基线：已发售系列列表 + 赛制禁牌表（Markdown 输出）

通用行为:
  - 所有 HTTP 请求带 User-Agent；Scryfall 请求间隔 >=100ms；
    429/5xx 指数退避并遵守 Retry-After，最多重试 5 次。
  - 磁盘缓存 tools/cache/{scryfall|mtgch}/<sha1>.json，
    键 = 方法+URL+排序参数的 SHA1；--no-cache 可绕过读取。
  - 错误分类：网络失败 / HTTP 失败 / 查询语法错误 / 分页不完整 /
    模糊名未精确命中 / 真实零结果，互不混淆，失败不静默当作"不存在"。
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

USER_AGENT = "NeoMtgDeckCacu/1.0"
SCRYFALL_BASE = "https://api.scryfall.com"
MTGCH_BASE = "https://mtgch.com"
TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(TOOL_DIR, "cache")
MIN_REQUEST_INTERVAL = 0.100  # 秒，Scryfall 请求节流
MAX_RETRIES = 5
MAX_PAGES = 100

LEGAL_OK = "legal"
BASIC_LAND_NAMES = {
    "Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes",
    "Snow-Covered Plains", "Snow-Covered Island", "Snow-Covered Swamp",
    "Snow-Covered Mountain", "Snow-Covered Forest", "Snow-Covered Wastes",
}


# ---------------------------------------------------------------- 错误模型
class MtgToolError(Exception):
    """工具错误基类"""


class NetworkError(MtgToolError):
    """网络层失败（DNS/连接/超时，重试耗尽后抛出）"""


class HttpError(MtgToolError):
    """HTTP 非 2xx 且不属于可建模的业务错误（含 429/5xx 重试耗尽）"""


class QuerySyntaxError(MtgToolError):
    """Scryfall 返回 error 对象（查询语法错误 / not_found 等 4xx）"""


class CardNotFound(MtgToolError):
    """精确查名未命中（含模糊匹配被拒绝的情形）"""


class PaginationIncomplete(MtgToolError):
    """分页遍历未完成（超过页数上限或 next_page 中断）"""


class DeckParseError(MtgToolError):
    """牌表文件解析失败"""


# ---------------------------------------------------------------- HTTP 层
_last_request_at = [0.0]


def _throttle():
    delta = time.monotonic() - _last_request_at[0]
    if delta < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - delta)


def _cache_path(service, method, url, params):
    key_src = "\n".join([
        method.upper(),
        url,
        json.dumps(params or {}, sort_keys=True, ensure_ascii=False),
    ])
    digest = hashlib.sha1(key_src.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, service, digest + ".json")


def _is_retryable(status):
    return status == 429 or status >= 500


def http_get_json(url, service, params=None, use_cache=True, timeout=30):
    """GET JSON：缓存 -> 节流 -> UA 请求 -> 429/5xx 指数退避重试。

    返回 (http_status, payload)。2xx/4xx 确定性响应（含 404）会被缓存；
    429/5xx 最终失败不缓存（避免旧失败永久命中）。"""
    params = params or {}
    cpath = _cache_path(service, "GET", url, params)
    if use_cache and os.path.exists(cpath):
        with open(cpath, "r", encoding="utf-8") as fh:
            entry = json.load(fh)
        return entry["http_status"], entry["payload"]

    full_url = url + ("?" + urllib.parse.urlencode(params) if params else "")
    attempt = 0
    delay = 1.0
    while True:
        _throttle()
        req = urllib.request.Request(
            full_url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                _last_request_at[0] = time.monotonic()
                status = resp.status
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            _last_request_at[0] = time.monotonic()
            status = exc.code
            body = exc.read().decode("utf-8", errors="replace")
            if _is_retryable(status) and attempt < MAX_RETRIES:
                wait = delay
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                if retry_after:
                    try:
                        wait = max(wait, float(retry_after))
                    except ValueError:
                        pass
                print(f"[warn] HTTP {status}，{wait:.1f}s 后重试 ({attempt + 1}/{MAX_RETRIES}): {full_url}",
                      file=sys.stderr)
                time.sleep(wait)
                attempt += 1
                delay *= 2
                continue
        except (urllib.error.URLError, OSError) as exc:
            if attempt < MAX_RETRIES:
                print(f"[warn] 网络错误，{delay:.1f}s 后重试 ({attempt + 1}/{MAX_RETRIES}): {exc}",
                      file=sys.stderr)
                time.sleep(delay)
                attempt += 1
                delay *= 2
                continue
            raise NetworkError(f"网络请求失败（重试 {MAX_RETRIES} 次后放弃）: {full_url}: {exc}") from exc
        break

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = {"_raw": body}

    if not _is_retryable(status):
        os.makedirs(os.path.dirname(cpath), exist_ok=True)
        entry = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "http_status": status,
            "url": full_url,
            "payload": payload,
        }
        with open(cpath, "w", encoding="utf-8") as fh:
            json.dump(entry, fh, ensure_ascii=False, indent=1)

    if _is_retryable(status):
        raise HttpError(f"HTTP {status}（重试 {MAX_RETRIES} 次后仍失败）: {full_url}")
    return status, payload


# ---------------------------------------------------------------- Scryfall 辅助
def scryfall_get(path, params=None, use_cache=True):
    """Scryfall GET；4xx error 对象抛 QuerySyntaxError，其余 4xx/5xx 抛 HttpError。"""
    status, payload = http_get_json(SCRYFALL_BASE + path, "scryfall", params, use_cache)
    if status >= 400:
        if isinstance(payload, dict) and payload.get("object") == "error":
            raise QuerySyntaxError(
                f"Scryfall {status} [{payload.get('code')}]: {payload.get('details')} -- {path}")
        raise HttpError(f"Scryfall HTTP {status}: {path}")
    return payload


def _fetch_list_object(first_data, use_cache):
    """遍历 Scryfall List 对象全部分页，返回合并后的 data 数组。"""
    items = list(first_data.get("data", []))
    data = first_data
    pages = 1
    while data.get("has_more"):
        pages += 1
        if pages > MAX_PAGES:
            raise PaginationIncomplete(f"分页超过 {MAX_PAGES} 页仍未结束（has_more 持续为真）")
        next_url = data.get("next_page")
        if not next_url:
            raise PaginationIncomplete("has_more=true 但缺少 next_page，分页不完整")
        status, payload = http_get_json(next_url, "scryfall", None, use_cache)
        if status >= 400:
            raise PaginationIncomplete(f"分页中途失败 HTTP {status}: {next_url}")
        data = payload
        items.extend(data.get("data", []))
    return items


def scryfall_search(query, unique="oracle", use_cache=True):
    """全分页搜索。返回 (cards, total_cards, warnings)。

    QuerySyntaxError 原样上抛（含假性 404/语法错误）；真实零结果是空列表而非异常。"""
    data = scryfall_get("/cards/search", {"q": query, "unique": unique}, use_cache)
    cards = _fetch_list_object(data, use_cache)
    return cards, data.get("total_cards", len(cards)), data.get("warnings") or []


def dedupe_by_oracle(cards):
    """按 oracle_id 去重，保留第一张印刷。"""
    seen = set()
    out = []
    for c in cards:
        oid = c.get("oracle_id") or c.get("id")
        if oid in seen:
            continue
        seen.add(oid)
        out.append(c)
    return out


def normalize_card(c):
    """提取统一字段；MDFC/双面牌从 card_faces 拼接 mana_cost / oracle_text。"""
    faces = c.get("card_faces") or []

    def from_faces(field, sep):
        parts = [str(f[field]) for f in faces if f.get(field)]
        if parts:
            return sep.join(parts)
        return c.get(field)

    face_records = [
        {
            "name": f.get("name"),
            "mana_cost": f.get("mana_cost"),
            "type_line": f.get("type_line"),
            "oracle_text": f.get("oracle_text"),
            "power": f.get("power"),
            "toughness": f.get("toughness"),
            "loyalty": f.get("loyalty"),
        }
        for f in faces
    ]
    return {
        "name": c.get("name"),
        "oracle_id": c.get("oracle_id"),
        "layout": c.get("layout"),
        "mana_cost": from_faces("mana_cost", " // "),
        "cmc": c.get("cmc"),
        "type_line": c.get("type_line"),
        "oracle_text": from_faces("oracle_text", "\n//\n"),
        "power": c.get("power") or (faces[0].get("power") if faces else None),
        "toughness": c.get("toughness") or (faces[0].get("toughness") if faces else None),
        "loyalty": c.get("loyalty") or (faces[0].get("loyalty") if faces else None),
        "legalities": c.get("legalities") or {},
        "set": c.get("set"),
        "set_name": c.get("set_name"),
        "games": c.get("games") or [],
        "keywords": c.get("keywords") or [],
        "color_identity": c.get("color_identity") or [],
        "card_faces": face_records,
    }


def name_matches(requested, card):
    """精确命中校验：请求名须等于牌全名或任一面名（不区分大小写）。"""
    names = {str(card.get("name", "")).lower()}
    for f in card.get("card_faces") or []:
        names.add(str(f.get("name", "")).lower())
    return requested.strip().lower() in names


# ---------------------------------------------------------------- mtgch 中文名
def fetch_chinese_name(english_name, use_cache=True):
    """返回 (translated_name 或 None, 错误描述 或 None)。

    查不到返回 (None, None) —— 属正常情形，由调用方标注"中文名缺失"。
    mtgch 2026 改版：旧端点 /api/v1/card-names/?q= 已 404，改用
    /api/v1/result?q=<名>&view=1（view=1 才返回 display_name/display_name_zh）。"""
    try:
        status, payload = http_get_json(
            MTGCH_BASE + "/api/v1/result", "mtgch",
            {"q": english_name, "view": 1}, use_cache)
    except MtgToolError as exc:
        return None, f"mtgch 查询失败: {exc}"
    if status >= 400:
        return None, f"mtgch HTTP {status}"
    items = payload.get("items") if isinstance(payload, dict) else None
    if not items:
        return None, None
    target = english_name.strip().lower()
    front = target.split(" // ")[0]
    # 优先取英文名精确匹配的条目（双面/历险牌允许按正面名匹配）
    for item in items:
        if not isinstance(item, dict):
            continue
        disp = str(item.get("display_name") or "").strip().lower()
        if disp == target or disp == front:
            return item.get("display_name_zh"), None
    first = items[0] if isinstance(items[0], dict) else {}
    return first.get("display_name_zh"), None


def fetch_set_chinese_names(set_code, use_cache=True):
    """按系列批量拉取 {英文名(小写): 中文名}——一次请求覆盖全系列。
    mtgch 对逐牌查询限流很凶（实测 429 风暴），批量场景一律走这里。
    失败返回 (None, 错误描述)。"""
    try:
        status, payload = http_get_json(
            MTGCH_BASE + f"/api/v1/set/{set_code.lower()}/cards/", "mtgch",
            {}, use_cache)
    except MtgToolError as exc:
        return None, f"mtgch 系列查询失败: {exc}"
    if status >= 400:
        return None, f"mtgch HTTP {status}"
    items = payload.get("items") if isinstance(payload, dict) else None
    if not items:
        return {}, None
    out = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        en = str(item.get("display_name") or "").strip().lower()
        zh = item.get("display_name_zh")
        if en and zh:
            out.setdefault(en, zh)
            out.setdefault(en.split(" // ")[0], zh)
    return out, None


# ---------------------------------------------------------------- check 核心
# Scryfall legalities 没有 explorer 字段。Explorer = 先驱合法 ∩ Arena 可用 ∩ Explorer 专属禁牌
# （当前专属禁牌仅 Tibalt's Trickery，且为 MTGA BO1 特例；Winota 已在先驱禁牌表内）。
# 赛制合法性查询一律按下表走别名推导，BO1 特例与队列差异仍需人工复核。
FORMAT_LEGALITY_ALIAS = {"explorer": "pioneer"}


def check_card(name, fmt, platform, use_cache=True):
    """逐牌三重核对。单牌任何失败都记录在 rec 中，不抛异常中断整体。

    rec.ok 为 True 仅当：精确命中 + 赛制 legal + 平台可用（若检查平台）。"""
    rec = {
        "english": name,
        "chinese": None,
        "legal": None,          # legalities[fmt] 原文
        "platform": platform,
        "platform_ok": None,    # 仅 platform=arena 时有意义
        "platform_prints": [],  # 实际通过平台检查的印刷 SET#NUM
        "layout": None,
        "type_line": None,
        "color_identity": None,
        "notes": [],
        "ok": True,
        "scryfall_name": None,
    }

    # 1. 赛制合法性（oracle 级 legalities）
    card = None
    try:
        status, payload = http_get_json(
            SCRYFALL_BASE + "/cards/named", "scryfall", {"exact": name}, use_cache)
    except MtgToolError as exc:
        rec["ok"] = False
        rec["notes"].append(f"Scryfall 请求失败: {exc}")
        status, payload = None, None
    if status == 404:
        rec["ok"] = False
        rec["notes"].append("Scryfall 精确查名未命中 (404 Card not found)")
    elif status is not None and status >= 400:
        rec["ok"] = False
        rec["notes"].append(f"Scryfall /cards/named HTTP {status}")
    elif payload is not None:
        card = payload
        if not name_matches(name, card):
            # 模糊匹配结果一律拒绝
            rec["ok"] = False
            rec["notes"].append(
                f"模糊匹配到 '{card.get('name')}'，与请求名不一致，按未命中处理")
            card = None
        else:
            rec["scryfall_name"] = card.get("name")
            rec["layout"] = card.get("layout")
            rec["type_line"] = card.get("type_line")
            rec["color_identity"] = card.get("color_identity") or []
            lookup_fmt = FORMAT_LEGALITY_ALIAS.get(fmt.lower(), fmt.lower())
            legal = (card.get("legalities") or {}).get(lookup_fmt)
            if legal is None:
                rec["ok"] = False
                rec["notes"].append(f"legalities 中无赛制 '{lookup_fmt}' 字段")
            else:
                rec["legal"] = legal
                if lookup_fmt != fmt.lower():
                    rec["notes"].append(
                        f"Scryfall 无 {fmt} 字段，按 {lookup_fmt} 合法性推导"
                        "（BO1/队列特例禁牌需另行人工复核）")
                if legal != LEGAL_OK:
                    rec["ok"] = False
                    rec["notes"].append(f"赛制 {lookup_fmt} 合法性: {legal}")

    # 2. 平台可用性（遍历全部印刷，不能只看 /cards/named 的最新印刷）
    if card is not None and platform and platform.lower() == "arena":
        try:
            prints, _, _ = scryfall_search(f'!"{name}"', unique="prints", use_cache=use_cache)
            arena_prints = [
                f"{(p.get('set') or '?').upper()}#{p.get('collector_number')}"
                for p in prints if "arena" in (p.get("games") or [])
            ]
            rec["platform_ok"] = bool(arena_prints)
            rec["platform_prints"] = arena_prints
            if not arena_prints:
                rec["ok"] = False
                rec["notes"].append(f"遍历 {len(prints)} 张印刷，无 Arena 版本")
        except QuerySyntaxError as exc:
            rec["ok"] = False
            rec["notes"].append(f"平台核对查询语法错误: {exc}")
        except MtgToolError as exc:
            rec["ok"] = False
            rec["notes"].append(f"平台核对失败: {exc}")

    # 3. 中文名（查不到不中断）
    zh, zh_err = fetch_chinese_name(name, use_cache)
    rec["chinese"] = zh
    if zh_err:
        rec["notes"].append(zh_err)
    if not zh:
        rec["notes"].append("中文名缺失")

    # 4. 张数无上限例外（牌面 "A deck can have any number of cards named ..."，
    #    如 Slime Against Humanity / Hare Apparent / Rat Colony；MDFC 读 card_faces）
    if card is not None:
        texts = [card.get("oracle_text") or ""]
        texts += [f.get("oracle_text") or "" for f in card.get("card_faces") or []]
        rec["any_number_of"] = any(
            "a deck can have any number of cards named" in t.lower() for t in texts)

    return rec


def render_check_table(records, fmt):
    lines = [
        "| 中文名 | English | 赛制合法 | 平台可用(通过的印刷) | 备注 |",
        "|---|---|---|---|---|",
    ]
    for r in records:
        zh = r["chinese"] or "中文名缺失"
        legal = r["legal"] if r["legal"] is not None else "未命中"
        legal_mark = ("✓ " if r["legal"] == LEGAL_OK else "✗ ") + legal
        if r["platform_ok"] is None:
            platform_cell = "—"
        else:
            prints = ", ".join(r["platform_prints"][:4])
            if len(r["platform_prints"]) > 4:
                prints += f" 等{len(r['platform_prints'])}个"
            platform_cell = ("✓ " if r["platform_ok"] else "✗ ") + (prints or "无 Arena 印刷")
        notes = "; ".join(r["notes"]) if r["notes"] else ""
        if r["layout"] and r["layout"] not in ("normal",):
            notes = (f"layout={r['layout']}" + ("; " + notes if notes else ""))
        lines.append(f"| {zh} | {r['english']} | {legal_mark} | {platform_cell} | {notes} |")
    return "\n".join(lines)


# ---------------------------------------------------------------- subcommand: search
def cmd_search(args):
    try:
        cards, total, warnings = scryfall_search(args.query, unique="prints", use_cache=not args.no_cache)
    except QuerySyntaxError as exc:
        print(f"[错误] 查询语法错误或未命中: {exc}", file=sys.stderr)
        return 2
    except PaginationIncomplete as exc:
        print(f"[错误] 分页不完整: {exc}", file=sys.stderr)
        return 3
    except MtgToolError as exc:
        print(f"[错误] 请求失败: {exc}", file=sys.stderr)
        return 1

    for w in warnings:
        print(f"[scryfall warning] {w}", file=sys.stderr)

    raw_count = len(cards)
    if args.unique == "oracle":
        cards = dedupe_by_oracle(cards)
    records = [normalize_card(c) for c in cards]

    out_json = json.dumps(records, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(out_json + "\n")
        print(f"[info] 已写入 {args.out}", file=sys.stderr)
    else:
        print(out_json)

    print(f"[摘要] 原始命中 {raw_count} 张印刷（API total_cards={total}）；"
          f"{'oracle 去重后' if args.unique == 'oracle' else '保留全部印刷'} {len(records)} 张；"
          f"失败项 0", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- subcommand: check
def cmd_check(args):
    names = list(args.names or [])
    if args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            names.extend(ln.strip() for ln in fh if ln.strip())
    if not names:
        print("[错误] 未提供任何牌名（位置参数或 --file）", file=sys.stderr)
        return 2

    records = []
    for name in names:
        try:
            rec = check_card(name, args.format, args.platform, use_cache=not args.no_cache)
        except MtgToolError as exc:
            rec = {"english": name, "chinese": None, "legal": None,
                   "platform": args.platform, "platform_ok": None,
                   "platform_prints": [], "layout": None, "notes": [f"核对异常: {exc}"],
                   "ok": False}
        records.append(rec)
        mark = "PASS" if rec["ok"] else "FAIL"
        print(f"[{mark}] {name}", file=sys.stderr)

    table = render_check_table(records, args.format)
    print(table)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False, indent=1)
        print(f"[info] JSON 已写入 {args.out}", file=sys.stderr)

    passed = sum(1 for r in records if r["ok"])
    failed = len(records) - passed
    print(f"\n汇总: {passed}/{len(records)} 通过，{failed} 失败"
          f"（赛制 {args.format}" + (f"，平台 {args.platform}" if args.platform else "") + "）",
          file=sys.stderr)
    return 0 if failed == 0 else 4


# ---------------------------------------------------------------- subcommand: validate
SECTION_HEADERS = {"deck": "main", "sideboard": "sideboard",
                   "commander": "commander", "companion": "companion"}


def parse_deckfile(path):
    """解析 MTGO/MTGA 导入格式。返回 {section: [(qty, name), ...]}。

    块头行 Deck/Sideboard/Commander/Companion 显式切换分区；
    无块头时，主牌后的空行切换为备牌。"""
    sections = {"commander": [], "companion": [], "main": [], "sideboard": []}
    current = "main"
    blank_switched = False
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line:
                if current == "main" and sections["main"] and not blank_switched:
                    current = "sideboard"
                    blank_switched = True
                continue
            low = line.lower()
            if low in SECTION_HEADERS:
                current = SECTION_HEADERS[low]
                continue
            m = re.match(r"^(\d+)\s+(.+)$", line)
            if not m:
                raise DeckParseError(f"第 {lineno} 行无法解析为 '数量 英文名': {line!r}")
            qty = int(m.group(1))
            name = m.group(2).strip()
            # 兼容 MTGO 导出尾部 "(SET) 123"
            name = re.sub(r"\s+\([A-Za-z0-9_]+\)\s+\S+$", "", name).strip()
            if not name:
                raise DeckParseError(f"第 {lineno} 行缺少牌名: {line!r}")
            sections[current].append((qty, name))
    return sections


def is_basic_land(type_line):
    return bool(type_line) and "Basic Land" in type_line


def cmd_validate(args):
    try:
        sections = parse_deckfile(args.deckfile)
    except (DeckParseError, OSError) as exc:
        print(f"[错误] 牌表解析失败: {exc}", file=sys.stderr)
        return 2

    violations = []

    def vio(msg):
        violations.append(msg)
        print(f"  [违规] {msg}")

    main = sections["main"]
    sideboard = sections["sideboard"]
    main_count = sum(q for q, _ in main)
    sb_count = sum(q for q, _ in sideboard) + sum(q for q, _ in sections["companion"])

    print(f"[info] 主牌 {main_count} 张，备牌 {sb_count} 张"
          + (f"，指挥官 {sum(q for q, _ in sections['commander'])} 张" if sections["commander"] else "")
          + f"（赛制 {args.format}" + ("，BO3" if args.bo3 else "") + "）", file=sys.stderr)

    # ---- 数量门禁
    if main_count < 60:
        vio(f"主牌 {main_count} 张 < 60")
    if args.no_sideboard and sb_count > 0:
        vio(f"--no-sideboard 生效但备牌 {sb_count} 张")
    if sb_count > 15:
        vio(f"备牌 {sb_count} 张 > 15")

    # ---- 逐牌核对（同名合并，复用 check 逻辑与缓存）
    allowed_colors = set(args.colors.lower()) if args.colors else None
    unique_names = sorted({name for sec in sections.values() for _, name in sec})
    card_info = {}
    for name in unique_names:
        try:
            rec = check_card(name, args.format, args.platform, use_cache=not args.no_cache)
        except MtgToolError as exc:
            rec = {"english": name, "ok": False, "notes": [f"核对异常: {exc}"],
                   "type_line": None, "color_identity": None, "legal": None,
                   "platform_ok": None}
        card_info[name] = rec

    # ---- 同名上限（基本地豁免；牌面 "any number of cards named" 豁免；同名跨主备合并计数）
    totals = {}
    for sec in ("main", "sideboard"):
        for qty, name in sections[sec]:
            totals[name] = totals.get(name, 0) + qty
    for name, total in sorted(totals.items()):
        rec = card_info[name]
        if is_basic_land(rec.get("type_line")) or total <= 4:
            continue
        if rec.get("any_number_of"):
            print(f"  [豁免] '{name}' 牌面允许任意张数，共 {total} 张", file=sys.stderr)
        else:
            vio(f"'{name}' 共 {total} 张 > 4（非基本地）")

    # ---- 逐牌三重核对 + 颜色身份
    print("[info] 逐牌核对:", file=sys.stderr)
    for name in unique_names:
        rec = card_info[name]
        total = totals.get(name, 0) + sum(q for q, n in sections["commander"] + sections["companion"] if n == name)
        mark = "PASS" if rec["ok"] else "FAIL"
        zh = rec.get("chinese") or "中文名缺失"
        print(f"  [{mark}] x{total} {name} ({zh})", file=sys.stderr)
        if not rec["ok"]:
            for note in rec.get("notes", []):
                vio(f"'{name}': {note}")
        if allowed_colors is not None:
            ci = set(c.lower() for c in (rec.get("color_identity") or []))
            overflow = ci - allowed_colors
            if overflow:
                vio(f"'{name}' 颜色身份 {sorted(ci)} 超出 --colors {args.colors} "
                    f"（多出 {sorted(overflow)}）")

    print("", file=sys.stderr)
    if violations:
        print(f"FAIL — {len(violations)} 项违规")
        return 4
    print("PASS — 全部门禁通过")
    return 0


# ---------------------------------------------------------------- subcommand: baseline
def cmd_baseline(args):
    # 已发售系列
    try:
        sets_data = scryfall_get("/sets", None, use_cache=not args.no_cache)
        all_sets = _fetch_list_object(sets_data, use_cache=not args.no_cache)
    except MtgToolError as exc:
        print(f"[错误] 系列列表获取失败: {exc}", file=sys.stderr)
        return 1
    released = [s for s in all_sets
                if (s.get("released_at") or "9999") <= args.date and (s.get("card_count") or 0) > 0]
    released.sort(key=lambda s: (s.get("released_at") or "", s.get("code") or ""))

    # 禁牌（explorer 等无 legalities 字段的赛制走别名推导）
    lookup_fmt = FORMAT_LEGALITY_ALIAS.get(args.format.lower(), args.format.lower())
    try:
        banned_cards, _, _ = scryfall_search(
            f"banned:{lookup_fmt} date<={args.date}", unique="cards",
            use_cache=not args.no_cache)
        banned = sorted(dedupe_by_oracle(banned_cards), key=lambda c: c.get("name", ""))
    except QuerySyntaxError as exc:
        print(f"[错误] 禁牌查询失败: {exc}", file=sys.stderr)
        return 2
    except MtgToolError as exc:
        print(f"[错误] 禁牌查询请求失败: {exc}", file=sys.stderr)
        return 1

    zh_banned = []
    for c in banned:
        zh, _ = fetch_chinese_name(c.get("name", ""), use_cache=not args.no_cache)
        zh_banned.append((c.get("name", ""), zh))

    lines = [
        f"## 环境基线（{args.format}，基准日 {args.date}）",
        "",
        f"### 已发售系列（released_at <= {args.date}，共 {len(released)} 个）",
        "",
        "| code | name | released_at |",
        "|---|---|---|",
    ]
    lines += [f"| {s.get('code')} | {s.get('name')} | {s.get('released_at')} |" for s in released]
    lines += [
        "",
        f"### {args.format} 禁牌（{len(banned)} 张，基准日 {args.date}）",
        "",
    ]
    if lookup_fmt != args.format.lower():
        lines += [
            f"> 注：Scryfall 无 {args.format} 禁牌数据，以上为 {lookup_fmt} 禁牌表推导；"
            f"{args.format} 专属/队列特例禁牌（如 MTGA BO1）需查官方公告另行补充。",
            "",
        ]
    lines += [f"- {zh} / {en}" if zh else f"- {en}（中文名缺失）" for en, zh in zh_banned]
    print("\n".join(lines))
    print(f"[摘要] 系列 {len(released)} 个，禁牌 {len(banned)} 张，失败项 0", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- 入口
def build_parser():
    p = argparse.ArgumentParser(
        prog="mtg_tool.py",
        description="MTG 套牌构筑工作流工具（Scryfall + mtgch.com）")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--no-cache", action="store_true", help="绕过磁盘缓存重新请求")

    sp = sub.add_parser("search", help="Scryfall 查询枚举候选牌（全分页）")
    sp.add_argument("query", help="Scryfall 查询式，如 'f:pioneer game:arena o:flash t:creature'")
    sp.add_argument("--unique", choices=["oracle", "prints"], default="oracle",
                    help="oracle(默认) 按 oracle_id 去重保留第一张印刷；prints 保留全部印刷")
    sp.add_argument("--out", help="结果写入 JSON 文件（缺省输出到 stdout）")
    add_common(sp)
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("check", help="逐牌三重核对：赛制合法 + 平台可用 + 中文名")
    sp.add_argument("names", nargs="*", help="牌名（双面牌用正面名）")
    sp.add_argument("--file", help="牌名清单文件（每行一个）")
    sp.add_argument("--format", required=True, help="赛制，如 pioneer / modern / standard")
    sp.add_argument("--platform", choices=["arena"], default=None,
                    help="指定后核对平台可用性（遍历全部印刷）")
    sp.add_argument("--out", help="结果写入 JSON 文件")
    add_common(sp)
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("validate", help="牌表机器门禁")
    sp.add_argument("deckfile", help="MTGO/MTGA 导入格式牌表文件")
    sp.add_argument("--format", required=True, help="赛制，如 pioneer")
    sp.add_argument("--platform", choices=["arena"], default="arena",
                    help="平台可用性核对（默认 arena；实体牌可不传？默认 arena 因工作流默认 MTGA）")
    sp.add_argument("--bo3", action="store_true", help="BO3 对局（记录用）")
    sp.add_argument("--no-sideboard", action="store_true", help="不允许备牌")
    sp.add_argument("--colors", help="颜色身份约束，如 ug（各牌 color_identity 须为其子集）")
    add_common(sp)
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("baseline", help="环境基线：已发售系列 + 禁牌表（Markdown）")
    sp.add_argument("--format", required=True, help="赛制，如 pioneer")
    sp.add_argument("--date", required=True, help="基准日期 YYYY-MM-DD")
    add_common(sp)
    sp.set_defaults(func=cmd_baseline)

    return p


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
