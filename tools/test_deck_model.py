#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/deck_model.py 的直接单元测试（Phase 1 统一解析层本体）。

经由各包装器的端到端行为契约见 test_parse_charter.py；本文件只测
deck_model 自身的公开 API：parse_text / parse_deck / Deck 适配器 /
front_name / is_dfc_name / strict 语义 / skipped 记录。
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck_model  # noqa: E402
from deck_model import (  # noqa: E402
    CardRef, Deck, DeckParseError, SkippedLine,
    front_name, is_dfc_name, parse_deck, parse_text,
)


class TestParseTextSections(unittest.TestCase):
    def test_sections_and_order(self):
        deck = parse_text(
            "Commander\n1 Kenrith, the Returned King\n"
            "Companion\n1 Lurrus of the Dream-Den\n"
            "Deck\n4 Fabled Passage\n2 Island\n"
            "Sideboard\n1 Negate\n")
        self.assertEqual(deck.commander,
                         (CardRef(1, "Kenrith, the Returned King", "commander"),))
        self.assertEqual(deck.companion,
                         (CardRef(1, "Lurrus of the Dream-Den", "companion"),))
        self.assertEqual(deck.main, (CardRef(4, "Fabled Passage", "main"),
                                     CardRef(2, "Island", "main")))
        self.assertEqual(deck.sideboard, (CardRef(1, "Negate", "sideboard"),))
        self.assertEqual(deck.skipped, ())

    def test_headers_case_insensitive_and_whitespace_padded(self):
        deck = parse_text("  DECK \n4 Shock\nSideBoard\n2 Negate\n")
        self.assertEqual([c.name for c in deck.main], ["Shock"])
        self.assertEqual([c.name for c in deck.sideboard], ["Negate"])

    def test_chinese_headers(self):
        deck = parse_text("主牌\n4 Llanowar Elves\n备牌\n3 Naturalize\n")
        self.assertEqual([c.name for c in deck.main], ["Llanowar Elves"])
        self.assertEqual([c.name for c in deck.sideboard], ["Naturalize"])

    def test_main_header_alias(self):
        deck = parse_text("Main\n4 Shock\n")
        self.assertEqual([c.name for c in deck.main], ["Shock"])

    def test_set_suffix_and_bracket_prefix_stripped(self):
        deck = parse_text("Deck\n"
                          "4 Bloated Contaminator (ONE) 159\n"
                          "2 Lightning Strike (M19)\n"
                          "1 [B] Opt (FDN) 60\n")
        self.assertEqual([c.name for c in deck.main],
                         ["Bloated Contaminator", "Lightning Strike", "Opt"])
        self.assertEqual([c.qty for c in deck.main], [4, 2, 1])

    def test_comments_and_blank_lines_skipped(self):
        deck = parse_text("Deck\n# 注释\n// 注释\n4 Shock\n\nSideboard\n1 Negate\n")
        self.assertEqual([c.name for c in deck.main], ["Shock"])
        self.assertEqual(deck.skipped, ())

    def test_mdfc_full_name_kept(self):
        deck = parse_text("Deck\n4 Clearwater Pathway // Murkwater Pathway\n")
        self.assertEqual(deck.main[0].name, "Clearwater Pathway // Murkwater Pathway")


class TestBlankLineSwitch(unittest.TestCase):
    def test_first_blank_switches_to_sideboard(self):
        deck = parse_text("4 Shock\n\n2 Negate\n")
        self.assertEqual([c.name for c in deck.main], ["Shock"])
        self.assertEqual([c.name for c in deck.sideboard], ["Negate"])

    def test_switch_happens_only_once(self):
        deck = parse_text("4 Shock\n\n2 Negate\n\n1 Island\n")
        self.assertEqual([c.name for c in deck.sideboard], ["Negate", "Island"])

    def test_blank_ignored_while_main_empty(self):
        deck = parse_text("\n\n4 Shock\n")
        self.assertEqual([c.name for c in deck.main], ["Shock"])
        self.assertEqual(deck.sideboard, ())

    def test_blank_in_commander_does_not_switch(self):
        deck = parse_text("Commander\n1 Kenrith, the Returned King\n\nDeck\n4 Shock\n")
        self.assertEqual(deck.sideboard, ())
        self.assertEqual([c.name for c in deck.main], ["Shock"])

    def test_explicit_header_after_blank_switch(self):
        deck = parse_text("4 Shock\n\nDeck\n2 Opt\n")
        self.assertEqual([c.name for c in deck.main], ["Shock", "Opt"])


class TestSkippedAndStrict(unittest.TestCase):
    def test_bad_lines_recorded_lenient(self):
        deck = parse_text("Deck\n4 Shock\n坏行甲\nSideboard\nfoobar\n1 Negate\n")
        self.assertEqual(deck.skipped,
                         (SkippedLine(3, "坏行甲", "bad-line"),
                          SkippedLine(5, "foobar", "bad-line")))
        self.assertEqual([c.name for c in deck.main], ["Shock"])
        self.assertEqual([c.name for c in deck.sideboard], ["Negate"])

    def test_bad_line_raises_strict_with_lineno(self):
        with self.assertRaises(DeckParseError) as cm:
            parse_text("Deck\n4 Shock\n坏行甲\n", strict=True)
        self.assertIn("第 3 行", str(cm.exception))
        self.assertIn("坏行甲", str(cm.exception))

    def test_unknown_header_line_is_bad_line(self):
        # 精确段头：'"Sideboard 备注文字"' 不是段头 → 坏行，后续牌张留在 main
        deck = parse_text("Deck\n4 Shock\nSideboard 备注文字\n2 Negate\n")
        self.assertEqual([c.name for c in deck.main], ["Shock", "Negate"])
        self.assertEqual(deck.sideboard, ())
        self.assertEqual(deck.skipped, (SkippedLine(3, "Sideboard 备注文字", "bad-line"),))

    def test_about_section_content_ignored(self):
        deck = parse_text("Deck\n4 Shock\n\nAbout\nName My Deck\n2 Negate\n")
        self.assertEqual([c.name for c in deck.main], ["Shock"])
        self.assertEqual(deck.sideboard, ())
        self.assertEqual(deck.skipped,
                         (SkippedLine(5, "Name My Deck", "about-section"),
                          SkippedLine(6, "2 Negate", "about-section")))

    def test_about_section_resumes_at_next_header(self):
        deck = parse_text("About\nName x\nSideboard\n1 Negate\n")
        self.assertEqual([c.name for c in deck.sideboard], ["Negate"])
        self.assertEqual(deck.skipped, (SkippedLine(2, "Name x", "about-section"),))

    def test_bom_text_input(self):
        deck = parse_text("﻿Deck\n4 Shock\n")
        self.assertEqual([c.name for c in deck.main], ["Shock"])


class TestParseDeckSource(unittest.TestCase):
    def test_path_object(self):
        path = Path(__file__).resolve().parent / "testdata" / "decklists" / "mtga_standard.txt"
        deck = parse_deck(path)
        self.assertEqual([c.qty for c in deck.main], [4, 2, 20])

    def test_str_path(self):
        path = str(Path(__file__).resolve().parent
                   / "testdata" / "decklists" / "mtga_standard.txt")
        self.assertEqual([c.qty for c in parse_deck(path).main], [4, 2, 20])

    def test_str_text_with_newline(self):
        deck = parse_deck("4 Shock\n2 Negate\n")
        self.assertEqual(len(deck.main), 2)

    def test_missing_str_path_raises_oserror(self):
        with self.assertRaises(OSError):
            parse_deck("不存在的牌表文件.txt")

    def test_bom_file_consumed(self):
        fd, path = tempfile.mkstemp(suffix=".txt")
        try:
            with open(fd, "w", encoding="utf-8-sig", newline="\n") as fh:
                fh.write("Deck\n4 Shock\n")
            self.assertEqual([c.name for c in parse_deck(path).main], ["Shock"])
        finally:
            Path(path).unlink()


class TestAdapters(unittest.TestCase):
    SAMPLE = ("Commander\n1 Kenrith, the Returned King\n"
              "Companion\n1 Lurrus of the Dream-Den\n"
              "Deck\n4 Fabled Passage\n2 Island\n"
              "Sideboard\n1 Negate\n")

    def setUp(self):
        self.deck = parse_text(self.SAMPLE)

    def test_as_section_dict(self):
        self.assertEqual(self.deck.as_section_dict(), {
            "commander": [(1, "Kenrith, the Returned King")],
            "companion": [(1, "Lurrus of the Dream-Den")],
            "main": [(4, "Fabled Passage"), (2, "Island")],
            "sideboard": [(1, "Negate")],
        })

    def test_main_side_pairs(self):
        self.assertEqual(self.deck.main_side_pairs(),
                         ([(4, "Fabled Passage"), (2, "Island")], [(1, "Negate")]))

    def test_flat_names_main_only(self):
        self.assertEqual(self.deck.flat_names(),
                         ["Fabled Passage"] * 4 + ["Island"] * 2)

    def test_entries_qty_name_section_order(self):
        self.assertEqual(self.deck.entries(), [
            (1, "Kenrith, the Returned King", "commander"),
            (1, "Lurrus of the Dream-Den", "companion"),
            (4, "Fabled Passage", "main"),
            (2, "Island", "main"),
            (1, "Negate", "sideboard"),
        ])

    def test_commanders_with_zone(self):
        self.assertEqual(self.deck.commanders_with_zone(),
                         [(1, "Kenrith, the Returned King", "commander"),
                          (1, "Lurrus of the Dream-Den", "companion")])

    def test_deck_is_frozen(self):
        with self.assertRaises(Exception):
            self.deck.main = ()

    def test_default_deck_is_empty(self):
        deck = Deck()
        self.assertEqual(deck.as_section_dict(),
                         {"commander": [], "companion": [], "main": [], "sideboard": []})
        self.assertEqual(deck.skipped, ())


class TestDfcHelpers(unittest.TestCase):
    def test_is_dfc_name(self):
        self.assertTrue(is_dfc_name("Clearwater Pathway // Murkwater Pathway"))
        self.assertFalse(is_dfc_name("Lightning Strike"))

    def test_front_name(self):
        self.assertEqual(front_name("Clearwater Pathway // Murkwater Pathway"),
                         "Clearwater Pathway")
        self.assertEqual(front_name("Lightning Strike"), "Lightning Strike")


if __name__ == "__main__":
    unittest.main()
