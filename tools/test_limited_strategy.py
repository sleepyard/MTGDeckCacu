#!/usr/bin/env python3
"""limited_strategy.py 的纯函数回归测试。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import limited_strategy as LS  # noqa: E402


class CardTable:
    def lookup(self, name):
        return self.cards.get(name)

    def __init__(self, cards):
        self.cards = {card["name"]: card for card in cards}


def card(name, colors, cmc, grade="B", count=1, cost=None, **extra):
    data = {
        "name": name,
        "colors": list(colors),
        "cmc": cmc,
        "cost": cost or ("{" + str(cmc) + "}" if cmc else ""),
        "type_line": "Creature",
        "grade": grade,
        "count": count,
    }
    data.update(extra)
    return data


class TestColorPlans(unittest.TestCase):
    def test_dual_depth_beats_shallow_mono(self):
        pool = [
            card("W Soldier", "W", 2, count=8, cost="{1}{W}"),
            card("U Drake", "U", 2, count=8, cost="{1}{U}"),
            card("Colorless Filler", [], 3, grade="C", count=8, cost="{3}"),
        ]
        plan = LS.choose_color_plan(pool, CardTable(pool))
        self.assertEqual(set(plan.colors), {"U", "W"})
        self.assertTrue(plan.depth_ok)

    def test_forced_colors_are_validated(self):
        with self.assertRaises(ValueError):
            LS.choose_color_plan([], forced_colors=["G", "G"])
        with self.assertRaises(ValueError):
            LS.choose_color_plan([], forced_colors=["X"])


class TestLimitedBuild(unittest.TestCase):
    def test_curve_factor_prefers_two_drops_when_available(self):
        pool = [
            card("Three Drop", "G", 3, grade="B", count=10, cost="{2}{G}"),
            card("Two Drop", "G", 2, grade="C", count=10, cost="{1}{G}"),
            card("Filler", [], 2, grade="C", count=5, cost="{2}"),
        ]
        deck = LS.build_limited_deck(pool, CardTable(pool), forced_colors=["G"])
        self.assertGreaterEqual(deck.curve.get(2, 0), 5)
        self.assertLessEqual(deck.curve.get(4, 0), 5)

    def test_splash_requires_explicit_strength_evidence(self):
        pool = [
            card("W Core", "W", 2, count=8, cost="{1}{W}"),
            card("U Core", "U", 2, count=8, cost="{1}{U}"),
            card("Filler", [], 3, grade="C", count=8, cost="{3}"),
            card("Black Bomb", "B", 5, grade="B+", cost="{4}{B}", iwd=0.04),
            card("Black Guess", "B", 5, grade="S", cost="{4}{B}"),
        ]
        table = CardTable(pool)
        plan = LS.choose_color_plan(pool, table, forced_colors=["W", "U"])
        splash = LS.find_splash_cards(pool, plan, table)
        self.assertEqual([item["name"] for item in splash], ["Black Bomb"])

    def test_insufficient_pool_is_reported_without_padding(self):
        pool = [card("Only Card", "G", 2, count=4, cost="{1}{G}")]
        deck = LS.build_limited_deck(pool, CardTable(pool), forced_colors=["G"])
        self.assertEqual(sum(item.count for item in deck.main), 4)
        self.assertIn("4/24", " ".join(deck.report))
        self.assertFalse(deck.valid)


if __name__ == "__main__":
    unittest.main(verbosity=1)
