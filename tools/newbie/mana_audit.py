#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""起手/卡地专项审计：三口径对比

口径 1【纯伦敦调度】= 我此前所有模拟器用的口径
     起手 7 张；若地数 ∉ [2,5] 则重抽（最多 2 次免费调度）
口径 2【MTGA BO1 真实规则】= Arena 的实际行为
     ① 抽 **两份** 7 张起手，**自动选**其中地牌比例更接近牌库比例的那份
     ② 然后才进入伦敦调度（玩家手动，2 次免费）
口径 3【保守：无平滑版 FO3 之后 / 强依赖留牌】
     起手 7 张，只有地数 ∉ [2,4] 才调度（更严格的留牌标准）

输出：起手无地/1地率、T3 未达 3 费、T4 未达 4 费、前 4 回合平均可用法力
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json, os, random, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, '..', 'data'))
M = json.load(open(os.path.join(DATA, 'rarity_map.json'), encoding='utf-8'))
LANDNAME = {'Forest', 'Island', 'Mountain', 'Swamp', 'Plains'}


def load_deck(path):
    deck = []
    cur = 'main'
    for raw in open(path, encoding='utf-8'):
        l = raw.strip()
        if not l or l.startswith('//') or l.startswith('#'):
            continue
        if l.lower() in ('sideboard', '备牌'):
            cur = 'side'
            continue
        if cur != 'main':
            continue
        parts = l.split(' ', 1)
        if len(parts) != 2:
            continue
        try:
            q = int(parts[0])
        except ValueError:
            continue
        n = parts[1].strip()
        deck += [n] * q
    return deck


def is_land(n):
    return n in LANDNAME or (n.split(' ')[-1] in LANDNAME)


def draw7(lib):
    return lib[:7], lib[7:]


def arena_smooth(lib, rng):
    """MTGA BO1：抽两份，取地牌比例更接近牌库的那份"""
    ratio = sum(1 for c in lib if is_land(c)) / len(lib)
    a, rest_a = draw7(lib[:7] + lib[7:])
    lb = lib[:]
    rng.shuffle(lb)
    b, rest_b = draw7(lb)
    ka = sum(1 for c in a if is_land(c))
    kb = sum(1 for c in b if is_land(c))
    pick_a = abs(ka / 7 - ratio) <= abs(kb / 7 - ratio)
    return (a, rest_a) if pick_a else (b, rest_b)


def run_one(deck, rng, mode='london', lo=2, hi=5, mulls=2):
    lib = deck[:]
    rng.shuffle(lib)
    if mode == 'smooth':
        hand, lib = arena_smooth(lib, rng)
    else:
        hand, lib = draw7(lib)
    for _ in range(mulls):
        k = sum(1 for c in hand if is_land(c))
        if lo <= k <= hi:
            break
        lib = lib + hand
        rng.shuffle(lib)
        hand, lib = draw7(lib)
    return hand, lib


def audit(path, n=60000):
    deck = load_deck(path)
    lands = sum(1 for c in deck if is_land(c))
    nonlands = len(deck) - lands
    res = {}
    for mode, lo, hi, mulls, label in [
            ('london', 2, 5, 2, '① 伦敦调度(我此前用的)'),
            ('smooth', 2, 5, 2, '② MTGA BO1 真实(含平滑)'),
            ('london', 2, 4, 2, '③ 严格留牌(2-4 地)'),
            ('london', 1, 6, 0, '④ 零调度(FOW 参考)')]:
        rng = random.Random(20260924)
        zero = one = 0
        t3short = t4short = 0
        mana_sum = 0
        draws = 0
        for _ in range(n):
            hand, lib = run_one(deck, rng, mode, lo, hi, mulls)
            k = sum(1 for c in hand if is_land(c))
            if k == 0:
                zero += 1
            if k <= 1:
                one += 1
            # 逐回合推演：只看地，不看咒语
            cur = k
            for t in range(1, 5):
                if t > 1:
                    if lib:
                        c = lib.pop(0)
                        if is_land(c):
                            cur += 1
                mana_sum += cur
                draws += 1
                if t == 3 and cur < 3:
                    t3short += 1
                if t == 4 and cur < 4:
                    t4short += 1
        res[label] = dict(zero=100.0 * zero / n, one=100.0 * one / n,
                          t3=100.0 * t3short / n, t4=100.0 * t4short / n,
                          mana=mana_sum / draws)
    return lands, nonlands, res


if __name__ == '__main__':
    files = sys.argv[1:] or [
        '../mono_black/deck_mono_black.txt',
        '../mono_red_blind/deck_mono_red_blind.txt',
        '../mono_green/deck_mono_green.txt',
        '../mono_blue_v2/deck_mono_blue_v2.txt',
        '../mono_white/deck_mono_white.txt',
    ]
    for f in files:
        if not os.path.exists(f if os.path.isabs(f) else os.path.join(HERE, f)):
            print('未找到', f); continue
        lands, nonlands, res = audit(f if os.path.isabs(f) else os.path.join(HERE, f))
        print('=' * 92)
        print('%s ｜ %d 地 / %d 咒语（%.1f%% 地）' % (os.path.basename(f), lands, nonlands, 100.0 * lands / (lands + nonlands)))
        print('=' * 92)
        print('%-28s %8s %8s %8s %8s %10s' % ('口径', '0地率', '≤1地率', 'T3<3费', 'T4<4费', '前4回合均地'))
        for k, v in res.items():
            print('%-28s %7.2f%% %7.2f%% %7.2f%% %7.2f%% %10.2f' % (k, v['zero'], v['one'], v['t3'], v['t4'], v['mana']))
        print()
