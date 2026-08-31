#!/usr/bin/env python3
"""mtga_draft_tool.py 离线回归测试（合成数据驱动，无网络）。"""

import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mtga_draft_tool as MDT  # noqa: E402


def _card(name, mtga_id, gih=None, ata=None, oh=None):
    return {"name": name, "mtga_id": mtga_id, "color": "G", "rarity": "common",
            "ever_drawn_win_rate": gih, "avg_pick": ata,
            "opening_hand_win_rate": oh, "avg_seen": None, "win_rate": None}


SAMPLE = [
    _card("Good Card", 1001, gih=0.58, ata=3.2, oh=0.57),
    _card("Bad Card", 1002, gih=0.51, ata=8.9),
    _card("No Data Card", 1003),
    _card("Double-Faced Card // Back", 1004, gih=0.55, ata=5.0),
]


class TestRatings(unittest.TestCase):
    def test_lookup_and_percent_conversion(self):
        r = MDT.Ratings(SAMPLE)
        e = r.lookup(grp_id=1001)
        self.assertEqual(e["gih_wr"], 58.0)   # 0-1 小数 → 百分数
        self.assertEqual(e["ata"], 3.2)
        # 牌名回退 + 双面牌取正面
        self.assertIs(r.lookup(name="Double-Faced Card // Back")["name"],
                      "Double-Faced Card // Back")
        self.assertEqual(r.lookup(name="Double-Faced Card")["gih_wr"], 55.0)
        # 无数据牌：字段为 None 不炸
        self.assertIsNone(r.lookup(grp_id=1003)["gih_wr"])
        self.assertIsNone(r.lookup(grp_id=9999))
        self.assertIsNone(r.lookup(name="Ghost"))

    def test_id_priority_over_name(self):
        dup = SAMPLE + [_card("Good Card", 2002, gih=0.40, ata=9.9)]
        r = MDT.Ratings(dup)
        self.assertEqual(r.lookup(grp_id=1001, name="Good Card")["gih_wr"], 58.0)


class TestLoadRatings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mtga_draft_test_")
        self._p = mock.patch.object(MDT, "RATINGS_DIR", Path(self.tmp))
        self._p.start()

    def tearDown(self):
        self._p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fetch_and_cache(self):
        with mock.patch.object(MDT, "fetch_ratings", return_value=SAMPLE) as f:
            ratings, age = MDT.load_ratings("TST")
            self.assertEqual(age, 0.0)
            self.assertEqual(ratings.lookup(grp_id=1001)["gih_wr"], 58.0)
            # 第二次走缓存，不再拉取
            ratings2, _age2 = MDT.load_ratings("TST")
            self.assertEqual(f.call_count, 1)
            self.assertEqual(ratings2.lookup(grp_id=1002)["ata"], 8.9)

    def test_stale_cache_triggers_refresh(self):
        path = MDT._ratings_path("TST", "QuickDraft")
        path.parent.mkdir(parents=True, exist_ok=True)
        old = time.time() - 10 * 86400
        path.write_text(json.dumps({"fetched_ts": old, "cards": SAMPLE}),
                        encoding="utf-8")
        with mock.patch.object(MDT, "fetch_ratings",
                               return_value=SAMPLE[:1]) as f:
            ratings, age = MDT.load_ratings("TST")
        self.assertEqual(f.call_count, 1)
        self.assertEqual(age, 0.0)
        self.assertIsNone(ratings.lookup(grp_id=1002))  # 已被新数据覆盖

    def test_fetch_failure_falls_back_to_stale_cache(self):
        path = MDT._ratings_path("TST", "QuickDraft")
        path.parent.mkdir(parents=True, exist_ok=True)
        old = time.time() - 10 * 86400
        path.write_text(json.dumps({"fetched_ts": old, "cards": SAMPLE}),
                        encoding="utf-8")
        with mock.patch.object(MDT, "fetch_ratings",
                               side_effect=MDT.DraftToolError("boom")):
            ratings, age = MDT.load_ratings("TST")
        self.assertIsNotNone(ratings)
        self.assertGreater(age, 9)
        self.assertEqual(ratings.lookup(grp_id=1001)["gih_wr"], 58.0)

    def test_fetch_failure_no_cache_degrades(self):
        with mock.patch.object(MDT, "fetch_ratings",
                               side_effect=MDT.DraftToolError("boom")):
            ratings, age = MDT.load_ratings("TST")
        self.assertIsNone(ratings)
        self.assertIsNone(age)


class TestCmdRatings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mtga_draft_test_")
        self._p = mock.patch.object(MDT, "RATINGS_DIR", Path(self.tmp))
        self._p.start()

    def tearDown(self):
        self._p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cmd_ratings_summary(self):
        import argparse
        import io
        from contextlib import redirect_stdout
        args = argparse.Namespace(set="TST", format="QuickDraft",
                                  refresh=False, top=2)
        buf = io.StringIO()
        with mock.patch.object(MDT, "fetch_ratings", return_value=SAMPLE):
            with redirect_stdout(buf):
                rc = MDT.cmd_ratings(args)
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("4 张", out)
        self.assertIn("Good Card", out)
        self.assertNotIn("No Data Card", out)  # 无 GIH WR 不进 top 榜


class TestBuildRatings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mtga_draft_test_")
        self._p = mock.patch.object(MDT, "DRAFT_RATINGS_DIR", Path(self.tmp))
        self._p.start()

    def tearDown(self):
        self._p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _cards(self):
        return [{"name": "Alpha Card", "mana_cost": "{1}{G}",
                 "type_line": "Creature", "rarity": "common",
                 "oracle_text": "Trample"},
                {"name": "Beta's Trick", "mana_cost": "{U}",
                 "type_line": "Instant", "rarity": "uncommon",
                 "oracle_text": "Draw a card."}]

    def test_parse_llm_grades(self):
        text = ('前言废话 [{"name": "Alpha Card", "grade": "B", "note": "合格"},'
                ' {"name": "Beta\'s Trick", "grade": "B+", "note": "强"},'
                ' {"name": "Ghost", "grade": "S", "note": "不在本批"},'
                ' {"name": "Alpha Card", "grade": "Z", "note": "非法等级"}] 尾巴')
        # 同名后者覆盖前者：非法等级回落 C
        got = MDT._parse_llm_grades(text, {"alpha card".upper() and "Alpha Card",
                                           "Beta's Trick"})
        self.assertEqual(got["Alpha Card"]["grade"], "C")   # Z 非法 → C
        self.assertEqual(got["Beta's Trick"]["grade"], "B+")
        self.assertNotIn("Ghost", got)
        with self.assertRaises(MDT.DraftToolError):
            MDT._parse_llm_grades("没有数组", {"Alpha Card"})

    def test_build_card_table_merges_and_skips(self):
        cards = self._cards()
        community = {"Alpha Card": {"score": 7.0, "note": "good"}}
        reply = json.dumps([{"name": "Alpha Card", "grade": "B", "note": "合格"},
                            {"name": "Beta's Trick", "grade": "A-", "note": "强"}],
                           ensure_ascii=False)
        with mock.patch.object(MDT.AUTO, "llm_chat", return_value=reply) as chat:
            table = MDT.build_card_table("TST", cards, community, "", {},
                                         progress=lambda *a: None)
        self.assertEqual(chat.call_count, 1)
        self.assertEqual(table["Alpha Card"]["grade"], "B")
        self.assertEqual(table["Alpha Card"]["community_score"], 7.0)
        self.assertEqual(table["Beta's Trick"]["grade"], "A-")
        # 持久化 + 幂等：第二轮全部已评，不再调 LLM
        self.assertTrue(MDT.card_table_path("TST").is_file())
        with mock.patch.object(MDT.AUTO, "llm_chat") as chat2:
            table2 = MDT.build_card_table("TST", cards, community, "", {},
                                          progress=lambda *a: None)
        chat2.assert_not_called()
        self.assertEqual(len(table2), 2)
        # CardTable 查询：弯引号归一化 + 双面牌取正面
        ct = MDT.load_card_table("TST")
        self.assertEqual(ct.lookup("Beta’s Trick")["grade"], "A-")
        self.assertIsNone(ct.lookup("Ghost"))

    def test_card_table_front_face_index(self):
        # 存储键为双面全名时，正面名查询也必须命中
        ct = MDT.CardTable({"Glamdring, Foe-hammer // Gleam of Death":
                            {"grade": "A-", "note": "双面"},
                            "Plain Card": {"grade": "C", "note": ""}})
        self.assertEqual(ct.lookup("Glamdring, Foe-hammer")["grade"], "A-")
        self.assertEqual(
            ct.lookup("Glamdring, Foe-hammer // Gleam of Death")["grade"], "A-")
        self.assertEqual(ct.lookup("Plain Card")["grade"], "C")

    def test_llm_missing_card_gets_placeholder(self):
        cards = self._cards()
        reply = json.dumps([{"name": "Alpha Card", "grade": "B", "note": "合格"}],
                           ensure_ascii=False)
        with mock.patch.object(MDT.AUTO, "llm_chat", return_value=reply):
            table = MDT.build_card_table("TST", cards, {}, "", {},
                                         progress=lambda *a: None)
        self.assertEqual(table["Beta's Trick"]["grade"], "")  # 漏评占位
        self.assertIn("漏评", table["Beta's Trick"]["note"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
