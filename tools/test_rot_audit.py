#!/usr/bin/env python3
"""rot_audit.py 的回归测试：mock 掉 urllib 边界，不接触真实网络。"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rot_audit  # noqa: E402

SETS_PAYLOAD = {
    "data": [
        {"code": "fdn", "set_type": "expansion", "released_at": "2024-11-15", "digital": False},
        {"code": "woe", "set_type": "expansion", "released_at": "2023-09-08", "digital": False},
        {"code": "otj", "set_type": "expansion", "released_at": "2024-04-19", "digital": False},
        {"code": "y22", "set_type": "alchemy", "released_at": "2021-12-09", "digital": True},
        {"code": "pwoe", "set_type": "promo", "released_at": "2025-01-01", "digital": False},
    ],
    "next_page": None,
}


def make_printings(sets):
    return {
        "data": [
            {"set": code, "collector_number": str(i + 1), "released_at": "2024-01-01",
             "name": "Test Card"}
            for i, code in enumerate(sets)
        ],
        "next_page": None,
    }


class RotAuditTestBase(unittest.TestCase):
    def setUp(self):
        rot_audit._sets = None
        self.calls = []

    def fake_get(self, printings_sets):
        def _get(url, tries=4):
            self.calls.append(url)
            if url.startswith("https://api.scryfall.com/sets"):
                return SETS_PAYLOAD
            if "cards/search" in url:
                return make_printings(printings_sets)
            return None
        return _get


class TestSetMeta(RotAuditTestBase):
    def test_set_meta_cached(self):
        with mock.patch.object(rot_audit, "get", self.fake_get(["fdn"])):
            first = rot_audit.set_meta()
            second = rot_audit.set_meta()
        self.assertIs(first, second)
        self.assertEqual(1, sum(1 for c in self.calls if "/sets" in c))
        self.assertEqual(("expansion", "2024-11-15", False), first["fdn"])


class TestAudit(RotAuditTestBase):
    def audit_with(self, printings_sets, name="Test Card"):
        with mock.patch.object(rot_audit, "get", self.fake_get(printings_sets)):
            return rot_audit.audit(name)

    def test_survivor_and_rotating_printings(self):
        a = self.audit_with(["woe", "fdn"])
        self.assertTrue(a["alive"])
        self.assertEqual(["fdn"], a["survive_sets"])
        self.assertEqual(["woe"], a["rot_sets"])

    def test_only_rotating_printings_dies(self):
        a = self.audit_with(["woe", "otj"])
        self.assertFalse(a["alive"])
        self.assertEqual([], a["survive_sets"])
        self.assertEqual(["otj", "woe"], a["rot_sets"])

    def test_promo_printing_cannot_save(self):
        # 促销印（非 core/expansion）即使日期新也不算命
        a = self.audit_with(["woe", "pwoe"])
        self.assertFalse(a["alive"])

    def test_digital_set_cannot_save(self):
        a = self.audit_with(["y22"])
        self.assertFalse(a["alive"])

    def test_pre_cutoff_expansion_does_not_save(self):
        # 轮替名单之外的旧 expansion（released_at < CUTOFF）同样不保命；
        # 这里用不在 ROTATING 名单里的代码模拟「2024-11-15 之前的扩展」
        payload = dict(SETS_PAYLOAD)
        payload["data"] = SETS_PAYLOAD["data"] + [
            {"code": "xyz", "set_type": "expansion", "released_at": "2024-01-01", "digital": False},
        ]
        def _get(url, tries=4):
            if url.startswith("https://api.scryfall.com/sets"):
                return payload
            return make_printings(["xyz"])
        with mock.patch.object(rot_audit, "get", _get):
            a = rot_audit.audit("Test Card")
        self.assertFalse(a["alive"])


class TestParseDeck(unittest.TestCase):
    def test_main_and_sideboard(self):
        content = (
            "# comment\n"
            "// another comment\n"
            "4 Lightning Strike\n"
            "20 Mountain\n"
            "\n"
            "Sideboard\n"
            "3 Roast\n"
            "not a card line\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(content)
            path = f.name
        try:
            main, side = rot_audit.parse_deck(path)
        finally:
            os.unlink(path)
        self.assertEqual([(4, "Lightning Strike"), (20, "Mountain")], main)
        self.assertEqual([(3, "Roast")], side)


if __name__ == "__main__":
    unittest.main()
