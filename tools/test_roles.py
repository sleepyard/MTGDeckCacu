#!/usr/bin/env python3
"""roles.py 的确定性标签回归测试，无网络和文件 I/O。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from roles import (  # noqa: E402
    RoleTag,
    classify_card,
    has_mechanic,
    has_root,
    merge_ai_tags,
    primary_role,
    score_tags,
)


class TestClassifyCard(unittest.TestCase):
    def test_removal_and_board_wipe(self):
        tags = classify_card({
            "type_line": "Sorcery",
            "oracle_text": "Destroy all creatures.",
        })
        self.assertTrue(has_root(tags, "removal"))
        self.assertTrue(has_mechanic(tags, "board_wipe"))

    def test_graveyard_exile_is_hate_not_removal(self):
        tags = classify_card({
            "type_line": "Instant",
            "oracle_text": "Exile target card from a graveyard.",
        })
        self.assertFalse(has_root(tags, "removal"))
        self.assertTrue(has_mechanic(tags, "graveyard_hate"))

    def test_creature_roles(self):
        tags = classify_card({
            "type_line": "Creature — Elf",
            "keywords": ["Flying", "Haste"],
            "cmc": 2,
            "power": "3",
            "oracle_text": "When this creature enters, draw a card.",
        })
        self.assertTrue(has_root(tags, "threat"))
        self.assertTrue(has_root(tags, "aggro"))
        self.assertTrue(has_root(tags, "card_advantage"))
        self.assertEqual(primary_role(tags), "card_advantage")

    def test_mana_dork_and_tutor(self):
        tags = classify_card({
            "type_line": "Creature — Elf Druid",
            "cmc": 2,
            "oracle_text": "{T}: Add {G}. Search your library for a basic land card.",
        })
        self.assertTrue(has_mechanic(tags, "mana_dork"))
        self.assertTrue(has_mechanic(tags, "ramp"))
        self.assertTrue(has_mechanic(tags, "tutor"))

    def test_bounce_is_cross_root_interaction(self):
        tags = classify_card({
            "type_line": "Instant",
            "oracle_text": "Return target creature to its owner’s hand.",
        })
        self.assertTrue(has_root(tags, "removal"))
        self.assertTrue(has_root(tags, "tempo"))
        self.assertTrue(has_root(tags, "control"))

    def test_indestructible_text_is_protection(self):
        tags = classify_card({
            "type_line": "Creature - Dog",
            "oracle_text": "Sacrifice this creature: Another target creature gains indestructible until end of turn.",
        })
        self.assertTrue(has_root(tags, "protection"))


class TestTagMergingAndScoring(unittest.TestCase):
    def test_ai_only_supplements_uncovered_root(self):
        rules = [RoleTag("removal", "destroy")]
        merged = merge_ai_tags(rules, [
            {"root": "removal", "mechanic": "exile", "source": "ai"},
            {"root": "card_advantage", "mechanic": "draw", "source": "ai"},
            {"root": "made_up", "mechanic": "anything", "source": "ai"},
        ])
        self.assertEqual(len(merged), 2)
        self.assertTrue(has_root(merged, "card_advantage"))
        self.assertFalse(has_mechanic(merged, "exile"))

    def test_same_root_uses_highest_mechanic_only(self):
        tags = [RoleTag("removal", "destroy"), RoleTag("removal", "board_wipe")]
        self.assertAlmostEqual(score_tags(tags), 1.9)

    def test_ai_tag_is_halved(self):
        self.assertAlmostEqual(
            score_tags([RoleTag("card_advantage", "draw", "ai")]), 0.6
        )


if __name__ == "__main__":
    unittest.main(verbosity=1)
