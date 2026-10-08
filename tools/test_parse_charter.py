#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""牌表解析层契约测试 —— Phase 1 后版本：9 个解析器已收敛为 deck_model 委托。

Phase 0 版钉的是 9 份实现各自为政的现状；Phase 1 统一解析层落地后，
本文件改写为**新行为规格**的契约：所有包装器共享同一解析语义
（见 deck_model.py  docstring 的规格 1-6），差异只剩各自的返回形状。
怪异行为断言已按规格改写：mtga_cost 坏行 → skipped 而非 (1,line) 假牌；
rot_audit 的 startswith 过宽匹配 → 精确段头；Commander/Companion 牌张
正确分派而不再混入主牌；BOM 不再产生假牌；中文段名、注释行、
无段头空行切备牌对所有解析器生效。

Phase 3 已修：sim_red 老式调度 → 统一伦敦调度（见 TestOpeningUnified）；
  8 个 sim_*.py 已收敛为 tools/newbie/goldfish/ 引擎 + data JSON + decks 模块，
  原文件转为兼容 shim（模块级 API 与 CLI 输出格式不变）。
Phase 2 已修：BASIC_LANDS 统一为 deck_model 单一定义（12 张），见
TestBasicLandsUnified。
"""

import contextlib
import io
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck_model  # noqa: E402
import mtg_tool  # noqa: E402
import deck_image  # noqa: E402
import deck_version  # noqa: E402
import rot_audit  # noqa: E402

NEWBIE_DIR = Path(__file__).resolve().parent / "newbie"
sys.path.insert(0, str(NEWBIE_DIR))

# newbie 各模块 import 时的副作用（Phase 1 未改变其时序）：
#   deck_cost / mtga_cost / mana_audit 在模块顶层 json.load(tools/data/rarity_map.json)
#   （该文件 gitignored，缺失时 import 直接 FileNotFoundError）；
#   且三者均执行 sys.stdout.reconfigure(encoding='utf-8')；
#   mana_audit2 顶层不读数据（仅 top_cmc 内懒加载）；
#   sim_green / sim_red 顶层 from mtga_cost import parse_deck（连带 rarity_map 加载）。
try:
    import deck_cost  # noqa: E402
    import mtga_cost  # noqa: E402
    import mana_audit  # noqa: E402
    import mana_audit2  # noqa: E402
    import sim_green  # noqa: E402
    import sim_red  # noqa: E402
    NEWBIE_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - 仅在缺 tools/data 时触发
    NEWBIE_IMPORT_ERROR = exc

DECKLISTS = Path(__file__).resolve().parent / "testdata" / "decklists"

BOM_SAMPLE = (
    "Deck\n"
    "4 Lightning Strike\n"
    "20 Mountain\n"
    "\n"
    "Sideboard\n"
    "2 Negate\n"
)


def decklist(name):
    return str(DECKLISTS / name)


def write_temp(text, encoding="utf-8"):
    """写临时牌表文件，返回路径（调用方负责清理）。"""
    fd, path = tempfile.mkstemp(suffix=".txt")
    with open(fd, "w", encoding=encoding, newline="\n") as fh:
        fh.write(text)
    return path


def write_bom_sample():
    """BOM 样本在运行时现写（utf-8-sig），避免工具链吃掉提交文件里的 BOM。"""
    return write_temp(BOM_SAMPLE, encoding="utf-8-sig")


class TempFileTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = []

    def tearDown(self):
        for p in self._tmp:
            Path(p).unlink(missing_ok=True)

    def temp_deck(self, text, encoding="utf-8"):
        path = write_temp(text, encoding)
        self._tmp.append(path)
        return path


class NewbieTestCase(TempFileTestCase):
    def setUp(self):
        super().setUp()
        if NEWBIE_IMPORT_ERROR is not None:
            self.skipTest("newbie 模块 import 失败（缺 tools/data/rarity_map.json？）: %r"
                          % (NEWBIE_IMPORT_ERROR,))


# ---------------------------------------------------------------- mtg_tool
class TestMtgToolParseDeckfile(TempFileTestCase):
    """mtg_tool.parse_deckfile：薄委托 strict=True；坏行抛 DeckParseError（含行号）。"""

    def test_standard_mtga(self):
        self.assertEqual(mtg_tool.parse_deckfile(decklist("mtga_standard.txt")), {
            "commander": [],
            "companion": [],
            "main": [(4, "Lightning Strike"), (2, "Shock"), (20, "Mountain")],
            "sideboard": [(3, "Negate"), (1, "Island")],
        })

    def test_set_suffix_stripped(self):
        self.assertEqual(mtg_tool.parse_deckfile(decklist("set_suffix.txt")), {
            "commander": [],
            "companion": [],
            "main": [(4, "Bloated Contaminator"), (2, "Lightning Strike"), (10, "Island")],
            "sideboard": [(2, "Negate")],
        })

    def test_commander_companion_sections(self):
        self.assertEqual(mtg_tool.parse_deckfile(decklist("commander_companion.txt")), {
            "commander": [(1, "Kenrith, the Returned King")],
            "companion": [(1, "Lurrus of the Dream-Den")],
            "main": [(4, "Fabled Passage"), (2, "Island")],
            "sideboard": [(1, "Negate")],
        })

    def test_mdfc_names_kept_whole(self):
        self.assertEqual(mtg_tool.parse_deckfile(decklist("mdfc.txt")), {
            "commander": [],
            "companion": [],
            "main": [(4, "Clearwater Pathway // Murkwater Pathway"),
                     (2, "Spikefield Hazard // Spikefield Cave")],
            "sideboard": [(1, "Glasspool Mimic // Glasspool Shore")],
        })

    def test_blank_line_switches_to_sideboard_once(self):
        self.assertEqual(mtg_tool.parse_deckfile(decklist("no_header_blank_split.txt")), {
            "commander": [],
            "companion": [],
            "main": [(4, "Lightning Strike"), (2, "Shock"), (20, "Mountain")],
            "sideboard": [(3, "Negate"), (1, "Island")],
        })

    def test_comments_now_skipped(self):
        # Phase 1 行为变化：注释行统一跳过，不再抛 DeckParseError
        got = mtg_tool.parse_deckfile(decklist("comments.txt"))
        self.assertEqual(got["main"], [(4, "Lightning Strike"), (2, "Shock")])
        self.assertEqual(got["sideboard"], [(2, "Negate")])

    def test_chinese_headers_now_recognized(self):
        # Phase 1 行为变化：中文段名统一识别，"主牌" 不再是坏行
        got = mtg_tool.parse_deckfile(decklist("chinese_sections.txt"))
        self.assertEqual(got["main"], [(4, "Llanowar Elves"), (20, "Forest")])
        self.assertEqual(got["sideboard"], [(3, "Naturalize")])

    def test_bom_file_now_accepted(self):
        # Phase 1 行为变化：统一 utf-8-sig 读取，BOM 兼容
        path = write_bom_sample()
        self._tmp.append(path)
        got = mtg_tool.parse_deckfile(path)
        self.assertEqual(got["main"], [(4, "Lightning Strike"), (20, "Mountain")])
        self.assertEqual(got["sideboard"], [(2, "Negate")])

    def test_bad_line_raises_with_lineno(self):
        # 严格语义不变：坏行抛 DeckParseError 且消息含行号
        with self.assertRaises(mtg_tool.DeckParseError) as cm:
            mtg_tool.parse_deckfile(decklist("bad_lines.txt"))
        self.assertIn("第 3 行", str(cm.exception))
        self.assertIn("这是一行无法解析的坏行", str(cm.exception))

    def test_error_class_compatibility(self):
        # mtg_tool.DeckParseError 同时是 deck_model.DeckParseError 与 MtgToolError
        self.assertTrue(issubclass(mtg_tool.DeckParseError, deck_model.DeckParseError))
        self.assertTrue(issubclass(mtg_tool.DeckParseError, mtg_tool.MtgToolError))
        # forge_tool 的既有 import 路径不破
        self.assertIs(mtg_tool.DeckParseError, mtg_tool.DeckParseError)
        self.assertTrue(callable(mtg_tool.parse_deckfile))


# ---------------------------------------------------------------- deck_image
class TestDeckImageParseDeck(TempFileTestCase):
    """deck_image.parse_deck：返回 (main, side, commanders)；统一解析语义。"""

    def test_standard_mtga(self):
        main, side, commanders = deck_image.parse_deck(decklist("mtga_standard.txt"))
        self.assertEqual(main, [(4, "Lightning Strike"), (2, "Shock"), (20, "Mountain")])
        self.assertEqual(side, [(3, "Negate"), (1, "Island")])
        self.assertEqual(commanders, [])

    def test_set_suffix_now_stripped(self):
        # Phase 1 行为变化（修复）：剥除 "(SET) 123" 后缀，牌名查 Scryfall 更准
        main, side, _ = deck_image.parse_deck(decklist("set_suffix.txt"))
        self.assertEqual(main, [(4, "Bloated Contaminator"),
                                (2, "Lightning Strike"),
                                (10, "Island")])
        self.assertEqual(side, [(2, "Negate")])

    def test_commander_companion_zone_triples(self):
        main, side, commanders = deck_image.parse_deck(decklist("commander_companion.txt"))
        self.assertEqual(main, [(4, "Fabled Passage"), (2, "Island")])
        self.assertEqual(side, [(1, "Negate")])
        self.assertEqual(commanders, [(1, "Kenrith, the Returned King", "commander"),
                                      (1, "Lurrus of the Dream-Den", "companion")])

    def test_blank_line_now_switches(self):
        # Phase 1 行为变化：统一空行切备牌语义
        main, side, commanders = deck_image.parse_deck(decklist("no_header_blank_split.txt"))
        self.assertEqual(main, [(4, "Lightning Strike"), (2, "Shock"), (20, "Mountain")])
        self.assertEqual(side, [(3, "Negate"), (1, "Island")])
        self.assertEqual(commanders, [])

    def test_comments_and_bad_lines_skipped(self):
        main, side, _ = deck_image.parse_deck(decklist("comments.txt"))
        self.assertEqual(main, [(4, "Lightning Strike"), (2, "Shock")])
        self.assertEqual(side, [(2, "Negate")])
        main, side, _ = deck_image.parse_deck(decklist("bad_lines.txt"))
        self.assertEqual(main, [(4, "Lightning Strike"), (2, "Shock")])
        self.assertEqual(side, [(1, "Negate")])

    def test_chinese_headers_now_recognized(self):
        # Phase 1 行为变化：中文段名识别，Naturalize 正确归备牌
        main, side, _ = deck_image.parse_deck(decklist("chinese_sections.txt"))
        self.assertEqual(main, [(4, "Llanowar Elves"), (20, "Forest")])
        self.assertEqual(side, [(3, "Naturalize")])

    def test_mdfc_names_kept_whole(self):
        main, side, _ = deck_image.parse_deck(decklist("mdfc.txt"))
        self.assertEqual(main, [(4, "Clearwater Pathway // Murkwater Pathway"),
                                (2, "Spikefield Hazard // Spikefield Cave")])
        self.assertEqual(side, [(1, "Glasspool Mimic // Glasspool Shore")])

    def test_bom_file_accepted(self):
        path = write_bom_sample()
        self._tmp.append(path)
        main, side, _ = deck_image.parse_deck(path)
        self.assertEqual(main, [(4, "Lightning Strike"), (20, "Mountain")])
        self.assertEqual(side, [(2, "Negate")])


# ---------------------------------------------------------------- deck_version
class TestDeckVersionParseDeck(TempFileTestCase):
    """deck_version.parse_deck：dict 返回（主牌键 "deck"）；坏行警告通道保留。"""

    def parse(self, path):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            result = deck_version.parse_deck(Path(path))
        return result, err.getvalue()

    def test_standard_mtga(self):
        got, warn = self.parse(decklist("mtga_standard.txt"))
        self.assertEqual(got, {
            "deck": [(4, "Lightning Strike"), (2, "Shock"), (20, "Mountain")],
            "sideboard": [(3, "Negate"), (1, "Island")],
        })
        self.assertEqual(warn, "")

    def test_set_suffix_stripped(self):
        got, _ = self.parse(decklist("set_suffix.txt"))
        self.assertEqual(got, {
            "deck": [(4, "Bloated Contaminator"), (2, "Lightning Strike"), (10, "Island")],
            "sideboard": [(2, "Negate")],
        })

    def test_commander_companion_keys(self):
        got, _ = self.parse(decklist("commander_companion.txt"))
        self.assertEqual(got, {
            "commander": [(1, "Kenrith, the Returned King")],
            "companion": [(1, "Lurrus of the Dream-Den")],
            "deck": [(4, "Fabled Passage"), (2, "Island")],
            "sideboard": [(1, "Negate")],
        })

    def test_bad_lines_warn_and_skip(self):
        # 警告通道保留：坏行打印 [警告] 后跳过
        got, warn = self.parse(decklist("bad_lines.txt"))
        self.assertEqual(got, {
            "deck": [(4, "Lightning Strike"), (2, "Shock")],
            "sideboard": [(1, "Negate")],
        })
        self.assertIn("无法解析的行: 这是一行无法解析的坏行", warn)
        self.assertIn("无法解析的行: foobar", warn)

    def test_comments_silently_skipped_no_warning(self):
        # Phase 1 行为变化：注释行统一跳过，不再走"坏行警告"通道
        got, warn = self.parse(decklist("comments.txt"))
        self.assertEqual(got, {
            "deck": [(4, "Lightning Strike"), (2, "Shock")],
            "sideboard": [(2, "Negate")],
        })
        self.assertEqual(warn, "")

    def test_blank_line_now_switches(self):
        # Phase 1 行为变化：统一空行切备牌语义
        got, _ = self.parse(decklist("no_header_blank_split.txt"))
        self.assertEqual(got, {
            "deck": [(4, "Lightning Strike"), (2, "Shock"), (20, "Mountain")],
            "sideboard": [(3, "Negate"), (1, "Island")],
        })

    def test_chinese_headers_now_recognized(self):
        # Phase 1 行为变化：中文段名识别、无警告，Naturalize 正确归备牌
        got, warn = self.parse(decklist("chinese_sections.txt"))
        self.assertEqual(got, {
            "deck": [(4, "Llanowar Elves"), (20, "Forest")],
            "sideboard": [(3, "Naturalize")],
        })
        self.assertEqual(warn, "")

    def test_mdfc_names_kept_whole(self):
        got, _ = self.parse(decklist("mdfc.txt"))
        self.assertEqual(got, {
            "deck": [(4, "Clearwater Pathway // Murkwater Pathway"),
                     (2, "Spikefield Hazard // Spikefield Cave")],
            "sideboard": [(1, "Glasspool Mimic // Glasspool Shore")],
        })

    def test_bom_consumed(self):
        path = write_bom_sample()
        self._tmp.append(path)
        got, warn = self.parse(path)
        self.assertEqual(got, {
            "deck": [(4, "Lightning Strike"), (20, "Mountain")],
            "sideboard": [(2, "Negate")],
        })
        self.assertEqual(warn, "")


# ---------------------------------------------------------------- rot_audit
class TestRotAuditParseDeck(TempFileTestCase):
    """rot_audit.parse_deck：(主牌, 备牌) 两个 [(qty, name)]；统一解析语义。"""

    def test_standard_mtga(self):
        cards, side = rot_audit.parse_deck(decklist("mtga_standard.txt"))
        self.assertEqual(cards, [(4, "Lightning Strike"), (2, "Shock"), (20, "Mountain")])
        self.assertEqual(side, [(3, "Negate"), (1, "Island")])

    def test_set_suffix_now_stripped(self):
        # Phase 1 行为变化：剥除 "(SET) 123" 后缀
        cards, side = rot_audit.parse_deck(decklist("set_suffix.txt"))
        self.assertEqual(cards, [(4, "Bloated Contaminator"),
                                 (2, "Lightning Strike"),
                                 (10, "Island")])
        self.assertEqual(side, [(2, "Negate")])

    def test_commander_cards_no_longer_in_main(self):
        # Phase 1 行为变化：commander/companion 正确分派，不再混入主牌
        cards, side = rot_audit.parse_deck(decklist("commander_companion.txt"))
        self.assertEqual(cards, [(4, "Fabled Passage"), (2, "Island")])
        self.assertEqual(side, [(1, "Negate")])

    def test_sideboard_header_must_be_exact(self):
        # Phase 1 行为变化：段头精确匹配，"Sideboard 备注文字" 是坏行（记入
        # skipped），后续牌张留在主牌
        path = self.temp_deck("Deck\n4 Shock\nSideboard 备注文字\n2 Negate\n")
        cards, side = rot_audit.parse_deck(path)
        self.assertEqual(cards, [(4, "Shock"), (2, "Negate")])
        self.assertEqual(side, [])

    def test_comments_skipped(self):
        cards, side = rot_audit.parse_deck(decklist("comments.txt"))
        self.assertEqual(cards, [(4, "Lightning Strike"), (2, "Shock")])
        self.assertEqual(side, [(2, "Negate")])

    def test_bad_lines_skipped(self):
        cards, side = rot_audit.parse_deck(decklist("bad_lines.txt"))
        self.assertEqual(cards, [(4, "Lightning Strike"), (2, "Shock")])
        self.assertEqual(side, [(1, "Negate")])

    def test_blank_line_now_switches(self):
        # Phase 1 行为变化：统一空行切备牌语义
        cards, side = rot_audit.parse_deck(decklist("no_header_blank_split.txt"))
        self.assertEqual(cards, [(4, "Lightning Strike"), (2, "Shock"), (20, "Mountain")])
        self.assertEqual(side, [(3, "Negate"), (1, "Island")])

    def test_chinese_headers_now_recognized(self):
        # Phase 1 行为变化：中文段名识别，Naturalize 正确归备牌
        cards, side = rot_audit.parse_deck(decklist("chinese_sections.txt"))
        self.assertEqual(cards, [(4, "Llanowar Elves"), (20, "Forest")])
        self.assertEqual(side, [(3, "Naturalize")])

    def test_mdfc_names_kept_whole(self):
        cards, side = rot_audit.parse_deck(decklist("mdfc.txt"))
        self.assertEqual(cards, [(4, "Clearwater Pathway // Murkwater Pathway"),
                                 (2, "Spikefield Hazard // Spikefield Cave")])
        self.assertEqual(side, [(1, "Glasspool Mimic // Glasspool Shore")])


# ---------------------------------------------------------------- newbie: deck_cost
class TestDeckCostParseDeck(NewbieTestCase):
    """newbie/deck_cost.parse_deck：扁平 list，Phase 1 起统一为 (qty, name, section)。"""

    def test_standard_mtga_qty_first_tuple(self):
        # Phase 1 行为变化：元素顺序统一 (qty, name, section)（旧的反序废弃），
        # section 取值 commander/companion/main/sideboard
        self.assertEqual(deck_cost.parse_deck(decklist("mtga_standard.txt")), [
            (4, "Lightning Strike", "main"),
            (2, "Shock", "main"),
            (20, "Mountain", "main"),
            (3, "Negate", "sideboard"),
            (1, "Island", "sideboard"),
        ])

    def test_set_suffix_stripped(self):
        self.assertEqual(deck_cost.parse_deck(decklist("set_suffix.txt")), [
            (4, "Bloated Contaminator", "main"),
            (2, "Lightning Strike", "main"),
            (10, "Island", "main"),
            (2, "Negate", "sideboard"),
        ])

    def test_bracket_prefix_stripped(self):
        path = self.temp_deck("Deck\n2 [B] Shock\n")
        self.assertEqual(deck_cost.parse_deck(path), [(2, "Shock", "main")])

    def test_chinese_sections(self):
        self.assertEqual(deck_cost.parse_deck(decklist("chinese_sections.txt")), [
            (4, "Llanowar Elves", "main"),
            (20, "Forest", "main"),
            (3, "Naturalize", "sideboard"),
        ])

    def test_commander_companion_dispatched(self):
        # Phase 1 行为变化：commander/companion 正确分派，不再混入 main
        self.assertEqual(deck_cost.parse_deck(decklist("commander_companion.txt")), [
            (1, "Kenrith, the Returned King", "commander"),
            (1, "Lurrus of the Dream-Den", "companion"),
            (4, "Fabled Passage", "main"),
            (2, "Island", "main"),
            (1, "Negate", "sideboard"),
        ])

    def test_blank_line_now_switches(self):
        # Phase 1 行为变化：统一空行切备牌语义
        self.assertEqual(deck_cost.parse_deck(decklist("no_header_blank_split.txt")), [
            (4, "Lightning Strike", "main"),
            (2, "Shock", "main"),
            (20, "Mountain", "main"),
            (3, "Negate", "sideboard"),
            (1, "Island", "sideboard"),
        ])

    def test_comments_and_bad_lines_skipped(self):
        self.assertEqual(deck_cost.parse_deck(decklist("comments.txt")), [
            (4, "Lightning Strike", "main"),
            (2, "Shock", "main"),
            (2, "Negate", "sideboard"),
        ])
        self.assertEqual(deck_cost.parse_deck(decklist("bad_lines.txt")), [
            (4, "Lightning Strike", "main"),
            (2, "Shock", "main"),
            (1, "Negate", "sideboard"),
        ])

    def test_mdfc_names_kept_whole(self):
        self.assertEqual(deck_cost.parse_deck(decklist("mdfc.txt")), [
            (4, "Clearwater Pathway // Murkwater Pathway", "main"),
            (2, "Spikefield Hazard // Spikefield Cave", "main"),
            (1, "Glasspool Mimic // Glasspool Shore", "sideboard"),
        ])

    def test_bom_file_accepted(self):
        path = write_bom_sample()
        self._tmp.append(path)
        self.assertEqual(deck_cost.parse_deck(path), [
            (4, "Lightning Strike", "main"),
            (20, "Mountain", "main"),
            (2, "Negate", "sideboard"),
        ])


# ---------------------------------------------------------------- newbie: mtga_cost
class TestMtgaCostParseDeck(NewbieTestCase):
    """newbie/mtga_cost.parse_deck：(主牌, 备牌)；坏行 → skipped（兜底假牌废弃）。"""

    def test_standard_mtga(self):
        main, side = mtga_cost.parse_deck(decklist("mtga_standard.txt"))
        self.assertEqual(main, [(4, "Lightning Strike"), (2, "Shock"), (20, "Mountain")])
        self.assertEqual(side, [(3, "Negate"), (1, "Island")])

    def test_set_suffix_stripped(self):
        main, side = mtga_cost.parse_deck(decklist("set_suffix.txt"))
        self.assertEqual(main, [(4, "Bloated Contaminator"), (2, "Lightning Strike"), (10, "Island")])
        self.assertEqual(side, [(2, "Negate")])

    def test_bad_lines_now_dropped(self):
        # Phase 1 行为变化：坏行记入 skipped 而不再兜底成 (1, line) 假牌
        main, side = mtga_cost.parse_deck(decklist("bad_lines.txt"))
        self.assertEqual(main, [(4, "Lightning Strike"), (2, "Shock")])
        self.assertEqual(side, [(1, "Negate")])

    def test_unknown_headers_no_longer_fake_cards(self):
        # Phase 1 行为变化：Commander/Companion 块头正确分派，不再变 (1, "Commander")
        main, side = mtga_cost.parse_deck(decklist("commander_companion.txt"))
        self.assertEqual(main, [(4, "Fabled Passage"), (2, "Island")])
        self.assertEqual(side, [(1, "Negate")])

    def test_chinese_sections(self):
        main, side = mtga_cost.parse_deck(decklist("chinese_sections.txt"))
        self.assertEqual(main, [(4, "Llanowar Elves"), (20, "Forest")])
        self.assertEqual(side, [(3, "Naturalize")])

    def test_comments_skipped(self):
        main, side = mtga_cost.parse_deck(decklist("comments.txt"))
        self.assertEqual(main, [(4, "Lightning Strike"), (2, "Shock")])
        self.assertEqual(side, [(2, "Negate")])

    def test_bracket_prefix_stripped(self):
        path = self.temp_deck("Deck\n2 [B] Shock\n")
        self.assertEqual(mtga_cost.parse_deck(path), ([(2, "Shock")], []))

    def test_blank_line_now_switches(self):
        # Phase 1 行为变化：统一空行切备牌语义
        main, side = mtga_cost.parse_deck(decklist("no_header_blank_split.txt"))
        self.assertEqual(main, [(4, "Lightning Strike"), (2, "Shock"), (20, "Mountain")])
        self.assertEqual(side, [(3, "Negate"), (1, "Island")])

    def test_mdfc_names_kept_whole(self):
        main, side = mtga_cost.parse_deck(decklist("mdfc.txt"))
        self.assertEqual(main, [(4, "Clearwater Pathway // Murkwater Pathway"),
                                (2, "Spikefield Hazard // Spikefield Cave")])
        self.assertEqual(side, [(1, "Glasspool Mimic // Glasspool Shore")])

    def test_bom_no_longer_fake_card(self):
        # Phase 1 行为变化：BOM 兼容，不再产生 (1, "\ufeffDeck") 假牌
        path = write_bom_sample()
        self._tmp.append(path)
        main, side = mtga_cost.parse_deck(path)
        self.assertEqual(main, [(4, "Lightning Strike"), (20, "Mountain")])
        self.assertEqual(side, [(2, "Negate")])


# ---------------------------------------------------------------- newbie: mana_audit / mana_audit2
class TestManaAuditLoadDeck(NewbieTestCase):
    """mana_audit.load_deck / mana_audit2.load_deck：[name]*qty 扁平展开，只含主牌。"""

    def assert_both(self, path, expected):
        self.assertEqual(mana_audit.load_deck(path), expected)
        self.assertEqual(mana_audit2.load_deck(path), expected)

    def test_standard_mtga_expands_flat(self):
        self.assert_both(decklist("mtga_standard.txt"),
                         ["Lightning Strike"] * 4 + ["Shock"] * 2 + ["Mountain"] * 20)

    def test_set_suffix_now_stripped(self):
        # Phase 1 行为变化（改善）：剥除 "(SET) 123" 后缀
        self.assert_both(decklist("set_suffix.txt"),
                         ["Bloated Contaminator"] * 4
                         + ["Lightning Strike"] * 2
                         + ["Island"] * 10)

    def test_sideboard_section_content_skipped(self):
        path = self.temp_deck("Deck\n4 Shock\nSideboard\n2 Negate\n")
        self.assert_both(path, ["Shock"] * 4)

    def test_chinese_sections(self):
        self.assert_both(decklist("chinese_sections.txt"),
                         ["Llanowar Elves"] * 4 + ["Forest"] * 20)

    def test_commander_cards_no_longer_in_main(self):
        # Phase 1 行为变化：commander/companion 正确分派，不再混入主牌
        self.assert_both(decklist("commander_companion.txt"),
                         ["Fabled Passage"] * 4 + ["Island"] * 2)

    def test_comments_and_bad_lines_skipped(self):
        self.assert_both(decklist("comments.txt"), ["Lightning Strike"] * 4 + ["Shock"] * 2)
        self.assert_both(decklist("bad_lines.txt"), ["Lightning Strike"] * 4 + ["Shock"] * 2)

    def test_blank_line_now_switches(self):
        # Phase 1 行为变化：统一空行切备牌语义，空行后牌张不再进主牌展开
        self.assert_both(decklist("no_header_blank_split.txt"),
                         ["Lightning Strike"] * 4 + ["Shock"] * 2 + ["Mountain"] * 20)

    def test_mdfc_names_kept_whole(self):
        self.assert_both(decklist("mdfc.txt"),
                         ["Clearwater Pathway // Murkwater Pathway"] * 4
                         + ["Spikefield Hazard // Spikefield Cave"] * 2)


# ---------------------------------------------------------------- newbie: sim 包装层（代表抽样）
class TestSimWrapperLoadDeck(NewbieTestCase):
    """sim_*.load_deck：mtga_cost.parse_deck 主牌 [name]*qty 展开 + 基本地名替换为 LAND。"""

    def test_sim_green_expands_and_maps_forest(self):
        path = self.temp_deck("Deck\n4 Forest\n2 Llanowar Elves\nSideboard\n1 Negate\n")
        self.assertEqual(sim_green.load_deck(path),
                         ["Forest"] * 4 + ["Llanowar Elves"] * 2)

    def test_sim_red_expands_and_maps_mountain(self):
        path = self.temp_deck("Deck\n4 Mountain\n2 Shock\nSideboard\n1 Negate\n")
        self.assertEqual(sim_red.load_deck(path), ["Mountain"] * 4 + ["Shock"] * 2)


# ---------------------------------------------------------------- 调度（Phase 3 已统一伦敦）
class TestOpeningUnified(NewbieTestCase):
    """Phase 3 起 sim_red / sim_green 统一走 goldfish 引擎的伦敦调度（7→6→5）。

    用零地牌库强制两次调度全部触发，断言终手牌数一致（确定性，与种子无关）。
    """

    def test_zero_land_deck_forces_two_mulligans(self):
        red = sim_red.Game(["Shock"] * 60, random.Random(42))
        green = sim_green.Game(["Llanowar Elves"] * 60, random.Random(42))
        # 伦敦调度：7→6→5，两者终手牌均为 5 张
        self.assertEqual(len(red.hand), 5)
        self.assertEqual(len(green.hand), 5)


# ---------------------------------------------------------------- 基本地清单（Phase 2 已统一）
class TestBasicLandsUnified(unittest.TestCase):
    """BASIC_LANDS 已统一为 deck_model 单一定义（12 张，含 Snow-Covered Wastes），
    deck_version / mtg_tool 各自原名 re-export 兼容。"""

    def test_unified_twelve(self):
        self.assertEqual(len(deck_model.BASIC_LANDS), 12)
        self.assertIn("Snow-Covered Wastes", deck_model.BASIC_LANDS)
        self.assertIs(deck_version.BASIC_LANDS, deck_model.BASIC_LANDS)
        self.assertIs(mtg_tool.BASIC_LAND_NAMES, deck_model.BASIC_LANDS)
        self.assertIn("Snow-Covered Wastes", deck_version.BASIC_LANDS)
        self.assertEqual(deck_version.BASIC_LANDS, mtg_tool.BASIC_LAND_NAMES)


if __name__ == "__main__":
    unittest.main()
