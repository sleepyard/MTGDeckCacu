#!/usr/bin/env python3
"""draft_advisor.py 的纯函数与严格 LLM 合约测试。"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import draft_advisor as DA  # noqa: E402


class Table:
    def __init__(self, grades):
        self.grades = grades

    def lookup(self, name):
        return {"grade": self.grades[name]}


def card(name, grade="B", **extra):
    value = {
        "name": name, "grade": grade, "colors": ["G"], "cmc": 2,
        "rarity": "common", "type_line": "Creature", "oracle_text": "",
    }
    value.update(extra)
    return value


class TestParsing(unittest.TestCase):
    def test_requires_complete_array(self):
        with self.assertRaises(ValueError):
            DA.parse_llm_scores('[{"name":"A","raw_power":0.5,"synergy":0.5,"reason":"ok"}]',
                                ["A", "B"])

    def test_rejects_out_of_range_and_missing_reason(self):
        text = json.dumps([
            {"name": "A", "raw_power": 1.1, "synergy": 0.5, "reason": "bad"},
            {"name": "B", "raw_power": 0.5, "synergy": 0.5, "reason": "ok"},
        ])
        with self.assertRaises(ValueError):
            DA.parse_llm_scores(text, ["A", "B"])


class TestPowerAnchor(unittest.TestCase):
    def test_blends_grade_and_gih_norm(self):
        # grade B → 锚点 0.6；混合 0.6*0.6 + 0.4*0.5 = 0.56
        self.assertAlmostEqual(
            DA.power_anchor(card("A", "B", gih_norm=0.5)), 0.56)

    def test_falls_back_to_grade_anchor(self):
        c = card("A", "B")
        self.assertAlmostEqual(DA.power_anchor(c), DA.grade_anchor(c))
        # gih_norm 非法值同样回退，不抛
        self.assertAlmostEqual(
            DA.power_anchor(card("A", "B", gih_norm="bad")), DA.grade_anchor(c))

    def test_build_prompt_carries_gih_wr_pct(self):
        pack = [card("A", gih_wr=0.558), card("B", gih_wr=54.1), card("C")]
        prompt = DA.build_prompt(pack, [])
        rows = json.loads(prompt.split("当前包：", 1)[1])
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(by_name["A"]["gih_wr_pct"], 55.8)  # 0-1 小数 → 百分比
        self.assertEqual(by_name["B"]["gih_wr_pct"], 54.1)  # 已是百分比原样
        self.assertNotIn("gih_wr_pct", by_name["C"])        # 无数据不加键
        self.assertIn("gih_wr_pct", prompt)


class TestMachineAxes(unittest.TestCase):
    def test_includes_color_fit(self):
        picked = [card(f"P{i}", colors=["W"]) for i in range(6)]
        off = DA.machine_axes(card("A", colors=["R"]), picked, {})
        self.assertEqual(off["color_fit"], 0.15)   # 脱离主色
        on = DA.machine_axes(card("B", colors=["W"]), picked, {})
        self.assertEqual(on["color_fit"], 1.0)     # 贴合主色
        early = DA.machine_axes(card("C", colors=["R"]), picked[:2], {})
        self.assertEqual(early["color_fit"], 0.5)  # 方向未明

    def test_machine_reason_flags_color_fit(self):
        picked = [card(f"P{i}", colors=["W"]) for i in range(6)]
        result = DA.recommend_pick([card("A", colors=["R"])], picked)
        self.assertIn("脱离主色", result.recommendations[0].reason)
        result = DA.recommend_pick([card("A", colors=["W"])], picked)
        self.assertIn("贴合主色", result.recommendations[0].reason)


class TestPromptShape(unittest.TestCase):
    def test_picked_summary_not_full_names(self):
        picked = [card(f"P{i}", colors=["W"], rarity="rare") for i in range(12)]
        picked.append(card("Big", colors=["R"], grade="S"))
        prompt = DA.build_prompt([card("A")], picked)
        self.assertNotIn("当前已抓牌", prompt)  # 不再传全名列表
        summary = json.loads(
            prompt.split("已抓牌池摘要：", 1)[1].split("\n当前包：", 1)[0])
        self.assertEqual(summary["colors"], {"W": 12, "R": 1})
        self.assertEqual(summary["curve"].get("2"), 13)      # 全部 cmc 2
        self.assertEqual(len(summary["key_cards"]), 10)      # 封顶 10
        self.assertIn("Big", summary["key_cards"])           # S 级入选
        self.assertIn("P0", summary["key_cards"])            # rare 入选

    def test_prompt_demands_picks_object_and_offcolor_rule(self):
        prompt = DA.build_prompt([card("A")], [])
        self.assertIn('"picks"', prompt)          # json_object 顶层形态
        self.assertIn("完全脱色的牌", prompt)
        self.assertIn("不得超过 0.3", prompt)     # 脱色 synergy 硬规则


class TestParsingShapes(unittest.TestCase):
    _payload = [{"name": "A", "raw_power": 0.5, "synergy": 0.5, "reason": "ok"}]

    def test_accepts_bare_list_picks_key_and_unique_list(self):
        for text in (json.dumps(self._payload),
                     json.dumps({"picks": self._payload}),
                     json.dumps({"结果": self._payload})):
            out = DA.parse_llm_scores(text, ["A"])
            self.assertEqual(out["A"]["raw_power"], 0.5)

    def test_rejects_dict_without_list(self):
        with self.assertRaises(ValueError):
            DA.parse_llm_scores('{"picks": {"not": "list"}}', ["A"])
        with self.assertRaises(ValueError):
            DA.parse_llm_scores('{"a": [], "b": []}', ["A"])  # 多 list 无唯一解


class TestRecommendation(unittest.TestCase):
    def test_machine_ranking_uses_grade_anchor(self):
        pack = [card("A", "S"), card("B", "C")]
        result = DA.recommend_pick(pack, [], table=Table({"A": "S", "B": "C"}))
        self.assertEqual(result.status, "disabled")
        self.assertEqual(result.recommendations[0].card["name"], "A")

    def test_offline_branch_blends_gih_norm(self):
        # 同等级离线时 GIH 归一化值决定 raw_power 次序（0.6 等级 + 0.4 GIH）
        pack = [card("A", "B", gih_norm=0.0), card("B", "B", gih_norm=1.0)]
        table = Table({"A": "B", "B": "B"})
        result = DA.recommend_pick(pack, [], table=table)
        self.assertEqual(result.status, "disabled")
        top = result.recommendations[0]
        self.assertEqual(top.card["name"], "B")
        self.assertAlmostEqual(top.scores["raw_power"], 0.6 * 0.6 + 0.4 * 1.0)
        self.assertAlmostEqual(result.recommendations[1].scores["raw_power"],
                               0.6 * 0.6 + 0.4 * 0.0)

    def test_valid_llm_response_overrides_two_axes_only(self):
        pack = [card("A"), card("B")]
        table = Table({"A": "B", "B": "B"})

        def request(_prompt):
            return json.dumps([
                {"name": "A", "raw_power": 0.1, "synergy": 0.1, "reason": "协同弱"},
                {"name": "B", "raw_power": 0.9, "synergy": 0.9, "reason": "协同强"},
            ])

        result = DA.recommend_pick(pack, [], table=table, llm_request=request)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.recommendations[0].card["name"], "B")
        self.assertIsNotNone(result.prompt)

    def test_invalid_llm_response_is_explicit_offline(self):
        pack = [card("A", "S"), card("B", "C")]
        result = DA.recommend_pick(pack, [], table=Table({"A": "S", "B": "C"}),
                                   llm_request=lambda _prompt: "not json")
        self.assertEqual(result.status, "offline")
        self.assertIn("LLM 离线", result.recommendations[0].reason)
        self.assertIsNotNone(result.error)


if __name__ == "__main__":
    unittest.main(verbosity=1)
