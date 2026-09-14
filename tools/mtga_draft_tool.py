#!/usr/bin/env python3
"""MTGA 快速轮抓（Quick Draft）驾驶舱：17Lands 胜率锚点 + 包/pick 跟踪 + LLM 推荐。

定位：轮抓期副驾。仅读 Player.log，不做任何鼠标键盘模拟。
数据源：
- 17Lands 单卡数据：直连（17lands.com card_ratings）优先、shiqidi 同源代理
  （shiqidi.lenitatis.com/api/card_data，schema 一致，含 mtga_id 可直接对齐
  grpId）兜底；2026 中直连端点失效期间由代理维持数据（实测 2026-09-13
  HOB PremierDraft 188 张）。磁盘缓存 tools/cache/17lands/<SET>_<format>.json，
  >3 天提示刷新；拉取失败/缺数据时降级为纯 LLM 模式并显式标注"无胜率锚点"。
- 轮抓载荷 schema 以 tools/auto/draft_samples/ 真实录样为准（mtga_auto_tool draft --record）。

仅 Python 标准库；复用 mtga_auto_tool 的日志管线/LLM 后端/监控台基建。
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mtga_auto_tool as AUTO  # noqa: E402 复用日志管线/LLM/监控台基建
import roles  # noqa: E402 纯函数角色标签（去除/反制/战斗诡计等判定）
from mtg_tool import fetch_set_chinese_names  # noqa: E402 按系列批量中文名（逐牌查询会被限流）

RATINGS_DIR = Path(__file__).resolve().parent / "cache" / "17lands"
# shiqidi（开源 lieyanqzu/shiqidi）同源代理 17Lands 新版卡牌数据接口，schema
# 与旧 card_ratings 一致；作 17Lands 直连的兜底源（实测 2026-09-13 可用，
# HOB PremierDraft 188 张）
SHIQIDI_URL = ("https://shiqidi.lenitatis.com/api/card_data"
               "?expansion={set_code}&event_type={fmt}&time_period=ALL_TIME")
RATINGS_URL = ("https://www.17lands.com/card_ratings/data"
               "?expansion={set_code}&format={fmt}")
RATINGS_MAX_AGE_DAYS = 3

# 本地预生成评分表（社区评测 + LLM 综合）：tools/cache/draft_ratings/<SET>.json
# 背景：2026 中 17lands 直连端点失效后，胜率硬锚点一度只能依赖本离线表；
# 后经 shiqidi 同源代理恢复在线数据（见 SHIQIDI_URL / fetch_ratings，
# 实测 2026-09-13），本表仍作轮抓中喂给 LLM 的事实锚点。
DRAFT_RATINGS_DIR = Path(__file__).resolve().parent / "cache" / "draft_ratings"

GRADES = ["S", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "F"]

BUILD_RATINGS_PROMPT = """\
你是万智牌限制赛（轮抓）评测员。根据给出的单卡 oracle 文本、社区评测分数（Draftsim 0-10，
可能缺失）与系列环境摘要，给每张牌一个轮抓等级与一句中文短评。

等级尺（字母）：S=统治级炸弹/答案；A=顶级；A-=强力首抓级；B+=优质主牌；B=合格主力；
B-=可用填充；C+=边缘可用；C=弱填充；C-=几乎不进主牌；D/F=不可用。
社区分数映射（严格一一对应，不得取区间上限）：10→S，9→A，8→A-，7→B+，6→B，
5→B-，4→C+，3→C，2→C-，1→D，0→F。
默认给整字母档；+/- 档仅当该牌明确比同社区分的邻居强/弱半档时使用，且短评必须说明理由。
允许基于 oracle 文本与系列环境偏离映射一档，偏离超过一档时短评必须说明原因。
纪律：一套系列中 B+ 及以上通常不超过 25%，别把"能用"评成"优质"。

输出：严格的 JSON 数组，每张牌一个对象 {"name": "<英文名>", "grade": "<字母>", "note": "<≤40字中文短评>"}。
不要输出任何额外文字。name 必须与输入完全一致。"""

# 17Lands 字段 → 内部锚点名（值都是 0-1 小数或 None； ATA/ALSA 是顺位值）
FIELD_MAP = {
    "gih_wr": "ever_drawn_win_rate",      # GIH WR：在手胜率（主锚点）
    "ata": "avg_pick",                    # ATA：平均被抓顺位（主锚点）
    "oh_wr": "opening_hand_win_rate",     # OH WR：起手胜率（备选）
    "alsa": "avg_seen",                   # ALSA：平均可见顺位（参考）
    "gp_wr": "win_rate",                  # 进牌池胜率（参考）
}


class DraftToolError(Exception):
    pass


# ---------------------------------------------------------------- 17Lands 胜率数据
def _fetch_json(url, source, timeout=30):
    """GET JSON（UA/Accept 头）；网络/HTTP/解析失败抛 DraftToolError（带数据源名）。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise DraftToolError(f"{source} HTTP {exc.code}: {url}")
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise DraftToolError(f"{source} 请求失败: {exc}")


def _as_card_list(data, source):
    """响应可能是裸 list 或 {"data": [...]}（同 TS 客户端，两种都兼容）；
    空列表视为该源失败（17lands 直连失效后对各系列返回全 0/空）。"""
    if isinstance(data, dict):
        data = data.get("data")
    if not isinstance(data, list) or not data:
        raise DraftToolError(f"{source} 返回异常：非空列表预期，"
                             f"实际 {str(data)[:120]!r}")
    return data


def fetch_ratings(set_code, fmt="QuickDraft", timeout=30):
    """拉取 17Lands 单卡数据 → 原始 list[dict]。

    17Lands 直连优先、shiqidi 同源代理兜底（2026 中直连失效期间由代理维持数据，
    实测 2026-09-13 代理可用）；两端都失败才抛 DraftToolError（串联两端错误）。"""
    errors = []
    sources = [
        ("17Lands 直连", RATINGS_URL.format(set_code=set_code, fmt=fmt)),
        ("shiqidi 代理", SHIQIDI_URL.format(set_code=set_code, fmt=fmt)),
    ]
    for source, url in sources:
        try:
            return _as_card_list(_fetch_json(url, source, timeout), source)
        except DraftToolError as exc:
            errors.append(str(exc))
    raise DraftToolError(
        f"两个数据源均失败（{set_code}/{fmt}）: " + "；".join(errors))


def _ratings_path(set_code, fmt):
    return RATINGS_DIR / f"{set_code}_{fmt}.json"


def save_ratings(set_code, fmt, data):
    RATINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = _ratings_path(set_code, fmt)
    path.write_text(json.dumps({"fetched_ts": time.time(), "cards": data},
                               ensure_ascii=False), encoding="utf-8")
    return path


class Ratings:
    """单卡胜率查询：优先按 mtga_id（=grpId）对齐，回退牌名。
    所有胜率输出为百分数 float（None 保留），顺位原样。"""

    def __init__(self, cards):
        self.by_id = {}
        self.by_name = {}
        for c in cards:
            entry = {"name": c.get("name"), "rarity": c.get("rarity"),
                     "color": c.get("color")}
            for out, src in FIELD_MAP.items():
                v = c.get(src)
                if isinstance(v, float) and src.endswith("rate"):
                    v = round(v * 100, 1)
                entry[out] = v
            if c.get("mtga_id") is not None:
                self.by_id[c["mtga_id"]] = entry
            if c.get("name"):
                self.by_name[c["name"].split(" // ")[0]] = entry

    def lookup(self, grp_id=None, name=None):
        if grp_id is not None and grp_id in self.by_id:
            return self.by_id[grp_id]
        if name:
            return self.by_name.get(name.split(" // ")[0])
        return None


def load_ratings(set_code, fmt="QuickDraft", refresh=False):
    """读缓存；过期/缺失时自动拉取并回写。返回 (Ratings, 缓存年龄天数 float)。
    完全无数据（拉取失败且无缓存）返回 (None, None)——调用方降级为纯 LLM 模式。"""
    path = _ratings_path(set_code, fmt)
    cards = None
    age_days = None
    if path.is_file() and not refresh:
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            cards = blob.get("cards")
            age_days = (time.time() - blob.get("fetched_ts", 0)) / 86400
        except (json.JSONDecodeError, OSError):
            cards = None
    if cards is None or (age_days is not None and age_days > RATINGS_MAX_AGE_DAYS):
        if cards is not None:
            print(f"[ratings] 缓存已超 {RATINGS_MAX_AGE_DAYS} 天，刷新中...",
                  file=sys.stderr)
        try:
            fresh = fetch_ratings(set_code, fmt)
            save_ratings(set_code, fmt, fresh)
            cards = fresh
            age_days = 0.0
        except DraftToolError as exc:
            if cards is None:
                print(f"[ratings] {exc}；无缓存可用 → 降级为无胜率锚点模式",
                      file=sys.stderr)
                return None, None
            print(f"[ratings] {exc}；沿用过期缓存（{age_days:.1f} 天）",
                  file=sys.stderr)
    return Ratings(cards), age_days


# ---------------------------------------------------------------- 色组胜率（color_ratings）
COLOR_RATINGS_URL = ("https://www.17lands.com/color_ratings/data"
                     "?expansion={set_code}&event_type={fmt}"
                     "&start_date=2016-01-01&end_date={today}")
SHIQIDI_COLOR_URL = ("https://shiqidi.lenitatis.com/api/color_ratings"
                     "?expansion={set_code}&event_type={fmt}"
                     "&start_date=2016-01-01&end_date={today}")


def fetch_color_ratings(set_code, fmt="PremierDraft", timeout=30):
    """拉取色组胜率行（color_name/short_name/wins/games/is_summary）→ list[dict]。

    17Lands 直连优先、shiqidi 代理兜底（同 fetch_ratings 口径）；
    两端都失败才抛 DraftToolError（串联两端错误）。"""
    today = datetime.now().strftime("%Y-%m-%d")
    errors = []
    sources = [
        ("17Lands 直连", COLOR_RATINGS_URL.format(
            set_code=set_code, fmt=fmt, today=today)),
        ("shiqidi 代理", SHIQIDI_COLOR_URL.format(
            set_code=set_code, fmt=fmt, today=today)),
    ]
    for source, url in sources:
        try:
            return _as_card_list(_fetch_json(url, source, timeout), source)
        except DraftToolError as exc:
            errors.append(str(exc))
    raise DraftToolError(
        f"两个数据源均失败（{set_code}/{fmt} 色组）: " + "；".join(errors))


def _color_ratings_path(set_code, fmt):
    return RATINGS_DIR / f"{set_code}_{fmt}_colors.json"


def save_color_ratings(set_code, fmt, rows):
    RATINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = _color_ratings_path(set_code, fmt)
    path.write_text(json.dumps({"fetched_ts": time.time(), "rows": rows},
                               ensure_ascii=False), encoding="utf-8")
    return path


def load_color_ratings(set_code, fmt="PremierDraft", refresh=False):
    """读色组缓存；过期/缺失自动拉取回写（与 load_ratings 相同的 3 天 TTL
    与过期兜底语义）。完全无数据返回 (None, None)。"""
    path = _color_ratings_path(set_code, fmt)
    rows = None
    age_days = None
    if path.is_file() and not refresh:
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            rows = blob.get("rows")
            age_days = (time.time() - blob.get("fetched_ts", 0)) / 86400
        except (json.JSONDecodeError, OSError):
            rows = None
    if rows is None or (age_days is not None and age_days > RATINGS_MAX_AGE_DAYS):
        try:
            fresh = fetch_color_ratings(set_code, fmt)
            save_color_ratings(set_code, fmt, fresh)
            rows = fresh
            age_days = 0.0
        except DraftToolError as exc:
            if rows is None:
                print(f"[colors] {exc}；无色组缓存可用", file=sys.stderr)
                return None, None
            print(f"[colors] {exc}；沿用过期缓存（{age_days:.1f} 天）",
                  file=sys.stderr)
    return rows, age_days


# ---------------------------------------------------------------- 本地预生成评分表（社区 + LLM）
def _norm_name(name):
    return (name or "").replace("’", "'").replace("‘", "'").strip()


def find_set_cards_json(set_code):
    """自动定位 SetReview/<SET>_*/data/scryfall_*.json（取最新目录）。"""
    root = Path(__file__).resolve().parent.parent / "SetReview"
    cands = sorted(root.glob(f"{set_code}_*/data/scryfall_*.json"))
    return cands[-1] if cands else None


def load_set_cards(path):
    """Scryfall 集合 JSON → 去基本地的单卡列表（含双面牌面文本合并）。"""
    cards = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    out = []
    for c in cards:
        try:
            if int(c.get("collector_number", 0)) >= 189 and \
                    "Land" in (c.get("type_line") or ""):
                continue
        except (TypeError, ValueError):
            pass
        oracle = c.get("oracle_text") or ""
        faces = c.get("card_faces") or []
        if faces:
            oracle = " // ".join(f.get("oracle_text") or "" for f in faces)
        out.append({"name": c["name"], "mana_cost": c.get("mana_cost") or "",
                    "type_line": c.get("type_line") or "",
                    "rarity": c.get("rarity") or "", "oracle_text": oracle})
    return out


def load_community(path):
    """社区评分明细 JSON（[{name, score, note}]）→ {归一化名: entry}。"""
    if not path or not Path(path).is_file():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {_norm_name(e["name"]): e for e in data if e.get("name")}


class CardTable:
    """轮抓期逐卡锚点查询：name → {grade, note, community_score}。
    双面/历险牌同时按全名与正面名索引（实测踩坑：LLM 输出的键是全名
    "Glamdring, Foe-hammer // Gleam of Death"，查询只给正面名会漏）。"""

    def __init__(self, table):
        self._by_name = {}
        for k, v in table.items():
            self._by_name[_norm_name(k)] = v
            front = _norm_name(k.split(" // ")[0])
            self._by_name.setdefault(front, v)

    def lookup(self, name):
        if not name:
            return None
        return self._by_name.get(_norm_name(name.split(" // ")[0]))

    def __len__(self):
        return len(self._by_name)


def card_table_path(set_code):
    return DRAFT_RATINGS_DIR / f"{set_code}.json"


def load_card_table(set_code):
    """读本地预生成评分表；无则 None（驾驶舱降级为纯 LLM 模式并标注）。"""
    path = card_table_path(set_code)
    if not path.is_file():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
        return CardTable(blob.get("cards") or {})
    except (json.JSONDecodeError, OSError):
        return None


def _parse_llm_grades(text, expect_names):
    """解析 LLM 返回的 JSON 数组；宽容截取首个 [ 到末个 ]。返回 {name: entry}。"""
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        raise DraftToolError(f"LLM 输出无 JSON 数组: {text[:120]!r}")
    try:
        arr = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise DraftToolError(f"LLM JSON 解析失败: {exc}: {text[start:start+120]!r}")
    out = {}
    for item in arr:
        if not isinstance(item, dict):
            continue
        name = _norm_name(str(item.get("name") or ""))
        grade = str(item.get("grade") or "").strip()
        if not name or name not in expect_names:
            continue
        if grade not in GRADES:
            grade = ""
        out[name] = {"grade": grade or "C", "note": str(item.get("note") or "")[:120]}
    return out


def build_card_table(set_code, cards, community, context, llm_cfg,
                     batch_size=25, refresh=False, progress=print):
    """分批调 LLM 生成逐卡评分；幂等合并进既有表（--refresh 重评全部）。
    返回 {name: entry}（全量表，含本轮未触及的旧条目）。"""
    existing = {}
    path = card_table_path(set_code)
    if path.is_file() and not refresh:
        try:
            existing = json.loads(path.read_text(encoding="utf-8")).get("cards") or {}
        except (json.JSONDecodeError, OSError):
            existing = {}
    todo = [c for c in cards if _norm_name(c["name"]) not in
            {_norm_name(k) for k in existing}]
    if not todo:
        progress(f"[build] {set_code} 评分表已完整（{len(existing)} 张），无需重评")
        return existing
    progress(f"[build] 待评 {len(todo)} 张（已有 {len(existing)} 张），"
             f"每批 {batch_size} 张")
    for off in range(0, len(todo), batch_size):
        batch = todo[off:off + batch_size]
        lines = []
        for c in batch:
            key = _norm_name(c["name"])
            comm = community.get(key)
            comm_s = (f"社区评分 {comm['score']}/10：{comm['note'][:200]}"
                      if comm else "社区评分缺失")
            lines.append(f"- {c['name']} {c['mana_cost']}（{c['rarity']}，"
                         f"{c['type_line']}）：{c['oracle_text'][:400]}\n  {comm_s}")
        prompt = (f"系列环境摘要：\n{context[:2000]}\n\n"
                  f"请给以下 {len(batch)} 张牌评级：\n" + "\n".join(lines))
        expect = {_norm_name(c["name"]) for c in batch}
        last_err = None
        for attempt in (1, 2):
            try:
                text = AUTO.llm_chat(llm_cfg, [
                    {"role": "system", "content": BUILD_RATINGS_PROMPT},
                    {"role": "user", "content": prompt}], timeout=180)
                got = _parse_llm_grades(text, expect)
                break
            except (DraftToolError, AUTO.AutoToolError) as exc:
                last_err = exc
                print(f"[build] 批次 {off} 第 {attempt} 次失败: {exc}",
                      file=sys.stderr)
        else:
            raise DraftToolError(f"批次 {off} 两次均失败: {last_err}")
        missing = expect - set(got)
        for m in missing:  # 漏评的牌给占位，--refresh 时再补
            got[m] = {"grade": "", "note": "LLM 漏评，待补"}
        for c in batch:
            key = _norm_name(c["name"])
            comm = community.get(key)
            entry = dict(got[key])
            entry["rarity"] = c["rarity"]
            if comm:
                entry["community_score"] = comm["score"]
            existing[c["name"]] = entry
        progress(f"[build] 已评 {min(off + batch_size, len(todo))}/{len(todo)}")
        DRAFT_RATINGS_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(
            {"set": set_code, "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             "source": "community+llm", "cards": existing},
            ensure_ascii=False, indent=1), encoding="utf-8")
    return existing


def cmd_build_ratings(args):
    cards_path = args.cards or find_set_cards_json(args.set)
    if not cards_path or not Path(cards_path).is_file():
        print(f"[错误] 找不到 {args.set} 的 Scryfall 集合 JSON（--cards 指定或 "
              f"SetReview/{args.set}_*/data/scryfall_*.json）", file=sys.stderr)
        return 2
    cards = load_set_cards(cards_path)
    community = load_community(args.community
                               or DRAFT_RATINGS_DIR / f"{args.set}_draftsim.json")
    context = ""
    if args.context and Path(args.context).is_file():
        context = Path(args.context).read_text(encoding="utf-8")
    try:
        llm_cfg = AUTO.load_llm_config()
    except AUTO.AutoToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 5
    try:
        table = build_card_table(args.set, cards, community, context, llm_cfg,
                                 batch_size=args.batch, refresh=args.refresh)
    except DraftToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    graded = sum(1 for e in table.values() if e.get("grade"))
    print(f"[build] 完成：{args.set} 共 {len(table)} 张，{graded} 张有等级 → "
          f"{card_table_path(args.set)}")
    return 0 if graded == len(table) else 3


# ---------------------------------------------------------------- 评分表导出（SetReview 03 文档）
def render_card_ratings_md(set_code, cards_path=None, fetch_cn=True,
                           progress=lambda *a: print(*a, file=sys.stderr)):
    """预生成评分表 + Scryfall 集合 JSON + mtgch 中文名 → 03_CardRatings.md 文本。
    按收藏编号排序；基本地列库存不评级；中文名缺失显式标注。"""
    table = load_card_table(set_code)
    if table is None:
        raise DraftToolError(f"评分表不存在: {card_table_path(set_code)}"
                             f"（先跑 build-ratings --set {set_code}）")
    cards_path = cards_path or find_set_cards_json(set_code)
    if not cards_path:
        raise DraftToolError(f"找不到 {set_code} 的 Scryfall 集合 JSON")
    raw = json.loads(Path(cards_path).read_text(encoding="utf-8-sig"))
    raw.sort(key=lambda c: int(c.get("collector_number") or 0))
    # 中文名：按系列批量端点一次拉全（逐牌查询会被 mtgch 429 限流，实测踩坑）；
    # 批量缺口再逐牌兜底
    cn_map = {}
    if fetch_cn:
        cn_map, err = fetch_set_chinese_names(set_code)
        if cn_map is None:
            progress(f"[export] 系列中文名批量拉取失败（{err}），逐牌兜底")
            cn_map = {}
        else:
            progress(f"[export] 系列中文名 {len(cn_map)} 条")
    lines = [f"# {set_code} 全卡逐张评级（轮抓校准版）", ""]
    lines.append("> 评级来源：社区评测（Draftsim 0-10）+ LLM 综合（oracle 文本与"
                 "系列环境摘要），离线预生成表 `tools/cache/draft_ratings/"
                 f"{set_code}.json`；与 C1 纸面初评冲突处以本表为准。"
                 "中文名来自 mtgch，缺失显式标注。")
    lines.append("")
    lines.append("| # | English | 中文 | 稀有度 | 评级 | 社区分 | 短评 |")
    lines.append("|---:|---|---|---|---|---|---|")
    graded = 0
    for c in raw:
        num = c.get("collector_number")
        name = c["name"]
        if "Basic Land" in (c.get("type_line") or ""):
            lines.append(f"| {num} | {name} | - | {c.get('rarity')} | - | - |"
                         " 基本地，库存牌 |")
            continue
        entry = table.lookup(name)
        cn = "-"
        if fetch_cn:
            cn = cn_map.get(name.strip().lower()) \
                or cn_map.get(name.split(" // ")[0].strip().lower())
            if not cn:
                cn_name, _err = AUTO.fetch_chinese_name(name.split(" // ")[0])
                cn = cn_name or "（缺）"
        grade = entry["grade"] if entry else "?"
        score = entry.get("community_score") if entry else None
        note = (entry.get("note") if entry else "未评级") or ""
        note = note.replace("|", "/")
        lines.append(f"| {num} | {name} | {cn} | {c.get('rarity')} | {grade} |"
                     f" {score if score is not None else '-'} | {note} |")
        graded += 1
    lines.append("")
    lines.append(f"覆盖：{graded} 张非基本地已评级；基础地列入库存不评级。")
    return "\n".join(lines) + "\n"


def cmd_export_md(args):
    try:
        text = render_card_ratings_md(args.set, args.cards,
                                      fetch_cn=not args.no_cn)
    except DraftToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else None
    if out is None:
        root = Path(__file__).resolve().parent.parent / "SetReview"
        cands = sorted(root.glob(f"{args.set}_*"))
        if not cands:
            print(f"[错误] 找不到 SetReview/{args.set}_* 目录（--out 指定输出）",
                  file=sys.stderr)
            return 2
        out = cands[-1] / "03_CardRatings.md"
    out.write_text(text, encoding="utf-8")
    print(f"[export] 已写入 {out}（{len(text.splitlines())} 行）")
    return 0


# ---------------------------------------------------------------- 开抓前环境简报（brief）
BRIEF_FLASH_PLAY_RATE = 0.30   # 留费注意点：瞬发/闪现牌的出场率阈值
AGGRO_PAIRS = ("WR", "RW", "WU", "RG", "WB")  # 快攻色组（速度判定用）
_DAMAGE_RE = re.compile(r"deals?\s+(\d+)\s+damage")
_MINUS_RE = re.compile(r"gets?\s+-(\d+)/-(\d+)")


def load_snapshot_raw(set_code):
    """SetReview 最新目录的 Scryfall 全牌快照原始 list（保留 cmc/power/toughness/
    keywords，load_set_cards 会丢这些字段）。缺快照抛 DraftToolError。"""
    path = find_set_cards_json(set_code)
    if not path:
        raise DraftToolError(
            f"找不到 {set_code} 的 Scryfall 快照（先跑 "
            f"set_preview_tool.py fetch {set_code.lower()}）")
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _snap_text(c):
    text = c.get("oracle_text") or ""
    faces = c.get("card_faces") or []
    if faces:
        text = " // ".join(f.get("oracle_text") or "" for f in faces)
    return text


def _is_token_card(c):
    return (c.get("layout") or "") in ("token", "double_faced_token")


def _is_creature_card(c):
    return "Creature" in (c.get("type_line") or "") and not _is_token_card(c)


def _int_stat(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse_damage_lines(cards):
    """从快照 oracle 文本解析伤害线："deals N damage" 与 "gets -N/-M"（按减防
    数值 M 计），只取 1..5 → {数值: [牌名]}。非伤害句（抓牌、"等于其力量"
    等无数值表述）不落线。"""
    lines = {}
    for c in cards:
        if _is_token_card(c):
            continue
        text = _snap_text(c)
        found = {int(m.group(1)) for m in _DAMAGE_RE.finditer(text)}
        found |= {int(m.group(2)) for m in _MINUS_RE.finditer(text)}
        for n in sorted(found):
            if 1 <= n <= 5:
                lines.setdefault(n, []).append(c["name"])
    return lines


def toughness_coverage(cards, lines):
    """每条伤害线 N → 快照生物中防御力 <= N 的占比。
    返回 {N: (covered, total, pct)}；无生物时 pct 为 None。"""
    toughs = [t for t in (_int_stat(c.get("toughness"))
                          for c in cards if _is_creature_card(c))
              if t is not None]
    total = len(toughs)
    out = {}
    for n in sorted(lines):
        covered = sum(1 for t in toughs if t <= n)
        out[n] = (covered, total, round(covered / total * 100, 1) if total else None)
    return out


def creature_baseline(cards):
    """普通（common）生物按 cmc 2–5 的中位力量/防御力基准
    → {cmc: (med_power, med_toughness, count)}。"""
    out = {}
    for cmc in range(2, 6):
        powers, toughs = [], []
        for c in cards:
            if not _is_creature_card(c) or (c.get("rarity") or "") != "common":
                continue
            if int(c.get("cmc") or -1) != cmc:
                continue
            p, t = _int_stat(c.get("power")), _int_stat(c.get("toughness"))
            if p is not None and t is not None:
                powers.append(p)
                toughs.append(t)
        if powers:
            out[cmc] = (_percentile(powers, 0.5), _percentile(toughs, 0.5),
                        len(powers))
    return out


def _brief_num(v, digits=1, suffix=""):
    return f"{v:.{digits}f}{suffix}" if isinstance(v, (int, float)) else "-"


def build_brief(set_code, fmt="PremierDraft", min_gih=500):
    """开抓前环境简报：八节（速度/强度/先后手/去除密度/去除线/留费注意点/
    生物强度/猝死情况）。返回 (report_md, console_summary)。

    快照或 17Lands 单卡数据缺失抛 DraftToolError；色组数据缺失降级标注。
    不伪造：先后手无公开聚合数据只给经验规则；猝死节全部是代理指标。"""
    snap_path = find_set_cards_json(set_code)
    cards = load_snapshot_raw(set_code)
    ratings, age = load_ratings(set_code, fmt)
    if ratings is None:
        raise DraftToolError(f"无 17Lands 单卡数据（{set_code}/{fmt}）")
    cache = json.loads(_ratings_path(set_code, fmt).read_text(encoding="utf-8"))
    raw = cache.get("cards") or []
    fetched = datetime.fromtimestamp(
        cache.get("fetched_ts", 0)).strftime("%Y-%m-%d")
    color_rows, _color_age = load_color_ratings(set_code, fmt)

    lr_idx = {}
    for c in raw:
        name = c.get("name") or ""
        lr_idx.setdefault(_norm_name(name), c)
        lr_idx.setdefault(_norm_name(name.split(" // ")[0]), c)

    def lr_of(c):
        e = lr_idx.get(_norm_name(c.get("name"))) or lr_idx.get(
            _norm_name((c.get("name") or "").split(" // ")[0]))
        if not e:
            return None
        wr = e.get("ever_drawn_win_rate")
        return {"gih_wr": round(wr * 100, 1) if isinstance(wr, (int, float))
                else None,
                "play_rate": e.get("play_rate"), "ata": e.get("avg_pick"),
                "gih_cnt": e.get("ever_drawn_game_count") or 0}

    def tags_of(c):
        return roles.classify_card(dict(c, oracle_text=_snap_text(c)))

    # ---- 速度：快攻色组胜率 + play_rate 加权平均 cmc（非地牌）+ 低费高出场
    pairs = []
    if color_rows:
        for r in color_rows:
            if r.get("is_summary") or not r.get("games"):
                continue
            pairs.append({"pair": r.get("short_name") or r.get("color_name"),
                          "wr": round(r["wins"] / r["games"] * 100, 1),
                          "games": r["games"]})
        pairs.sort(key=lambda p: -p["wr"])
    aggro = [p for p in pairs if p["pair"] in AGGRO_PAIRS]
    aggro_wr = None
    if aggro:
        aggro_wr = round(sum(p["wr"] * p["games"] for p in aggro)
                         / sum(p["games"] for p in aggro), 1)
    wsum = wnum = 0.0
    played = []
    for c in cards:
        e = lr_of(c)
        cmc = c.get("cmc")
        if not e or cmc is None or "Land" in (c.get("type_line") or ""):
            continue
        pr = e["play_rate"]
        if isinstance(pr, (int, float)) and pr > 0:
            wsum += pr * cmc
            wnum += pr
            played.append((c, e))
    wcmc = round(wsum / wnum, 2) if wnum else None
    cheap_top = sorted(((c, e) for c, e in played
                        if (c.get("cmc") or 99) <= 2),
                       key=lambda ce: -(ce[1]["play_rate"] or 0))[:5]
    signals = []
    if aggro_wr is not None:
        signals.append("快" if aggro_wr >= 52.0 else ("慢" if aggro_wr <= 49.0
                                                     else "中"))
    if wcmc is not None:
        signals.append("快" if wcmc <= 2.8 else ("慢" if wcmc >= 3.2 else "中"))
    if not signals:
        verdict = "数据不足"
    elif "快" in signals:
        verdict = "快"
    elif all(s == "慢" for s in signals):
        verdict = "慢"
    else:
        verdict = "中"

    # ---- 强度：可靠样本（#GIH >= min_gih）的 GIH WR 分布与顶流
    reliable = []
    for c in cards:
        e = lr_of(c)
        if e and e["gih_wr"] is not None and e["gih_cnt"] >= min_gih:
            reliable.append((c, e))
    wrs = [e["gih_wr"] for _c, e in reliable]
    bombs = [ce for ce in reliable if ce[1]["gih_wr"] >= 58.0]
    median_wr = _percentile(wrs, 0.5)
    top10 = sorted(reliable, key=lambda ce: -ce[1]["gih_wr"])[:10]

    # ---- 去除密度：普通/非普通 removal 按颜色与稀有度；hard 与 burn 分列
    removal_colors = {}
    hard, burn = [], []
    for c in cards:
        if _is_token_card(c) or (c.get("rarity") or "") not in ("common",
                                                                "uncommon"):
            continue
        tags = tags_of(c)
        if not roles.has_root(tags, "removal"):
            continue
        colors = c.get("colors") or []
        color = colors[0] if len(colors) == 1 else ("多色" if colors else "无色")
        slot = removal_colors.setdefault(color, {"common": 0, "uncommon": 0,
                                                 "wrs": []})
        slot[c["rarity"]] += 1
        e = lr_of(c)
        if e and e["gih_wr"] is not None:
            slot["wrs"].append(e["gih_wr"])
        if any(roles.has_mechanic(tags, m)
               for m in ("destroy", "exile", "board_wipe")):
            hard.append(c["name"])
        if roles.has_mechanic(tags, "damage"):
            burn.append(c["name"])
    removal_total = sum(s["common"] + s["uncommon"]
                        for s in removal_colors.values())

    # ---- 去除线 / 留费注意点 / 生物强度 / 猝死代理
    dmg_lines = parse_damage_lines(cards)
    coverage = toughness_coverage(cards, dmg_lines)
    flash_watch = []
    for c in cards:
        if _is_token_card(c) or (c.get("rarity") or "") not in ("common",
                                                                "uncommon"):
            continue
        types = (c.get("type_line") or "").lower()
        kws = [k.lower() for k in (c.get("keywords") or [])]
        if "instant" not in types and "flash" not in kws:
            continue
        e = lr_of(c)
        if e and isinstance(e["play_rate"], (int, float)) \
                and e["play_rate"] >= BRIEF_FLASH_PLAY_RATE:
            flash_watch.append((c, e))
    flash_watch.sort(key=lambda ce: -(ce[1]["gih_wr"] or 0))
    baseline = creature_baseline(cards)
    top_creatures = sorted((ce for ce in reliable if _is_creature_card(ce[0])),
                           key=lambda ce: -ce[1]["gih_wr"])[:10]
    haste_wrs, aggro_wrs = [], []
    for c in cards:
        kws = [k.lower() for k in (c.get("keywords") or [])]
        e = lr_of(c)
        if not e or e["gih_wr"] is None:
            continue
        if "haste" in kws:
            haste_wrs.append(e["gih_wr"])
        if roles.has_root(tags_of(c), "aggro"):
            aggro_wrs.append(e["gih_wr"])
    haste_wr = round(sum(haste_wrs) / len(haste_wrs), 1) if haste_wrs else None
    aggro_tag_wr = round(sum(aggro_wrs) / len(aggro_wrs), 1) \
        if aggro_wrs else None
    fastest = pairs[0] if pairs else None
    commons = [c for c in cards if _is_creature_card(c)
               and (c.get("rarity") or "") == "common"]
    low_curve = [c for c in commons if (c.get("cmc") or 99) <= 2]
    low_curve_pct = round(len(low_curve) / len(commons) * 100, 1) \
        if commons else None

    # ---------------------------------------------------------------- 渲染
    lines = [
        f"# {set_code} {fmt} 开抓前环境简报",
        "",
        f"> 口径：event_type={fmt}；单卡数据 time_period=ALL_TIME、抓取 {fetched}"
        f"（缓存 {_ratings_path(set_code, fmt)}，年龄 {age:.1f} 天，"
        f"{len(raw)} 张）；色组数据 2016-01-01..{datetime.now():%Y-%m-%d}"
        + (f"（{len(color_rows)} 行）" if color_rows else "（不可用，已降级标注）")
        + f"；牌面快照 {snap_path}（{len(cards)} 张）；"
        f"胜率类指标只用 #GIH >= {min_gih} 的可靠样本（{len(reliable)} 张）。",
        "",
        f"## 速度（判定：{verdict}）",
        "",
        f"- 快攻色组（{'/'.join(AGGRO_PAIRS)}）合并胜率："
        f"{_brief_num(aggro_wr, suffix='%')}"
        f"（{len(aggro)} 组；色组数据{'缺失' if not color_rows else '见下表'}）",
        f"- play_rate 加权平均 cmc（非地牌）：{_brief_num(wcmc, 2)}",
        f"- 判定规则：快攻色组 WR >= 52% 或加权 cmc <= 2.8 偏快；"
        f"WR <= 49% 且加权 cmc >= 3.2 偏慢；其余为中。以上为启发式阈值。",
        "",
        "| 色组 | 胜率 | 场次 |",
        "|---|---:|---:|",
    ]
    lines += [f"| {p['pair']} | {p['wr']}% | {p['games']} |" for p in pairs] \
        or ["| （无） | | |"]
    lines += ["", "低费（cmc<=2）高出场牌 TOP 5：", "",
              "| 牌 | cmc | play_rate | GIH WR |", "|---|---:|---:|---:|"]
    lines += [f"| {c['name']} | {c.get('cmc')} | "
              f"{_brief_num((e['play_rate'] or 0) * 100, suffix='%')} | "
              f"{_brief_num(e['gih_wr'], suffix='%')} |"
              for c, e in cheap_top] or ["| （无） | | | |"]
    lines += [
        "",
        "## 强度",
        "",
        f"- 可靠样本 {len(reliable)} 张；炸弹（GIH WR ≥ 58%）{len(bombs)} 张；"
        f"中位数 {_brief_num(median_wr, suffix='%')}；"
        f"顶底差距 {_brief_num((max(wrs) - min(wrs)) if wrs else None, suffix='%')}",
        "",
        "| # | 牌 | GIH WR | ATA | #GIH |",
        "|---:|---|---:|---:|---:|",
    ]
    lines += [f"| {i} | {c['name']} | {e['gih_wr']} | "
              f"{_brief_num(e['ata'])} | {e['gih_cnt']} |"
              for i, (c, e) in enumerate(top10, 1)] or ["| （无） | | | | |"]
    lines += [
        "",
        "## 先后手",
        "",
        "> **数据缺口：无公开先后手聚合数据**——17Lands/shiqidi 公开接口均不"
        "提供先后手胜率拆分，本节不给出任何数字。",
        "",
        "经验规则（与速度节联动，非数据结论）：环境越快，先手权重越高，"
        "轮抓与备牌更偏向抢节奏；环境越慢，后手多抓一张牌的价值上升，"
        "长盘资源配置优先级提高。",
        "",
        "## 去除密度",
        "",
        f"- 普通/非普通去除共 {removal_total} 张；hard removal"
        f"（destroy/exile/扫场）{len(hard)} 张，burn（伤害类）{len(burn)} 张",
        "",
        "| 颜色 | 普通 | 非普通 | 平均 GIH WR（去除质量） |",
        "|---|---:|---:|---:|",
    ]
    for color in ("W", "U", "B", "R", "G", "多色", "无色"):
        s = removal_colors.get(color)
        if not s:
            continue
        mean_wr = round(sum(s["wrs"]) / len(s["wrs"]), 1) if s["wrs"] else None
        lines.append(f"| {color} | {s['common']} | {s['uncommon']} | "
                     f"{_brief_num(mean_wr, suffix='%')} |")
    lines += [
        "",
        f"- hard removal：{', '.join(hard) if hard else '（无）'}",
        f"- burn：{', '.join(burn) if burn else '（无）'}",
        "",
        "## 去除线",
        "",
        "从 oracle 解析 deals N damage 与 -N/-M（按 M 计，N/M 取 1..5），"
        "对照快照生物防御力分布：",
        "",
        "| 伤害线 | 覆盖生物 | 占比 | 代表牌 |",
        "|---:|---:|---:|---|",
    ]
    lines += [f"| {n} 点 | {cov[0]}/{cov[1]} | "
              f"{_brief_num(cov[2], suffix='%')} | "
              f"{', '.join(dmg_lines[n][:3])} |"
              for n, cov in coverage.items()] or ["| （无） | | | |"]
    lines += [
        "",
        "## 留费注意点",
        "",
        f"普通/非普通瞬发/闪现牌中 play_rate ≥ {BRIEF_FLASH_PLAY_RATE:.0%} 者，"
        "按 GIH WR 排序——对手留费开放时最可能持有的牌：",
        "",
        "| 牌 | 费用 | GIH WR | play_rate |",
        "|---|---|---:|---:|",
    ]
    lines += [f"| {c['name']} | {c.get('mana_cost') or '-'} | "
              f"{_brief_num(e['gih_wr'], suffix='%')} | "
              f"{_brief_num((e['play_rate'] or 0) * 100, suffix='%')} |"
              for c, e in flash_watch] or ["| （无） | | | |"]
    lines += [
        "",
        "## 生物强度",
        "",
        "普通（common）生物按 cmc 2–5 的中位力量/防御力基准：",
        "",
        "| cmc | 中位力量 | 中位防御力 | 样本 |",
        "|---:|---:|---:|---:|",
    ]
    lines += [f"| {cmc} | {p} | {t} | {n} |"
              for cmc, (p, t, n) in sorted(baseline.items())] \
        or ["| （无） | | | |"]
    lines += ["", "GIH WR 最高生物 TOP 10：", "",
              "| 牌 | GIH WR | ATA | #GIH |", "|---|---:|---:|---:|"]
    lines += [f"| {c['name']} | {e['gih_wr']} | {_brief_num(e['ata'])} | "
              f"{e['gih_cnt']} |" for c, e in top_creatures] \
        or ["| （无） | | | |"]
    lines += [
        "",
        "## 猝死情况",
        "",
        "> **以下为代理指标（proxy）**：公开接口没有对局时长/回合数数据，"
        "无法直接度量猝死率，只能用速度相关代理推断。",
        "",
        f"- haste 牌平均 GIH WR：{_brief_num(haste_wr, suffix='%')}"
        f"（{len(haste_wrs)} 张）",
        f"- aggro 标签牌平均 GIH WR：{_brief_num(aggro_tag_wr, suffix='%')}"
        f"（{len(aggro_wrs)} 张）",
        f"- 最快色组：{fastest['pair'] + ' ' + str(fastest['wr']) + '%' if fastest else '-'}",
        f"- 低曲线密度（普通生物 cmc<=2 占比）：{_brief_num(low_curve_pct, suffix='%')}",
        "",
    ]
    report_md = "\n".join(lines)

    cov3 = coverage.get(3)
    summary = [
        f"{set_code}/{fmt} 环境简报（单卡数据 {fetched}，{len(raw)} 张；"
        f"快照 {len(cards)} 张）",
        f"速度判定：{verdict}（快攻色组 WR {_brief_num(aggro_wr, suffix='%')}，"
        f"加权平均 cmc {_brief_num(wcmc, 2)}）",
        f"强度：炸弹(≥58%) {len(bombs)} 张，中位 "
        f"{_brief_num(median_wr, suffix='%')}"
        + (f"，顶流 {top10[0][0]['name']} {top10[0][1]['gih_wr']}%"
           if top10 else ""),
        "先后手：无公开聚合数据（报告内为经验规则，非数字结论）",
        f"去除：普通/非普通 {removal_total} 张（hard {len(hard)} / "
        f"burn {len(burn)}）"
        + (f"；3 点覆盖 {_brief_num(cov3[2], suffix='%')} 生物" if cov3 else ""),
        f"留费注意：{', '.join(c['name'] for c, _e in flash_watch[:3]) or '（无）'}",
        f"猝死代理：haste 牌均 WR {_brief_num(haste_wr, suffix='%')}，最快色组 "
        f"{fastest['pair'] + ' ' + str(fastest['wr']) + '%' if fastest else '-'}"
        "（代理指标，非对局时长）",
    ]
    return report_md, summary


def cmd_brief(args):
    set_code = args.set.upper()
    try:
        report_md, summary = build_brief(set_code, args.fmt,
                                         min_gih=args.min_gih)
    except DraftToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else AUDIT_DIR / (
        f"FormatBrief_{set_code}_{args.fmt}_"
        f"{datetime.now().strftime('%Y%m%d')}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report_md, encoding="utf-8")
    for line in summary:
        print(f"[brief] {line}")
    print(f"[brief] 报告 → {out}")
    return 0


# ---------------------------------------------------------------- 回归检查（regress）
AUDIT_DIR = Path(__file__).resolve().parent.parent / "AuditReport"
# 等级 → 质量分（S 最高 11，F 最低 1），用于秩相关与错配比较
GRADE_SCORE = {g: len(GRADES) - i for i, g in enumerate(GRADES)}


def _ranks(values):
    """升序平均秩（平局取均值），最小值秩 1。"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return 0.0
    return cov / (vx * vy) ** 0.5


def spearman(pairs):
    """Spearman 等级相关：平局平均秩 + 秩上 Pearson。pairs=[(x, y), ...]；
    少于 2 对返回 None。"""
    if len(pairs) < 2:
        return None
    xs = _ranks([p[0] for p in pairs])
    ys = _ranks([p[1] for p in pairs])
    return _pearson(xs, ys)


def _percentile(values, q):
    """线性插值分位数；空序列返回 None。"""
    s = sorted(values)
    if not s:
        return None
    idx = (len(s) - 1) * q
    lo = int(idx)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def join_table_ratings(table_map, raw_cards):
    """我方评分表 {name: entry} × 17Lands 原始记录按归一化牌名 join
    （双面牌对齐正面名，同 CardTable 规则）。
    返回 (joined, missing)：missing 为 17Lands 有而我方无评级的牌（漏评，
    不计入指标）。joined 条目含 name/grade/note/gih_wr(百分数)/ata/gih_cnt。"""
    ours = {}
    for k, v in table_map.items():
        ours.setdefault(_norm_name(k), (k, v))
        ours.setdefault(_norm_name(k.split(" // ")[0]), (k, v))
    joined, missing = [], []
    seen = set()
    for c in raw_cards:
        name = c.get("name") or ""
        hit = ours.get(_norm_name(name)) \
            or ours.get(_norm_name(name.split(" // ")[0]))
        if hit is None:
            missing.append(name)
            continue
        our_name, entry = hit
        if our_name in seen:
            continue
        seen.add(our_name)
        wr = c.get("ever_drawn_win_rate")
        joined.append({
            "name": our_name,
            "grade": entry.get("grade") or "",
            "note": entry.get("note"),
            "gih_wr": round(wr * 100, 1) if isinstance(wr, (int, float)) else None,
            "ata": c.get("avg_pick"),
            "gih_cnt": c.get("ever_drawn_game_count") or 0,
        })
    return joined, sorted(missing)


def grade_stats(joined, min_gih=500):
    """分档聚合：按 GRADES 顺序输出 {grade, count, mean_gih_wr, mean_ata,
    small_sample}；空档跳过；小样本（#GIH < min_gih）单独计数。"""
    rows = []
    for g in GRADES:
        entries = [j for j in joined if j["grade"] == g]
        if not entries:
            continue
        wrs = [j["gih_wr"] for j in entries if j["gih_wr"] is not None]
        atas = [j["ata"] for j in entries if j["ata"] is not None]
        rows.append({
            "grade": g, "count": len(entries),
            "mean_gih_wr": round(sum(wrs) / len(wrs), 1) if wrs else None,
            "mean_ata": round(sum(atas) / len(atas), 2) if atas else None,
            "small_sample": sum(1 for j in entries if j["gih_cnt"] < min_gih),
        })
    return rows


def find_mismatches(joined, min_gih=500, top=10):
    """错配清单：高估 = 我方 ≥B+ 且 GIH WR 低于系列中位数（按差距排序）；
    低估 = 我方 ≤C 且 GIH WR 进入系列前 25%（按胜率排序）。
    阈值与候选都只用 #GIH >= min_gih 的可靠样本。
    返回 (overrated, underrated, median, q3)。"""
    pool = [j for j in joined if j["grade"] in GRADE_SCORE
            and j["gih_wr"] is not None and j["gih_cnt"] >= min_gih]
    median = _percentile([j["gih_wr"] for j in pool], 0.5)
    q3 = _percentile([j["gih_wr"] for j in pool], 0.75)
    if median is None:
        return [], [], None, None
    over = [j for j in pool
            if GRADE_SCORE[j["grade"]] >= GRADE_SCORE["B+"]
            and j["gih_wr"] < median]
    over.sort(key=lambda j: j["gih_wr"])            # 低于中位数最多者在前
    under = [j for j in pool
             if GRADE_SCORE[j["grade"]] <= GRADE_SCORE["C"]
             and j["gih_wr"] >= q3]
    under.sort(key=lambda j: -j["gih_wr"])
    return over[:top], under[:top], median, q3


def cmd_regress(args):
    set_code = args.set.upper()
    path = card_table_path(set_code)
    if not path.is_file():
        print(f"[错误] 评分表不存在: {path}（先跑 set_preview_tool.py rate "
              f"{set_code.lower()} 或 mtga_draft_tool.py build-ratings）",
              file=sys.stderr)
        return 2
    try:
        table_map = json.loads(path.read_text(encoding="utf-8")).get("cards") or {}
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[错误] 评分表损坏: {path}: {exc}", file=sys.stderr)
        return 2

    ratings, age = load_ratings(set_code, args.fmt)
    if ratings is None:
        print(f"[错误] 无 17Lands 数据（{set_code}/{args.fmt}），无法回归",
              file=sys.stderr)
        return 2
    cache = json.loads(_ratings_path(set_code, args.fmt).read_text(encoding="utf-8"))
    raw_cards = cache.get("cards") or []
    fetched = datetime.fromtimestamp(cache.get("fetched_ts", 0)
                                     ).strftime("%Y-%m-%d")

    joined, missing = join_table_ratings(table_map, raw_cards)
    placeholders = sorted(j["name"] for j in joined if not j["grade"])
    graded = [j for j in joined if j["grade"] in GRADE_SCORE]
    small = sorted(j["name"] for j in graded if j["gih_cnt"] < args.min_gih)
    corr_pool = [j for j in graded if j["gih_cnt"] >= args.min_gih]
    pairs_wr = [(GRADE_SCORE[j["grade"]], j["gih_wr"])
                for j in corr_pool if j["gih_wr"] is not None]
    pairs_ata = [(GRADE_SCORE[j["grade"]], j["ata"])
                 for j in corr_pool if j["ata"] is not None]
    sp_wr = spearman(pairs_wr)
    sp_ata = spearman(pairs_ata)
    stats = grade_stats(joined, args.min_gih)
    over, under, median, q3 = find_mismatches(joined, args.min_gih)

    def fmt_sp(v):
        return f"{v:+.3f}" if v is not None else "样本不足"

    def mismatch_rows(rows):
        return [f"| {j['name']} | {j['grade']} | "
                f"{j['gih_wr'] if j['gih_wr'] is not None else '-'} | "
                f"{round(j['ata'], 1) if j['ata'] is not None else '-'} | "
                f"{j['gih_cnt']} |"
                for j in rows]

    lines = [
        f"# {set_code} {args.fmt} 评级回归检查",
        "",
        f"> 口径：event_type={args.fmt}，time_period=ALL_TIME；数据抓取 {fetched}"
        f"（缓存 {_ratings_path(set_code, args.fmt)}，年龄 {age:.1f} 天）；"
        f"17Lands {len(raw_cards)} 张，我方评分表 {len(table_map)} 张，"
        f"join {len(joined)} 张，漏评 {len(missing)} 张，占位跳过 "
        f"{len(placeholders)} 张；相关系数与错配排名剔除 #GIH < {args.min_gih} "
        f"的小样本 {len(small)} 张。",
        "",
        "## 分档聚合（小样本计入表内，行尾 * 标记含小样本的档）",
        "",
        "| 等级 | 张数 | 平均 GIH WR | 平均 ATA |",
        "|---|---:|---:|---:|",
    ]
    for r in stats:
        wr = f"{r['mean_gih_wr']}" if r["mean_gih_wr"] is not None else "-"
        ata = f"{r['mean_ata']}" if r["mean_ata"] is not None else "-"
        mark = " *" if r["small_sample"] else ""
        lines.append(f"| {r['grade']} | {r['count']} | {wr} | {ata} |{mark}")
    lines += [
        "",
        "## Spearman 等级相关（等级质量分 S=11…F=1）",
        "",
        f"- 等级 vs GIH WR：{fmt_sp(sp_wr)}（n={len(pairs_wr)}；正相关 = "
        f"等级越高胜率越高，符合预期）",
        f"- 等级 vs ATA：{fmt_sp(sp_ata)}（n={len(pairs_ata)}；负相关 = "
        f"等级越高被抓顺位越早，符合预期）",
        "",
        f"## 高估 TOP 10（我方 ≥B+ 且 GIH WR 低于系列中位数 "
        f"{median if median is not None else '-'}%）",
        "",
        "| 牌 | 等级 | GIH WR | ATA | #GIH |",
        "|---|---|---:|---:|---:|",
    ]
    lines += mismatch_rows(over) or ["| （无） | | | | |"]
    lines += [
        "",
        f"## 低估 TOP 10（我方 ≤C 且 GIH WR 进入系列前 25%（≥ "
        f"{q3 if q3 is not None else '-'}%））",
        "",
        "| 牌 | 等级 | GIH WR | ATA | #GIH |",
        "|---|---|---:|---:|---:|",
    ]
    lines += mismatch_rows(under) or ["| （无） | | | | |"]
    lines += ["", f"## 漏评清单（17Lands 有、我方无评级，{len(missing)} 张）", ""]
    lines += [f"- {n}" for n in missing] or ["（无）"]
    if placeholders:
        lines += ["", f"## 占位跳过（评分表 grade 为空，{len(placeholders)} 张）", ""]
        lines += [f"- {n}" for n in placeholders]
    lines += [
        "", "## 小样本说明", "",
        f"ever_drawn_game_count < {args.min_gih} 的牌保留在分档聚合表内（* 标记），"
        f"但不参与 Spearman 相关系数与高估/低估排名"
        + (f"：{', '.join(small)}" if small else "；本次无小样本牌") + "。",
        "",
    ]

    out = Path(args.out) if args.out else AUDIT_DIR / (
        f"RatingRegression_{set_code}_{args.fmt}_"
        f"{datetime.now().strftime('%Y%m%d')}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")

    print(f"[regress] {set_code}/{args.fmt}: join {len(joined)} 张，"
          f"漏评 {len(missing)}，占位 {len(placeholders)}，小样本 {len(small)}")
    print(f"[regress] Spearman 等级 vs GIH WR = {fmt_sp(sp_wr)}，"
          f"vs ATA = {fmt_sp(sp_ata)}")
    if over:
        print(f"[regress] 最高估: {over[0]['name']}（{over[0]['grade']}，"
              f"GIH WR {over[0]['gih_wr']}）")
    if under:
        print(f"[regress] 最低估: {under[0]['name']}（{under[0]['grade']}，"
              f"GIH WR {under[0]['gih_wr']}）")
    print(f"[regress] 报告 → {out}")
    return 0


# ---------------------------------------------------------------- CLI
def cmd_ratings(args):
    try:
        ratings, age = load_ratings(args.set, args.format, refresh=args.refresh)
    except DraftToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    if ratings is None:
        return 2
    n = len(ratings.by_name)
    anchor = sum(1 for e in ratings.by_name.values() if e["gih_wr"] is not None)
    print(f"[ratings] {args.set}/{args.format}: {n} 张（{anchor} 张有 GIH WR），"
          f"缓存年龄 {age:.1f} 天 → {_ratings_path(args.set, args.format)}")
    top = sorted((e for e in ratings.by_name.values() if e["gih_wr"] is not None),
                 key=lambda e: -e["gih_wr"])[:args.top]
    for e in top:
        ata = "-" if e["ata"] is None else f"{e['ata']:.1f}"
        print(f"  {e['gih_wr']:5.1f}%  ATA {ata:>4}  {e['name']}")
    return 0


def build_parser():
    import argparse
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("ratings", help="拉取/刷新 17Lands 单卡胜率缓存")
    pr.add_argument("--set", required=True, help="系列代码（如 FDN、OM1）")
    pr.add_argument("--format", default="QuickDraft",
                    help="17Lands 赛制口径（默认 QuickDraft，备选 PremierDraft）")
    pr.add_argument("--refresh", action="store_true", help="强制重新拉取")
    pr.add_argument("--top", type=int, default=10, help="打印 GIH WR 前 N 名")
    pr.set_defaults(func=cmd_ratings)

    pb = sub.add_parser("build-ratings",
                        help="社区评测 + LLM 离线预生成逐卡评分表（轮抓锚点）")
    pb.add_argument("--set", required=True, help="系列代码（如 HOB）")
    pb.add_argument("--cards", help="Scryfall 集合 JSON（缺省自动找 SetReview 最新目录）")
    pb.add_argument("--community",
                    help="社区评分 JSON（缺省 cache/draft_ratings/<SET>_draftsim.json）")
    pb.add_argument("--context", help="系列环境摘要 md（如 02_LimitedEnvironment.md）")
    pb.add_argument("--batch", type=int, default=25, help="每批评级张数（默认 25）")
    pb.add_argument("--refresh", action="store_true", help="全部重评（默认只补未评）")
    pb.set_defaults(func=cmd_build_ratings)

    pe = sub.add_parser("export-md",
                        help="评分表 → SetReview 03_CardRatings.md（含 mtgch 中文名）")
    pe.add_argument("--set", required=True, help="系列代码（如 HOB）")
    pe.add_argument("--cards", help="Scryfall 集合 JSON（缺省自动找 SetReview）")
    pe.add_argument("--out", help="输出路径（缺省 SetReview/<SET>_最新目录/03_CardRatings.md）")
    pe.add_argument("--no-cn", action="store_true", help="跳过中文名抓取")
    pe.set_defaults(func=cmd_export_md)

    pg = sub.add_parser("regress",
                        help="评级表 × 17Lands 数据回归检查（分档均值/Spearman/错配）")
    pg.add_argument("--set", required=True, help="系列代码（如 TDM）")
    pg.add_argument("--fmt", default="PremierDraft",
                    help="17Lands event_type 口径（默认 PremierDraft）")
    pg.add_argument("--out", help="报告输出路径（缺省 AuditReport/"
                                  "RatingRegression_<SET>_<fmt>_<日期>.md）")
    pg.add_argument("--min-gih", type=int, default=500,
                    help="GIH 样本量下限（默认 500；低于则剔除出相关系数与错配排名）")
    pg.set_defaults(func=cmd_regress)

    pb2 = sub.add_parser("brief",
                         help="开抓前环境简报（速度/强度/去除/留费/生物/猝死代理）")
    pb2.add_argument("--set", required=True, help="系列代码（如 TDM）")
    pb2.add_argument("--fmt", default="PremierDraft",
                     help="17Lands event_type 口径（默认 PremierDraft）")
    pb2.add_argument("--out", help="报告输出路径（缺省 AuditReport/"
                                   "FormatBrief_<SET>_<fmt>_<日期>.md）")
    pb2.add_argument("--min-gih", type=int, default=500,
                     help="GIH 样本量下限（默认 500）")
    pb2.set_defaults(func=cmd_brief)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
