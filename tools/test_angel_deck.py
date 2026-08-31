#!/usr/bin/env python3
"""Selesnya Angels example deck structure tests."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import constructed_strategy as CS  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
DECK_PATH = ROOT / "DeckList" / "Explorer_Angel_Tribal" / "angel_deck_v2.txt"


class TestAngelDeck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.deck = CS.parse_seed_file(str(DECK_PATH))

    def test_import_shape(self):
        self.assertEqual(sum(quantity for quantity, _ in self.deck.main), 60)
        self.assertEqual(sum(quantity for quantity, _ in self.deck.sideboard), 15)
        self.assertFalse(self.deck.commander)
        self.assertFalse(self.deck.companion)

    def test_core_engine_and_tribal_mana_sources_are_present(self):
        main = {name: quantity for quantity, name in self.deck.main}
        for name in ("Giada, Font of Hope", "Bishop of Wings",
                     "Youthful Valkyrie", "Righteous Valkyrie",
                     "Resplendent Angel", "Lyra Dawnbringer",
                     "Archangel of Wrath", "Collected Company"):
            self.assertIn(name, main)
        self.assertEqual(main["Archangel of Wrath"], 4)
        self.assertEqual(main["Collected Company"], 4)
        self.assertEqual(main["Cavern of Souls"], 4)
        self.assertEqual(main["Secluded Courtyard"], 4)
        self.assertNotIn("Exemplar of Light", main)
        self.assertNotIn("Archangel of Thune", main)

    def test_sideboard_is_explicit_and_singleton_safe(self):
        sideboard = {name: quantity for quantity, name in self.deck.sideboard}
        self.assertEqual(sideboard["Portable Hole"], 3)
        self.assertEqual(sideboard["Rest in Peace"], 3)
        self.assertEqual(sideboard["Damping Sphere"], 2)
        self.assertEqual(sideboard["Settle the Wreckage"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
