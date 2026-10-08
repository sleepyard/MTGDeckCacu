#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标准「单白衍生物」金鱼模拟器（BO1 口径）—— 兼容 shim。

★ Phase 3 起实现迁移至 tools/newbie/goldfish/（engine + data/mono_white.json +
  decks/mono_white.py），本文件仅保留原模块级 API 与 CLI 输出格式。
★ 行为变更：贪心施放排序补牌名 tiebreaker（原实现在 set 迭代序上受
  PYTHONHASHSEED 影响，结果跨进程不可复现），且调度已与全系列统一为
  伦敦调度（7→6→5），黄金数值随之两次重钉（见 tools/test_goldfish_engine.py）。

用法: python3 sim_mono_white.py [局数] [牌表文件] [--var 构型名]
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mtga_cost import parse_deck  # noqa: F401,E402  保留原顶层副作用（rarity_map 加载）
from goldfish.decks import mono_white as _mw  # noqa: E402

Game = _mw.Game
POOL = _mw.POOL
LAND = _mw.LAND
LANDS = _mw.BASIC_PREFIX   # 原模块变量名（'Plains'）
load_deck = _mw.load_deck
run = _mw.run
resolve_deck_path = _mw.resolve_deck_path

if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    n = int(args[0]) if args else 8000
    f = args[1] if len(args) > 1 else 'deck_mono_white.txt'
    deck = load_deck(os.path.join(HERE, f))
    print('牌库 %d 张 | 对局 %d 局' % (len(deck), n))
    r = run(deck, n)
    print('均杀 %.2f | T4 %.1f%% | T5 %.1f%% | T6 %.1f%% | T7 %.1f%% | 卡地率 %.1f%%'
          % (r['mean'], r['t4'], r['t5'], r['t6'], r['t7'], r['stuck']))
    print('累计伤害:', ' '.join('T%d %.0f' % (t, v) for t, v in list(r['curve'].items())[:11]))
