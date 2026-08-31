#!/usr/bin/env python3
"""Anthem theme toolkit asset contract tests."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import constructed_strategy as CS  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
TOOLKIT_PATH = ROOT / "Toolkits" / "Anthem" / "toolkit.json"
MTGA_IMPORT_PATH = ROOT / "Toolkits" / "Anthem" / "mtga_import.txt"


EXPECTED = {
    "Rally the Ranks": ("KHM", "20"),
    "Radiant Destiny": ("RIX", "18"),
    "Icon of Ancestry": ("M20", "229"),
    "Vanquisher's Banner": ("XLN", "251"),
    "Adaptive Automaton": ("BRR", "1"),
    "Banner of Kinship": ("FDN", "127"),
    "Always Watching": ("SIR", "10"),
    "Benalish Marshal": ("DOM", "6"),
    "Heraldic Banner": ("ELD", "222"),
    "The Immortal Sun": ("RIX", "180"),
    "Weaver of Harmony": ("NEO", "213"),
    "Angel of Invention": ("KLR", "7"),
    "Felidar Retreat": ("ZNR", "16"),
    "Anointed Procession": ("AKR", "2"),
    "Trial of Solidarity": ("AKR", "42"),
    "The Great Henge": ("ELD", "161"),
}

EXPECTED_UPDATES = {
    "Patchwork Banner": ("BLB", "247"),
    "An Unexpected Party // At the Door": ("HOB", "29"),
    "Door of Destinies": ("SPG", "146"),
    "Chronicle of Victory": ("ECL", "253"),
    "Kinbinding": ("ECL", "20"),
    "Elvish Archdruid": ("FDN", "219"),
    "Dwynen, Gilt-Leaf Daen": ("FDN", "217"),
    "Glacier Godmaw": ("EOE", "188"),
    "Lumen-Class Frigate": ("EOE", "25"),
    "Comforting Counsel": ("SOS", "143"),
    "Fíli the Pathfinder": ("HOB", "14"),
    "The Arkenstone // Seek the Heart": ("HOB", "170"),
    "Suki, Courageous Rescuer": ("TLA", "37"),
    "Invasion Tactics": ("TLA", "183"),
    "Leyline of Hope": ("DSK", "18"),
}


class TestAnthemToolkit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(TOOLKIT_PATH.read_text(encoding="utf-8"))

    def test_theme_identity_and_optional_contract(self):
        self.assertEqual(self.data["toolkit_type"], "theme")
        self.assertEqual(self.data["theme"], "anthem")
        self.assertEqual(self.data["selection_policy"]["default_status"], "reference_only")
        self.assertTrue(all(entry["selection_status"] == "consider"
                            for entry in self.data["support_cards"]))
        self.assertEqual(len({entry["name"] for entry in self.data["support_cards"]}), 31)

    def test_screened_cards_have_exact_printings_and_groups(self):
        cards = {entry["name"]: entry for entry in self.data["support_cards"]}
        self.assertEqual(set(cards), set(EXPECTED) | set(EXPECTED_UPDATES))
        for name, printing in EXPECTED.items():
            self.assertEqual((cards[name]["set"], cards[name]["collector_number"]), printing)
            self.assertTrue(cards[name]["component_group"])
            self.assertTrue(cards[name]["note"])
        for name, printing in EXPECTED_UPDATES.items():
            self.assertEqual((cards[name]["set"], cards[name]["collector_number"]), printing)
            self.assertTrue(cards[name]["component_group"])
            self.assertTrue(cards[name]["note"])

    def test_validation_snapshot_matches_inventory(self):
        validation = self.data["validation"]
        self.assertEqual(validation["exact_printings_checked"], len(EXPECTED) + len(EXPECTED_UPDATES))
        self.assertEqual(validation["formats"]["pioneer"], "legal")
        self.assertEqual(validation["platforms"], ["arena"])
        self.assertTrue(validation["recheck_on_update"])

    def test_mtga_import_matches_inventory_as_one_of_list(self):
        imported = CS.parse_seed_file(str(MTGA_IMPORT_PATH))
        expected_names = {entry["name"] for entry in self.data["support_cards"]}
        self.assertEqual({name for _, name in imported.main}, expected_names)
        self.assertTrue(all(quantity == 1 for quantity, _ in imported.main))
        self.assertFalse(imported.sideboard)


if __name__ == "__main__":
    unittest.main(verbosity=1)
