#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盲测：按三层角色枚举红池候选（不读任何前作）

输出每个角色的完整候选清单（含 oracle 文本、稀有度、存活、环境入牌率），
供人工挑选。用途 = 盲测协议第 3 条「候选由枚举产生」。
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
R = {n: e for n, e in M.items() if e['arena'] and not e['basic'] and set(e['ci']) <= {'R'}}


def tx(e):
    return (e['oracle'] or '') + ' ' + ' '.join(f['oracle_text'] for f in (e['faces'] or []))


def dump(title, pat, cmc_max=3, gold=True, limit=40):
    rows = []
    for n, e in R.items():
        if e['cmc'] > cmc_max:
            continue
        if not gold and e['rarity'] in ('rare', 'mythic'):
            continue
        if re.search(pat, tx(e), re.I):
            rows.append((e['cmc'], e['rarity'], PLAY.get(n, {}).get('deck_pct', 0), n, e))
    rows.sort(key=lambda r: (r[0], -r[2]))
    print('=' * 120)
    print('%s   (%d 张, cmc<=%d%s)' % (title, len(rows), cmc_max, '' if gold else ', 仅非金'))
    print('=' * 120)
    for c, r, pct, n, e in rows[:limit]:
        tag = 'JG' if r in ('rare', 'mythic') else '  '
        alive = '' if e['alive'] else '将退'
        print('%-26s %-4s %-4s %-4s %-4s %5.1f%% %s' % (n[:26], tag, r[:4], c, alive, pct,
              (e['oracle'] or '').replace('\n', ' | ')[:62]))
    print()
    return rows


if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if what in ('all', 'l1'):
        dump('L1-a 廉价直伤 (cmc<=2)',
             r'deals? \d+ damage to (any target|target (player|opponent|creature or planeswalker)|each opponent)', 2, True)
    if what in ('all', 'cre'):
        dump('L1-b 红色 1-2 费生物 (需人工看身材/异能)',
             r'^', 2, True, limit=60)
    if what in ('all', 'l3'):
        dump('L3 每张咒语触发的回报件',
             r'[Ww]henever you cast (a|an|your|an instant|a noncreature|an instant or sorcery)|Prowess|Flurry|Opus', 3, True)
    if what in ('all', 'l2'):
        dump('L2 每个伤害实例 +N / 翻倍',
             r'deals? that much damage plus \d|would deal .{0,50}damage.{0,25}(twice|double)|noncombat damage.{0,60}(plus \d|instead)|opponents are dealt noncombat damage', 3, True, limit=20)
    if what in ('all', 'mobilize'):
        dump('关键词轴 动员 Mobilize（攻击时生成临时攻击衍生物）',
             r'\b[Mm]obilize\s+\d+', 3, True, limit=40)
