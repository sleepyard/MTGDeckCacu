#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/deck_config.py 回归测试（Phase 2 配置数据化）。

最重要的契约是【默认值等价性】：load_params() 在无 JSON 时的结果必须与
迁移前各模块常量的原值逐项相等（字面量硬值断言，防假绿）。其余覆盖：
JSON 覆盖生效、坏 JSON/缺失文件回退、未知键 warning、类型不符保持默认、
BASIC_LANDS 统一。

测试均通过临时路径注入，不创建真实 strategy_params.json（兜底路径必须绿）。
"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck_config  # noqa: E402
import deck_core  # noqa: E402
import deck_model  # noqa: E402
import deck_version  # noqa: E402
import mtg_tool  # noqa: E402
import mtga_log_tool  # noqa: E402
import rot_audit  # noqa: E402


def load(path_text_map):
    """写临时 JSON（或 None 表示不存在）并 load_params 注入，返回 (params, stderr)。"""
    tmp = tempfile.mkdtemp()
    path = Path(tmp) / "strategy_params.json"
    if path_text_map is not None:
        path.write_text(path_text_map, encoding="utf-8")
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        params = deck_config.load_params(path)
    return params, err.getvalue()


class TestDefaultEquivalence(unittest.TestCase):
    """load_params() 默认值 == 迁移前常量原值（字面量硬值，防假绿）。"""

    @classmethod
    def setUpClass(cls):
        cls.params, cls.warn = load(None)  # 文件不存在 → 纯默认

    def test_missing_file_warns_once(self):
        self.assertIn("参数文件不存在", self.warn)

    def test_deck_core_grade_eq(self):
        self.assertEqual(self.params["deck_core"]["GRADE_EQ"], {
            "S": 0.60, "A": 0.57, "A-": 0.56, "B+": 0.55, "B": 0.545,
            "B-": 0.54, "C+": 0.53, "C": 0.525, "C-": 0.52, "D": 0.51,
            "F": 0.48,
        })

    def test_deck_core_scalars(self):
        dc = self.params["deck_core"]
        self.assertEqual(dc["HIGH_GRADES"], ["S", "A", "A-", "B+", "B"])
        self.assertEqual(dc["RARITY_SCORE"],
                         {"mythic": 1.0, "rare": 0.7, "uncommon": 0.45, "common": 0.2})
        self.assertEqual(dc["AXES"], {
            "raw_power": 0.20, "synergy": 0.15, "curve_fit": 0.15,
            "color_fit": 0.15, "color_openness": 0.10, "signal": 0.10,
            "fixer": 0.05, "removal": 0.05, "rarity": 0.05,
        })
        self.assertEqual(dc["WASPAS_LAMBDA"], 0.5)
        self.assertEqual(dc["CURVE_TARGET"],
                         {"1": [2, 4], "2": [5, 7], "3": [4, 6], "4": [3, 5], "5": [2, 4]})
        self.assertEqual(dc["CURVE_RATING"], {
            "TIERS": [
                {"label": "优秀", "ratio": 0.40, "mid": 3, "delta": 5},
                {"label": "良好", "ratio": 0.30, "mid": 2, "delta": 2},
                {"label": "偏慢", "ratio": 0.20, "mid": 0, "delta": -3},
            ],
            "FALLBACK": {"label": "不足", "delta": -5},
        })
        self.assertEqual(dc["SIGNAL_OPEN_DELTA"], 0.3)
        self.assertEqual(dc["SIGNAL_CLOSED_DELTA"], -0.2)
        self.assertEqual(dc["ALSA_MARGIN"], 1.5)
        self.assertEqual(dc["FALLBACK_PER_HIGH"], 0.1)
        self.assertEqual(dc["COLOR_FIT_MAIN_COLORS"], 2)
        self.assertEqual(dc["COLOR_FIT_NEUTRAL_PICKS"], 5)
        self.assertEqual(dc["TARGET_NON_LANDS"], 23)
        self.assertEqual(dc["LAND_MIN"], 16)
        self.assertEqual(dc["LAND_MAX"], 19)
        self.assertEqual(dc["STRATEGY_TARGETS"], {
            "aggro": {"creature": 16, "removal": 3},
            "mid": {"creature": 13, "removal": 3},
            "control": {"creature": 10, "removal": 6},
        })
        self.assertEqual(dc["DEPTH_MONO_MIN"], 14)
        self.assertEqual(dc["DEPTH_DUAL_MIN"], 8)
        self.assertEqual(dc["SPLASH_MAX_CARDS"], 3)
        self.assertEqual(dc["SPLASH_DISCOUNT"], 0.3)
        self.assertEqual(dc["SPLASH_IWD_THRESHOLD"], 0.03)
        self.assertEqual(dc["SPLASH_SCORE_THRESHOLD"], 6.0)

    def test_deck_core_land_count_params(self):
        self.assertEqual(self.params["deck_core"]["LAND_COUNT"], {
            "BASE": 17,
            "CMC_STEPS": [[">", 4.0, 2], [">", 3.4, 1], ["<", 2.5, -2], ["<", 2.8, -1]],
            "RAMP_MIN": 4,
            "RAMP_DELTA": -1,
            "SPLASH_PER": 0.5,
            "SPLASH_MAX_ADD": 2,
            "CAPS": [["<=", 2.5, "<=", 2, 16], ["<", 2.8, "<=", 1, 17]],
        })

    def test_deck_core_land_check_params(self):
        self.assertEqual(self.params["deck_core"]["LAND_CHECK"], {
            "P3_DRAWS": 9, "P3_K": 2, "P3_MIN": 0.90,
            "P5_DRAWS": 11, "P5_K": 4, "P5_MIN": 0.70,
        })

    def test_mtga_log_tool_params(self):
        self.assertEqual(self.params["mtga_log_tool"], {
            "RISK_TURN3_LANDS": 3,
            "RISK_MULLIGAN_LIMIT": 2,
            "RISK_STUCK_NONLAND": 4,
            "CATEGORY_ACTIONS": {
                "PlayLand": "下地",
                "CastSpell": "施放",
                "Put": "放进战场",
                "Draw": "抓牌",
                "DrawCard": "抓牌",
            },
        })

    def test_rot_audit_params(self):
        self.assertEqual(self.params["rot_audit"], {
            "ROTATION_DATE": "2027-02-02",
            "ROTATION_SUMMARY": "WOE LCI MKM OTJ(+BIG) BLB DSK",
            "ROTATING_SETS": ["woe", "woc", "lci", "lcc", "mkm", "mkc", "otj",
                              "otc", "big", "blb", "blc", "dsk", "dsc"],
        })


class TestConsumerAliases(unittest.TestCase):
    """各模块兼容别名 == 迁移前常量原值（经绑定处转型后的最终形态）。"""

    def test_deck_core_aliases(self):
        self.assertEqual(deck_core.GRADE_EQ["S"], 0.60)
        self.assertEqual(deck_core.GRADE_EQ["F"], 0.48)
        self.assertEqual(len(deck_core.GRADE_EQ), 11)
        self.assertEqual(deck_core.HIGH_GRADES, {"S", "A", "A-", "B+", "B"})
        self.assertEqual(deck_core.RARITY_SCORE["rare"], 0.7)
        self.assertAlmostEqual(sum(deck_core.AXES.values()), 1.0)
        self.assertEqual(deck_core.CURVE_TARGET,
                         {1: (2, 4), 2: (5, 7), 3: (4, 6), 4: (3, 5), 5: (2, 4)})
        self.assertEqual(deck_core.STRATEGY_TARGETS["mid"], {"creature": 13, "removal": 3})
        self.assertEqual(deck_core.TARGET_NON_LANDS, 23)
        self.assertEqual((deck_core.LAND_MIN, deck_core.LAND_MAX), (16, 19))
        self.assertEqual((deck_core.DEPTH_MONO_MIN, deck_core.DEPTH_DUAL_MIN), (14, 8))
        self.assertEqual(deck_core.SPLASH_MAX_CARDS, 3)
        self.assertEqual(deck_core.SPLASH_DISCOUNT, 0.3)
        self.assertEqual(deck_core.SPLASH_IWD_THRESHOLD, 0.03)
        self.assertEqual(deck_core.SPLASH_SCORE_THRESHOLD, 6.0)
        self.assertEqual(deck_core.SIGNAL_OPEN_DELTA, 0.3)
        self.assertEqual(deck_core.SIGNAL_CLOSED_DELTA, -0.2)
        self.assertEqual(deck_core.ALSA_MARGIN, 1.5)
        self.assertEqual(deck_core.COLOR_FIT_MAIN_COLORS, 2)

    def test_deck_core_functions_behavior(self):
        # 行为抽查（test_draft_core 有全量）：曲线评级/地数/概率门槛与旧实现一致
        self.assertEqual(deck_core.curve_rating({}), ("不足", -5))
        self.assertEqual(deck_core.curve_rating({1: 4, 2: 4, 3: 3, 4: 3, 5: 6}),
                         ("优秀", 5))
        self.assertEqual(deck_core.land_count(3.0), 17)
        self.assertEqual(deck_core.land_count(4.5), 19)
        self.assertEqual(deck_core.land_count(2.3), 16)
        p3, p5, ok = deck_core.land_check(17)
        self.assertTrue(ok)
        self.assertGreater(p3, 0.90)
        self.assertGreater(p5, 0.70)

    def test_mtga_log_tool_aliases(self):
        self.assertEqual(mtga_log_tool.RISK_TURN3_LANDS, 3)
        self.assertEqual(mtga_log_tool.RISK_MULLIGAN_LIMIT, 2)
        self.assertEqual(mtga_log_tool.RISK_STUCK_NONLAND, 4)
        self.assertEqual(mtga_log_tool.CATEGORY_ACTIONS["PlayLand"], "下地")
        self.assertEqual(len(mtga_log_tool.CATEGORY_ACTIONS), 5)

    def test_rot_audit_aliases(self):
        self.assertEqual(rot_audit.ROTATION_DATE, "2027-02-02")
        self.assertEqual(rot_audit.ROTATION_SUMMARY, "WOE LCI MKM OTJ(+BIG) BLB DSK")
        self.assertEqual(rot_audit.ROTATING,
                         {"woe", "woc", "lci", "lcc", "mkm", "mkc", "otj",
                          "otc", "big", "blb", "blc", "dsk", "dsc"})


class TestJsonOverride(unittest.TestCase):
    def test_override_applies(self):
        params, warn = load(json.dumps({
            "deck_core": {"TARGET_NON_LANDS": 25,
                          "LAND_COUNT": {"BASE": 18}},
            "rot_audit": {"ROTATION_DATE": "2028-01-01"},
        }, ensure_ascii=False))
        self.assertEqual(warn, "")
        self.assertEqual(params["deck_core"]["TARGET_NON_LANDS"], 25)
        self.assertEqual(params["deck_core"]["LAND_COUNT"]["BASE"], 18)
        # 缺键静默用默认
        self.assertEqual(params["deck_core"]["LAND_MIN"], 16)
        self.assertEqual(params["mtga_log_tool"]["RISK_TURN3_LANDS"], 3)
        self.assertEqual(params["rot_audit"]["ROTATION_DATE"], "2028-01-01")

    def test_int_float_interchangeable(self):
        params, warn = load(json.dumps({"deck_core": {"WASPAS_LAMBDA": 1}}))
        self.assertEqual(warn, "")
        self.assertEqual(params["deck_core"]["WASPAS_LAMBDA"], 1)


class TestFallbackAndWarnings(unittest.TestCase):
    def test_bad_json_falls_back_with_warning(self):
        params, warn = load("{not valid json")
        self.assertIn("参数文件损坏", warn)
        self.assertEqual(params["deck_core"]["TARGET_NON_LANDS"], 23)

    def test_non_dict_root_falls_back(self):
        params, warn = load("[1, 2, 3]")
        self.assertIn("根节点不是对象", warn)
        self.assertEqual(params["deck_core"]["TARGET_NON_LANDS"], 23)

    def test_unknown_key_warns_and_ignored(self):
        params, warn = load(json.dumps({
            "deck_core": {"TARGET_NON_LANDS": 25, "NO_SUCH_KEY": 1},
            "no_such_section": {"x": 1},
        }))
        self.assertIn("未知参数键: deck_core.NO_SUCH_KEY", warn)
        self.assertIn("未知参数节: no_such_section", warn)
        self.assertEqual(params["deck_core"]["TARGET_NON_LANDS"], 25)
        self.assertNotIn("NO_SUCH_KEY", params["deck_core"])
        self.assertNotIn("no_such_section", params)

    def test_type_mismatch_keeps_default(self):
        params, warn = load(json.dumps({"deck_core": {"TARGET_NON_LANDS": "二十三"}}))
        self.assertIn("参数类型不符", warn)
        self.assertEqual(params["deck_core"]["TARGET_NON_LANDS"], 23)

    def test_never_writes_back(self):
        tmp = tempfile.mkdtemp()
        path = Path(tmp) / "strategy_params.json"
        path.write_text(json.dumps({"deck_core": {"TARGET_NON_LANDS": 25}}),
                        encoding="utf-8")
        before = path.read_text(encoding="utf-8")
        deck_config.load_params(path)
        self.assertEqual(path.read_text(encoding="utf-8"), before)


class TestBasicLandsUnified(unittest.TestCase):
    def test_single_source_twelve(self):
        self.assertEqual(len(deck_model.BASIC_LANDS), 12)
        self.assertIs(deck_version.BASIC_LANDS, deck_model.BASIC_LANDS)
        self.assertIs(mtg_tool.BASIC_LAND_NAMES, deck_model.BASIC_LANDS)
        self.assertIn("Snow-Covered Wastes", deck_version.BASIC_LANDS)

    def test_any_number_single_source(self):
        self.assertIs(deck_version.ANY_NUMBER, deck_model.ANY_NUMBER)
        self.assertEqual(len(deck_version.ANY_NUMBER), 9)
        self.assertIn("Rat Colony", deck_version.ANY_NUMBER)


class TestExampleJsonMirrorsDefaults(unittest.TestCase):
    def test_example_file_matches_defaults(self):
        example = (Path(__file__).resolve().parent / "data" / "config"
                   / "strategy_params.example.json")
        self.assertTrue(example.is_file(), "示例文件缺失")
        self.assertEqual(json.loads(example.read_text(encoding="utf-8")),
                         deck_config.DEFAULTS)


if __name__ == "__main__":
    unittest.main()
