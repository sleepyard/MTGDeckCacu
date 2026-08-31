#!/usr/bin/env python3
"""Tribal toolkit asset and explicit-seed contract tests."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import constructed_strategy as CS  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
TOOLKIT_PATH = ROOT / "Toolkits" / "Tribal" / "toolkit.json"
SEED_PATH = ROOT / "Toolkits" / "Examples" / "Dog" / "selected_seed.txt"
MTGA_IMPORT_PATH = ROOT / "Toolkits" / "Tribal" / "mtga_import.txt"


EXPECTED_SUPPORT = {
    "Cavern of Souls": ("灵魂洞窟", "LCI", "269"),
    "Haunting Voyage": ("乱心旅途", "KHM", "98"),
    "Rally the Ranks": ("集结军伍", "KHM", "20"),
    "Radiant Destiny": ("辉煌命运", "RIX", "18"),
    "Arcane Adaptation": ("玄秘适境", "XLN", "46"),
    "Reflections of Littjara": ("利雅拉映影", "KHM", "73"),
    "Realmwalker": ("境域行者", "KHM", "188"),
    "Kolvori, God of Kinship // The Ringhart Crest": ("亲缘神蔻沃莉", "KHM", "181"),
    "Metallic Mimic": ("金属拟态械", "KLR", "251"),
    "Icon of Ancestry": ("先祖绘像", "M20", "229"),
    "Roaming Throne": ("游荡王座", "LCI", "258"),
    "Vanquisher's Banner": ("得胜者战旗", "XLN", "251"),
    "Unclaimed Territory": ("无主领地", "XLN", "258"),
    "Secluded Courtyard": ("幽僻庭院", "NEO", "275"),
    "Bloodline Pretender": ("血脉顶替客", "KHM", "235"),
    "Pillar of Origins": ("源始雕柱", "XLN", "241"),
    "Three Tree City": ("三树城", "BLB", "260"),
}

EXPECTED_UPDATES = {
    "Barkform Harvester": ("BLB", "243"),
    "Patchwork Banner": ("BLB", "247"),
    "Three Tree Mascot": ("BLB", "251"),
    "Soulstone Sanctuary": ("FDN", "133"),
    "Bloodline Bidding": ("ECL", "91"),
    "Changeling Wayfinder": ("ECL", "1"),
    "Chronicle of Victory": ("ECL", "253"),
    "Crib Swap": ("ECL", "11"),
    "Gathering Stone": ("ECL", "257"),
    "Selfless Safewright": ("ECL", "193"),
    "Stalactite Dagger": ("ECL", "261"),
    "Door of Destinies": ("SPG", "146"),
    "Firdoch Core": ("ECL", "255"),
    "Graveshifter": ("ECL", "104"),
    "Unbury": ("ECL", "123"),
    "Winnowing": ("ECL", "43"),
    "Secret Tunnel": ("TLA", "278"),
    "White Lotus Tile": ("TLA", "262"),
    "Orcrist, Goblin-cleaver": ("HOB", "177"),
    "An Unexpected Party // At the Door": ("HOB", "29"),
}


class TestGenericTribalToolkit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(TOOLKIT_PATH.read_text(encoding="utf-8"))

    def test_toolkit_is_generic_not_tribe_specific(self):
        self.assertEqual(self.data["toolkit_id"], "tribal-generic")
        self.assertEqual(self.data["toolkit_type"], "tribal")
        self.assertEqual(self.data["theme"], "tribal")
        self.assertNotIn("tribe", self.data)
        self.assertNotIn("tribe_anchors", self.data)

    def test_supplied_support_cards_are_present_with_exact_printings(self):
        support = {entry["name"]: entry for entry in self.data["support_cards"]}
        self.assertTrue(set(EXPECTED_SUPPORT).issubset(support))
        for name, (name_zh, set_code, collector_number) in EXPECTED_SUPPORT.items():
            self.assertEqual(support[name]["name_zh"], name_zh)
            self.assertEqual(support[name]["set"], set_code)
            self.assertEqual(support[name]["collector_number"], collector_number)

    def test_incremental_entries_are_present_with_exact_printings(self):
        support = {entry["name"]: entry for entry in self.data["support_cards"]}
        self.assertEqual(set(support), set(EXPECTED_SUPPORT) | set(EXPECTED_UPDATES))
        for name, printing in EXPECTED_UPDATES.items():
            self.assertEqual((support[name]["set"], support[name]["collector_number"]), printing)

    def test_inventory_is_optional_by_default(self):
        entries = self.data["support_cards"]
        self.assertEqual(self.data["selection_policy"]["default_status"], "reference_only")
        self.assertTrue(all(entry["selection_status"] == "consider" for entry in entries))
        self.assertEqual(len({entry["name"] for entry in entries}), len(entries))

    def test_validation_snapshot_covers_every_entry(self):
        validation = self.data["validation"]
        self.assertEqual(validation["exact_printings_checked"], 37)
        self.assertEqual(validation["formats"]["pioneer"], "legal")
        self.assertEqual(validation["platforms"], ["arena"])
        self.assertTrue(validation["recheck_on_update"])

    def test_explicit_seed_is_not_the_inventory(self):
        seed = CS.parse_seed_file(str(SEED_PATH))
        self.assertEqual(sum(quantity for quantity, _ in seed.main), 40)
        first_lines = SEED_PATH.read_text(encoding="utf-8").splitlines()[:3]
        self.assertTrue(first_lines[0].startswith("# Explicit seed snapshot for a Dog"))
        self.assertIn("not the toolkit inventory", first_lines[1])

    def test_mtga_import_matches_inventory_as_one_of_list(self):
        imported = CS.parse_seed_file(str(MTGA_IMPORT_PATH))
        expected_names = {entry["name"] for entry in self.data["support_cards"]}
        self.assertEqual({name for _, name in imported.main}, expected_names)
        self.assertTrue(all(quantity == 1 for quantity, _ in imported.main))
        self.assertFalse(imported.sideboard)


if __name__ == "__main__":
    unittest.main(verbosity=1)
