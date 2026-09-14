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


class TestFetchRatingsSources(unittest.TestCase):
    """fetch_ratings：17Lands 直连优先，shiqidi 代理兜底（补丁 _fetch_json，无网络）。"""

    def test_direct_primary_success(self):
        with mock.patch.object(MDT, "_fetch_json", return_value=SAMPLE) as f:
            data = MDT.fetch_ratings("TST", "PremierDraft")
        self.assertEqual(len(data), 4)
        self.assertEqual(f.call_count, 1)
        self.assertIn("17lands.com", f.call_args[0][0])
        self.assertIn("format=PremierDraft", f.call_args[0][0])

    def test_dict_payload_unwrapped(self):
        # 响应可能是 {"data": [...]} 而非裸 list
        with mock.patch.object(MDT, "_fetch_json",
                               return_value={"data": SAMPLE}) as f:
            data = MDT.fetch_ratings("TST")
        self.assertEqual(f.call_count, 1)
        self.assertEqual(len(data), 4)

    def test_fallback_to_shiqidi_on_failure(self):
        def side(url, source, timeout=30):
            if "17lands.com" in url:
                raise MDT.DraftToolError("直连挂了")
            return SAMPLE
        with mock.patch.object(MDT, "_fetch_json", side_effect=side) as f:
            data = MDT.fetch_ratings("TST")
        self.assertEqual(f.call_count, 2)
        self.assertIn("shiqidi", f.call_args_list[1][0][0])
        self.assertEqual(len(data), 4)

    def test_empty_list_counts_as_source_failure(self):
        def side(url, source, timeout=30):
            return [] if "17lands.com" in url else SAMPLE
        with mock.patch.object(MDT, "_fetch_json", side_effect=side) as f:
            data = MDT.fetch_ratings("TST")
        self.assertEqual(f.call_count, 2)   # 空列表 → 回退代理
        self.assertEqual(len(data), 4)

    def test_both_fail_raises_chained_error(self):
        with mock.patch.object(MDT, "_fetch_json",
                               side_effect=MDT.DraftToolError("x")) as f:
            with self.assertRaises(MDT.DraftToolError) as ctx:
                MDT.fetch_ratings("TST", "PremierDraft")
        self.assertEqual(f.call_count, 2)
        msg = str(ctx.exception)
        self.assertIn("两个数据源均失败", msg)
        self.assertIn("TST/PremierDraft", msg)


class TestSpearmanMath(unittest.TestCase):
    def test_perfect_monotonic(self):
        pairs = [(1, 10), (2, 20), (3, 30), (4, 40)]
        self.assertAlmostEqual(MDT.spearman(pairs), 1.0)

    def test_reversed(self):
        pairs = [(1, 40), (2, 30), (3, 20), (4, 10)]
        self.assertAlmostEqual(MDT.spearman(pairs), -1.0)

    def test_ties_use_average_ranks(self):
        # x 秩 = [1, 2.5, 2.5, 4]，y 秩 = [1, 2, 3, 4]
        # Pearson：cov=4.5，vx=4.5，vy=5.0 → 4.5/sqrt(22.5)≈0.948683
        pairs = [(1, 1), (2, 2), (2, 3), (4, 4)]
        self.assertAlmostEqual(MDT.spearman(pairs), 0.9487, places=4)

    def test_insufficient_pairs_returns_none(self):
        self.assertIsNone(MDT.spearman([(1, 2)]))
        self.assertIsNone(MDT.spearman([]))


class TestJoinAndMismatch(unittest.TestCase):
    def test_join_aligns_double_faced_front_name(self):
        table = {"Glamdring, Foe-hammer // Gleam of Death": {"grade": "A-"},
                 "Plain Card": {"grade": "C"}}
        raw = [{"name": "Glamdring, Foe-hammer // Gleam of Death",
                "ever_drawn_win_rate": 0.55, "avg_pick": 4.0,
                "ever_drawn_game_count": 900},
               {"name": "Plain Card", "ever_drawn_win_rate": 0.50,
                "avg_pick": 7.0, "ever_drawn_game_count": 800},
               {"name": "Unknown Card", "ever_drawn_win_rate": 0.51,
                "avg_pick": 6.0, "ever_drawn_game_count": 700}]
        joined, missing = MDT.join_table_ratings(table, raw)
        self.assertEqual(len(joined), 2)
        by_name = {j["name"]: j for j in joined}
        self.assertEqual(by_name["Glamdring, Foe-hammer // Gleam of Death"]
                         ["gih_wr"], 55.0)          # 0-1 → 百分数
        self.assertEqual(by_name["Plain Card"]["gih_cnt"], 800)
        self.assertEqual(missing, ["Unknown Card"])  # 漏评

    def test_find_mismatches(self):
        joined = [
            {"name": "Over", "grade": "B+", "gih_wr": 40.0, "ata": 5.0,
             "gih_cnt": 1000},
            {"name": "U1", "grade": "C", "gih_wr": 55.0, "ata": 6.0,
             "gih_cnt": 1000},
            {"name": "U2", "grade": "D", "gih_wr": 60.0, "ata": 7.0,
             "gih_cnt": 1000},
            {"name": "M1", "grade": "C", "gih_wr": 45.0, "ata": 6.0,
             "gih_cnt": 1000},
            {"name": "M2", "grade": "C", "gih_wr": 50.0, "ata": 6.0,
             "gih_cnt": 1000},
            {"name": "Small", "grade": "D", "gih_wr": 99.0, "ata": 1.0,
             "gih_cnt": 10},                          # 小样本，须剔除
        ]
        over, under, median, q3 = MDT.find_mismatches(joined, min_gih=500)
        self.assertEqual(median, 50.0)
        self.assertEqual(q3, 55.0)
        self.assertEqual([j["name"] for j in over], ["Over"])
        self.assertEqual([j["name"] for j in under], ["U2", "U1"])  # 按胜率降序


class TestRegress(unittest.TestCase):
    """regress 端到端（缓存文件驱动，无网络）：13 张 17Lands 牌 × 12 条我方评级。"""

    LR_CARDS = [
        # (name, GIH WR%, ATA, #GIH)；1-10 严格单调（已知 Spearman 答案）
        ("Bomb Rare", 60.0, 2.0, 1000), ("Top Uncommon", 58.0, 3.0, 1000),
        ("Solid One", 56.0, 3.5, 1000), ("Good Common", 55.0, 4.0, 1000),
        ("Okay One", 53.0, 5.0, 1000), ("Filler A", 52.0, 6.0, 1000),
        ("Filler B", 51.0, 6.5, 1000), ("Weak One", 49.0, 7.0, 1000),
        ("Bad One", 47.0, 8.0, 1000), ("Trap Card", 44.0, 9.0, 1000),
        ("Tiny Sample", 90.0, 1.5, 100),      # 小样本：剔除出相关/错配
        ("Ghost Unrated", 57.0, 3.2, 2000),   # 我方无评级：漏评
        ("Placeholder Card", 50.0, 6.2, 1000),  # 我方占位 grade ""
    ]
    GRADES_MAP = {
        "Bomb Rare": "S", "Top Uncommon": "A", "Solid One": "A-",
        "Good Common": "B+", "Okay One": "B", "Filler A": "B-",
        "Filler B": "C+", "Weak One": "C", "Bad One": "C-",
        "Trap Card": "D", "Tiny Sample": "B", "Placeholder Card": "",
    }

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="regress_test_")
        self._patches = [
            mock.patch.object(MDT, "RATINGS_DIR", Path(self.tmp) / "17lands"),
            mock.patch.object(MDT, "DRAFT_RATINGS_DIR",
                              Path(self.tmp) / "draft_ratings"),
        ]
        for p in self._patches:
            p.start()
        raw = [{"name": n, "mtga_id": 1000 + i,
                "ever_drawn_win_rate": wr / 100.0, "avg_pick": ata,
                "opening_hand_win_rate": None, "avg_seen": None,
                "win_rate": None, "ever_drawn_game_count": cnt}
               for i, (n, wr, ata, cnt) in enumerate(self.LR_CARDS)]
        cache_dir = MDT.RATINGS_DIR
        cache_dir.mkdir(parents=True)
        (cache_dir / "TST_PremierDraft.json").write_text(json.dumps(
            {"fetched_ts": time.time(), "cards": raw}), encoding="utf-8")
        table = {n: {"grade": g, "note": "t", "rarity": "common"}
                 for n, g in self.GRADES_MAP.items()}
        MDT.DRAFT_RATINGS_DIR.mkdir(parents=True)
        MDT.card_table_path("TST").write_text(json.dumps(
            {"set": "TST", "cards": table}), encoding="utf-8")
        self.out = Path(self.tmp) / "report.md"

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _args(self, **kw):
        import argparse
        base = dict(set="TST", fmt="PremierDraft", out=str(self.out),
                    min_gih=500)
        base.update(kw)
        return argparse.Namespace(**base)

    def test_regress_end_to_end(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = MDT.cmd_regress(self._args())
        self.assertEqual(rc, 0)
        headline = buf.getvalue()
        # Tiny Sample（B 级 90% 胜率）若混入相关池，Spearman 必 < 1
        self.assertIn("Spearman 等级 vs GIH WR = +1.000", headline)
        self.assertIn("vs ATA = -1.000", headline)

        text = self.out.read_text(encoding="utf-8")
        self.assertIn("event_type=PremierDraft", text)      # 口径
        self.assertIn("time_period=ALL_TIME", text)
        self.assertIn("## 分档聚合", text)
        self.assertIn("| S | 1 | 60.0 | 2.0 |", text)
        self.assertIn("| B | 2 | 71.5 | 3.25 | *", text)   # 含小样本档打 *
        self.assertIn("## Spearman 等级相关", text)
        self.assertIn("## 高估 TOP 10", text)
        self.assertIn("## 低估 TOP 10", text)
        self.assertIn("## 漏评清单", text)
        self.assertIn("- Ghost Unrated", text)
        self.assertIn("## 占位跳过", text)
        self.assertIn("- Placeholder Card", text)
        self.assertIn("## 小样本说明", text)
        self.assertIn("Tiny Sample", text)

    def test_grade_stats_aggregation(self):
        joined, missing = MDT.join_table_ratings(
            {n: {"grade": g} for n, g in self.GRADES_MAP.items()},
            json.loads((MDT.RATINGS_DIR / "TST_PremierDraft.json")
                       .read_text(encoding="utf-8"))["cards"])
        self.assertEqual(len(joined), 12)
        self.assertEqual(missing, ["Ghost Unrated"])
        stats = {r["grade"]: r for r in MDT.grade_stats(joined, min_gih=500)}
        self.assertEqual(stats["S"]["count"], 1)
        self.assertEqual(stats["S"]["mean_gih_wr"], 60.0)
        self.assertEqual(stats["B"]["count"], 2)            # Okay One + Tiny Sample
        self.assertEqual(stats["B"]["small_sample"], 1)
        self.assertEqual(stats["B"]["mean_gih_wr"], 71.5)

    def test_missing_card_table_is_usage_error(self):
        MDT.card_table_path("TST").unlink()
        self.assertEqual(MDT.cmd_regress(self._args()), 2)


COLOR_ROWS = [
    {"color_name": "All", "short_name": "All", "wins": 5000, "games": 10000,
     "is_summary": True},
    {"color_name": "White-Red", "short_name": "WR", "wins": 550, "games": 1000,
     "is_summary": False},
    {"color_name": "Blue-Black", "short_name": "UB", "wins": 480, "games": 1000,
     "is_summary": False},
]


class TestColorRatings(unittest.TestCase):
    """fetch/load_color_ratings：直连优先代理兜底 + 3 天 TTL 缓存（无网络）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="colors_test_")
        self._p = mock.patch.object(MDT, "RATINGS_DIR", Path(self.tmp))
        self._p.start()

    def tearDown(self):
        self._p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fetch_order_direct_first(self):
        def side(url, source, timeout=30):
            if "17lands.com" in url:
                raise MDT.DraftToolError("直连挂了")
            return COLOR_ROWS
        with mock.patch.object(MDT, "_fetch_json", side_effect=side) as f:
            rows = MDT.fetch_color_ratings("TST", "PremierDraft")
        self.assertEqual(f.call_count, 2)
        self.assertIn("17lands.com/color_ratings", f.call_args_list[0][0][0])
        self.assertIn("shiqidi", f.call_args_list[1][0][0])
        self.assertIn("event_type=PremierDraft", f.call_args_list[0][0][0])
        self.assertIn("start_date=2016-01-01", f.call_args_list[0][0][0])
        self.assertEqual(len(rows), 3)

    def test_fetch_both_fail_raises(self):
        with mock.patch.object(MDT, "_fetch_json",
                               side_effect=MDT.DraftToolError("x")):
            with self.assertRaises(MDT.DraftToolError) as ctx:
                MDT.fetch_color_ratings("TST")
        self.assertIn("色组", str(ctx.exception))

    def test_load_caches_and_reuses(self):
        with mock.patch.object(MDT, "fetch_color_ratings",
                               return_value=COLOR_ROWS) as f:
            rows, age = MDT.load_color_ratings("TST", "PremierDraft")
            self.assertEqual(age, 0.0)
            self.assertTrue(
                (Path(self.tmp) / "TST_PremierDraft_colors.json").is_file())
            rows2, _ = MDT.load_color_ratings("TST", "PremierDraft")
            self.assertEqual(f.call_count, 1)   # 第二次走缓存
            self.assertEqual(len(rows2), 3)

    def test_stale_cache_triggers_refresh_and_falls_back(self):
        path = Path(self.tmp) / "TST_PremierDraft_colors.json"
        old = time.time() - 10 * 86400
        path.write_text(json.dumps({"fetched_ts": old, "rows": COLOR_ROWS[:1]}),
                        encoding="utf-8")
        with mock.patch.object(MDT, "fetch_color_ratings",
                               return_value=COLOR_ROWS) as f:
            rows, age = MDT.load_color_ratings("TST", "PremierDraft")
        self.assertEqual(f.call_count, 1)       # 过期 → 刷新
        self.assertEqual(len(rows), 3)
        # 刷新失败 → 沿用过期缓存；无缓存 → (None, None)
        path.write_text(json.dumps({"fetched_ts": old, "rows": COLOR_ROWS[:1]}),
                        encoding="utf-8")
        with mock.patch.object(MDT, "fetch_color_ratings",
                               side_effect=MDT.DraftToolError("boom")):
            rows, age = MDT.load_color_ratings("TST", "PremierDraft")
        self.assertEqual(len(rows), 1)
        self.assertGreater(age, 9)
        path.unlink()
        with mock.patch.object(MDT, "fetch_color_ratings",
                               side_effect=MDT.DraftToolError("boom")):
            self.assertEqual(MDT.load_color_ratings("TST", "PremierDraft"),
                             (None, None))


def _snap_card(name, text="", tl="Creature — Beast", p=None, t=None, cmc=2,
               rarity="common", layout="normal", colors=None, kws=None,
               cost="{2}"):
    """Scryfall 快照形 dict（build_brief 需要 cmc/power/toughness/keywords）。"""
    return {"name": name, "oracle_text": text, "type_line": tl, "power": p,
            "toughness": t, "cmc": cmc, "rarity": rarity, "layout": layout,
            "colors": colors or [], "keywords": kws or [], "mana_cost": cost}


class TestBriefMetrics(unittest.TestCase):
    """parse_damage_lines / toughness_coverage / creature_baseline 手算断言。"""

    def test_parse_damage_lines(self):
        cards = [
            _snap_card("Shock", "{R} deals 2 damage to any target.",
                       tl="Instant"),
            _snap_card("Big Burn", "deals 5 damage to target creature.",
                       tl="Sorcery"),
            _snap_card("Overkill", "deals 6 damage to you.", tl="Sorcery"),
            _snap_card("Debilitate",
                       "target creature gets -3/-3 until end of turn.",
                       tl="Sorcery"),
            _snap_card("Power Burn", "deals damage equal to its power.",
                       tl="Sorcery"),                       # 无数值 → 拒绝
            _snap_card("Divination", "Draw two cards.", tl="Sorcery"),  # 非伤害句
        ]
        lines = MDT.parse_damage_lines(cards)
        self.assertEqual(lines.get(2), ["Shock"])
        self.assertEqual(lines.get(5), ["Big Burn"])
        self.assertEqual(lines.get(3), ["Debilitate"])
        self.assertNotIn(6, lines)                          # 1..5 之外排除
        self.assertEqual(sum(len(v) for v in lines.values()), 3)

    def test_toughness_coverage(self):
        cards = [
            _snap_card("T1", t="1"), _snap_card("T2", t="2"),
            _snap_card("T3", t="3"), _snap_card("T4", t="4"),
            _snap_card("Star", t="*"),                      # 不可解析剔除
            _snap_card("Spell", tl="Instant"),              # 非生物剔除
            _snap_card("Token", t="2", layout="token"),     # token 剔除
        ]
        cov = MDT.toughness_coverage(cards, {2: ["x"], 3: ["y"]})
        self.assertEqual(cov[2], (2, 4, 50.0))
        self.assertEqual(cov[3], (3, 4, 75.0))

    def test_creature_baseline(self):
        cards = [
            _snap_card("A", p="2", t="2", cmc=2),
            _snap_card("B", p="3", t="1", cmc=2),
            _snap_card("C", p="2", t="3", cmc=2, rarity="uncommon"),  # 非普通剔除
            _snap_card("D", p="4", t="4", cmc=4),
            _snap_card("E", p="1", t="1", cmc=1),                     # cmc<2 剔除
        ]
        base = MDT.creature_baseline(cards)
        self.assertEqual(base[2], (2.5, 1.5, 2))   # P 中位 2.5 / T 中位 1.5
        self.assertEqual(base[4], (4.0, 4.0, 1))
        self.assertNotIn(3, base)
        self.assertNotIn(1, base)


class TestBuildBrief(unittest.TestCase):
    """build_brief 端到端：fixture 快照 + fixture 17lands/色组缓存（无网络）。"""

    SNAPSHOT = [
        _snap_card("Dragon Bomb", "Flying", p="5", t="5", cmc=5,
                   rarity="rare", colors=["R"], kws=["Flying"], cost="{3}{R}{R}"),
        _snap_card("Shock", "{R} deals 2 damage to any target.",
                   tl="Instant", colors=["R"], cost="{R}"),
        _snap_card("Doom Blade", "Destroy target creature.",
                   tl="Instant", colors=["B"], cost="{1}{B}"),
        _snap_card("Counter Spell", "Counter target spell.",
                   tl="Instant", colors=["U"], cost="{1}{U}"),
        _snap_card("Grizzly Bears", "", p="2", t="2", cmc=2, colors=["G"]),
        _snap_card("Hill Giant", "", p="3", t="3", cmc=4, colors=["R"]),
        _snap_card("Swift Raptor", "Haste", p="2", t="1", cmc=2, colors=["R"],
                   kws=["Haste"], cost="{1}{R}"),
        _snap_card("Castle Guard", "", p="1", t="4", cmc=3, colors=["W"]),
        _snap_card("Weak Vanilla", "", p="2", t="2", cmc=2, colors=["G"]),
    ]
    # name → (GIH WR%, play_rate, ATA, #GIH)
    LR = {
        "Dragon Bomb": (60.0, 0.50, 2.0, 2000),
        "Shock": (53.0, 0.50, 4.0, 1500),
        "Doom Blade": (52.0, 0.40, 4.5, 1500),
        "Counter Spell": (50.0, 0.35, 5.0, 1200),
        "Grizzly Bears": (51.0, 0.60, 5.5, 2000),
        "Hill Giant": (49.0, 0.50, 6.0, 1800),
        "Swift Raptor": (54.0, 0.55, 4.2, 1900),
        "Castle Guard": (48.0, 0.40, 6.5, 1600),
        "Weak Vanilla": (44.0, 0.45, 8.0, 1700),
    }

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="brief_test_"))
        self._p = mock.patch.object(MDT, "RATINGS_DIR", self.tmp / "17lands")
        self._p.start()
        MDT.RATINGS_DIR.mkdir(parents=True)
        raw = [{"name": n, "mtga_id": 2000 + i,
                "ever_drawn_win_rate": wr / 100.0, "play_rate": pr,
                "avg_pick": ata, "ever_drawn_game_count": cnt}
               for i, (n, (wr, pr, ata, cnt)) in enumerate(self.LR.items())]
        (MDT.RATINGS_DIR / "TST_PremierDraft.json").write_text(json.dumps(
            {"fetched_ts": time.time(), "cards": raw}), encoding="utf-8")
        (MDT.RATINGS_DIR / "TST_PremierDraft_colors.json").write_text(
            json.dumps({"fetched_ts": time.time(), "rows": COLOR_ROWS}),
            encoding="utf-8")
        self.snap = self.tmp / "scryfall_tst_preview_20260901_1200.json"
        self.snap.write_text(json.dumps(self.SNAPSHOT, ensure_ascii=False),
                             encoding="utf-8")

    def tearDown(self):
        self._p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_build_brief_all_sections(self):
        with mock.patch.object(MDT, "find_set_cards_json",
                               return_value=self.snap):
            report, summary = MDT.build_brief("TST", "PremierDraft")
        for section in ("## 速度", "## 强度", "## 先后手", "## 去除密度",
                        "## 去除线", "## 留费注意点", "## 生物强度", "## 猝死情况"):
            self.assertIn(section, report)
        # 先后手：明确数据缺口，不伪造数字
        self.assertIn("无公开先后手聚合数据", report)
        # 猝死节标注代理
        self.assertIn("proxy", report)
        # 速度判定数字可回溯：WR 55.0% ≥ 52% → 快
        self.assertIn("判定：快", report)
        self.assertIn("55.0%", report)
        # 强度：9 张可靠样本，炸弹 1 张（Dragon Bomb 60%），中位 51.0%
        self.assertIn("炸弹（GIH WR ≥ 58%）1 张", report)
        self.assertIn("中位数 51.0%", report)
        # 去除：hard（Doom Blade）与 burn（Shock）分列
        self.assertIn("hard removal", report)
        self.assertIn("Doom Blade", report)
        self.assertIn("Shock", report)
        # 去除线：2 点覆盖 6 张生物中防御力≤2 的 3 张
        self.assertIn("| 2 点 | 3/6 | 50.0% | Shock |", report)
        # 留费注意点：三张瞬发 play_rate 均 ≥0.30
        self.assertIn("Counter Spell", report)
        # 生物基准：cmc2 普通生物 3 张，中位 2/2
        self.assertIn("| 2 | 2.0 | 2.0 | 3 |", report)
        # 控制台摘要：速度判定 + 先后手缺口 + 猝死代理
        joined = "\n".join(summary)
        self.assertIn("速度判定：快", joined)
        self.assertIn("无公开聚合数据", joined)
        self.assertIn("代理指标", joined)

    def test_build_brief_missing_snapshot_raises(self):
        with mock.patch.object(MDT, "find_set_cards_json",
                               return_value=None):
            with self.assertRaises(MDT.DraftToolError) as ctx:
                MDT.build_brief("TST", "PremierDraft")
        self.assertIn("set_preview_tool.py fetch", str(ctx.exception))

    def test_cmd_brief_writes_report_and_prints_summary(self):
        import argparse
        import io
        from contextlib import redirect_stdout
        out = self.tmp / "brief.md"
        args = argparse.Namespace(set="TST", fmt="PremierDraft", out=str(out),
                                  min_gih=500)
        buf = io.StringIO()
        with mock.patch.object(MDT, "find_set_cards_json",
                               return_value=self.snap):
            with redirect_stdout(buf):
                rc = MDT.cmd_brief(args)
        self.assertEqual(rc, 0)
        self.assertTrue(out.is_file())
        text = out.read_text(encoding="utf-8")
        self.assertIn("## 速度", text)
        self.assertIn("[brief] 速度判定：快", buf.getvalue())
        # 缺快照 → 退出码 2
        with mock.patch.object(MDT, "find_set_cards_json", return_value=None):
            self.assertEqual(MDT.cmd_brief(args), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)