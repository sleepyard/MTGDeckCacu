#!/usr/bin/env python3
"""draft_advisor.py 的纯函数与严格 LLM 合约测试。"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import draft_advisor as DA  # noqa: E402


class Table:
    def __init__(self, grades):
        self.grades = grades

    def lookup(self, name):
        return {"grade": self.grades[name]}


def card(name, grade="B", **extra):
    value = {
        "name": name, "grade": grade, "colors": ["G"], "cmc": 2,
        "rarity": "common", "type_line": "Creature", "oracle_text": "",
    }
    value.update(extra)
    return value


class TestParsing(unittest.TestCase):
    def test_requires_complete_array(self):
        with self.assertRaises(ValueError):
            DA.parse_llm_scores('[{"name":"A","raw_power":0.5,"synergy":0.5,"reason":"ok"}]',
                                ["A", "B"])

    def test_rejects_out_of_range_and_missing_reason(self):
        text = json.dumps([
            {"name": "A", "raw_power": 1.1, "synergy": 0.5, "reason": "bad"},
            {"name": "B", "raw_power": 0.5, "synergy": 0.5, "reason": "ok"},
        ])
        with self.assertRaises(ValueError):
            DA.parse_llm_scores(text, ["A", "B"])


class TestRecommendation(unittest.TestCase):
    def test_machine_ranking_uses_grade_anchor(self):
        pack = [card("A", "S"), card("B", "C")]
        result = DA.recommend_pick(pack, [], table=Table({"A": "S", "B": "C"}))
        self.assertEqual(result.status, "disabled")
        self.assertEqual(result.recommendations[0].card["name"], "A")

    def test_valid_llm_response_overrides_two_axes_only(self):
        pack = [card("A"), card("B")]
        table = Table({"A": "B", "B": "B"})

        def request(_prompt):
            return json.dumps([
                {"name": "A", "raw_power": 0.1, "synergy": 0.1, "reason": "协同弱"},
                {"name": "B", "raw_power": 0.9, "synergy": 0.9, "reason": "协同强"},
            ])

        result = DA.recommend_pick(pack, [], table=table, llm_request=request)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.recommendations[0].card["name"], "B")
        self.assertIsNotNone(result.prompt)

    def test_invalid_llm_response_is_explicit_offline(self):
        pack = [card("A", "S"), card("B", "C")]
        result = DA.recommend_pick(pack, [], table=Table({"A": "S", "B": "C"}),
                                   llm_request=lambda _prompt: "not json")
        self.assertEqual(result.status, "offline")
        self.assertIn("LLM 离线", result.recommendations[0].reason)
        self.assertIsNotNone(result.error)


if __name__ == "__main__":
    unittest.main(verbosity=1)
