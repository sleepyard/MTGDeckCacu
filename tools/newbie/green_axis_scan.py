#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""绿池轴线三层重扫（真盲测：绿池无任何历史工程）

先让数据说话：公平评估绿色所有候选轴，**不预设任何结论**。
每条轴测 L1使能 / L2增幅 / L3回报（非金、cmc≤3、轮替存活）。

用法: python3 green_axis_scan.py
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, '..', 'data'))
M = json.load(open(os.path.join(DATA, 'rarity_map.json'), encoding='utf-8'))
DECKS = json.load(open(os.path.join(DATA, 'metagame_cards.json'), encoding='utf-8'))
PLAY = {c['name']: c for c in DECKS['cards']}
GOLD = ('rare', 'mythic')

G = {n: e for n, e in M.items()
     if e['arena'] and not e['basic'] and set(e['ci']) <= {'G'}}


def tx(e):
    return (e['oracle'] or '') + ' ' + ' '.join(f['oracle_text'] for f in (e['faces'] or []))


def cnt(pat, cmc=3, nongold=True, alive=True):
    if pat == r'—':
        return []
    out = []
    for n, e in G.items():
        if e['cmc'] > cmc:
            continue
        if nongold and e['rarity'] in GOLD:
            continue
        if alive and not e['alive']:
            continue
        if re.search(pat, tx(e), re.I):
            out.append((e['cmc'], n, e))
    out.sort()
    return out


AXES = {
    '① +1/+1 豆 Counters': dict(
        L1=r'\+1/\+1 counter',
        L2=r'twice that many \+1/\+1|additional \+1/\+1 counter|double the number of \+1/\+1|enters with (an additional|two) \+1/\+1',
        L3=r'[Ww]henever you put one or more \+1/\+1|creature you control with a \+1/\+1 counter'),
    '② 地落 Landfall': dict(
        L1=r'[Ll]andfall|whenever a land you control enters',
        L2=r'play (an|two) additional land|additional land on each|enters with an additional',
        L3=r'[Ll]andfall.{0,70}(draw|create|deal|\+1/\+1|put|target)'),
    '③ 大兽/加速 Ramp': dict(
        L1=r'costs? \{.{1,3}\} less|add \{G\}|search your library for a (basic )?(Forest|land)|\{T\}: Add \{G\}',
        L2=r'costs? \{.{1,3}\} less|add .{0,10}additional',
        L3=r'costs? \{.{1,3}\} less'),
    '④ 坟场 Graveyard': dict(
        L1=r'[Mm]ill \d|put .{0,25}into your graveyard|from your graveyard',
        L2=r'for each .{0,30}card in your graveyard|cards? in your graveyard.{0,25}(instead|twice)',
        L3=r'(return|put) .{0,40}from your graveyard|[Ww]henever .{0,25}card.{0,20}graveyard'),
    '⑤ 衍生物 Tokens': dict(
        L1=r'[Cc]reate .{0,40}token',
        L2=r'twice that many|double the number of tokens|create twice',
        L3=r'[Ww]henever (a |one or more )?(creature )?tokens? .{0,35}enter|tokens you control get \+'),
    '⑥ 力量缩放 Power': dict(
        L1=r'gets \+\d/\+\d|\+1/\+1 counter|power and toughness (are|is) equal',
        L2=r'double (its|their|the) power|power .{0,15}doubled|\*/\*',
        L3=r'power 4 or greater|with power \d+ or greater|greatest power|deals? damage equal to its power'),
    '⑦ 牺牲/死触 Sacrifice': dict(
        L1=r'[Ss]acrifice (a|another|this|two) (creature|permanent|land|artifact)',
        L2=r'twice that many|instead of sacrificing',
        L3=r'[Ww]henever you sacrifice|[Ww]henever (a|another) creature you control dies'),
    '⑧ 磨牌 Mill': dict(
        L1=r'[Mm]ill \d',
        L2=r'mill .{0,25}(twice|double|that many)',
        L3=r'[Ww]henever .{0,25}mill|mills? (a|two|three|four|five|six|seven|X|\d)'),
    '⑨ 结界 Enchantments': dict(
        L1=r'[Ee]nchantment',
        L2=r'each enchantment.{0,30}(additional|twice)|enchantment.{0,20}instead',
        L3=r'[Ww]henever an? enchantment|[Ee]nchantments you control'),
}


def main():
    print('=' * 108)
    print('绿池轴线三层重扫（非金 / cmc<=3 / 轮替存活）★ 绿池无前作，本表为真盲测')
    print('绿池可用牌名：%d' % len(G))
    print('=' * 108)
    print('%-26s %8s %8s %8s  %s' % ('轴线', 'L1使能', 'L2增幅', 'L3回报', '判定'))
    print('-' * 108)
    rows = []
    for name, d in AXES.items():
        l1, l2, l3 = cnt(d['L1']), cnt(d['L2']), cnt(d['L3'])
        ok = len(l1) >= 6 and len(l2) >= 2 and len(l3) >= 3
        v = '★★ 三层齐备' if ok else ('◇ 缺L2' if len(l1) >= 6 and len(l3) >= 3 else '✗ 散件')
        rows.append((name, l1, l2, l3, v))
        print('%-26s %8d %8d %8d  %s' % (name, len(l1), len(l2), len(l3), v))
    print()
    for name, l1, l2, l3, v in rows:
        if v == '✗ 散件':
            continue
        print('【%s】%s' % (name, v))
        for lab, lst in (('L1', l1), ('L2', l2), ('L3', l3)):
            if not lst:
                print('   %s: （无）' % lab)
                continue
            s = '、'.join('%s%s' % (n, ('(%.1f%%)' % PLAY[n]['deck_pct']) if PLAY.get(n, {}).get('deck_pct', 0) >= 0.5 else '')
                          for _, n, _ in sorted(lst, key=lambda x: -PLAY.get(x[1], {}).get('deck_pct', 0))[:9])
            print('   %s: %s' % (lab, s))
        print()
    print('=' * 108)
    print('★ 各轴「总可用候选数」（把金卡也算进来，看看放开预算能补多少）')
    print('=' * 108)
    for name, d in AXES.items():
        a = len(cnt(d['L1'], 4, False)); b = len(cnt(d['L2'], 4, False)); c = len(cnt(d['L3'], 4, False))
        print('  %-26s L1 %3d ｜ L2 %3d ｜ L3 %3d   （含金、cmc≤4）' % (name, a, b, c))


if __name__ == '__main__':
    main()
