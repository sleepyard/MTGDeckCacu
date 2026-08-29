#!/usr/bin/env python3
"""deck_pooper.py 输入解析与渲染测试，不访问网络。"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck_pooper as DP  # noqa: E402
import constructed_strategy as CS  # noqa: E402
import limited_strategy as LS  # noqa: E402


class TestPoolParsing(unittest.TestCase):
    def test_parse_pool_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pool.txt"
            path.write_text("Deck\n2 Llanowar Elves\n\nSideboard\n1 Naturalize\n", encoding="utf-8")
            self.assertEqual(DP.parse_pool_text(str(path)), [
                (2, "Llanowar Elves"), (1, "Naturalize")
            ])

    def test_parse_sample_requires_complete(self):
        row = {"payload": {"Payload": json.dumps({
            "DraftStatus": "PickNext", "PickedCards": ["1"]
        })}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.jsonl"
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                DP.parse_pool_sample(str(path))

    def test_parse_sample_uses_final_picked_cards(self):
        rows = [
            {"payload": {"Payload": json.dumps({
                "DraftStatus": "PickNext", "PickedCards": ["old"]
            })}},
            {"payload": {"Payload": json.dumps({
                "DraftStatus": "Complete", "PickedCards": ["1", "1", "2"]
            })}},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            self.assertEqual(DP.parse_pool_sample(str(path)), [(2, "1"), (1, "2")])

    def test_load_candidates_requires_json_array(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidates.json"
            path.write_text(json.dumps({"data": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                DP.load_candidates(str(path))


class TestRendering(unittest.TestCase):
    def test_render_includes_reasons_and_report(self):
        base = {"name": "Forest", "colors": ["G"], "cmc": 0,
                "type_line": "Basic Land — Forest", "count": 1}
        selected = LS.SelectedCard(base, 17, 0.5, "基础地填充")
        deck = LS.LimitedDeck(
            colors=("G",), strategy="mid", splash=[], main=[selected],
            lands={"G": 17}, sideboard=[], curve={1: 0}, average_cmc=0,
            depth_ok=True, depth_note="", land_check=(0.95, 0.8, True),
            report=["颜色: G"],
        )
        self.assertIn("17 Forest", DP.render_deck(deck))
        self.assertNotIn("# 选牌理由", DP.render_deck(deck))
        self.assertIn("基础地填充", DP.render_report(deck, explain=True))

    def test_render_constructed_has_commander_section(self):
        commander = CS.ConstructedEntry({"name": "General", "type_line": "Creature"},
                                         1, "M9", "种子指挥官")
        main = CS.ConstructedEntry({"name": "Forest", "type_line": "Basic Land — Forest"},
                                   24, "M4", "补充基础地来源")
        deck = CS.ConstructedDeck("brawl", [main], [], [commander], {}, ("G",), True)
        text = DP.render_constructed_deck(deck)
        self.assertTrue(text.startswith("Commander\n1 General\n\nDeck\n"))
        self.assertNotIn("Sideboard", text)


class TestCommand(unittest.TestCase):
    def test_missing_ratings_is_explicit_error(self):
        args = DP.build_parser().parse_args([
            "limited", "--pool", "pool.txt", "--set", "HOB"
        ])
        with mock.patch.object(DP.mtga_draft_tool, "load_card_table", return_value=None):
            self.assertEqual(DP.cmd_limited(args), 2)

    def test_draft_command_forwards_to_mtga_pipeline(self):
        args = DP.build_parser().parse_args([
            "draft", "--watch", "--set", "HOB", "--llm", "--port", "8643",
            "--max-polls", "1"
        ])
        with mock.patch.object(DP.mtga_auto_tool, "main", return_value=0) as main:
            self.assertEqual(DP.cmd_draft(args), 0)
        main.assert_called_once_with([
            "draft", "--watch", "--set", "HOB", "--port", "8643", "--llm",
            "--max-polls", "1"
        ])

    def test_constructed_gate_failure_does_not_write_deck(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = Path(tmp) / "candidates.json"
            seed = Path(tmp) / "seed.txt"
            output = Path(tmp) / "deck.txt"
            candidates.write_text(json.dumps([{
                "name": "Seed", "colors": ["G"], "color_identity": ["G"],
                "type_line": "Creature", "legalities": {"pioneer": "legal"},
                "games": ["arena"], "module": "M1",
            }]), encoding="utf-8")
            seed.write_text("1 Seed\n", encoding="utf-8")
            args = DP.build_parser().parse_args([
                "constructed", "--format", "pioneer", "--seed", str(seed),
                "--candidates", str(candidates), "--out", str(output)
            ])
            self.assertEqual(DP.cmd_constructed(args), 4)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main(verbosity=1)
