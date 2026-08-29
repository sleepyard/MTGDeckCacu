#!/usr/bin/env python3
"""DeckPooper v1 的限制赛、轮抓和构筑赛入口。

策略和推荐逻辑分别位于纯函数模块；本文件只负责参数、文件和缓存边界。
"""

import argparse
import contextlib
import io
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import limited_strategy as LS  # noqa: E402
import constructed_strategy as CS  # noqa: E402
import mtg_tool  # noqa: E402
import mtga_draft_tool  # noqa: E402
import mtga_auto_tool  # noqa: E402


SECTION_HEADERS = {"deck", "sideboard", "commander", "companion", "pool"}
DRAFT_COMPLETE_STATUSES = {"Complete", "Completed"}


def parse_pool_text(path: str) -> List[Tuple[int, str]]:
    """解析数量+英文名牌池文本，接受 MTGA/MTGO 的 Deck/Sideboard 头。"""
    entries = []
    current = "main"
    with open(path, "r", encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line:
                continue
            low = line.lower()
            if low in SECTION_HEADERS:
                current = low
                continue
            match = re.match(r"^(\d+)\s+(.+?)\s*$", line)
            if not match:
                raise ValueError(f"牌池第 {lineno} 行无法解析为 '数量 英文名': {line!r}")
            quantity = int(match.group(1))
            name = re.sub(r"\s+\([A-Za-z0-9_]+\)\s+\S+$", "", match.group(2)).strip()
            if quantity <= 0 or not name:
                raise ValueError(f"牌池第 {lineno} 行数量或牌名无效: {line!r}")
            entries.append((quantity, name))
    if not entries:
        raise ValueError(f"牌池文件为空: {path}")
    return entries


def _inner_status(payload: Mapping):
    if not isinstance(payload, Mapping):
        return None
    inner = payload.get("Payload")
    if isinstance(inner, str):
        try:
            inner = json.loads(inner)
        except json.JSONDecodeError:
            return None
    return inner if isinstance(inner, Mapping) else None


def parse_pool_sample(path: str) -> List[Tuple[int, str]]:
    """从录样 JSONL 提取终态 PickedCards（grpId），拒绝中间态牌池。"""
    completed = None
    with open(path, "r", encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, 1):
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"录样第 {lineno} 行 JSON 无法解析: {exc}")
            inner = _inner_status(row.get("payload", row))
            if not inner or inner.get("DraftStatus") not in DRAFT_COMPLETE_STATUSES:
                continue
            picked = inner.get("PickedCards")
            if isinstance(picked, list) and picked:
                completed = [str(value) for value in picked if str(value)]
    if not completed:
        raise ValueError("录样中没有终态 Complete/PickedCards，拒绝使用中间态牌池")
    counts = {}
    for grp_id in completed:
        counts[grp_id] = counts.get(grp_id, 0) + 1
    return [(quantity, grp_id) for grp_id, quantity in counts.items()]


def _fetch_named(name: str, use_cache: bool) -> Mapping:
    raw = mtg_tool.scryfall_get("/cards/named", {"exact": name}, use_cache=use_cache)
    card = mtg_tool.normalize_card(raw)
    card.update({
        "name": raw.get("name") or card.get("name"),
        "colors": raw.get("colors") or [],
        "rarity": raw.get("rarity") or "",
        "cost": card.get("mana_cost") or "",
        "type": card.get("type_line") or "",
    })
    return card


def _fetch_grp(grp_id: str, use_cache: bool) -> Mapping:
    raw = mtg_tool.scryfall_get(f"/cards/arena/{grp_id}", use_cache=use_cache)
    card = mtg_tool.normalize_card(raw)
    card.update({
        "name": raw.get("name") or card.get("name"),
        "colors": raw.get("colors") or [],
        "rarity": raw.get("rarity") or "",
        "cost": card.get("mana_cost") or "",
        "type": card.get("type_line") or "",
    })
    return card


def load_pool(path: str, use_cache: bool) -> List[Mapping]:
    """根据扩展名/内容加载牌名池或录样 grpId 池，并聚合同名数量。"""
    is_jsonl = Path(path).suffix.lower() in {".jsonl", ".json"}
    entries = parse_pool_sample(path) if is_jsonl else parse_pool_text(path)
    cards = []
    cache: Dict[str, Mapping] = {}
    for quantity, value in entries:
        if is_jsonl:
            card = cache.get(value)
            if card is None:
                card = _fetch_grp(value, use_cache)
                cache[value] = card
        else:
            card = cache.get(value.lower())
            if card is None:
                card = _fetch_named(value, use_cache)
                cache[value.lower()] = card
        item = dict(card)
        item["count"] = quantity
        cards.append(item)
    return cards


def render_deck(deck: LS.LimitedDeck) -> str:
    basic = {"W": "Plains", "U": "Island", "B": "Swamp",
             "R": "Mountain", "G": "Forest"}
    lines = ["Deck"]
    for entry in sorted(deck.main, key=lambda item: (item.card.get("cmc") or 0,
                                                     item.card.get("name") or "")):
        lines.append(f"{entry.count} {entry.card['name']}")
    for color, quantity in sorted(deck.lands.items()):
        lines.append(f"{quantity} {basic[color]}")
    if deck.sideboard:
        lines.extend(["", "Sideboard"])
        for entry in sorted(deck.sideboard, key=lambda item: item.card.get("name") or ""):
            lines.append(f"{entry.count} {entry.card['name']}")
    return "\n".join(lines) + "\n"


def render_report(deck: LS.LimitedDeck, explain: bool = False) -> str:
    lines = ["# DeckPooper 限制赛构筑报告", ""]
    lines.extend(f"- {line}" for line in deck.report)
    if deck.violations:
        lines.extend(["", "## 门禁失败"])
        lines.extend(f"- {violation}" for violation in deck.violations)
    if explain and deck.main:
        lines.extend(["", "## 主牌选择"])
        lines.extend(f"- {entry.count} {entry.card['name']}：{entry.reason}（分数 {entry.score:.3f}）"
                     for entry in deck.main)
    return "\n".join(lines) + "\n"


def load_candidates(path: str) -> List[Mapping]:
    """加载 mtg_tool search --out 产生的规范化候选数组。"""
    with open(path, "r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, list) or not data:
        raise ValueError("候选文件必须是非空 JSON 数组")
    if any(not isinstance(item, Mapping) for item in data):
        raise ValueError("候选文件包含非对象记录")
    return data


def render_constructed_deck(deck: CS.ConstructedDeck) -> str:
    lines = []
    if deck.commander:
        lines.append("Commander")
        lines.extend(f"{item.count} {item.card['name']}" for item in deck.commander)
        lines.append("")
    lines.append("Deck")
    entries = sorted(deck.main, key=lambda item: (
        not ("land" in str(item.card.get("type_line") or "").lower()),
        item.card.get("name") or ""))
    lines.extend(f"{item.count} {item.card['name']}" for item in entries)
    if deck.sideboard:
        lines.extend(["", "Sideboard"])
        lines.extend(f"{item.count} {item.card['name']}" for item in deck.sideboard)
    return "\n".join(lines) + "\n"


def render_constructed_report(deck: CS.ConstructedDeck, explain: bool = False) -> str:
    lines = ["# DeckPooper 构筑赛报告", ""]
    lines.extend(f"- {line}" for line in deck.report)
    if deck.violations:
        lines.extend(["", "## 门禁失败"])
        lines.extend(f"- {violation}" for violation in deck.violations)
    if explain:
        lines.extend(["", "## 主牌模块"])
        lines.extend(f"- {item.count} {item.card['name']}：{item.module}，{item.reason}"
                     for item in deck.main)
    return "\n".join(lines) + "\n"


def validate_constructed_text(deck_text: str, fmt: str, bo3: bool = False,
                              colors: Sequence[str] = (), platform=None):
    """Run the canonical ``mtg_tool`` validator against rendered output.

    The validator consumes a deck file, so the generated text is kept in a
    short-lived temporary directory and never becomes an output artifact.
    ``platform`` values other than Arena are already covered by the candidate
    legality gate; ``mtg_tool`` currently has a dedicated print check only for
    Arena, so those values intentionally map to ``None`` here.
    """
    with tempfile.TemporaryDirectory(prefix="deckpooper_validate_") as tmp:
        deck_path = Path(tmp) / "deck.txt"
        deck_path.write_text(deck_text, encoding="utf-8")
        validator_args = argparse.Namespace(
            deckfile=str(deck_path),
            format=fmt,
            platform="arena" if platform == "arena" else None,
            bo3=bo3,
            no_sideboard=False,
            colors="".join(colors).lower() or None,
            no_cache=False,
        )
        stdout, stderr = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = mtg_tool.cmd_validate(validator_args)
        except Exception as exc:  # validator failures are a hard gate
            return 2, f"validator exception: {exc}"
        diagnostics = "\n".join(
            line.strip() for line in (stdout.getvalue() + "\n" + stderr.getvalue()).splitlines()
            if line.strip()
        )
        return int(code), diagnostics


def cmd_limited(args) -> int:
    try:
        table = mtga_draft_tool.load_card_table(args.set)
        if table is None:
            raise ValueError(f"缺少评分表 tools/cache/draft_ratings/{args.set}.json")
        pool = load_pool(args.pool, use_cache=not args.no_cache)
        deck = LS.build_limited_deck(
            pool, table=table,
            forced_colors=list(args.colors.upper()) if args.colors else None,
            strategy=args.strategy,
        )
    except (OSError, ValueError, mtg_tool.MtgToolError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2

    deck_text = render_deck(deck)
    report_text = render_report(deck, explain=args.explain)
    if args.report:
        Path(args.report).write_text(report_text, encoding="utf-8")
    print(report_text, end="")
    if not deck.valid:
        return 4
    if args.out:
        Path(args.out).write_text(deck_text, encoding="utf-8")
    if not args.out:
        print(deck_text, end="")
    return 0


def cmd_constructed(args) -> int:
    try:
        candidates = load_candidates(args.candidates)
        seed = CS.parse_seed_file(args.seed)
        deck = CS.build_constructed_deck(
            candidates, seed, args.format, bo3=args.bo3,
            strategy=args.strategy, platform=args.platform)
        deck_text = render_constructed_deck(deck)
        if deck.valid:
            validate_code, diagnostics = validate_constructed_text(
                deck_text, args.format, bo3=args.bo3, colors=deck.colors,
                platform=args.platform)
            if validate_code:
                detail = " ".join(diagnostics.split())[:1000]
                message = f"mtg_tool validate 失败 (exit code {validate_code})"
                if detail:
                    message += f": {detail}"
                deck.violations.append(message)
                deck.valid = False
                deck.report.append(message)
            else:
                deck.report.append("mtg_tool validate: 通过")
        report_text = render_constructed_report(deck, explain=args.explain)
        if args.report:
            Path(args.report).write_text(report_text, encoding="utf-8")
        print(report_text, end="")
        if not deck.valid:
            return 4
        if args.out:
            Path(args.out).write_text(deck_text, encoding="utf-8")
        else:
            print(deck_text, end="")
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2


def cmd_draft(args) -> int:
    """转发到已有 MTGA 轮抓管线，避免复制日志 tail 和面板实现。"""
    forwarded = ["draft"]
    if args.watch:
        forwarded.append("--watch")
    elif args.record:
        forwarded.append("--record")
    if args.set_code:
        forwarded.extend(["--set", args.set_code])
    if args.port is not None:
        forwarded.extend(["--port", str(args.port)])
    if args.llm:
        forwarded.append("--llm")
    if args.llm_config:
        forwarded.extend(["--llm-config", args.llm_config])
    for name, value in (("--log", args.log), ("--poll", args.poll),
                        ("--max-polls", args.max_polls)):
        if value is not None:
            forwarded.extend([name, str(value)])
    if args.from_start:
        forwarded.append("--from-start")
    return mtga_auto_tool.main(forwarded)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    limited = sub.add_parser("limited", help="从牌池构建限制赛 40 张套牌")
    limited.add_argument("--pool", required=True, help="牌池文本或 Complete 录样 JSONL")
    limited.add_argument("--set", required=True, help="评分表系列码，如 HOB")
    limited.add_argument("--colors", help="强制主色，如 GU")
    limited.add_argument("--strategy", choices=LS.STRATEGIES, default="mid")
    limited.add_argument("--out", help="输出 MTGA 牌表路径")
    limited.add_argument("--report", help="输出 Markdown 报告路径")
    limited.add_argument("--explain", action="store_true", help="在牌表尾部写入逐张选牌理由")
    limited.add_argument("--no-cache", action="store_true", help="跳过 Scryfall 磁盘缓存")
    limited.set_defaults(func=cmd_limited)
    constructed = sub.add_parser("constructed", help="从种子与候选池构建构筑赛套牌")
    constructed.add_argument("--format", required=True, help="赛制，如 pioneer 或 brawl")
    constructed.add_argument("--seed", required=True, help="种子牌文件")
    constructed.add_argument("--candidates", required=True, help="mtg_tool search 输出的 JSON")
    constructed.add_argument("--bo3", action="store_true", help="生成最多 15 张备牌")
    constructed.add_argument("--platform", choices=["arena", "paper", "mtgo"],
                             help="额外平台可用性门禁")
    constructed.add_argument("--strategy", choices=("aggro", "mid", "control"), default="mid")
    constructed.add_argument("--out", help="输出牌表路径；门禁失败时不写出")
    constructed.add_argument("--report", help="输出 Markdown 报告路径")
    constructed.add_argument("--explain", action="store_true", help="报告中展开模块与选牌理由")
    constructed.set_defaults(func=cmd_constructed)
    draft = sub.add_parser("draft", help="转发轮抓录样或实时 pick 面板")
    mode = draft.add_mutually_exclusive_group()
    mode.add_argument("--record", action="store_true", help="录样模式")
    mode.add_argument("--watch", action="store_true", help="实时 pick 面板")
    draft.add_argument("--set", dest="set_code", help="系列码，如 HOB")
    draft.add_argument("--port", type=int, default=None, help="面板端口")
    draft.add_argument("--llm", action="store_true", help="启用八轴 LLM 推荐")
    draft.add_argument("--llm-config", metavar="PATH", help="LLM 端点配置 JSON 路径")
    draft.add_argument("--log", help="Player.log 路径")
    draft.add_argument("--poll", type=float, help="轮询间隔秒")
    draft.add_argument("--from-start", action="store_true", help="从日志开头处理")
    draft.add_argument("--max-polls", type=int, help="最多轮询次数")
    draft.set_defaults(func=cmd_draft)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
