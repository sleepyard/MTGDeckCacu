#!/usr/bin/env python3
"""deck_core.py 回归测试：8 轴 WASPAS / 信号读取 / 组牌骨架。
纯函数，无网络无文件 I/O。运行：python tools/test_draft_core.py"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck_core as DC  # noqa: E402


class TestGradeEq(unittest.TestCase):
    def test_mapping_monotonic(self):
        order = ["S", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "F"]
        vals = [DC.grade_eq(g) for g in order]
        self.assertEqual(vals, sorted(vals, reverse=True))

    def test_unknown_falls_back(self):
        self.assertEqual(DC.grade_eq(""), 0.525)
        self.assertEqual(DC.grade_eq(None), 0.525)
        self.assertEqual(DC.grade_eq("X"), 0.525)


class TestWaspas(unittest.TestCase):
    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(DC.AXES.values()), 1.0)

    def test_all_perfect_and_all_zero(self):
        hi = DC.waspas({a: 1.0 for a in DC.AXES})
        lo = DC.waspas({a: 0.0 for a in DC.AXES})
        self.assertAlmostEqual(hi, 1.0)
        self.assertLess(lo, 0.01)  # EPS 防除零，乘积项近 0

    def test_neutral_default(self):
        mid = DC.waspas({})
        self.assertAlmostEqual(mid, 0.5, places=6)

    def test_ranking(self):
        strong = DC.waspas({"raw_power": 0.9, "synergy": 0.8})
        weak = DC.waspas({"raw_power": 0.3, "synergy": 0.2})
        self.assertGreater(strong, weak)

    def test_clamps_out_of_range(self):
        a = DC.waspas({"raw_power": 5.0})
        b = DC.waspas({"raw_power": 1.0})
        self.assertAlmostEqual(a, b)


class TestMachineAxes(unittest.TestCase):
    def test_rarity(self):
        self.assertEqual(DC.rarity_score("mythic"), 1.0)
        self.assertEqual(DC.rarity_score("common"), 0.2)
        self.assertEqual(DC.rarity_score("weird"), 0.2)

    def test_removal(self):
        self.assertEqual(DC.removal_score(["removal", "tempo"]), 1.0)
        self.assertEqual(DC.removal_score(["threat"]), 0.0)
        self.assertEqual(DC.removal_score(None), 0.0)

    def test_fixer(self):
        self.assertEqual(DC.fixer_score([], [], []), 0.5)
        self.assertGreater(DC.fixer_score(["G"], ["G", "W"], ["G", "W"]),
                           DC.fixer_score(["G"], [], ["G", "W"]))


class TestCurve(unittest.TestCase):
    def test_slot_clamp(self):
        self.assertEqual(DC.cmc_slot(0), 1)
        self.assertEqual(DC.cmc_slot(2), 2)
        self.assertEqual(DC.cmc_slot(9), 5)

    def test_fit_fills_gap(self):
        self.assertEqual(DC.curve_fit_score({}, 2), 1.0)      # 2 费全缺
        self.assertEqual(DC.curve_fit_score({2: 6}, 2), 0.5)  # 区间内
        self.assertEqual(DC.curve_fit_score({2: 8}, 2), 0.1)  # 溢出

    def test_rating(self):
        good = {1: 3, 2: 6, 3: 5, 4: 4, 5: 3}
        label, score = DC.curve_rating(good)
        self.assertEqual((label, score), ("优秀", 5))
        slow = {1: 0, 2: 2, 3: 5, 4: 6, 5: 10}
        self.assertEqual(DC.curve_rating(slow)[0], "不足")
        self.assertEqual(DC.curve_rating({}), ("不足", -5))


class TestSignals(unittest.TestCase):
    def test_alsa_open_and_closed(self):
        s = {}
        # ALSA 4.0 的牌第 7 抓还在 → 开放；ALSA 2.0 的牌第 1 抓已见不到不加分
        DC.update_signals(s, [{"colors": ["U"], "alsa": 4.0},
                              {"colors": ["R"], "alsa": 8.0}], pick_number=7)
        self.assertAlmostEqual(s["U"], DC.SIGNAL_OPEN_DELTA)
        self.assertNotIn("R", s)  # 第 7 抓见 ALSA 8.0 属正常，不触发

    def test_alsa_closed(self):
        s = {}
        # pick 2 见 ALSA 3.0 落在 ±1.5 带内 → 不触发
        DC.update_signals(s, [{"colors": ["B"], "alsa": 3.0}], pick_number=2)
        self.assertEqual(s.get("B", 0.0), 0.0)
        # pick 1 就见到 ALSA 5.0 的牌（远早于预期仍有剩 → 该色被抢）→ closed
        DC.update_signals(s, [{"colors": ["B"], "alsa": 5.0}], pick_number=1)
        self.assertAlmostEqual(s["B"], DC.SIGNAL_CLOSED_DELTA)

    def test_fallback_high_grade_count(self):
        s = {}
        DC.update_signals(s, [{"colors": ["G"], "grade": "A"},
                              {"colors": ["G"], "grade": "B"},
                              {"colors": ["W"], "grade": "C"}], pick_number=3)
        self.assertAlmostEqual(s["G"], 0.2)   # 两张高等级 ×0.1
        self.assertNotIn("W", s)              # C 不算高等级

    def test_clamp(self):
        s = {"U": 0.95}
        for _ in range(3):
            DC.update_signals(s, [{"colors": ["U"], "alsa": 1.0}], pick_number=9)
        self.assertEqual(s["U"], 1.0)

    def test_openness_score(self):
        self.assertEqual(DC.color_openness_score({}, []), 0.5)
        self.assertAlmostEqual(DC.color_openness_score({"U": 1.0}, ["U"]), 1.0)
        self.assertAlmostEqual(
            DC.color_openness_score({"U": 1.0, "B": -1.0}, ["U", "B"]), 0.5)


class TestLandCount(unittest.TestCase):
    def test_baseline(self):
        self.assertEqual(DC.land_count(3.0), 17)

    def test_high_cmc(self):
        self.assertEqual(DC.land_count(4.5), 19)
        self.assertEqual(DC.land_count(3.6), 18)

    def test_low_cmc_caps(self):
        self.assertEqual(DC.land_count(2.3), 16)
        self.assertEqual(DC.land_count(2.6), 16)  # <2.8 → 17，但 ≤2.5 不成立…
        # 2.6: base 17-1=16? <2.8 → −1 → 16，clamp 下限 16

    def test_draw_reduces_land(self):
        """教学口径：抓牌 ≥4 张 → 减 1 地（旧项目代码写反，此处钉死）。"""
        self.assertEqual(DC.land_count(3.0, draw_ramp_count=4),
                         DC.land_count(3.0) - 1)
        self.assertEqual(DC.land_count(3.0, draw_ramp_count=3),
                         DC.land_count(3.0))

    def test_splash_adds(self):
        self.assertEqual(DC.land_count(3.0, splash_count=4), 19)  # +2 封顶
        self.assertEqual(DC.land_count(3.2, splash_count=2), 18)

    def test_clamp_range(self):
        self.assertGreaterEqual(DC.land_count(1.5), DC.LAND_MIN)
        self.assertLessEqual(DC.land_count(6.0, splash_count=9), DC.LAND_MAX)


class TestColorDepthAndSplash(unittest.TestCase):
    def test_mono(self):
        ok, _ = DC.color_depth_ok({"G": 15}, ("mono", ["G"]))
        self.assertTrue(ok)
        ok, msg = DC.color_depth_ok({"G": 10}, ("mono", ["G"]))
        self.assertFalse(ok)
        self.assertIn("G 缺 4", msg)

    def test_dual(self):
        ok, _ = DC.color_depth_ok({"G": 8, "U": 9}, ("dual", ["G", "U"]))
        self.assertTrue(ok)
        ok, _ = DC.color_depth_ok({"G": 8, "U": 5}, ("dual", ["G", "U"]))
        self.assertFalse(ok)

    def test_splash_cap(self):
        ok, msg = DC.color_depth_ok({"G": 8, "U": 8, "B": 5},
                                    ("splash", ["G", "U"], ["B"]))
        self.assertFalse(ok)
        self.assertIn("上限", msg)

    def test_splash_ok(self):
        self.assertTrue(DC.splash_ok(1, iwd=0.04))
        self.assertFalse(DC.splash_ok(1, iwd=0.02))
        self.assertFalse(DC.splash_ok(2, iwd=0.10))  # 2 个异色符号不 splash
        self.assertTrue(DC.splash_ok(1, effective_score=6.5))
        self.assertFalse(DC.splash_ok(1, effective_score=5.0))
        self.assertFalse(DC.splash_ok(1))            # 无数据不进


class TestManaBase(unittest.TestCase):
    def test_parse_mana_pips_splits_hybrid(self):
        self.assertEqual(DC.parse_mana_pips("{1}{W}{W}{U/G}{W/P}"),
                         {"W": 3.0, "U": 0.5, "G": 0.5})

    def test_proportional(self):
        alloc = DC.mana_base({"G": 20, "U": 10}, 17)
        self.assertEqual(sum(alloc.values()), 17)
        self.assertGreater(alloc["G"], alloc["U"])
        self.assertGreaterEqual(alloc["U"], 1)

    def test_min_one_each(self):
        alloc = DC.mana_base({"G": 30, "U": 1}, 8)
        self.assertGreaterEqual(alloc["U"], 1)

    def test_splash_discount(self):
        plain = DC.mana_base({"G": 20, "B": 10}, 17)
        splash = DC.mana_base({"G": 20, "B": 10}, 17, splash_colors={"B"})
        self.assertLess(splash["B"], plain["B"])

    def test_empty(self):
        self.assertEqual(DC.mana_base({}, 17), {})
        self.assertEqual(DC.mana_base({"G": 5}, 0), {})


class TestLandCheck(unittest.TestCase):
    def test_hypergeom_bounds(self):
        self.assertEqual(DC.hypergeom_at_least(40, 17, 9, 18), 0.0)
        p = DC.hypergeom_at_least(40, 17, 9, 2)
        self.assertTrue(0.0 < p <= 1.0)

    def test_17_lands_passes(self):
        """经典 40/17 应过自检线（p3>0.9, p5>0.7）。"""
        p3, p5, ok = DC.land_check(17)
        self.assertGreater(p3, 0.90)
        self.assertGreater(p5, 0.70)
        self.assertTrue(ok)

    def test_15_lands_fails(self):
        _p3, _p5, ok = DC.land_check(15)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main(verbosity=1)
