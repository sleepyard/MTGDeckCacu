#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""供需分析：真实牌表的稀有度用量 vs 每包野卡产出 → 找出真正的瓶颈线。

回答：
  Q1 非普通的野卡产量是不是最大？
  Q2 秘稀在套牌里的实际用量是不是比稀有少？
  Q3 预算压到「4 稀有 + 0 秘稀」后，哪条线变成瓶颈？（是否反而没省到钱）
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json, os, sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, '..', 'data'))
M = json.load(open(os.path.join(DATA, 'rarity_map.json'), encoding='utf-8'))
DECKS = json.load(open(os.path.join(DATA, 'metagame_decks.json'), encoding='utf-8'))
RAR = ['common', 'uncommon', 'rare', 'mythic']
LB = {'common': '普通', 'uncommon': '非普通', 'rare': '稀有', 'mythic': '秘稀', 'basic': '基本地'}

# 每包产出（官方推导；金色包每 10 包推进 1 点野卡进度，对两条轮轨同比放大）
G = 1 + 0.1
SUPPLY = {
    'common':   1/3.,                      # 仅包内替换 1:3
    'uncommon': (1/6.) * G + 1/5.,         # 进度轮 1:6 + 替换 1:5
    'rare':     (4/30.) * G + 1/30.,       # 进度轮 4:30 + 替换 1:30
    'mythic':   (1/30.) * G + 1/30.,       # 进度轮 1:30 + 替换 1:30
}

_PFX = None


def look(name):
    global _PFX
    e = M.get(name)
    if e is not None:
        return e
    if _PFX is None:
        _PFX = {k.split(' // ')[0]: k for k in M if ' // ' in k}
    k = _PFX.get(name)
    return M.get(k) if k else None


def pack_out():
    print('=' * 72)
    print('Q1  每包野卡产出对比（1 包 = 1000 金 / 200 宝石）')
    print('-' * 72)
    print('%-8s %12s %12s %14s' % ('稀有度', '每包张数', '每张需包数', '每 100 包得'))
    for r in RAR:
        s = SUPPLY[r]
        print('%-8s %12.4f %12.2f %14.1f' % (LB[r], s, 1/s, s*100))
    print()
    print('→ 排序：非普通 %.3f ＞ 普通 %.3f ＞ 稀有 %.3f ＞ 秘稀 %.3f（张/包）'
          % tuple(SUPPLY[r] for r in ['uncommon', 'common', 'rare', 'mythic']))
    print('→ 非普通是稀有的 %.2f 倍，普通是稀有的 %.2f 倍'
          % (SUPPLY['uncommon']/SUPPLY['rare'], SUPPLY['common']/SUPPLY['rare']))
    print('  原因：进度轮（非普通 1:6 / 稀有 4:30）速率相近，但**包内替换率差 6 倍**（1:5 vs 1:30）')
    print()
    print('  ⚠ 但「产量大」≠「够用」：还要看套牌的需求量（Q2/Q3）。')


def deck_usage():
    print()
    print('=' * 72)
    print('Q2  真实牌表的稀有度用量（480 副标准牌表，2026-09-08~09-21）')
    print('-' * 72)
    tot = Counter()
    per = {r: [] for r in RAR + ['basic']}
    n = 0
    for dk in DECKS:
        c = Counter()
        for x in dk['main']:
            e = look(x['n'])
            if e is None:
                c['??'] += x['q']; continue
            c['basic' if e['basic'] else e['rarity']] += x['q']
        n += 1
        for r in RAR + ['basic']:
            tot[r] += c[r]
            per[r].append(c[r])          # ★ 即使为 0 也追加，修正上一版 bug
    nonland = sum(tot[r] for r in RAR)
    print('有效牌表 %d 副，主牌合计 %d 张（基本地 %d 张）' % (n, sum(tot.values()), tot['basic']))
    print()
    print('%-8s %9s %11s %9s %9s %12s' % ('稀有度', '总张数', '每副均值', '中位数', '每副峰值', '占非地牌比例'))
    for r in RAR:
        v = sorted(per[r])
        print('%-8s %9d %11.2f %9d %9d %11.1f%%'
              % (LB[r], tot[r], sum(v)/n, v[n//2], v[-1], 100.*tot[r]/nonland))
    print()
    m_avg, r_avg = tot['mythic']/n, tot['rare']/n
    print('★ 秘稀每副均值 %.2f 张 vs 稀有每副均值 %.2f 张 ⇒ 秘稀 : 稀有 = 1 : %.1f'
          % (m_avg, r_avg, r_avg/m_avg))
    z = lambda r, k: sum(1 for v in per[r] if v <= k)
    print('  不带秘稀的牌表 %d/%d (%.1f%%)｜秘稀 ≤2 张 %d/%d (%.1f%%)｜秘稀 ≤4 张 %d/%d (%.1f%%)'
          % (z('mythic', 0), n, 100.*z('mythic', 0)/n, z('mythic', 2), n, 100.*z('mythic', 2)/n,
             z('mythic', 4), n, 100.*z('mythic', 4)/n))
    print('  不带稀有的牌表 %d/%d (%.1f%%)' % (z('rare', 0), n, 100.*z('rare', 0)/n))
    print()
    print('%-26s %5s %7s %8s %7s %7s' % ('牌型', '副数', '普通', '非普通', '稀有', '秘稀'))
    by = defaultdict(lambda: [Counter(), 0])
    for dk in DECKS:
        e_ = by[dk['arch']]; e_[1] += 1
        for x in dk['main']:
            ee = look(x['n'])
            if ee is None or ee['basic']:
                continue
            e_[0][ee['rarity']] += x['q']
    rows = sorted([(a, v[1], v[0]) for a, v in by.items() if v[1] >= 15], key=lambda t: -t[1])
    for a, cnt, c in rows[:16]:
        print('%-26s %5d %7.1f %8.1f %7.1f %7.1f'
              % (a[:26], cnt, c['common']/cnt, c['uncommon']/cnt, c['rare']/cnt, c['mythic']/cnt))
    return per, n


def constraint(per, n):
    print()
    print('=' * 72)
    print('Q3  ★ 金卡预算压到「4 稀有 + 0 秘稀」后，哪条线变成瓶颈？')
    print('-' * 72)
    avg = {r: sum(per[r])/n for r in RAR}
    print('典型牌表（480 副均值）：基本地 %.1f ｜ 普通 %.1f ｜ 非普通 %.1f ｜ 稀有 %.1f ｜ 秘稀 %.1f'
          % (sum(per['basic'])/n, avg['common'], avg['uncommon'], avg['rare'], avg['mythic']))
    print()
    print('【满配版】各线独立所需包数：')
    for r in RAR:
        print('   %-6s %5.1f 张 → %6.1f PP' % (LB[r], avg[r], avg[r]/SUPPLY[r]))
    print('   ⇒ 满配 PP核心 = max(稀有, 秘稀) = %.1f PP' % max(avg['rare']/SUPPLY['rare'], avg['mythic']/SUPPLY['mythic']))
    print()
    print('【预算版】稀有砍到 4、秘稀 0，普通/非普通不变：')
    lines = {'rare': 4.0, 'mythic': 0.0, 'uncommon': avg['uncommon'], 'common': avg['common']}
    mx = max(lines[r]/SUPPLY[r] for r in RAR)
    for r in ['rare', 'mythic', 'uncommon', 'common']:
        pp = lines[r]/SUPPLY[r]
        print('   %-6s %5.1f 张 → %6.1f PP%s' % (LB[r], lines[r], pp, '   ← 瓶颈' if abs(pp-mx) < 1e-9 else ''))
    print()
    print('   ⇒ 结论 A：预算版的总造价 = **%.1f PP**，比满配的 %.1f PP 只降 %.0f%%'
          % (mx, max(avg['rare']/SUPPLY['rare'], avg['mythic']/SUPPLY['mythic']),
             100*(1 - mx/max(avg['rare']/SUPPLY['rare'], avg['mythic']/SUPPLY['mythic']))))
    print('   ⇒ 结论 B：瓶颈从「稀有」变成了「%s」' % LB[max(lines, key=lambda r: lines[r]/SUPPLY[r])])
    print()
    # 最优平衡点
    print('【★ 反直觉推论】既然 %s 线已经强制你买 %.1f 包，那这些包顺带产出的稀有野卡是"免费的"：'
          % (LB[max(lines, key=lambda r: lines[r]/SUPPLY[r])], mx))
    for r in RAR:
        print('   该预算下"免费可容纳"的 %s 张数 ≈ %.1f 张' % (LB[r], mx * SUPPLY[r]))
    print('   ⇒ 也就是说：如果非普通线真的卡在 %.0f PP，那么把稀有从 4 张提到 5-6 张**不额外花钱**。'
          % (avg['uncommon']/SUPPLY['uncommon']))
    print('   ⇒ 反过来：**为了"省"而把稀有压到 4 张，可能一分钱没省**（因为瓶颈在别处）。')


if __name__ == '__main__':
    pack_out()
    per, n = deck_usage()
    constraint(per, n)
