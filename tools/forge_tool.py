#!/usr/bin/env python3
"""Forge 套牌测试 CLI：MTGO/MTGA 牌表 → Forge .dck 转换、AI vs AI 无头模拟、GUI 试玩入口。

依赖（均需先安装，见 tools/README.md）：
- 便携 JDK：tools/jdk/bin/java(.exe)，或 JAVA_HOME / PATH 中的 java 17+
- Forge 2.x：tools/forge/（内含主 jar 与 forge.exe）

仅 Python 标准库（3.7+）。牌表解析复用 mtg_tool.parse_deckfile。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mtg_tool import DeckParseError, parse_deckfile  # noqa: E402

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
FORGE_DIR = TOOLS_DIR / "forge"
SIMDECKS_DIR = FORGE_DIR / "simdecks"
RESULT_DIR = REPO_ROOT / "SimResult"

AI_CAVEAT = ("Forge AI 口径：快攻/中速表现尚可，控制一般，组合技严重失真；"
             "未实现的牌无法导入。本结果仅为 AI 对局样本，不等于真人对局胜率。")


class ForgeToolError(Exception):
    pass


# ---------------------------------------------------------------- 环境定位
def find_java():
    """解析顺序：tools/jdk → JAVA_HOME → PATH。返回可执行文件路径。"""
    exe = "java.exe" if os.name == "nt" else "java"
    candidates = [TOOLS_DIR / "jdk" / "bin" / exe]
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidates.append(Path(java_home) / "bin" / exe)
    for cand in candidates:
        if cand.is_file():
            return str(cand)
    on_path = shutil.which("java")
    if on_path:
        return on_path
    raise ForgeToolError("未找到 Java：请安装便携 JDK 到 tools/jdk/，或配置 JAVA_HOME/PATH（需 Java 17+）")


def find_forge_jar():
    """在 tools/forge/ 下定位模拟入口主 jar（排除安装器）。"""
    if not FORGE_DIR.is_dir():
        raise ForgeToolError(f"Forge 未安装：{FORGE_DIR} 不存在")
    jars = [p for p in FORGE_DIR.rglob("*.jar") if "installer" not in p.name.lower()]
    if not jars:
        raise ForgeToolError(f"{FORGE_DIR} 下未找到 Forge 主 jar")
    def rank(p):
        name = p.name.lower()
        if name.startswith("forge-gui-desktop") and "jar-with-dependencies" in name:
            return 0
        if name.startswith("forge-gui-desktop"):
            return 1
        if name.startswith("forge"):
            return 2
        return 3
    return sorted(jars, key=rank)[0]


def forge_deck_dir(fmt="constructed"):
    """Forge 用户档案的牌表目录（sim 的 -d 只从这里读牌；-D 仅锦标赛模式生效）。

    Windows: %APPDATA%/Forge/decks/{constructed|commander}。"""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        base = base / "Forge" / "decks"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Forge" / "decks"
    else:
        base = Path.home() / ".forge" / "decks"
    return base / ("commander" if fmt == "commander" else "constructed")


# ---------------------------------------------------------------- convert
def sanitize_name(text):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_") or "deck"


def to_dck(sections, name):
    """生成 Forge .dck 文本。companion 分区 Forge 无对应结构，调用方需另行处理。"""
    lines = ["[metadata]", f"Name={name}"]
    for header, key in (("[Main]", "main"), ("[Sideboard]", "sideboard"),
                        ("[Commander]", "commander")):
        entries = sections.get(key) or []
        if not entries:
            continue
        lines.append(header)
        # Forge 只认双面牌的正面名（如 "Spikefield Hazard // Spikefield Cave" → "Spikefield Hazard"）
        lines.extend(f"{qty} {card.split(' // ')[0]}" for qty, card in entries)
    return "\n".join(lines) + "\n"


def convert_deck(deckfile, name=None, out_dir=SIMDECKS_DIR):
    """牌表 → .dck 文件，返回 (dck路径, 警告列表)。"""
    path = Path(deckfile)
    sections = parse_deckfile(str(path))
    deck_name = name or path.stem
    warnings = []
    if sections.get("companion"):
        warnings.append("companion 分区无 Forge 对应结构，未写入 .dck："
                        + ", ".join(n for _, n in sections["companion"]))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dck_path = out_dir / (sanitize_name(deck_name) + ".dck")
    dck_path.write_text(to_dck(sections, deck_name), encoding="utf-8")
    return dck_path, warnings


def cmd_convert(args):
    try:
        dck_path, warnings = convert_deck(args.deckfile, name=args.name, out_dir=args.out)
    except (DeckParseError, OSError) as exc:
        print(f"[错误] 牌表解析失败: {exc}", file=sys.stderr)
        return 2
    for w in warnings:
        print(f"[警告] {w}", file=sys.stderr)
    print(str(dck_path))
    return 0


# ---------------------------------------------------------------- sim
# Forge sim 真实输出（2.0.13 实测）：
#   Game Outcome: Ai(1)-X has won because all opponents have lost
#   Match Result: Ai(1)-X: 2 Ai(2)-Y: 0      <- 每局后的累计比分，最后一行为最终
#   Game Result: Game 2 ended in 2938 ms. Ai(1)-X has won!
MATCH_RESULT_PATTERN = re.compile(r"Match Result:\s*(.+)$", re.I)
SCORE_PATTERN = re.compile(r"Ai\(\d+\)-(.+?):\s*(\d+)")
GAME_RESULT_PATTERN = re.compile(r"Game Result: Game \d+ ended.*?(?:has won!|$)", re.I)
GAME_WIN_FALLBACK = re.compile(r"Game Result: Game \d+ ended.*Ai\(\d+\)-(.+?) has won!", re.I)
DRAW_PATTERN = re.compile(r"\b(draw|tie)\b", re.I)
LOAD_FAIL_PATTERN = re.compile(r"(could not|failed to|cannot).*(load|read|parse).*(deck|dck)|not implemented", re.I)


def _owner(player_text, deck_names):
    for name in deck_names:
        if name.lower() in player_text.lower():
            return name
    return None


def parse_sim_output(text, deck_names):
    """从 Forge sim 输出统计各套牌胜局数。优先取最后一行 Match Result 累计比分；
    缺失时回退逐局 'Game Result ... has won!' 计数。无法解析返回 None。"""
    wins = {name: 0 for name in deck_names}
    last_tally = None
    fallback_wins = {name: 0 for name in deck_names}
    games_played = 0
    draws = 0
    for line in text.splitlines():
        m = MATCH_RESULT_PATTERN.search(line)
        if m:
            last_tally = m.group(1)
            continue
        if GAME_RESULT_PATTERN.search(line):
            games_played += 1
            w = GAME_WIN_FALLBACK.search(line)
            if w:
                owner = _owner(w.group(1), deck_names)
                if owner:
                    fallback_wins[owner] += 1
            elif DRAW_PATTERN.search(line):
                draws += 1
    if last_tally is not None:
        for player, score in SCORE_PATTERN.findall(last_tally):
            owner = _owner(player, deck_names)
            if owner:
                wins[owner] = int(score)
        if games_played:
            draws = max(games_played - sum(wins.values()), 0)
        return wins, draws
    if games_played:
        return fallback_wins, draws
    return None


def cmd_sim(args):
    try:
        java = find_java()
        jar = find_forge_jar()
    except ForgeToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 5

    deck_dir = forge_deck_dir(args.format)
    decks = []
    warnings = []
    for deckfile in (args.deck_a, args.deck_b):
        try:
            dck_path, w = convert_deck(deckfile, out_dir=deck_dir)
        except (DeckParseError, OSError) as exc:
            print(f"[错误] 牌表解析失败: {exc}", file=sys.stderr)
            return 2
        decks.append(dck_path)
        warnings.extend(w)
    for w in warnings:
        print(f"[警告] {w}", file=sys.stderr)

    cmd = [java, "-Dfile.encoding=UTF-8", "-jar", str(jar), "sim",
           "-d", decks[0].name, decks[1].name]
    if args.matches:
        cmd += ["-m", str(args.matches)]
    else:
        cmd += ["-n", str(args.games)]
    if args.format != "constructed":
        cmd += ["-f", args.format]
    cmd += ["-c", str(args.clock)]
    if args.quiet:
        cmd.append("-q")

    print(f"[info] 执行: {' '.join(cmd)}", file=sys.stderr)
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        proc = subprocess.run(cmd, cwd=str(FORGE_DIR), capture_output=True, timeout=None)
        output = proc.stdout.decode("utf-8", errors="replace") \
            + "\n--- stderr ---\n" + proc.stderr.decode("utf-8", errors="replace")
    except OSError as exc:
        print(f"[错误] Forge 启动失败: {exc}", file=sys.stderr)
        return 6

    RESULT_DIR.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    base = f"{stamp}_{decks[0].stem}_vs_{decks[1].stem}"
    log_path = RESULT_DIR / (base + ".log")
    log_path.write_text(output, encoding="utf-8")

    load_failed = bool(LOAD_FAIL_PATTERN.search(output))
    deck_names = [d.stem for d in decks]
    parsed = parse_sim_output(output, deck_names)

    lines = [
        f"# Forge 模拟报告: {deck_names[0]} vs {deck_names[1]}",
        "",
        f"- 开始时间: {started}",
        f"- Forge jar: {jar.name}",
        f"- 命令: `{' '.join(cmd)}`",
        f"- 进程退出码: {proc.returncode}",
        "",
    ]
    if parsed:
        wins, draws = parsed
        total = sum(wins.values()) + draws
        lines += [
            "## 结果",
            "",
            f"- {deck_names[0]} 胜: {wins[deck_names[0]]}",
            f"- {deck_names[1]} 胜: {wins[deck_names[1]]}",
            f"- 平局: {draws}",
            f"- 总局数: {total}",
            "",
        ]
        for name in deck_names:
            if total:
                lines.append(f"- {name} 胜率: {wins[name] / total:.1%}")
        lines.append("")
    else:
        lines += ["## 结果", "", "未能从输出解析胜负，请查阅原始日志。", ""]
    if load_failed:
        lines += ["> [警告] 日志疑似含套牌加载失败 / 牌未实现信息，结果可能无效，请核对原始日志。", ""]
    lines += ["> " + AI_CAVEAT, "", f"原始日志: {log_path.name}", ""]
    report_path = RESULT_DIR / (base + ".md")
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print(str(report_path))
    if parsed:
        wins, draws = parsed
        print(f"{deck_names[0]} {wins[deck_names[0]]} : {wins[deck_names[1]]} {deck_names[1]}"
              f"（平局 {draws}）", file=sys.stderr)
    if proc.returncode != 0:
        print(f"[错误] Forge 进程退出码 {proc.returncode}，详见 {log_path}", file=sys.stderr)
        return 6
    return 0


# ---------------------------------------------------------------- play
def cmd_play(args):
    if not FORGE_DIR.is_dir():
        print(f"[错误] Forge 未安装：{FORGE_DIR} 不存在", file=sys.stderr)
        return 5
    if args.deckfile:
        try:
            dck_path, warnings = convert_deck(args.deckfile, out_dir=forge_deck_dir())
        except (DeckParseError, OSError) as exc:
            print(f"[错误] 牌表解析失败: {exc}", file=sys.stderr)
            return 2
        for w in warnings:
            print(f"[警告] {w}", file=sys.stderr)
        print(f"[info] 已写入 {dck_path}，在 Forge 牌表编辑器 / 对局选牌界面可直接选用", file=sys.stderr)
    # forge.exe 包装器只认系统 Java（注册表/PATH），找不到便携 JDK 会弹
    # "requires a Java Runtime Environment 17"。改为复刻 forge.cmd 的官方
    # JVM 参数直接用便携 JDK 启动，确定性最高。
    try:
        subprocess.Popen(
            [find_java(), "-Xmx4096m", "-Dio.netty.tryReflectionSetAccessible=true",
             "-Dfile.encoding=UTF-8", "-jar", str(find_forge_jar())],
            cwd=str(FORGE_DIR))
    except (OSError, ForgeToolError) as exc:
        print(f"[错误] Forge 启动失败: {exc}", file=sys.stderr)
        return 6
    print("[info] Forge GUI 已启动", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- main
def build_parser():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("convert", help="MTGO/MTGA 牌表 → Forge .dck")
    pc.add_argument("deckfile")
    pc.add_argument("--name", help="套牌名（默认取文件名）")
    pc.add_argument("--out", default=str(SIMDECKS_DIR), help=".dck 输出目录")
    pc.set_defaults(func=cmd_convert)

    ps = sub.add_parser("sim", help="AI vs AI 无头模拟，输出胜率报告到 SimResult/")
    ps.add_argument("deck_a")
    ps.add_argument("deck_b")
    ps.add_argument("--games", type=int, default=10, help="总局数（默认 10）")
    ps.add_argument("--matches", type=int, default=0, help="BO<M> 场数，设置后覆盖 --games")
    ps.add_argument("--format", default="constructed",
                    choices=["constructed", "brawl", "commander"])
    ps.add_argument("--clock", type=int, default=120, help="单局最长秒数，超时判平（默认 120）")
    ps.add_argument("--quiet", action="store_true", help="静默模式，仅输出结果")
    ps.set_defaults(func=cmd_sim)

    pp = sub.add_parser("play", help="启动 Forge GUI 人工试玩")
    pp.add_argument("deckfile", nargs="?", help="可选：先转换为 .dck 供编辑器导入")
    pp.set_defaults(func=cmd_play)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
