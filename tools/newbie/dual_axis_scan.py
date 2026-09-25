#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双色轴线矩阵：对每个色组测各轴的三层密度（非金 / cmc≤3 / 存活）

用法: python3 dual_axis_scan.py [色组…]     默认扫全部 10 组
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, '..', 'data'))
M = json.load(open(os.path.join(DATA, 'rarity_map.json'), encoding='utf-8'))
DECKS = json.load(open(os.path.join(DATA, 'metagame_cards.json'), encoding='utf-8'))
PLAY = {c['name']: c for c in DECKS['cards']}
GOLD = ('rare', 'mythic')

PAIRS = ['WU', 'UB', 'BR', 'RG', 'GW',          # 盟友色对
         'WB', 'UR', 'BG', 'RW', 'GU']          # 对色对
CN = {'W': '白', 'U': '蓝', 'B': '黑', 'R': '红', 'G': '绿'}


def tx(e):
    return (e['oracle'] or '') + ' ' + ' '.join(f['oracle_text'] for f in (e['faces'] or []))


def pool(pair):
    want = set(pair)
    return {n: e for n, e in M.items()
            if e['arena'] and not e['basic'] and set(e['ci']) <= want}


AXES = {
    '燃烧直伤': (r'deals? \d+ damage to (any target|target|each opponent|target player)',),
    '生命流失': (r'each opponent loses \d|target opponent loses \d',),
    '身材/豆': (r'\+1/\+1 counter|gets \+\d/\+\d until end of turn',),
    '飞行/穿透': (r'Flying|[Cc]an\'t be blocked|Menace',),
    '咒语连发': (r'[Ww]henever you cast (a noncreature|an instant|your (first|second|third)|a spell)|Prowess|Flurry|Opus',),
    '进场触发': (r'[Ww]hen this creature enters|[Ww]hen .{0,20}enters the battlefield',),
    '坟场': (r'[Mm]ill \d|from your graveyard|put .{0,25}into your graveyard',),
    '地落': (r'[Ll]andfall|whenever a land you control enters',),
    '牺牲/死亡': (r'[Ss]acrifice (a|another|this|two) (creature|permanent|artifact)|creature you control dies',),
    '衍生物': (r'[Cc]reate .{0,40}token',),
    '去除': (r'[Dd]estroy target|exile target|-[X0-9]+/-[X0-9]+ until end of turn',),
    '抽牌/引擎': (r'[Dd]raw (a|two|three|X) card|whenever you draw',),
}


def scan(pair):
    P = pool(pair)
    rows = []
    for name, (pat,) in AXES.items():
        hits = []
        for n, e in P.items():
            if e['cmc'] > 3 or e['rarity'] in GOLD or not e['alive']:
                continue
            if re.search(pat, tx(e), re.I):
                hits.append((PLAY.get(n, {}).get('deck_pct', 0), n, e))
        hits.sort(reverse=True)
        rows.append((name, hits))
    return rows


def main():
    pairs = sys.argv[1:] or PAIRS
    for pair in pairs:
        rows = scan(pair)
        print('=' * 100)
        print('【%s】%s+%s  （池内牌名 %d）' % (pair, CN.get(pair[0]), CN.get(pair[1]), len(pool(pair))))
        print('=' * 100)
        print('%-12s %6s  %s' % ('轴线', '非金数', '代表牌（按环境入牌率）'))
        for name, hits in sorted(rows, key=lambda r: -len(r[1])):
            if not hits:
                continue
            top = '、'.join('%s%s' % (n, ('(%.0f%%)' % pct) if pct >= 1 else '') for pct, n, _ in hits[:5])
            print('%-12s %6d  %s' % (name, len(hits), top[:92]))
        print()


if __name__ == '__main__':
    main()
