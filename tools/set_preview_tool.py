#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
set_preview_tool.py — 新系列预览期（模式 P，置信度 C0）持续跟踪 CLI（仅标准库）

Subcommands:
  init     生成 SetReview/{SET}_{YYYYMMDD}/ 目录骨架（00-06 七件套 + data/），
           预填模式 P 与 Scryfall 系列元数据（card_count / released_at）
  fetch    拉取 set:<code> unique:cards 全分页快照，与上一快照 diff
           （主键 oracle_id；changed = oracle_text/mana_cost/type_line/card_faces 变化），
           批次追加 preview_state.json 与 06_ChangeLog.md
  status   只读汇总：公开进度 / 最近批次 / 评分表覆盖 / 距发售天数 / G 门禁状态
  rate     增量调用 mtga_draft_tool.build_card_table 生成预览期限制评分
           （changed 牌先删旧条目重评；条目加 confidence=C0 / source=preview）
  report   刷新 01_SetOverview.md 预览进度节与 03_CardRatings.md 骨架
           （仅替换 AUTO 标记块内内容，不覆盖人工段落）
  watch    轮询 fetch → 有新批次则 rate → status 摘要（--poll/--max-polls）

通用行为:
  - 网络层复用 mtg_tool（缓存 / 节流 / 重试 / 错误分类），--no-cache 可绕过缓存；
  - 基本地/衍生物计入库存但不计入"待评级张数"（工作流规则 1b）；
  - 错误分类：网络失败 / 查询错误 / 本地状态错误 / 零结果，失败不静默；
    退出码：0 成功，1 网络请求失败，2 用法或本地状态错误，
    3 部分完成（如评分有占位），4 零结果。
"""
import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mtg_tool  # noqa: E402 Scryfall HTTP 层 / 错误分类 / BASIC_LAND_NAMES
import mtga_draft_tool  # noqa: E402 build_card_table / CardTable / 评分表路径
import mtga_auto_tool as AUTO  # noqa: E402 LLM 配置与调用（llm_chat 由 build_card_table 使用）
import runlog  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SET_REVIEW_ROOT = REPO_ROOT / "SetReview"
DEFAULT_LLM_CONFIG = Path(__file__).resolve().parent / "llm_config.json"
STATE_FILENAME = "preview_state.json"

# diff "changed" 判定字段（工作流 0b：牌面勘误须重新评价）
CHANGED_FIELDS = ("oracle_text", "mana_cost", "type_line", "card_faces")
TOKEN_LAYOUTS = ("token", "double_faced_token")
MANIFEST_GATES = ("G0", "G1", "G2", "G3", "G4")


class PreviewToolError(Exception):
    """本地状态/文件错误（与网络错误区分）"""


# ---------------------------------------------------------------- 目录与状态
def resolve_review_dir(set_code, dir_arg=None):
    """--dir 显式指定优先；否则取 SetReview/{SET}_* 中最新目录
    （同 find_set_cards_json 规则）。目录不存在抛 PreviewToolError。"""
    if dir_arg:
        path = Path(dir_arg)
        if not path.is_dir():
            raise PreviewToolError(f"指定目录不存在: {path}")
        return path
    cands = sorted(SET_REVIEW_ROOT.glob(f"{set_code.upper()}_*"))
    cands = [p for p in cands if p.is_dir()]
    if not cands:
        raise PreviewToolError(
            f"找不到 SetReview/{set_code.upper()}_* 目录（先跑 init 或用 --dir 指定）")
    return cands[-1]


def state_path(review_dir):
    return Path(review_dir) / "data" / STATE_FILENAME


def load_state(review_dir):
    path = state_path(review_dir)
    if not path.is_file():
        return {"set": None, "mode": "P", "batches": []}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise PreviewToolError(f"状态文件损坏: {path}: {exc}")
    state.setdefault("batches", [])
    return state


def save_state(review_dir, state):
    path = state_path(review_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")


def latest_snapshot_path(review_dir, state):
    """最近批次引用的快照文件；state 缺批次时回退 data/ 里最新 preview 快照。"""
    batches = state.get("batches") or []
    if batches:
        path = Path(review_dir) / "data" / batches[-1].get("snapshot", "")
        if path.is_file():
            return path
    data_dir = Path(review_dir) / "data"
    cands = sorted(data_dir.glob("scryfall_*_preview_*.json"))
    return cands[-1] if cands else None


def load_snapshot(path):
    cards = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(cards, list):
        raise PreviewToolError(f"快照不是牌张数组: {path}")
    return cards


# ---------------------------------------------------------------- 牌张判定
def card_key(c):
    """牌身份主键：oracle_id（工作流 1b），缺失回退印刷 id。"""
    return c.get("oracle_id") or c.get("id")


def card_fingerprint(c):
    """changed 判定指纹：oracle_text / mana_cost / type_line / card_faces。"""
    return tuple(
        json.dumps(c.get(f), ensure_ascii=False, sort_keys=True) if f == "card_faces"
        else (c.get(f) or "")
        for f in CHANGED_FIELDS
    )


def is_excluded_from_rating(c):
    """基本地/衍生物不计入"待评级张数"（工作流 1b）。

    沿用 mtga_draft_tool.load_set_cards 的基本地排除口径
    （BASIC_LAND_NAMES / "Basic Land" / 收藏号 >=189 的地），另排除 token 版式。"""
    if (c.get("layout") or "") in TOKEN_LAYOUTS:
        return True
    type_line = c.get("type_line") or ""
    if (c.get("name") or "") in mtg_tool.BASIC_LAND_NAMES:
        return True
    if "Basic Land" in type_line:
        return True
    try:
        if int(c.get("collector_number", 0)) >= 189 and "Land" in type_line:
            return True
    except (TypeError, ValueError):
        pass
    return False


def collector_sort_key(c):
    try:
        return (0, int(c.get("collector_number", 0)))
    except (TypeError, ValueError):
        return (1, 0)


def cards_for_rating(cards):
    """原始快照 → build_card_table 入参（排除基本地/衍生物，双面牌合并牌面文本，
    口径同 mtga_draft_tool.load_set_cards）。"""
    out = []
    for c in cards:
        if is_excluded_from_rating(c):
            continue
        oracle = c.get("oracle_text") or ""
        faces = c.get("card_faces") or []
        if faces:
            oracle = " // ".join(f.get("oracle_text") or "" for f in faces)
        out.append({"name": c["name"], "mana_cost": c.get("mana_cost") or "",
                    "type_line": c.get("type_line") or "",
                    "rarity": c.get("rarity") or "", "oracle_text": oracle})
    return out


def changed_card_names(state):
    """历批次 changed 并集（重评是幂等的，并集比仅最近批次更稳）。"""
    names = []
    for b in state.get("batches") or []:
        names.extend(b.get("changed") or [])
    return sorted(set(names))


# ---------------------------------------------------------------- 评分表读写
def read_rating_table(set_code):
    """读 tools/cache/draft_ratings/<SET>.json 原始 {name: entry}；无文件返回 {}。"""
    path = mtga_draft_tool.card_table_path(set_code)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("cards") or {}
    except (json.JSONDecodeError, OSError):
        return {}


def write_rating_table(set_code, cards_map):
    path = mtga_draft_tool.card_table_path(set_code)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"set": set_code, "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         "source": "community+llm", "cards": cards_map},
        ensure_ascii=False, indent=1), encoding="utf-8")


def table_coverage(table, rate_cards):
    """评分表对当前待评清单的覆盖：(rated, placeholder, unrated, 待补名单)。"""
    rated = placeholder = 0
    unrated = []
    norm_index = {}
    for k, v in table.items():
        norm_index[mtga_draft_tool._norm_name(k)] = v
    for c in rate_cards:
        entry = norm_index.get(mtga_draft_tool._norm_name(c["name"]))
        if entry is None:
            unrated.append(c["name"])
        elif not entry.get("grade"):
            placeholder += 1
            unrated.append(c["name"])
        else:
            rated += 1
    return rated, placeholder, len(rate_cards) - rated - placeholder, unrated


# ---------------------------------------------------------------- AUTO 标记块
def replace_auto_block(text, marker, body):
    """替换 <!-- AUTO:BEGIN/END marker --> 之间的内容；无标记则追加到文末。
    人工段落一律不动。"""
    begin = f"<!-- AUTO:BEGIN {marker} -->"
    end = f"<!-- AUTO:END {marker} -->"
    block = f"{begin}\n{body.rstrip()}\n{end}"
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
    if pattern.search(text):
        return pattern.sub(lambda _m: block, text)
    return text.rstrip() + "\n\n" + block + "\n"


# ---------------------------------------------------------------- 骨架模板
def manifest_skeleton(set_code, meta):
    return f"""# {set_code} 系列评估运行清单（预览期）

## 运行状态

| 字段 | 值 |
|---|---|
| 系列 | {meta.get('name') or set_code} |
| 系列代码 | `{set_code}` |
| 运行模式 | `P 预览` |
| 置信度 | `C0`（预览期仅临时评级，随批次可能重评） |
| 目标平台 | MTG Arena；同时保留实体牌面语义 |
| 发售日 | {meta.get('released_at') or '未知'} |
| set_type | {meta.get('set_type') or '未知'} |
| Scryfall card_count | {meta.get('card_count') or 0} |
| 官方完整牌表 | 否（预览期增量公开） |
| 卡牌数据源 | Scryfall `set:{set_code.lower()} unique:cards`，增量快照见 `data/` |

## 数据状态

| 项目 | 状态 | 说明 |
|---|---|---|
| G0 工具包同步 | 未开始 |  |
| G1 数据完整性 | 未开始 | 官方完整牌表发布前无法通过 |
| G2 全卡覆盖 | 未开始 | 预览期只覆盖已公开牌 |
| G3 构筑候选 | 未开始 |  |
| G4 最终交付 | 未开始 |  |

## 重要限制

1. 预览期所有评级为 C0 临时评级，随新批次可能重评；牌面勘误以最新快照为准。
2. Scryfall 对未发售系列的 legalities 不可作发售即入赛制的依据，须看 set_type。
3. 无聚合胜率数据（模式 P 无 17Lands/赛事样本），强度文字为牌面纸面推演。
"""


def overview_skeleton(set_code):
    return f"""# {set_code} 系列评估总览（预览期）

> 状态：`P 预览` | 置信度：`C0`

## 预览进度

<!-- AUTO:BEGIN preview-progress -->
（尚未执行 fetch；本节由 tools/set_preview_tool.py report/status 维护）
<!-- AUTO:END preview-progress -->

## 结论摘要

### 限制赛

（待人工填写）

### 构筑赛

（待人工填写）

## 系列机制

（待人工填写）

## 待确认规则

（待人工填写）
"""


def card_ratings_skeleton(set_code):
    return f"""# {set_code} 全卡逐张评级（预览期临时版）

> 预览期评级为 C0 临时评级，随批次更新；正式版以官方完整牌表后校准为准。

<!-- AUTO:BEGIN card-ratings -->
（尚未执行 fetch/rate；本节由 tools/set_preview_tool.py report 维护）
<!-- AUTO:END card-ratings -->

## A / B 级限制赛详评

（人工填写，工具不覆盖本节）
"""


def simple_skeleton(set_code, title, body):
    return f"# {set_code} {title}\n\n{body}\n"


CHANGELOG_HEADER = "| 日期 | 快照 | 变更 | 理由 / 证据 |\n|---|---|---|---|"


def changelog_skeleton(set_code):
    return f"# {set_code} 评估变更日志\n\n{CHANGELOG_HEADER}\n"


# ---------------------------------------------------------------- subcommand: init
def cmd_init(args):
    set_code = args.set.upper()
    existing = [p for p in sorted(SET_REVIEW_ROOT.glob(f"{set_code}_*")) if p.is_dir()]
    if existing:
        print(f"[错误] 目录已存在，拒绝覆盖: {existing[-1]}", file=sys.stderr)
        return 2
    try:
        meta = mtg_tool.scryfall_get(f"/sets/{set_code.lower()}",
                                     use_cache=not args.no_cache)
    except mtg_tool.QuerySyntaxError as exc:
        print(f"[错误] 系列代码未命中: {exc}", file=sys.stderr)
        return 2
    except mtg_tool.MtgToolError as exc:
        print(f"[错误] 系列元数据请求失败: {exc}", file=sys.stderr)
        return 1

    day = args.date or date.today().strftime("%Y%m%d")
    review_dir = SET_REVIEW_ROOT / f"{set_code}_{day}"
    review_dir.mkdir(parents=True)
    (review_dir / "data").mkdir()

    files = {
        "00_RunManifest.md": manifest_skeleton(set_code, meta),
        "01_SetOverview.md": overview_skeleton(set_code),
        "02_LimitedEnvironment.md": simple_skeleton(
            set_code, "限制赛环境分析", "（预览期暂缺，待官方完整牌表后填写）"),
        "03_CardRatings.md": card_ratings_skeleton(set_code),
        "04_ConstructedWatchlist.md": simple_skeleton(
            set_code, "构筑观察表",
            "| 优先级 | 牌 | 赛制 | 用途 | 目标牌表 / 新轴 | 一句话理由 | 置信度 |\n"
            "|---|---|---|---|---|---|---|\n"),
        "05_TestLog.md": simple_skeleton(
            set_code, "测试记录",
            "| 日期 | 来源 / 队列 | 样本口径 | 原结论 | 新证据 | 调整 | 置信度变化 |\n"
            "|---|---|---|---|---|---|---|\n"),
        "06_ChangeLog.md": changelog_skeleton(set_code),
    }
    for name, text in files.items():
        (review_dir / name).write_text(text, encoding="utf-8")

    state = {
        "set": set_code, "mode": "P",
        "card_count": meta.get("card_count") or 0,
        "released_at": meta.get("released_at"),
        "set_type": meta.get("set_type"),
        "batches": [],
    }
    save_state(review_dir, state)
    print(f"[init] 已生成 {review_dir}（发售日 {state['released_at']}，"
          f"card_count {state['card_count']}）")
    return 0


# ---------------------------------------------------------------- subcommand: fetch
def fetch_set_cards(set_code, use_cache):
    """拉取 set:<code> unique:cards 全分页。返回 (cards, warnings)。"""
    cards, _total, warnings = mtg_tool.scryfall_search(
        f"set:{set_code.lower()} unique:cards", unique="cards", use_cache=use_cache)
    return cards, warnings


def do_fetch(args):
    """执行 fetch；返回 (exit_code, batch 或 None)。watch 复用。"""
    set_code = args.set.upper()
    try:
        review_dir = resolve_review_dir(set_code, args.dir)
    except PreviewToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2, None
    state = load_state(review_dir)

    try:
        cards, warnings = fetch_set_cards(set_code, use_cache=not args.no_cache)
    except mtg_tool.QuerySyntaxError as exc:
        print(f"[错误] 查询语法错误或系列未命中: {exc}", file=sys.stderr)
        return 2, None
    except mtg_tool.PaginationIncomplete as exc:
        print(f"[错误] 分页不完整（快照未保存）: {exc}", file=sys.stderr)
        return 3, None
    except mtg_tool.MtgToolError as exc:
        print(f"[错误] 请求失败: {exc}", file=sys.stderr)
        return 1, None
    for w in warnings:
        print(f"[scryfall warning] {w}", file=sys.stderr)
    if not cards:
        print(f"[错误] 查询返回 0 张牌（系列 {set_code} 可能尚无公开牌张，"
              f"与网络失败区分）", file=sys.stderr)
        return 4, None

    prev_path = latest_snapshot_path(review_dir, state)
    prev_cards = load_snapshot(prev_path) if prev_path else []
    prev_by_key = {card_key(c): c for c in prev_cards if card_key(c)}
    curr_by_key = {card_key(c): c for c in cards if card_key(c)}

    added = sorted(c["name"] for k, c in curr_by_key.items() if k not in prev_by_key)
    removed = sorted(c["name"] for k, c in prev_by_key.items() if k not in curr_by_key)
    changed = sorted(
        curr_by_key[k]["name"] for k in curr_by_key.keys() & prev_by_key.keys()
        if card_fingerprint(curr_by_key[k]) != card_fingerprint(prev_by_key[k]))
    has_diff = bool(added or removed or changed) or not prev_cards

    ts_file = datetime.now().strftime("%Y%m%d_%H%M")
    snap_name = f"scryfall_{set_code.lower()}_preview_{ts_file}.json"
    snap_path = Path(review_dir) / "data" / snap_name

    batch = None
    if not has_diff:
        print(f"[fetch] 与上一快照无变化（已公开 {len(cards)} 张），不追加批次")
    else:
        if snap_path.exists():  # 同一分钟内重复 fetch 且有变化：覆盖同名快照
            print(f"[warn] 快照 {snap_name} 已存在，覆盖", file=sys.stderr)
        snap_path.write_text(json.dumps(cards, ensure_ascii=False, indent=1) + "\n",
                             encoding="utf-8")
        batch = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "snapshot": snap_name,
            "revealed": len(cards),
            "rated_scope": len([c for c in cards if not is_excluded_from_rating(c)]),
            "added": added, "changed": changed, "removed": removed,
        }
        state.setdefault("batches", []).append(batch)
        save_state(review_dir, state)
        append_changelog(review_dir, set_code, batch)

    card_count = state.get("card_count") or 0
    coverage = f"{len(cards)}/{card_count}" if card_count else f"{len(cards)}/未知"
    print(f"[fetch] {set_code} 已公开 {coverage}；本批新增 {len(added)} / "
          f"变更 {len(changed)} / 移除 {len(removed)}"
          + (f" → {snap_path}" if batch else ""))
    return 0, batch


def append_changelog(review_dir, set_code, batch):
    path = Path(review_dir) / "06_ChangeLog.md"
    if path.is_file():
        text = path.read_text(encoding="utf-8")
    else:
        text = changelog_skeleton(set_code)
    if CHANGELOG_HEADER.splitlines()[0] not in text:
        text = text.rstrip() + "\n\n" + CHANGELOG_HEADER + "\n"
    if not text.endswith("\n"):
        text += "\n"
    day = batch["ts"][:10]

    def names(lst, limit=8):
        if not lst:
            return "无"
        s = "、".join(lst[:limit])
        return s + (f" 等{len(lst)}张" if len(lst) > limit else "")

    summary = (f"预览批次（已公开 {batch['revealed']} 张）："
               f"新增 {len(batch['added'])} 张（{names(batch['added'])}）；"
               f"变更 {len(batch['changed'])} 张（{names(batch['changed'])}）；"
               f"移除 {len(batch['removed'])} 张（{names(batch['removed'])}）")
    row = f"| {day} | {batch['snapshot']} | {summary} | set_preview_tool fetch 自动批次 |\n"
    path.write_text(text + row, encoding="utf-8")


def cmd_fetch(args):
    code, batch = do_fetch(args)
    if code == 0 and batch:
        runlog.log_run("set_preview_tool.py", "ok",
                       "fetch 已公开 %d；新增 %d / 变更 %d / 移除 %d"
                       % (batch["revealed"], len(batch["added"]),
                          len(batch["changed"]), len(batch["removed"])))
    return code


# ---------------------------------------------------------------- subcommand: status
def parse_gates(review_dir):
    """从 00_RunManifest.md 解析 G 门禁行；解析不了返回 None（跳过）。"""
    path = Path(review_dir) / "00_RunManifest.md"
    if not path.is_file():
        return None
    gates = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*(G\d[^|]*)\|\s*([^|]*)\|\s*([^|]*)\|", line.strip())
        if m:
            gates.append((m.group(1).strip(), m.group(2).strip(), m.group(3).strip()))
    return gates or None


def build_status_lines(set_code, review_dir):
    state = load_state(review_dir)
    batches = state.get("batches") or []
    card_count = state.get("card_count") or 0
    lines = [f"# {set_code} 预览期状态（{Path(review_dir).name}）", ""]

    snap_path = latest_snapshot_path(review_dir, state)
    if snap_path:
        cards = load_snapshot(snap_path)
        rate_cards = cards_for_rating(cards)
        revealed = len(cards)
    else:
        cards, rate_cards, revealed = [], [], 0
    coverage = f"{revealed}/{card_count}" if card_count else f"{revealed}/未知"
    pct = f"（{revealed / card_count:.0%}）" if card_count and revealed else ""
    lines.append(f"- 公开进度：{coverage}{pct}；待评级张数 {len(rate_cards)}"
                 f"（基本地/衍生物 {revealed - len(rate_cards)} 张仅计库存）")

    if batches:
        b = batches[-1]
        lines.append(f"- 最近批次：{b['ts'][:16]} `{b['snapshot']}` —— 新增 "
                     f"{len(b['added'])} / 变更 {len(b['changed'])} / 移除 {len(b['removed'])}"
                     f"（累计 {len(batches)} 批）")
    else:
        lines.append("- 最近批次：无（尚未 fetch）")

    table = read_rating_table(set_code)
    rated, placeholder, unrated, _missing = table_coverage(table, rate_cards)
    lines.append(f"- 评分表覆盖：已评 {rated} / 占位 {placeholder} / 未评 {unrated}"
                 f"（{mtga_draft_tool.card_table_path(set_code)}"
                 f"{'，文件不存在' if not table and rate_cards else ''}）")

    released_at = state.get("released_at")
    if released_at:
        try:
            days = (date.fromisoformat(released_at) - date.today()).days
            if days > 0:
                lines.append(f"- 距发售日 {released_at} 还有 {days} 天")
            else:
                lines.append(f"- 发售日 {released_at} 已过 {-days} 天")
        except ValueError:
            lines.append(f"- 发售日字段无法解析: {released_at}")
    else:
        lines.append("- 发售日：未知")

    gates = parse_gates(review_dir)
    if gates is None:
        lines.append("- 门禁：00_RunManifest.md 未找到或无法解析（跳过）")
    else:
        for name, status, note in gates:
            lines.append(f"- 门禁 {name}：{status}" + (f"（{note}）" if note else ""))
    return lines


def cmd_status(args):
    set_code = args.set.upper()
    try:
        review_dir = resolve_review_dir(set_code, args.dir)
    except PreviewToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    for line in build_status_lines(set_code, review_dir):
        print(line)
    return 0


# ---------------------------------------------------------------- subcommand: rate
def load_llm_cfg_or_error(args):
    """rate 必须拿到 LLM 配置；拿不到明确报错（退出码 5），绝不静默跳过。"""
    try:
        return AUTO.load_llm_config(args.llm_config)
    except AUTO.AutoToolError as exc:
        print(f"[错误] rate 需要 LLM 配置：{exc}", file=sys.stderr)
        return None


def do_rate(args):
    """执行 rate；返回 (exit_code, placeholders list)。watch 复用。"""
    set_code = args.set.upper()
    try:
        review_dir = resolve_review_dir(set_code, args.dir)
    except PreviewToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2, []
    state = load_state(review_dir)
    snap_path = latest_snapshot_path(review_dir, state)
    if not snap_path:
        print(f"[错误] 无预览快照（先跑 fetch）: {review_dir}/data/", file=sys.stderr)
        return 2, []

    llm_cfg = load_llm_cfg_or_error(args)
    if llm_cfg is None:
        return 5, []

    rate_cards = cards_for_rating(load_snapshot(snap_path))

    # 删旧条目让 build_card_table 重评：牌面变更（工作流 0b）+ 占位条目
    # （占位不删会被幂等跳过，永远无法补评）
    changed = changed_card_names(state)
    table_map = read_rating_table(set_code)
    # 双面牌按全名与正面名都算 changed（评分表键两种形态都可能出现）
    norm_changed = {mtga_draft_tool._norm_name(n) for n in changed}
    norm_changed |= {mtga_draft_tool._norm_name(n.split(" // ")[0])
                     for n in changed}
    dropped_changed = [k for k in list(table_map)
                       if mtga_draft_tool._norm_name(k) in norm_changed
                       or mtga_draft_tool._norm_name(k.split(" // ")[0])
                       in norm_changed]
    dropped_placeholder = [k for k in list(table_map)
                           if k not in dropped_changed
                           and not table_map[k].get("grade")]
    for k in dropped_changed + dropped_placeholder:
        del table_map[k]
    if dropped_changed:
        print(f"[rate] {len(dropped_changed)} 张牌面变更，已删旧条目待重评: "
              f"{', '.join(dropped_changed)}")
    if dropped_placeholder:
        print(f"[rate] {len(dropped_placeholder)} 张占位，重试补评: "
              f"{', '.join(dropped_placeholder)}")
    if dropped_changed or dropped_placeholder:
        write_rating_table(set_code, table_map)

    community = mtga_draft_tool.load_community(args.community)
    context = ""
    overview = Path(review_dir) / "01_SetOverview.md"
    if overview.is_file():
        context = overview.read_text(encoding="utf-8")

    try:
        table = mtga_draft_tool.build_card_table(
            set_code, rate_cards, community, context, llm_cfg,
            batch_size=args.batch)
    except mtga_draft_tool.DraftToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 1, []

    # 条目标注置信度与来源（CardTable 只读 grade/note/community_score，多余字段
    # 向后兼容）：系列已发售（state.released_at <= 今天，init 时写入）盖
    # C1/llm_review；预览期或 released_at 缺失回退 C0/preview。setdefault 语义：
    # 已有戳不覆盖。
    released_at = state.get("released_at")
    if released_at and released_at <= date.today().isoformat():
        confidence, source = "C1", "llm_review"
    else:
        confidence, source = "C0", "preview"
    table_map = read_rating_table(set_code)
    for entry in table_map.values():
        entry.setdefault("confidence", confidence)
        entry.setdefault("source", source)
    write_rating_table(set_code, table_map)

    placeholders = sorted(k for k, v in table_map.items() if not v.get("grade"))
    if placeholders:
        print(f"[rate] 待补清单（{len(placeholders)} 张占位，重跑 rate 补评）:")
        for name in placeholders:
            print(f"  - {name}")
    print(f"[rate] 完成：{len(table_map)} 张在表，"
          f"{len(table_map) - len(placeholders)} 张有等级 → "
          f"{mtga_draft_tool.card_table_path(set_code)}")
    return (3 if placeholders else 0), placeholders


def cmd_rate(args):
    code, _placeholders = do_rate(args)
    return code


# ---------------------------------------------------------------- subcommand: report
def report_progress_body(set_code, review_dir):
    lines = build_status_lines(set_code, review_dir)
    return "\n".join(lines[2:])  # 去掉标题行与空行，正文嵌入 01


def report_ratings_body(set_code, review_dir):
    state = load_state(review_dir)
    snap_path = latest_snapshot_path(review_dir, state)
    if not snap_path:
        return "（尚无预览快照，先跑 fetch）"
    cards = sorted(load_snapshot(snap_path), key=collector_sort_key)
    table = mtga_draft_tool.load_card_table(set_code)
    lines = [
        "| # | English | 稀有度 | 临时等级 | 置信度 | 备注 |",
        "|---:|---|---|---|---|---|",
    ]
    for c in cards:
        num = c.get("collector_number")
        name = c["name"]
        if is_excluded_from_rating(c):
            lines.append(f"| {num} | {name} | {c.get('rarity')} | - | - |"
                         " 基本地/衍生物，库存不评级 |")
            continue
        entry = table.lookup(name) if table else None
        grade = entry["grade"] if entry and entry.get("grade") else "未评级"
        note = ((entry.get("note") if entry else "") or "").replace("|", "/")
        lines.append(f"| {num} | {name} | {c.get('rarity')} | {grade} | C0 | {note} |")
    lines.append("")
    lines.append(f"覆盖：已公开 {len(cards)} 张，其中 "
                 f"{len([c for c in cards if not is_excluded_from_rating(c)])} 张待评级；"
                 "全部评级为预览期 C0 临时评级。")
    return "\n".join(lines)


def cmd_report(args):
    set_code = args.set.upper()
    try:
        review_dir = resolve_review_dir(set_code, args.dir)
    except PreviewToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2

    overview = Path(review_dir) / "01_SetOverview.md"
    text = overview.read_text(encoding="utf-8") if overview.is_file() \
        else overview_skeleton(set_code)
    text = replace_auto_block(text, "preview-progress",
                              report_progress_body(set_code, review_dir))
    overview.write_text(text, encoding="utf-8")

    ratings = Path(review_dir) / "03_CardRatings.md"
    text = ratings.read_text(encoding="utf-8") if ratings.is_file() \
        else card_ratings_skeleton(set_code)
    text = replace_auto_block(text, "card-ratings",
                              report_ratings_body(set_code, review_dir))
    ratings.write_text(text, encoding="utf-8")

    print(f"[report] 已刷新 {overview} 与 {ratings} 的 AUTO 块（人工段落未动）")
    return 0


# ---------------------------------------------------------------- subcommand: watch
def cmd_watch(args):
    polls = 0
    print(f"[watch] 开始监控 {args.set.upper()} 预览批次（每 {args.poll:.0f}s 轮询，"
          f"Ctrl+C 停止）", file=sys.stderr)
    try:
        while True:
            code, batch = do_fetch(args)
            if code not in (0,):
                print(f"[watch] fetch 退出码 {code}，本轮跳过后续步骤",
                      file=sys.stderr)
            elif batch and (batch["added"] or batch["changed"]):
                llm_cfg = load_llm_cfg_or_error(args)
                if llm_cfg is None:
                    print("[watch] 无 LLM 配置，本轮跳过 rate（fetch 结果已保存）",
                          file=sys.stderr)
                else:
                    do_rate(args)
            try:
                review_dir = resolve_review_dir(args.set.upper(), args.dir)
                for line in build_status_lines(args.set.upper(), review_dir)[2:]:
                    print(f"[watch] {line}", file=sys.stderr)
            except PreviewToolError as exc:
                print(f"[watch] status 失败: {exc}", file=sys.stderr)
            polls += 1
            if args.max_polls and polls >= args.max_polls:
                break
            time.sleep(args.poll)
    except KeyboardInterrupt:
        print("\n[watch] 已停止", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- 入口
def build_parser():
    p = argparse.ArgumentParser(
        prog="set_preview_tool.py",
        description="新系列预览期（模式 P / C0）持续跟踪：建档 / 快照 diff / 增量评级 / 报告")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--dir", help="SetReview 目录（缺省自动取 SetReview/<SET>_最新目录）")
        sp.add_argument("--no-cache", action="store_true", help="绕过磁盘缓存重新请求")

    def add_llm(sp):
        sp.add_argument("--llm-config", default=str(DEFAULT_LLM_CONFIG),
                        help="LLM 配置 JSON（默认 tools/llm_config.json；"
                             "缺失时 rate 明确报错）")

    sp = sub.add_parser("init", help="生成 SetReview/<SET>_<日期>/ 预览期骨架（00-06 + data/）")
    sp.add_argument("set", help="系列代码（如 TDM）")
    sp.add_argument("--date", help="目录日期 YYYYMMDD（默认今天）")
    add_common(sp)
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("fetch", help="拉取已公开牌快照并与上一快照 diff，追加批次与变更日志")
    sp.add_argument("set", help="系列代码（如 TDM）")
    add_common(sp)
    sp.set_defaults(func=cmd_fetch)

    sp = sub.add_parser("status", help="只读汇总：公开进度 / 最近批次 / 评分覆盖 / 门禁")
    sp.add_argument("set", help="系列代码（如 TDM）")
    add_common(sp)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("rate", help="增量 LLM 评级（changed 牌先重评；条目标注 C0/preview）")
    sp.add_argument("set", help="系列代码（如 TDM）")
    sp.add_argument("--community", help="社区评分 JSON（[{name, score, note}]）")
    sp.add_argument("--batch", type=int, default=25, help="每批评级张数（默认 25）")
    add_llm(sp)
    add_common(sp)
    sp.set_defaults(func=cmd_rate)

    sp = sub.add_parser("report", help="刷新 01 预览进度节与 03 评级骨架（仅 AUTO 块）")
    sp.add_argument("set", help="系列代码（如 TDM）")
    add_common(sp)
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("watch", help="轮询 fetch → 新批次则 rate → status 摘要")
    sp.add_argument("set", help="系列代码（如 TDM）")
    sp.add_argument("--poll", type=float, default=3600.0,
                    help="轮询间隔秒（默认 3600）")
    sp.add_argument("--max-polls", type=int,
                    help="最多轮询次数后退出（测试/冒烟用，默认无限）")
    sp.add_argument("--community", help="社区评分 JSON（传给 rate）")
    sp.add_argument("--batch", type=int, default=25, help="每批评级张数（默认 25）")
    add_llm(sp)
    add_common(sp)
    sp.set_defaults(func=cmd_watch)

    return p


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    rc = args.func(args)
    runlog.log_run("set_preview_tool.py", "ok" if rc == 0 else "error",
                   f"{args.cmd} exit={rc}")
    return rc


if __name__ == "__main__":
    sys.exit(runlog.run_logged("set_preview_tool.py", main))
