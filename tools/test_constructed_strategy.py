#!/usr/bin/env python3
"""constructed_strategy.py 的结构门禁回归测试。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import constructed_strategy as CS  # noqa: E402


def candidate(name, colors=("G",), module=None, land=False, commander=False, companion=False):
    value = {
        "name": name,
        "colors": list(colors),
        "color_identity": list(colors),
        "cmc": 3,
        "mana_cost": "{2}{G}" if not land else "",
        "type_line": "Basic Land — Forest" if land else "Creature",
        "oracle_text": "",
        "legalities": {"pioneer": "legal", "brawl": "legal"},
        "games": ["arena", "paper", "mtgo"],
    }
    if module:
        value["module"] = module
    if commander:
        value["is_commander"] = True
    if companion:
        value["is_companion"] = True
    return value


def normal_pool():
    cards = [candidate("Seed Payoff", module="M1"),
             candidate("Forest", land=True)]
    for module in ("M1", "M2", "M3", "M5", "M8"):
        for index in range(1, 5):
            cards.append(candidate(f"{module} Card {index}", module=module))
    cards.extend(candidate(f"Filler {index}", module="M1") for index in range(1, 8))
    cards.append(candidate("Side Hate", module="M6"))
    return cards


class TestSeedParsing(unittest.TestCase):
    def test_sections_and_bare_names(self):
        seed = CS.parse_seed_lines([
            "Commander", "1 General", "Deck", "2 Seed Payoff",
            "Sideboard", "Hate Card", "# comment",
        ])
        self.assertEqual(seed.commander, ((1, "General"),))
        self.assertEqual(seed.main, ((2, "Seed Payoff"),))
        self.assertEqual(seed.sideboard, ((1, "Hate Card"),))


class TestConstructedBuild(unittest.TestCase):
    def test_normal_build_preserves_seed_and_shape(self):
        pool = normal_pool()
        seed = CS.SeedSet(main=((4, "Seed Payoff"),))
        deck = CS.build_constructed_deck(pool, seed, "pioneer", bo3=True)
        self.assertTrue(deck.valid, deck.violations)
        self.assertEqual(sum(item.count for item in deck.main), 60)
        self.assertLessEqual(sum(item.count for item in deck.sideboard), 15)
        self.assertEqual(sum(item.count for item in deck.main
                             if item.card["name"] == "Seed Payoff"), 4)
        self.assertTrue(all(deck.modules.get(module, 0) > 0
                            for module in CS.REQUIRED_MODULES))
        self.assertNotIn("Side Hate", {item.card["name"] for item in deck.main})

    def test_seed_outside_candidates_is_error(self):
        with self.assertRaises(ValueError):
            CS.build_constructed_deck(normal_pool(),
                                      CS.SeedSet(main=((1, "Missing"),)), "pioneer")

    def test_brawl_build_is_singleton_and_has_commander(self):
        commander = candidate("General", commander=True)
        pool = [commander, candidate("Seed Card", module="M1")]
        modules = ("M1", "M2", "M3", "M5", "M8")
        pool.extend(candidate(f"Unique {index}", module=modules[index % len(modules)])
                    for index in range(1, 71))
        seed = CS.SeedSet(main=((1, "Seed Card"),), commander=((1, "General"),))
        deck = CS.build_constructed_deck(pool, seed, "brawl")
        self.assertTrue(deck.valid, deck.violations)
        self.assertEqual(sum(item.count for item in deck.main), 99)
        self.assertEqual(sum(item.count for item in deck.commander), 1)
        self.assertTrue(all(item.count == 1 for item in deck.main
                            if "Basic" not in item.card.get("type_line", "")))

    def test_copy_limit_counts_main_and_sideboard_together(self):
        duplicate = candidate("Duplicate")
        deck = CS.ConstructedDeck(
            "pioneer",
            [CS.ConstructedEntry(duplicate, 3, "M1", "main")],
            [CS.ConstructedEntry(duplicate, 2, "M6", "side")],
            [], {}, ("G",), True,
        )
        violations = CS.validate_constructed(deck, CS.SeedSet(main=()))
        self.assertTrue(any("Duplicate 总数 5" in item for item in violations))


    def test_normal_build_preserves_companion_outside_main(self):
        pool = normal_pool()
        companion = candidate("Lutri", colors=("G",), companion=True)
        pool.append(companion)
        seed = CS.SeedSet(main=((4, "Seed Payoff"),), companion=((1, "Lutri"),))
        deck = CS.build_constructed_deck(pool, seed, "pioneer", bo3=True)
        self.assertTrue(deck.valid, deck.violations)
        self.assertEqual(sum(item.count for item in deck.companion), 1)
        self.assertEqual(deck.companion[0].card["name"], "Lutri")
        self.assertNotIn("Lutri", {item.card["name"] for item in deck.main})
        self.assertNotIn("Lutri", {item.card["name"] for item in deck.sideboard})
        self.assertEqual(deck.modules["M7"], 1)

    def test_companion_limit_is_separate_from_sideboard(self):
        companion = candidate("Lutri", companion=True)
        deck = CS.ConstructedDeck(
            "pioneer", [], [], [], {}, ("G",), True,
            companion=[CS.ConstructedEntry(companion, 2, "M7", "test")],
        )
        violations = CS.validate_constructed(deck, CS.SeedSet(main=()))
        self.assertTrue(any("Companion 2 > 1" in item for item in violations))


if __name__ == "__main__":
    unittest.main(verbosity=1)
