#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""起手/卡地专项审计 v2 —— 修正三个问题

修正：
  ① **伦敦调度必须减手牌**（7→6→5），此前实现每次重抽都是 7 张 = 免费调度（真 bug）
  ② 加入 **MTGA BO1 手牌平滑**（抽两份，取地数更接近牌库比例的一份），作为对照
  ③ **门槛按套牌曲线定**，而不是一律用 T3<3：
       低曲线套牌（最高 2 费）只需 **T2 有 2 费**
       3 费套牌需要 **T3 有 3 费**

输出：起手地数分布、无地率、关键回合「未达可用费用」率、平均可用法力
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json, os, random, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
LANDNAME = {'Forest', 'Island', 'Mountain', 'Swamp', 'Plains', 'Wastes'}


def load_deck(path):
    deck, cur = [], 'main'
    for raw in open(path, encoding='utf-8'):
        l = raw.strip()
        if not l or l.startswith('//') or l.startswith('#'):
            continue
        if l.lower() in ('sideboard', '备牌'):
            cur = 'side'; continue
        if cur != 'main':
            continue
        p = l.split(' ', 1)
        if len(p) != 2:
            continue
        try:
            q = int(p[0])
        except ValueError:
            continue
        deck += [p[1].strip()] * q
    return deck


def is_land(n):
    return n in LANDNAME


def top_cmc(deck):
    """牌表最高费用（用于确定"需要几块地"）"""
    M = json.load(open(os.path.join(HERE, '..', 'data', 'rarity_map.json'), encoding='utf-8'))
    mx = 0
    for n in set(deck):
        if is_land(n):
            continue
        e = M.get(n)
        if e:
            mx = max(mx, int(e['cmc'] or 0))
    return mx


def deal(lib, rng, smooth=False):
    """发起手。smooth=True 时模拟 MTGA BO1：抽两份取地数更接近比例的一份"""
    a = lib[:7]
    if not smooth:
        return a, lib[7:]
    lb = lib[:]
    rng.shuffle(lb)
    b = lb[:7]
    ratio = sum(1 for c in lib if is_land(c)) / len(lib)
    ka = sum(1 for c in a if is_land(c))
    kb = sum(1 for c in b if is_land(c))
    if abs(ka - 7 * ratio) <= abs(kb - 7 * ratio):
        return a, lib[7:]
    return b, lb[7:]


def keep(hand, lo, hi):
    k = sum(1 for c in hand if is_land(c))
    return lo <= k <= hi


def one_game(deck, rng, smooth=False, lo=2, hi=5, max_mull=2):
    """返回 (起手地数, 每回合可用地数列表)"""
    lib = deck[:]
    rng.shuffle(lib)
    size = 7
    hand, lib = deal(lib, rng, smooth)
    for _ in range(max_mull):
        if keep(hand, lo, hi):
            break
        # ★ 真实伦敦调度：手牌数 -1
        size -= 1
        lib = lib + hand
        rng.shuffle(lib)
        hand = lib[:size]
        lib = lib[size:]
    k = sum(1 for c in hand if is_land(c))
    avail = []
    cur = 0
    h = k                       # 手上还有几块地
    for t in range(1, 7):
        if t > 1:
            if lib:
                c = lib.pop(0)
                if is_land(c):
                    h += 1
        if h > 0:
            h -= 1
            cur += 1            # 本回合下地
        avail.append(cur)
    return k, avail


def audit(path, n=60000):
    deck = load_deck(path)
    lands = sum(1 for c in deck if is_land(c))
    mx = top_cmc(deck)
    need2 = 2
    need3 = 3 if mx >= 3 else 0
    res = {}
    for label, smooth, lo, hi in [('① 伦敦调度·修正(7→6→5)', False, 2, 5),
                                  ('② MTGA 平滑 + 伦敦(修正)', True, 2, 5),
                                  ('③ 伦敦·严格留牌(2-4 地)', False, 2, 4),
                                  ('④ 零调度(对照)', False, 1, 6)]:
        rng = random.Random(20260924)
        zero = one = 0
        short2 = short3 = 0
        mana = Counter()
        if label.startswith('④'):
            smooth, maxm = False, 0
        else:
            maxm = 2
        for _ in range(n):
            k, avail = one_game(deck, rng, smooth, lo, hi, maxm)
            if k == 0:
                zero += 1
            if k <= 1:
                one += 1
            if avail[1] < need2:          # T2 可用地 < 2
                short2 += 1
            if need3 and avail[2] < need3:  # T3 可用地 < 3
                short3 += 1
            for i, v in enumerate(avail[:5]):
                mana[i + 1] += v
        res[label] = dict(zero=100.0 * zero / n, one=100.0 * one / n,
                          s2=100.0 * short2 / n,
                          s3=(100.0 * short3 / n) if need3 else None,
                          mana=[mana[i] / n for i in range(1, 6)])
    return lands, len(deck) - lands, mx, res


if __name__ == '__main__':
    files = sys.argv[1:] or [
        '../mono_black/deck_mono_black.txt',
        '../mono_red_blind/deck_mono_red_blind.txt',
        '../mono_white/deck_mono_white.txt',
        '../mono_blue_v2/deck_mono_blue_v2.txt',
        '../mono_green/deck_mono_green.txt',
    ]
    for f in files:
        fp = f if os.path.isabs(f) else os.path.join(HERE, f)
        if not os.path.exists(fp):
            print('未找到', f); continue
        lands, non, mx, res = audit(fp)
        print('=' * 96)
        print('%s ｜ %d 地 / %d 咒语（%.1f%%）｜ 最高费用 %d' %
              (os.path.basename(fp), lands, non, 100.0 * lands / (lands + non), mx))
        print('=' * 96)
        print('%-28s %7s %7s %9s %9s %s' % ('口径', '0地率', '≤1地率',
              'T2<2费', 'T3<3费', '前5回合平均可用地'))
        for k, v in res.items():
            s3 = ('%8.2f%%' % v['s3']) if v['s3'] is not None else '     —  '
            print('%-28s %6.2f%% %6.2f%% %8.2f%% %s %s' % (k, v['zero'], v['one'], v['s2'], s3,
                  ' '.join('%.2f' % x for x in v['mana'])))
        print()
