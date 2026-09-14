#!/usr/bin/env python3
"""tools/deck_version.py 的回归测试。"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import deck_version


def write_deck(path, main_cards, side_cards=None):
    lines = [f"{q} {name}" for name, q in main_cards]
    if side_cards:
        lines.append("")
        lines.append("Sideboard")
        lines.extend(f"{q} {name}" for name, q in side_cards)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_valid_main():
    cards = [("Forest", 20), ("Island", 16)]
    for i in range(6):
        cards.append((f"Test Card {i}", 4))
    return cards


class DeckVersionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.deck_src = self.root / "src.txt"

    def tearDown(self):
        self._tmp.cleanup()

    def run_tool(self, extra_args, deck_cards=None, side_cards=None):
        write_deck(self.deck_src,
                   deck_cards if deck_cards is not None else make_valid_main(),
                   side_cards)
        return deck_version.main(["--root", str(self.root),
                                  "--deck-file", str(self.deck_src)] + extra_args)

    def test_first_version_creates_pair(self):
        ret = self.run_tool(["--format", "Explorer", "--colors", "MonoGreen",
                             "--theme", "LandPlant", "--notes", "首版"])
        self.assertEqual(ret, 0)
        folder = self.root / "DeckList" / "Explorer_MonoGreen_LandPlant"
        deck = folder / "LandPlantV1.txt"
        report = folder / "LandPlantV1.md"
        self.assertTrue(deck.is_file())
        self.assertTrue(report.is_file())
        self.assertEqual(deck.read_text(encoding="utf-8"),
                         self.deck_src.read_text(encoding="utf-8"))
        text = report.read_text(encoding="utf-8")
        self.assertIn(date.today().isoformat(), text)
        self.assertIn("首版", text)
        for sec in deck_version.REPORT_SECTIONS:
            self.assertIn(f"## {sec}", text)

    def test_second_run_assigns_v2_without_overwrite(self):
        self.assertEqual(self.run_tool(
            ["--format", "Explorer", "--colors", "MonoGreen", "--theme", "LandPlant"]), 0)
        folder = self.root / "DeckList" / "Explorer_MonoGreen_LandPlant"
        v1_content = (folder / "LandPlantV1.txt").read_text(encoding="utf-8")
        ret = self.run_tool(
            ["--format", "Explorer", "--colors", "MonoGreen", "--theme", "LandPlant"],
            deck_cards=make_valid_main() + [("Forest", 1)])
        self.assertEqual(ret, 0)
        self.assertTrue((folder / "LandPlantV2.txt").is_file())
        self.assertTrue((folder / "LandPlantV2.md").is_file())
        self.assertEqual((folder / "LandPlantV1.txt").read_text(encoding="utf-8"),
                         v1_content)

    def test_dir_targets_subfolder_and_reuses_stem(self):
        sub = Path("DeckList/Explorer_SlimeAgainstHumanity/Golgari")
        self.assertEqual(self.run_tool(["--dir", str(sub), "--name", "SlimeGolgari"]), 0)
        ret = self.run_tool(["--dir", str(sub)])
        self.assertEqual(ret, 0)
        folder = self.root / sub
        self.assertTrue((folder / "SlimeGolgariV1.txt").is_file())
        self.assertTrue((folder / "SlimeGolgariV2.txt").is_file())
        self.assertTrue((folder / "SlimeGolgariV2.md").is_file())

    def test_gate_main_under_60(self):
        ret = self.run_tool(
            ["--format", "Explorer", "--colors", "MonoGreen", "--theme", "LandPlant"],
            deck_cards=[("Forest", 40), ("Test Card", 4)])
        self.assertEqual(ret, 2)

    def test_gate_five_copies_non_exempt(self):
        ret = self.run_tool(
            ["--format", "Explorer", "--colors", "MonoGreen", "--theme", "LandPlant"],
            deck_cards=[("Forest", 55), ("Giant Growth", 5)])
        self.assertEqual(ret, 2)

    def test_gate_any_number_exempt(self):
        ret = self.run_tool(
            ["--format", "Explorer", "--colors", "MonoGreen", "--theme", "Slime"],
            deck_cards=[("Forest", 40), ("Slime Against Humanity", 20)])
        self.assertEqual(ret, 0)

    def test_gate_sideboard_14(self):
        ret = self.run_tool(
            ["--format", "Explorer", "--colors", "MonoGreen", "--theme", "LandPlant"],
            side_cards=[("Naturalize", 4), ("Negate", 4), ("Dispel", 4), ("Fog", 2)])
        self.assertEqual(ret, 2)

    def test_gate_set_suffix_stripped(self):
        self.deck_src.write_text("4 Opt (FDN) 60\n56 Island\n", encoding="utf-8")
        sections = deck_version.parse_deck(self.deck_src)
        self.assertEqual(sections["deck"][0], (4, "Opt"))

    def test_config_json_with_chinese(self):
        write_deck(self.deck_src, make_valid_main())
        cfg = self.root / "cfg.json"
        cfg.write_text(json.dumps({
            "format": "Explorer",
            "colors": "MonoGreen",
            "theme": "反人淤泥",
            "notes": "中文备注",
            "deck_file": str(self.deck_src),
            "root": str(self.root),
        }, ensure_ascii=False), encoding="utf-8")
        ret = deck_version.main(["--config", str(cfg)])
        self.assertEqual(ret, 0)
        folder = self.root / "DeckList" / "Explorer_MonoGreen_反人淤泥"
        self.assertTrue((folder / "反人淤泥V1.txt").is_file())
        text = (folder / "反人淤泥V1.md").read_text(encoding="utf-8")
        self.assertIn("中文备注", text)


if __name__ == "__main__":
    unittest.main()
