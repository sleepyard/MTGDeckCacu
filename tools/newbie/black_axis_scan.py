#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""黑池轴线三层重扫（方法论 v2：L1使能 / L2增幅 / L3回报）"""
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
B = {n: e for n, e in M.items() if e['arena'] and not e['basic'] and set(e['ci']) <= {'B'}}


def tx(e):
    return (e['oracle'] or '') + ' ' + ' '.join(f['oracle_text'] for f in (e['faces'] or []))


def cnt(pat, cmc=3, nongold=True, alive=True):
    if pat == r'—':
        return []
    out = []
    for n, e in B.items():
        if e['cmc'] > cmc or (nongold and e['rarity'] in GOLD) or (alive and not e['alive']):
            continue
        if re.search(pat, tx(e), re.I):
            out.append((e['cmc'], n, e))
    out.sort()
    return out


AXES = {
    '① 坟场 Graveyard': dict(
        L1=r'[Mm]ill \d|put .{0,25}into your graveyard|from your graveyard|sacrifice',
        L2=r'for each .{0,30}card in your graveyard|cards? in your graveyard.{0,25}(instead|twice)',
        L3=r'(return|put) .{0,40}from your graveyard|whenever .{0,25}card.{0,20}graveyard'),
    '② 牺牲/贵族 Sacrifice': dict(
        L1=r'[Ss]acrifice (a|another|this|two) (creature|permanent|artifact)',
        L2=r'twice that many|instead of sacrificing|sacrificed.{0,30}instead',
        L3=r'[Ww]henever you sacrifice|[Ww]henever (a|another) creature you control dies'),
    '③ 生命流失 Drain': dict(
        L1=r'each opponent loses \d|target opponent loses \d|you gain \d+ life and (each opponent|target opponent) loses',
        L2=r'(lose|gains?).{0,25}(twice|that much) .{0,20}life|life loss.{0,20}(twice|doubled)',
        L3=r'[Ww]henever an opponent loses life|[Ww]henever you gain life'),
    '④ 弃牌 Discard': dict(
        L1=r'[Tt]arget (player|opponent) discards|[Ee]ach (player|opponent) discards',
        L2=r'discard.{0,25}(twice|two cards? instead|that many)',
        L3=r'[Ww]henever .{0,25}discard|[Ii]f an opponent discards'),
    '⑤ -1/-1 豆 Counters': dict(
        L1=r'-1/-1 counter',
        L2=r'twice that many -1/-1|additional -1/-1 counter',
        L3=r'[Ww]henever .{0,25}-1/-1 counter|creature .{0,25}with a -1/-1 counter'),
    '⑥ 死触/去除 Removal': dict(
        L1=r'[Dd]estroy target|-[X0-9]+/-[X0-9]+ until end of turn|exile target creature',
        L2=r'destroy (two|up to two)|destroy all',
        L3=r'[Ww]henever (a|another) creature (dies|you control dies)'),
    '⑦ 敏捷快攻 Aggro': dict(
        L1=r'\bHaste\b|Menace|[Dd]eathouch',
        L2=r'other creatures you control get \+|creatures you control get \+',
        L3=r'[Ww]henever this creature (attacks|deals combat damage)'),
}


def main():
    print('=' * 108)
    print('黑池轴线三层重扫（非金 / cmc<=3 / 轮替存活）｜黑池可用牌名 %d' % len(B))
    print('=' * 108)
    print('%-24s %8s %8s %8s  %s' % ('轴线', 'L1使能', 'L2增幅', 'L3回报', '判定'))
    print('-' * 108)
    rows = []
    for name, d in AXES.items():
        l1, l2, l3 = cnt(d['L1']), cnt(d['L2']), cnt(d['L3'])
        ok = len(l1) >= 6 and len(l2) >= 2 and len(l3) >= 3
        v = '★★ 三层齐备' if ok else ('◇ 缺L2' if len(l1) >= 6 and len(l3) >= 3 else '✗ 散件')
        rows.append((name, l1, l2, l3, v))
        print('%-24s %8d %8d %8d  %s' % (name, len(l1), len(l2), len(l3), v))
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
    print('★ 含金 + cmc≤4 的可用总数（放开预算能补多少）')
    print('=' * 108)
    for name, d in AXES.items():
        print('  %-24s L1 %3d ｜ L2 %3d ｜ L3 %3d' % (name,
              len(cnt(d['L1'], 4, False)), len(cnt(d['L2'], 4, False)), len(cnt(d['L3'], 4, False))))


if __name__ == '__main__':
    main()
