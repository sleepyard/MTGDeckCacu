#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盲测：单红「燃烧」金鱼模拟器（重写版）—— 兼容 shim。

★ Phase 3 起实现迁移至 tools/newbie/goldfish/（engine + data/red_blind.json +
  decks/red_blind.py），本文件仅保留原模块级 API 与 CLI 输出格式。

用法: python3 sim_red_blind.py <局数> <牌表文件>
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mtga_cost import parse_deck  # noqa: F401,E402  保留原顶层副作用（rarity_map 加载）
from goldfish.decks.red_blind import (  # noqa: F401,E402
    Game, POOL, LAND, load_deck, run, resolve_deck_path)

if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    f = sys.argv[2] if len(sys.argv) > 2 else 'deck_mono_red_blind.txt'
    deck = load_deck(resolve_deck_path(f))
    r = run(deck, n)
    rc = run(deck, n, pen=0.6)
    print('%-26s N=%-6d 公平 均杀 %.2f T4 %5.1f%% | 保守 均杀 %.2f T4 %5.1f%% | 卡地 %.1f%%'
          % (os.path.basename(f), n, r['mean'], r['t4'], rc['mean'], rc['t4'], r['stuck']))
