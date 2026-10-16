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
    def test_sideboard_seed_is_preserved_and_reserved_across_sections(self):
        pool = normal_pool() + [candidate("Reserved", module="M1")]
        seed = CS.SeedSet(main=((4, "Seed Payoff"),), sideboard=((2, "Reserved"),))
        for bo3 in (False, True):
            deck = CS.build_constructed_deck(pool, seed, "pioneer", bo3=bo3)
            self.assertTrue(deck.valid, deck.violations)
            self.assertEqual(sum(e.count for e in deck.sideboard if e.card["name"] == "Reserved"), 2)
            self.assertLessEqual(sum(e.count for e in deck.main + deck.sideboard if e.card["name"] == "Reserved"), 4)
            if not bo3:
                self.assertEqual(sum(e.count for e in deck.sideboard), 2)

    def test_invalid_sideboard_seed_never_silently_disappears(self):
        pool = normal_pool()
        illegal = candidate("Illegal Side", module="M6")
        illegal["legalities"]["pioneer"] = "banned"
        pool.append(illegal)
        with self.assertRaises(ValueError):
            CS.build_constructed_deck(pool, CS.SeedSet(main=((4, "Seed Payoff"),),
                                      sideboard=((1, "Illegal Side"),)), "pioneer", bo3=True)
        with self.assertRaises(ValueError):
            CS.build_constructed_deck(pool, CS.SeedSet(main=((4, "Seed Payoff"),),
                                      sideboard=((1, "Seed Payoff"),)), "pioneer", bo3=True)

    def test_duplicate_seed_rows_are_checked_as_total(self):
        deck = CS.build_constructed_deck(normal_pool(), CS.SeedSet(main=((4, "Seed Payoff"),)), "pioneer")
        seed = CS.SeedSet(main=((3, "Seed Payoff"), (2, "Seed Payoff")))
        self.assertTrue(any("需要 5" in v for v in CS.validate_constructed(deck, seed)))

    def test_companion_consumes_sideboard_capacity(self):
        pool = normal_pool() + [candidate("Companion", companion=True)]
        seed = CS.SeedSet(main=((4, "Seed Payoff"),), companion=((1, "Companion"),))
        deck = CS.build_constructed_deck(pool, seed, "pioneer", bo3=True)
        self.assertTrue(deck.valid, deck.violations)
        self.assertLessEqual(sum(e.count for e in deck.sideboard + deck.companion), 15)

    def test_sideboard_missing_from_output_is_a_gate_failure(self):
        deck = CS.build_constructed_deck(normal_pool(), CS.SeedSet(main=((4, "Seed Payoff"),)), "pioneer")
        seed = CS.SeedSet(main=((4, "Seed Payoff"),), sideboard=((1, "Side Hate"),))
        self.assertTrue(any("sideboard 种子牌" in v for v in CS.validate_constructed(deck, seed)))

    def test_synergy_breaks_same_cost_tie_and_names_supporting_seed(self):
        anchor = candidate("Anchor", module="M1")
        anchor["type_line"] = "Creature — Elf"
        payoff = candidate("A Payoff", module="M1")
        payoff["oracle_text"] = "Other Elves you control get +1/+1."
        filler = candidate("Z Unrelated", module="M1")
        selected, _, _ = CS._select_nonlands([payoff, filler],
            [CS.ConstructedEntry(anchor, 4, "M1", "seed")], 8, False, {"G"}, "mid")
        self.assertEqual(selected[-1].card["name"], "A Payoff")
        self.assertIn("Anchor", selected[-1].reason)

    def test_alchemy_is_rejected(self):
        with self.assertRaises(ValueError):
            CS.build_constructed_deck(normal_pool(), CS.SeedSet(main=((1, "Seed Payoff"),)), "alchemy")

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

    def test_nonbasic_lands_respect_land_target(self):
        pool = normal_pool()
        nonbasic = candidate("Temple", land=True)
        nonbasic["type_line"] = "Land"
        pool.append(nonbasic)
        deck = CS.build_constructed_deck(
            pool, CS.SeedSet(main=((4, "Seed Payoff"),)), "pioneer")
        self.assertEqual(sum(item.count for item in deck.main), 60)
        lands = [item for item in deck.main
                 if "land" in item.card.get("type_line", "").lower()]
        self.assertEqual(sum(item.count for item in lands), 24)

    def test_flexible_lands_preserve_basic_color_mix(self):
        flexible = candidate("Mana Confluence", land=True)
        flexible["type_line"] = "Land"
        flexible["colors"] = []
        flexible["color_identity"] = []
        flexible["oracle_text"] = "{T}: Add one mana of any color."
        w_spell = CS.ConstructedEntry({"name": "W Spell", "mana_cost": "{W}",
                                       "type_line": "Creature"}, 1, "M1", "test")
        u_spell = CS.ConstructedEntry({"name": "U Spell", "mana_cost": "{U}",
                                       "type_line": "Creature"}, 1, "M1", "test")
        lands = CS._land_entries([flexible], [], [w_spell, u_spell], 8, False,
                                 {"W", "U"})
        by_name = {item.card["name"]: item.count for item in lands}
        self.assertEqual(by_name.get("Mana Confluence"), 4)
        self.assertGreater(by_name.get("Plains", 0), 0)
        self.assertGreater(by_name.get("Island", 0), 0)

    def test_core_roles_beat_hate_module(self):
        pack_leader = candidate("Pack Leader")
        pack_leader["oracle_text"] = "Other Dogs you control get +1/+1. Whenever this attacks, prevent all combat damage."
        self.assertEqual(CS._module(pack_leader), "M8")

    def test_basic_color_mix_weights_spell_quantities(self):
        white = CS.ConstructedEntry({"name": "White Spell", "mana_cost": "{W}"}, 4, "M1", "test")
        blue = CS.ConstructedEntry({"name": "Blue Spell", "mana_cost": "{U}"}, 1, "M1", "test")
        lands = CS._land_entries([], [], [white, blue], 10, False, {"W", "U"})
        counts = {item.card["name"]: item.count for item in lands}
        # mana_base reserves one source per required color before weighting.
        self.assertEqual(counts, {"Plains": 7, "Island": 3})

    def test_actual_produced_mana_counts_colorless_identity_dual(self):
        dual = candidate("Known Dual", colors=(), land=True)
        dual["type_line"] = "Land"
        dual["produced_mana"] = ["W", "U"]
        dual["oracle_text"] = "{T}: Add {W} or {U}."
        spells = [CS.ConstructedEntry({"name": "White", "mana_cost": "{W}"}, 4, "M1", "test"),
                  CS.ConstructedEntry({"name": "Blue", "mana_cost": "{U}"}, 4, "M1", "test")]
        lands = CS._land_entries([dual], [], spells, 10, False, {"W", "U"})
        self.assertEqual(sum(item.count for item in lands), 10)
        self.assertEqual({item.card["name"]: item.count for item in lands},
                         {"Known Dual": 4, "Island": 3, "Plains": 3})

    def test_tiny_remaining_land_budget_does_not_overfill(self):
        spells = [CS.ConstructedEntry({"name": color, "mana_cost": "{" + color + "}"},
                                     1, "M1", "test") for color in ("W", "U")]
        lands = CS._land_entries([], [], spells, 1, False, {"W", "U"})
        self.assertEqual(sum(item.count for item in lands), 1)

    def test_transform_back_land_is_not_main_deck_land(self):
        transform = candidate("Journey", land=True)
        transform["type_line"] = "Legendary Enchantment // Legendary Land"
        transform["layout"] = "transform"
        modal = candidate("Pathway", land=True)
        modal["type_line"] = "Land // Land"
        modal["layout"] = "modal_dfc"
        self.assertFalse(CS._is_land(transform))
        self.assertTrue(CS._is_land(modal))


if __name__ == "__main__":
    unittest.main(verbosity=1)
