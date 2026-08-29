#!/usr/bin/env python3
"""MTGA 快速轮抓（Quick Draft）驾驶舱：17Lands 胜率锚点 + 包/pick 跟踪 + LLM 推荐。

定位：轮抓期副驾。仅读 Player.log，不做任何鼠标键盘模拟。
数据源：
- 17Lands card_ratings 站点端点（其前端自用 JSON，含 mtga_id 可直接对齐 grpId），
  磁盘缓存 tools/cache/17lands/<SET>_<format>.json，>3 天提示刷新；
  拉取失败/缺数据时降级为纯 LLM 模式并显式标注"无胜率锚点"。
- 轮抓载荷 schema 以 tools/auto/draft_samples/ 真实录样为准（mtga_auto_tool draft --record）。

仅 Python 标准库；复用 mtga_auto_tool 的日志管线/LLM 后端/监控台基建。
"""

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mtga_auto_tool as AUTO  # noqa: E402 复用日志管线/LLM/监控台基建
from mtg_tool import fetch_set_chinese_names  # noqa: E402 按系列批量中文名（逐牌查询会被限流）

RATINGS_DIR = Path(__file__).resolve().parent / "cache" / "17lands"
RATINGS_URL = ("https://www.17lands.com/card_ratings/data"
               "?expansion={set_code}&format={fmt}")
RATINGS_MAX_AGE_DAYS = 3

# 本地预生成评分表（社区评测 + LLM 综合）：tools/cache/draft_ratings/<SET>.json
# 背景：17Lands 公共端点/S3 已于 2026 前后关闭（实测各系列全 0），
# 胜率硬锚点改为离线预生成表，轮抓中作 LLM 的事实锚点。
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
def fetch_ratings(set_code, fmt="QuickDraft", timeout=30):
    """拉取 17Lands 单卡数据 → 原始 list[dict]。失败抛 DraftToolError。"""
    url = RATINGS_URL.format(set_code=set_code, fmt=fmt)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise DraftToolError(f"17Lands HTTP {exc.code}（{set_code}/{fmt}）")
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise DraftToolError(f"17Lands 请求失败: {exc}")
    if not isinstance(data, list) or not data:
        raise DraftToolError(f"17Lands 返回异常（{set_code}/{fmt}）：非空列表预期，"
                             f"实际 {str(data)[:120]!r}")
    return data


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
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
