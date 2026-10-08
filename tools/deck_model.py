#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一牌表模型与解析层（底层架构强化计划 Phase 1）。

历史上 tools/ 下有 9 份各自为政的 parse_deck / load_deck 实现
（mtg_tool / deck_image / deck_version / rot_audit / newbie 下 5 份），
行为在注释、BOM、SET 后缀、中文段名、Commander 分派、坏行处理上互相分叉。
本模块是唯一实质实现，其余解析器全部收敛为一两行委托。

公开 API：
  CardRef / SkippedLine / Deck      —— 数据模型（frozen dataclass）
  DeckParseError                    —— 解析失败异常（strict 模式抛出）
  parse_deck(source, strict=False)  —— I/O 边界：路径（str/Path）或文本 → Deck
  parse_text(text, strict=False)    —— 纯函数：文本 → Deck
  front_name(name) / is_dfc_name(name) —— MDFC 辅助

解析规格（Phase 1 统一行为）：
  1. 文件按 utf-8-sig 读（BOM 兼容）；文本输入先剥开头 \\ufeff。
  2. 段头整行精确匹配、大小写不敏感、允许首尾空白：
     deck/main/主牌→main，sideboard/备牌→sideboard，
     commander→commander，companion→companion；
     about→其后内容忽略（逐行记入 skipped，reason="about-section"，
     直到下一个段头）。deck_version 旧实现虽识别 about 段但从不消费
     result["about"]（validate/report 均不读），故安全废弃。
  3. 剥除行尾 `(SET) 123` 后缀（编号可省）与 `[xxx]` 前缀。
  4. 跳过 `#`、`//` 注释行与空行；无段头时主牌后首个空行切备牌
     （仅一次，且主牌非空才触发 —— mtg_tool 语义）。
  5. 坏行（不匹配 `数量 牌名`）：strict=True 抛 DeckParseError（含行号）；
     strict=False 记入 skipped（reason="bad-line"），不静默、不兜底成假牌。
  6. MDFC 牌名保留 ` // ` 全名。
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "CardRef", "SkippedLine", "Deck", "DeckParseError",
    "parse_deck", "parse_text", "front_name", "is_dfc_name",
    "SECTION_HEADERS", "REASON_BAD_LINE", "REASON_ABOUT_SECTION",
    "BASIC_LANDS", "ANY_NUMBER",
]

REASON_BAD_LINE = "bad-line"
REASON_ABOUT_SECTION = "about-section"

SECTION_HEADERS = {
    "deck": "main", "main": "main", "主牌": "main",
    "sideboard": "sideboard", "备牌": "sideboard",
    "commander": "commander", "companion": "companion",
    "about": "about",
}

SECTIONS = ("commander", "companion", "main", "sideboard")

# 基本地名单（单一来源；Phase 2 统一前 deck_version 缺 Snow-Covered Wastes）
BASIC_LANDS = frozenset({
    "Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes",
    "Snow-Covered Plains", "Snow-Covered Island", "Snow-Covered Swamp",
    "Snow-Covered Mountain", "Snow-Covered Forest", "Snow-Covered Wastes",
})

# 规则文本允许任意张数的牌（静态豁免名单，供离线门禁使用；mtg_tool 的在线
# 核对走 oracle_text 动态判定，语义更全，不消费本列表。按需扩充）
ANY_NUMBER = frozenset({
    "Slime Against Humanity", "Rat Colony", "Persistent Petitioners",
    "Relentless Rats", "Shadowborn Apostle", "Seven Dwarves",
    "Dragon's Approach", "Hare Apparent", "Templar Knight",
})

_LINE_RE = re.compile(
    r"^(\d+)\s+(?:\[[^\]]+\]\s*)?(.+?)(?:\s+\([A-Za-z0-9_]+\)\s*\d*)?$")


class DeckParseError(Exception):
    """牌表解析失败（strict 模式下首个坏行抛出，消息含行号）。"""


@dataclass(frozen=True)
class CardRef:
    qty: int
    name: str
    section: str  # commander / companion / main / sideboard


@dataclass(frozen=True)
class SkippedLine:
    line_no: int
    raw: str
    reason: str  # REASON_BAD_LINE / REASON_ABOUT_SECTION


@dataclass(frozen=True)
class Deck:
    commander: tuple = ()
    companion: tuple = ()
    main: tuple = ()
    sideboard: tuple = ()
    skipped: tuple = ()

    # ---------------------------------------------------------------- 适配器
    def as_section_dict(self):
        """对齐 mtg_tool.parse_deckfile 返回：4 键齐全，值为 [(qty, name)]。"""
        return {sec: [(c.qty, c.name) for c in getattr(self, sec)]
                for sec in SECTIONS}

    def main_side_pairs(self):
        """对齐 rot_audit / mtga_cost：(main, side) 两个 [(qty, name)]。"""
        return ([(c.qty, c.name) for c in self.main],
                [(c.qty, c.name) for c in self.sideboard])

    def flat_names(self):
        """对齐 mana_audit / mana_audit2：主牌 [name]*qty 展开（只含主牌）。"""
        return [c.name for c in self.main for _ in range(c.qty)]

    def entries(self):
        """扁平 [(qty, name, section)]，按 commander→companion→main→sideboard。"""
        return [(c.qty, c.name, c.section) for sec in SECTIONS
                for c in getattr(self, sec)]

    def commanders_with_zone(self):
        """对齐 deck_image 三元组通道：[(qty, name, zone)]。"""
        return ([(c.qty, c.name, "commander") for c in self.commander]
                + [(c.qty, c.name, "companion") for c in self.companion])


def front_name(name):
    """MDFC 取正面名；单面牌原样返回。"""
    return name.split(" // ")[0]


def is_dfc_name(name):
    """牌名是否为 `Front // Back` 双面全名。"""
    return " // " in name


def parse_text(text, *, strict=False):
    """纯函数：牌表文本 → Deck。strict=True 时首个坏行抛 DeckParseError。"""
    if text.startswith("﻿"):  # 文本输入剥开头 BOM
        text = text[1:]
    acc = {sec: [] for sec in SECTIONS}
    skipped = []
    current = "main"
    blank_switched = False
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            if current == "main" and acc["main"] and not blank_switched:
                current = "sideboard"
                blank_switched = True
            continue
        header = SECTION_HEADERS.get(line.lower())
        if header is not None:
            current = header
            continue
        if line.startswith("#") or line.startswith("//"):
            continue
        if current == "about":
            skipped.append(SkippedLine(line_no, line, REASON_ABOUT_SECTION))
            continue
        m = _LINE_RE.match(line)
        if not m:
            if strict:
                raise DeckParseError(
                    f"第 {line_no} 行无法解析为 '数量 英文名': {line!r}")
            skipped.append(SkippedLine(line_no, line, REASON_BAD_LINE))
            continue
        qty, name = int(m.group(1)), m.group(2).strip()
        if not name:
            if strict:
                raise DeckParseError(f"第 {line_no} 行缺少牌名: {line!r}")
            skipped.append(SkippedLine(line_no, line, REASON_BAD_LINE))
            continue
        acc[current].append(CardRef(qty, name, current))
    return Deck(commander=tuple(acc["commander"]),
                companion=tuple(acc["companion"]),
                main=tuple(acc["main"]),
                sideboard=tuple(acc["sideboard"]),
                skipped=tuple(skipped))


def parse_deck(source, *, strict=False):
    """I/O 边界：source 为路径（str/Path）或牌表文本，返回 Deck。

    str 含换行符时按文本解析，否则按路径打开（不存在的路径照常抛 OSError）；
    Path 一律按路径。文件按 utf-8-sig 读（BOM 兼容）。
    """
    if isinstance(source, os.PathLike):
        text = Path(source).read_text(encoding="utf-8-sig")
    elif isinstance(source, str) and "\n" not in source and "\r" not in source:
        with open(source, "r", encoding="utf-8-sig") as fh:
            text = fh.read()
    else:
        text = str(source)
    return parse_text(text, strict=strict)
