#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""goldfish 引擎契约测试（Phase 3）。

两层：
  1. 引擎单测：伦敦调度手牌数序列、LONDON=False 历史口径、击杀判定（dmg>=20）、
     同种子可复现、data JSON schema 校验（未知 tag / 缺键 / bool 非 int）、
     expand 基本地映射、机制注册表与 nc_channel 共享通道语义。
  2. 黄金数值（哦鲸鲸式精确断言）：8 套牌组、合成牌库（POOL 前 11 张 ×4 +
     地补到 60）、seed=20260924、N=8000。其中 6 套与迁移前旧 sim 逐值全等；
     sim_red（调度修复：老式重抓 7 → 伦敦 7→6→5）与 sim_mono_white（施放排序
     补牌名 tiebreaker，修复跨进程不可复现）为修复后的新钉值。
"""
import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(TOOLS_DIR / "newbie"))

from goldfish import engine, mechanics  # noqa: E402
from goldfish.decks import (  # noqa: E402
    black, blue, blue_spells, green, mono_white, red, red_blind, white)

N = 8000


def synth_deck(mod):
    """合成牌库：POOL 前 11 张 ×4 + 地哨兵补到 60（与基线捕获口径一致）。"""
    deck = []
    for name in list(mod.POOL)[:11]:
        deck += [name] * 4
    deck += [mod.LAND] * (60 - len(deck))
    return deck


# ---------------------------------------------------------------- 引擎单测
class _ToyGame(engine.GameBase):
    POOL = {}
    LAND = 'Forest'

    def play_turn(self):
        self.turn += 1
        return False


class _ToyOldMulligan(_ToyGame):
    LONDON = False


class _KillGame(_ToyGame):
    def play_turn(self):
        self.turn += 1
        self.dmg = 20.0
        return self.dmg >= 20


class TestEngineCore(unittest.TestCase):
    def test_london_mulligan_shrinks_hand(self):
        """零地牌库强制两次调度：伦敦 7→6→5，终手牌 5。"""
        g = _ToyGame(["Llanowar Elves"] * 60, random.Random(42))
        self.assertEqual(len(g.hand), 5)

    def test_old_mulligan_redraws_full_seven(self):
        """LONDON=False 保留老式重抓满 7 的能力（引擎兼容开关，现役牌组已不用）。"""
        g = _ToyOldMulligan(["Llanowar Elves"] * 60, random.Random(42))
        self.assertEqual(len(g.hand), 7)

    def test_keep_range_stops_mulligan(self):
        """起手 3 地（在 2-5 留牌区间内）→ 不调度，终手牌 7；
        全地牌库（7 地 > KEEP_HI）→ 强制两次调度，终手牌 5。"""
        g = _ToyGame.__new__(_ToyGame)
        g.rng, g.pen = random.Random(1), 1.0
        g.lib = ["X"] * 50 + ["Forest"] * 3   # pop 自尾部 → 起手 3 地 4 非地
        g.hand, g.lands, g.bf, g.dmg, g.turn = [], 0, [], 0.0, 0
        g.opening()
        self.assertEqual(len(g.hand), 7)
        self.assertEqual(g.lands_in_hand(), 3)

        g2 = _ToyGame(["Forest"] * 60, random.Random(42))
        self.assertEqual(len(g2.hand), 5)

    def test_kill_at_damage_20(self):
        """dmg>=20 即击杀：第 1 回合打满 20 → mean 1.0、T3 100%。"""
        r = engine.run(_KillGame, ["X"] * 60, 100, max_turn=14)
        self.assertEqual(r["mean"], 1.0)
        self.assertEqual(r["t3"], 100.0)

    def test_same_seed_reproducible(self):
        d = synth_deck(green)
        r1 = green.run(d, 400)
        r2 = green.run(d, 400)
        self.assertEqual(r1, r2)

    def test_expand_maps_basic_prefix(self):
        got = engine.expand([(4, "Forest"), (2, "Llanowar Elves")], "Forest", "Forest")
        self.assertEqual(got, ["Forest"] * 4 + ["Llanowar Elves"] * 2)


class TestPoolSchema(unittest.TestCase):
    def _write(self, obj):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f)
        self.addCleanup(os.remove, path)
        return path

    def _pool(self, entry):
        return self._write({"land": "Forest", "basic_prefix": "Forest",
                            "pool": {"X": entry}})

    def test_valid_pool_loads(self):
        path = self._pool({"k": "C", "c": 1, "p": 1, "d": 1, "dork": 1})
        land, prefix, pool = engine.load_pool(path)
        self.assertEqual((land, prefix), ("Forest", "Forest"))
        self.assertEqual(pool["X"]["dork"], 1)

    def test_unknown_tag_rejected(self):
        path = self._pool({"k": "C", "c": 1, "p": 1, "d": 1, "no_such_mechanic": 1})
        with self.assertRaises(ValueError):
            engine.load_pool(path)

    def test_missing_key_rejected(self):
        path = self._pool({"k": "C", "c": 1, "p": 1})
        with self.assertRaises(ValueError):
            engine.load_pool(path)

    def test_bool_is_not_int_rejected(self):
        path = self._pool({"k": "C", "c": True, "p": 1, "d": 1})
        with self.assertRaises(ValueError):
            engine.load_pool(path)

    def test_negative_cost_rejected(self):
        path = self._pool({"k": "C", "c": -1, "p": 1, "d": 1})
        with self.assertRaises(ValueError):
            engine.load_pool(path)


class TestMechanicsRegistry(unittest.TestCase):
    def test_all_data_tags_registered(self):
        """data/ 下全部 JSON 通过 schema 校验（= 所有 tag 已注册）。"""
        for path in sorted(engine.DATA_DIR.glob("*.json")):
            engine.load_pool(path)  # 不抛即过

    def test_landfall_handlers_callable(self):
        for tag in ("landfall_ctr", "landfall_double", "landfall_dblpow"):
            self.assertTrue(callable(engine.HANDLERS[tag]))

    def test_marker_tags_register_as_none(self):
        self.assertIn("dork", engine.HANDLERS)
        self.assertIsNone(engine.HANDLERS["dork"])

    def test_nc_channel_tomik_double_barbs(self):
        """Tomik +1 → double_nc 翻倍 → 伤害入账 → 每个 Barbs team_pump+1。"""
        class G:
            dmg = 0.0
            team_pump = 0
            bf = [{"tags": {"tomik": 1}}, {"tags": {"double_nc": 1}},
                  {"tags": {"barbs": 1}}, {"tags": {"barbs": 1}}]
        mechanics.nc_channel(G, 2)
        self.assertEqual(G.dmg, 6.0)       # (2 + 1) * 2
        self.assertEqual(G.team_pump, 2)

    def test_nc_channel_nonpositive_noop(self):
        class G:
            dmg = 0.0
            team_pump = 0
            bf = [{"tags": {"tomik": 1}}]
        mechanics.nc_channel(G, 0)
        self.assertEqual(G.dmg, 0.0)
        self.assertEqual(G.team_pump, 0)


# ---------------------------------------------------------------- 黄金数值
class TestGoldenValues(unittest.TestCase):
    """合成牌库 + seed=20260924 + N=8000 的精确钉值。

    除 red / mono_white 外均与迁移前旧 sim 逐值全等（迁移零失真证据）。
    """

    def test_black(self):
        d = synth_deck(black)
        r, rc = black.run(d, N), black.run(d, N, pen=0.6)
        self.assertEqual(r["mean"], 4.6735)
        self.assertEqual((r["t4"], r["t5"], r["t6"]), (48.9, 91.65, 97.1625))
        self.assertEqual(r["stuck"], 30.0125)      # T3 未达 3 地口径
        self.assertEqual(rc["mean"], 5.271)

    def test_blue(self):
        d = synth_deck(blue)
        r, rc = blue.run(d, N), blue.run(d, N, pen=0.6)
        self.assertEqual(r["mean"], 5.3665)
        self.assertEqual((r["t5"], r["t6"], r["t8"]), (75.65, 93.45, 98.0))
        self.assertEqual(r["stuck"], 8.8125)
        self.assertEqual(rc["mean"], 5.82275)
        self.assertEqual(r["agg"]["sd"], 1.602625)
        self.assertEqual(r["agg"]["ss"], 0.68675)

    def test_blue_spells(self):
        d = synth_deck(blue_spells)
        r, rc = blue_spells.run(d, N), blue_spells.run(d, N, pen=0.6)
        self.assertEqual(r["mean"], 10.774375)
        self.assertEqual((r["t5"], r["t6"]), (0.0, 0.0625))
        self.assertEqual(r["stuck"], 0.3125)
        self.assertEqual(r["spells"], 2.853625)
        self.assertEqual(rc["mean"], 11.121625)

    def test_green(self):
        d = synth_deck(green)
        r, rc = green.run(d, N), green.run(d, N, pen=0.6)
        self.assertEqual(r["mean"], 5.8225)
        self.assertEqual((r["t5"], r["t6"], r["t7"]), (43.3875, 85.075, 95.1375))
        self.assertEqual(r["stuck"], 12.925)
        self.assertEqual(rc["mean"], 6.571125)

    def test_red_blind(self):
        d = synth_deck(red_blind)
        r, rc = red_blind.run(d, N), red_blind.run(d, N, pen=0.6)
        self.assertEqual(r["mean"], 5.96225)
        self.assertEqual((r["t4"], r["t5"]), (4.55, 40.1875))
        self.assertEqual(r["stuck"], 6.8875)
        self.assertEqual(rc["mean"], 6.783625)

    def test_white(self):
        d = synth_deck(white)
        r, rc = white.run(d, N), white.run(d, N, penetrate=0.6)
        self.assertEqual(r["mean"], 5.15325)
        self.assertEqual((r["t3"], r["t4"], r["t5"], r["t6"]),
                         (0.0, 17.8625, 85.375, 93.9875))
        self.assertEqual(r["stuck"], 10.65)
        self.assertEqual(rc["mean"], 5.836625)

    def test_red_new_golden_after_mulligan_fix(self):
        """★ 修复后新钉值：调度由老式重抓 7 统一为伦敦 7→6→5。
        （旧 sim_red 钉值：mean 5.424375 / t4 9.2625 / t5 68.5 / stuck 6.825 /
          cons 5.899，仅作历史对照，不再复现。）"""
        d = synth_deck(red)
        r, rc = red.run(d, N), red.run(d, N, penetrate=0.6)
        self.assertEqual(r["mean"], 5.682125)
        self.assertEqual((r["t3"], r["t4"], r["t5"]), (0.0, 7.8, 61.1625))
        self.assertEqual(r["stuck"], 7.9375)
        self.assertEqual(rc["mean"], 6.211375)

    def test_mono_white_new_golden_after_sort_and_mulligan_fix(self):
        """★ 修复后新钉值：施放排序补牌名 tiebreaker + 调度统一为伦敦 7→6→5。
        旧值对照：老式调度下同种子跨进程 4.7453 / 5.0814（不可复现）
        → tiebreaker 修复后 4.927375（仍老式调度）
        → 伦敦化后本钉值。"""
        d = synth_deck(mono_white)
        r = mono_white.run(d, N)
        self.assertEqual(r["mean"], 5.093375)
        self.assertEqual((r["t4"], r["t5"], r["t6"], r["t7"]),
                         (20.7125, 84.1875, 93.3, 96.8))
        self.assertEqual(r["stuck"], 11.7875)


if __name__ == "__main__":
    unittest.main()
