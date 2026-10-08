#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""红池轴线三层重扫（盲测用 · 不依赖任何前作）

公平评估红色所有候选轴，每条轴测 L1使能 / L2增幅 / L3回报（非金、cmc≤3）。
★ 与前次不同：本次**逐条轴给出实例**，接受数据推翻"燃烧轴"的可能。

用法: python3 red_axis_scan.py
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

R = {n: e for n, e in M.items()
     if e['arena'] and not e['basic'] and set(e['ci']) <= {'R'}}


def tx(e):
    return (e['oracle'] or '') + ' ' + ' '.join(f['oracle_text'] for f in (e['faces'] or []))


# 每条轴的三层定义（红池专用，语义严格：L2 必须是"倍增/额外"，不是"产出"）
AXES = {
    '① 燃烧直伤 Burn': dict(
        L1=r'deals? \d+ damage to (any target|target|each opponent|target player)',
        L2=r'(would deal|deals?) .{0,30}damage.{0,30}(instead|plus \d|twice|double)|damage.{0,20}is doubled',
        L3=r'[Ww]henever (you cast|one or more opponents are dealt)',
        note='资源=伤害事件；L2=伤害放大；L3=施放触发额外伤害/pump'),
    '② 造兵+进场打点 Tokens': dict(
        L1=r'[Cc]reate .{0,40}(token|tokens)',
        L2=r'twice that many|double the number of tokens|create twice',
        L3=r'[Ww]henever (a|another|one or more) (creature|token|nontoken) .{0,35}enter',
        note='资源=进场事件；L2=翻倍；L3=进场打点'),
    '③ 牺牲/贵族 Sacrifice': dict(
        L1=r'[Ss]acrifice (a|another|this|two) (creature|permanent|artifact)',
        L2=r'twice that many|instead of sacrificing|sacrificed.{0,30}instead',
        L3=r'[Ww]henever you sacrifice|[Ww]henever (a|another) creature you control dies',
        note='资源=死亡事件；L2=替代效应；L3=死亡回报'),
    '④ 神器 Artifacts': dict(
        L1=r'[Aa]rtifact',
        L2=r'artifact spells? .{0,25}cost|artifacts? you control .{0,25}(additional|twice)|copy .{0,20}artifact',
        L3=r'[Ww]henever an? (nontoken )?artifact',
        note='资源=神器进场；L2=减费/复制；L3=神器进场回报'),
    '⑤ 弃牌 Discard': dict(
        L1=r'[Dd]iscard (a|two|your|one or more|\d)',
        L2=r'discard.{0,25}(twice|two cards instead|that many)',
        L3=r'[Ww]henever you discard|[Ii]f you discard',
        note='资源=弃牌；L2=额外弃牌/替代；L3=弃牌回报'),
    '⑥ 地落 Landfall': dict(
        L1=r'[Ll]andfall|whenever a land you control enters',
        L2=r'play (an|two) additional land|additional land on each',
        L3=r'[Ll]andfall.{0,60}(draw|create|deal|\+1/\+1|put|target)',
        note='资源=地进场；L2=额外下地；L3=地落回报'),
    '⑦ +1/+1 豆 Counters': dict(
        L1=r'\+1/\+1 counter',
        L2=r'twice that many \+1/\+1|additional \+1/\+1 counter|double the number of \+1/\+1',
        L3=r'[Ww]henever you put one or more \+1/\+1|creature you control with a \+1/\+1 counter',
        note='资源=豆；L2=加倍；L3=豆回报'),
    '⑧ 力量缩放 Power': dict(
        L1=r'gets \+\d/\+\d|\+1/\+1 counter',
        L2=r'double (its|their|the) power|power .{0,15}doubled|twice .{0,15}power',
        L3=r'power 4 or greater|with power \d+ or greater|greatest power',
        note='资源=力量；L2=翻倍；L3=高力量回报'),
    '⑨ 坟场 Graveyard': dict(
        L1=r'[Mm]ill \d|put .{0,25}into your graveyard|from your graveyard',
        L2=r'cards? in your graveyard.{0,25}(instead|twice)|for each .{0,25}card in your graveyard',
        L3=r'(return|put) .{0,40}from your graveyard|[Ww]henever .{0,25}card.{0,20}graveyard',
        note='资源=坟场张数；L2=缩放；L3=返场/回收'),
    '⑩ 敏捷节奏 Haste tempo': dict(
        L1=r'\bHaste\b',
        L2=r'—',
        L3=r'—',
        note='纯节奏：无 L2/L3（对照项，验证"不是所有轴都要三层"）'),
}


def cnt(pool, pat, cmc=3, nongold=True):
    if pat == r'—':
        return []
    out = []
    for n, e in pool.items():
        if e['cmc'] > cmc:
            continue
        if nongold and e['rarity'] in GOLD:
            continue
        if re.search(pat, tx(e), re.I):
            out.append((e['cmc'], n, e))
    out.sort()
    return out


def main():
    print('=' * 104)
    print('红池轴线三层重扫（非金 / cmc≤3 / 公平评估所有候选轴）')
    print('池内红色可用牌名：%d' % len(R))
    print('=' * 104)
    print('%-22s %8s %8s %8s   %-12s %s' % ('轴线', 'L1使能', 'L2增幅', 'L3回报', '判定', '说明'))
    print('-' * 104)
    rows = []
    for name, d in AXES.items():
        l1, l2, l3 = cnt(R, d['L1']), cnt(R, d['L2']), cnt(R, d['L3'])
        complete = len(l1) >= 6 and len(l2) >= 2 and len(l3) >= 3
        if d['L2'] == r'—':
            verdict = '对照（无三层）'
        elif complete:
            verdict = '★★ 三层齐备'
        elif len(l1) >= 6 and len(l3) >= 3:
            verdict = '◇ 缺 L2'
        else:
            verdict = '✗ 散件'
        rows.append((name, l1, l2, l3, verdict, d['note']))
        print('%-22s %8d %8d %8d   %-12s %s' % (name, len(l1), len(l2), len(l3), verdict, d['note'][:26]))
    print()
    print('=' * 104)
    print('各轴三层实例（按真实环境入牌率排序，帮助判断"哪些牌真的在用"）')
    print('=' * 104)
    for name, l1, l2, l3, verdict, note in rows:
        if verdict == '对照（无三层）':
            continue
        print()
        print('【%s】%s' % (name, verdict))
        for lab, lst in (('L1', l1), ('L2', l2), ('L3', l3)):
            if not lst:
                print('   %s: （无）' % lab)
                continue
            items = sorted(lst, key=lambda x: -PLAY.get(x[1], {}).get('deck_pct', 0))[:8]
            s = '、'.join('%s%s' % (n, ('(%.1f%%)' % PLAY[n]['deck_pct']) if n in PLAY and PLAY[n]['deck_pct'] >= 0.5 else '')
                          for _, n, _ in items)
            print('   %s: %s' % (lab, s))

    # Mobilize is an attack-time token axis, not a three-layer multiplier axis.
    # Keep it as a separate keyword pass so a Cavalcade-style shell cannot be
    # missed merely because it has no token-doubling payoff in the red pool.
    mobilize = cnt(R, r'\b[Mm]obilize\s+\d+', cmc=3, nongold=False)
    print()
    print('=' * 104)
    print('补充关键词轴：动员 Mobilize（攻击时生成当回合攻击衍生物）')
    print('=' * 104)
    if mobilize:
        for _, n, e in mobilize:
            alive = '存活' if e.get('alive') else '将退'
            print('   %-28s cmc=%-3g %-4s %s' % (n, e['cmc'], alive,
                  (tx(e).replace('\n', ' | ')[:120])))
    else:
        print('   （无红色候选）')


if __name__ == '__main__':
    main()
