#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纯蓝金鱼模拟器（BO1 口径）—— 兼容 shim。

★ Phase 3 起实现迁移至 tools/newbie/goldfish/（engine + data/blue.json +
  decks/blue.py），本文件仅保留原模块级 API 与 CLI 输出格式。

⚠ 金鱼对蓝色的系统性偏差（报告须单列）：弹回/反击/闪现对金鱼完全无价值，
  tempo 路线会被严重低估；结论必须结合"哪些价值金鱼看不见"来读。

用法: python3 sim_blue.py <局数> <牌表文件>
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mtga_cost import parse_deck  # noqa: F401,E402  保留原顶层副作用（rarity_map 加载）
from goldfish.decks.blue import (  # noqa: F401,E402
    Game, POOL, LAND, load_deck, run, resolve_deck_path)

if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    f = sys.argv[2] if len(sys.argv) > 2 else 'deck_mono_blue.txt'
    deck = load_deck(resolve_deck_path(f))
    r = run(deck, n)
    rc = run(deck, n, pen=0.6)
    print('%-26s N=%-6d 公平 均杀 %.2f T5 %5.1f%% T6 %5.1f%% | 保守 均杀 %.2f | 卡地 %.1f%%'
          % (os.path.basename(f), n, r['mean'], r['t5'], r['t6'], rc['mean'], r['stuck']))
    if r['agg']:
        print('      触发统计/局：第二抽 %.2f 次 ｜ 第二咒语 %.2f 次 ｜ Lyra造天使 %.2f 个'
              % (r['agg'].get('sd', 0), r['agg'].get('ss', 0), r['agg'].get('lyra', 0)))
