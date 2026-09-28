#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""白池轴线三层重扫（方法论 v2：L1使能 / L2增幅 / L3回报）"""
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
W = {n: e for n, e in M.items() if e['arena'] and not e['basic'] and set(e['ci']) <= {'W'}}


def tx(e):
    return (e['oracle'] or '') + ' ' + ' '.join(f['oracle_text'] for f in (e['faces'] or []))


def cnt(pat, cmc=3, nongold=True, alive=True):
    if pat == r'—':
        return []
    out = []
    for n, e in W.items():
        if e['cmc'] > cmc or (nongold and e['rarity'] in GOLD) or (alive and not e['alive']):
            continue
        if re.search(pat, tx(e), re.I):
            out.append((e['cmc'], n, e))
    out.sort()
    return out


AXES = {
    '① 衍生物/铺场 Tokens': dict(
        L1=r'[Cc]reate .{0,50}(token|tokens)',
        L2=r'tokens? you control get|creatures? you control get \+|double the number|twice that many tokens',
        L3=r'[Ww]henever (a|one or more|another).{0,30}(token|creature).{0,25}(enters|dies)|[Ee]qual to the number of creatures you control'),
    '② +1/+1 豆 Counters': dict(
        L1=r'\+1/\+1 counter',
        L2=r'double the number of \+1/\+1|twice that many \+1/\+1|additional \+1/\+1 counter',
        L3=r'[Ww]henever .{0,30}\+1/\+1 counter|[Rr]emove a \+1/\+1 counter'),
    '③ 生命获得 Lifegain': dict(
        L1=r'you gain \d+ life|gains? \d+ life',
        L2=r'gain twice that much|twice that much life|double the amount of life',
        L3=r'[Ww]henever you gain life|gained \d+ or more life|if you gained life'),
    '④ 系命 Lifelink': dict(
        L1=r'\b[Ll]ifelink\b',
        L2=r'gain twice|double the amount',
        L3=r'[Ww]henever you gain life'),
    '⑤ 节奏闪避 Tempo': dict(
        L1=r'\bFlying\b|\b[Ff]irst strike\b|\b[Vv]igilance\b',
        L2=r'creatures you control get \+|other creatures you control get',
        L3=r'[Ww]henever this creature (attacks|deals combat damage)|[Ww]henever a creature you control attacks'),
    '⑥ 贴皮/武具 AuraEquip': dict(
        L1=r'[Ee]nchant creature|Equipped creature|Job select|\bEquip\b',
        L2=r'equipped creature.{0,30}double|enchanted creature.{0,30}double',
        L3=r'[Ww]henever .{0,25}(Aura|Equipment).{0,25}(enters|attacks)|[Cc]ost.{0,15}less.{0,25}(Aura|Equipment)'),
    '⑦ 坟场 Graveyard': dict(
        L1=r'[Mm]ill \d|put .{0,25}into your graveyard|from your graveyard',
        L2=r'for each .{0,30}card in your graveyard',
        L3=r'(return|put) .{0,40}from your graveyard|whenever .{0,25}card.{0,20}graveyard'),
    '⑧ 去除/干扰 Removal': dict(
        L1=r'[Ee]xile target|[Dd]estroy target|tap target creature|can\'t attack or block',
        L2=r'destroy all|exile all',
        L3=r'[Ww]henever .{0,25}(dies|exiled)'),
}


def main():
    print('=' * 108)
    print('白池轴线三层重扫（非金 / cmc<=3 / 轮替存活）｜白池可用牌名 %d' % len(W))
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
