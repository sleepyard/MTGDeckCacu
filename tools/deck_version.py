#!/usr/bin/env python3
"""套牌版本化交付脚手架：按本项目 DeckList 约定创建新版本套牌。

用法:
  python tools/deck_version.py --format Explorer --colors MonoGreen --theme LandPlant \
      --deck-file path/to/deck.txt [--notes "备注"]
  python tools/deck_version.py --dir DeckList/Explorer_SlimeAgainstHumanity/Golgari \
      --deck-file path/to/deck.txt
  python tools/deck_version.py --config params.json

行为:
  1. 定位目标目录：--dir 优先（相对项目根或绝对路径），
     否则组合为 DeckList/{format}_{colors}_{theme}/，不存在时自动创建。
  2. 扫描目录内已有 *V{N}.txt，分配下一个版本号（禁止覆盖旧版）。
  3. 写入牌表 {Name}V{N}.txt（MTGA 导入格式原样拷贝）；Name 默认取目录内
     最新版本文件的主名，目录为空时取 --name 或 --theme。
  4. 生成 {Name}V{N}.md 报告骨架（已存在则跳过，不覆盖）。
  5. 基础门禁校验：主牌 >= 60、备牌 0 或 15、同名 >4 报警
     （基本地与 ANY_NUMBER 豁免名单除外）；有问题时返回退出码 2。

Git Bash 下中文命令行参数会被 GBK 控制台弄乱，含中文时一律用 --config
传 JSON（UTF-8），键：format/colors/theme/name/dir/deck_file/notes/root。
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import runlog
from deck_model import (ANY_NUMBER, BASIC_LANDS, REASON_BAD_LINE,
                        parse_deck as _parse_deck)

# BASIC_LANDS / ANY_NUMBER 单一来源在 deck_model（Phase 2 统一，修复本地名单
# 缺 Snow-Covered Wastes 的问题）；此处保留原名 re-export 兼容。

VERSION_RE = re.compile(r"^(.*?)V(\d+)\.txt$", re.IGNORECASE)

# 报告骨架章节，参照 DeckList 下现存 V{n}.md（LandPlant/PeerAbyss/Lantern 等）的公共结构
REPORT_SECTIONS = [
    "运行基线",
    "体检",
    "检索覆盖",
    "构筑方向",
    "最终导入牌表",
    "主牌功能表",
    "备牌功能表",
    "改动对照",
    "留牌与回合节奏",
    "换备简表",
    "可调仓位",
    "运行清单",
]


def parse_deck(path):
    """薄委托：deck_model.parse_deck → {section: [(qty, name)]}。

    主牌键为 "deck"（对齐 validate 与既有调用）；只含非空分区；
    坏行打印警告后跳过（警告通道沿用旧行为）。BOM 由 utf-8-sig 读取兼容。
    """
    deck = _parse_deck(Path(path))
    for skip in deck.skipped:
        if skip.reason == REASON_BAD_LINE:
            print(f"  [警告] 无法解析的行: {skip.raw}", file=sys.stderr)
    result = {}
    for key, cards in (("commander", deck.commander), ("companion", deck.companion),
                       ("deck", deck.main), ("sideboard", deck.sideboard)):
        if cards:
            result[key] = [(c.qty, c.name) for c in cards]
    return result


def validate(sections):
    """基础门禁：返回问题列表，空列表表示通过。"""
    problems = []
    main = sum(q for q, _ in sections.get("deck", []))
    side = sum(q for q, _ in sections.get("sideboard", []))
    if main < 60:
        problems.append(f"主牌 {main} 张 < 60")
    if side not in (0, 15):
        problems.append(f"备牌 {side} 张（应为 0 或 15）")
    counts = {}
    for sec, cards in sections.items():
        if sec in ("commander", "companion"):
            continue
        for q, name in cards:
            counts[name] = counts.get(name, 0) + q
    for name, total in counts.items():
        if total > 4 and name not in BASIC_LANDS and name not in ANY_NUMBER:
            problems.append(f"同名超限: {name} x{total}")
    return problems


def scan_versions(folder):
    """返回目录内 (max_version, latest_name)；无版本文件时返回 (0, None)。"""
    best_num, best_name = 0, None
    for f in folder.glob("*V*.txt"):
        m = VERSION_RE.match(f.name)
        if m and int(m.group(2)) > best_num:
            best_num, best_name = int(m.group(2)), m.group(1)
    return best_num, best_name


def build_report(name, version, args, notes):
    lines = [f"# {name} V{version}（{args.format or '（赛制待填）'} / {args.theme or name}）",
             "",
             f"- 日期：{date.today().isoformat()}",
             f"- 版本备注：{notes or '（待填）'}",
             ""]
    for sec in REPORT_SECTIONS:
        lines.append(f"## {sec}")
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path,
                    help="JSON 参数文件（UTF-8）。含中文时一律用此方式传参。"
                         "键：format/colors/theme/name/dir/deck_file/notes/root")
    ap.add_argument("--dir", help="目标目录（相对项目根或绝对路径），最优先；"
                                  "用于方向子文件夹，如 DeckList/Explorer_SlimeAgainstHumanity/Golgari")
    ap.add_argument("--format", help="赛制，如 Explorer / Pioneer")
    ap.add_argument("--colors", help="色组，如 MonoGreen / Boros / FullColor")
    ap.add_argument("--theme", help="套牌主题名称，如 LandPlant")
    ap.add_argument("--name", help="文件主名（默认取目录内最新版本主名，其次 --theme）")
    ap.add_argument("--deck-file", type=Path, help="MTGA 导入格式牌表")
    ap.add_argument("--notes", default="", help="写入报告的版本备注")
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent,
                    help="项目根目录（默认取脚本上级）")
    args = ap.parse_args(argv)

    if args.config:
        cfg = json.loads(args.config.read_text(encoding="utf-8-sig"))
        for key in ("format", "colors", "theme", "name", "dir", "notes"):
            if cfg.get(key):
                setattr(args, key, cfg[key])
        if cfg.get("deck_file"):
            args.deck_file = Path(cfg["deck_file"])
        if cfg.get("root"):
            args.root = Path(cfg["root"])

    if not args.deck_file:
        ap.error("必须提供 --deck-file（或 --config 中的 deck_file）")

    if args.dir:
        folder = Path(args.dir)
        if not folder.is_absolute():
            folder = args.root / folder
    else:
        if not (args.format and args.colors and args.theme):
            ap.error("必须提供 --dir，或 --format/--colors/--theme 三者（或 --config）")
        folder = args.root / "DeckList" / f"{args.format}_{args.colors}_{args.theme}"
    folder.mkdir(parents=True, exist_ok=True)

    max_version, latest_name = scan_versions(folder)
    version = max_version + 1
    name = args.name or latest_name or args.theme
    if not name:
        ap.error("目录为空且未提供 --theme/--name，无法确定文件主名")

    deck_out = folder / f"{name}V{version}.txt"
    deck_out.write_text(args.deck_file.read_text(encoding="utf-8-sig"),
                        encoding="utf-8", newline="\n")

    report_out = folder / f"{name}V{version}.md"
    report_existed = report_out.exists()
    if not report_existed:
        report_out.write_text(build_report(name, version, args, args.notes),
                              encoding="utf-8", newline="\n")

    problems = validate(parse_deck(deck_out))
    print(f"[完成] {deck_out}")
    print(f"[完成] {report_out}" + ("（已存在，未覆盖）" if report_existed else ""))
    fmt = (args.format or "pioneer").lower()
    print(f"[提示] 完整三重校验：python tools/mtg_tool.py validate {deck_out} --format {fmt} --bo3")
    if problems:
        print("[门禁警告]")
        for p in problems:
            print(f"  - {p}")
        runlog.log_run("deck_version.py", "error",
                       f"{name}V{version} {deck_out} 门禁警告{len(problems)}条 exit=2")
        return 2
    print("[门禁] 基础校验通过")
    runlog.log_run("deck_version.py", "ok", f"{name}V{version} {deck_out} exit=0")
    return 0


if __name__ == "__main__":
    sys.exit(runlog.run_logged("deck_version.py", main))
