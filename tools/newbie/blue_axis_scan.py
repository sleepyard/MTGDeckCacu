#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蓝池轴线三层重扫（盲测用）

先让数据说话：公平评估蓝色所有候选轴，**不预设"tempo"**。
特别关注用户观察到的信号：FRA《现实裂界》是否给蓝色补了异常强的单卡/轴。

用法: python3 blue_axis_scan.py
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

U = {n: e for n, e in M.items()
     if e['arena'] and not e['basic'] and set(e['ci']) <= {'U'}}


def tx(e):
    return (e['oracle'] or '') + ' ' + ' '.join(f['oracle_text'] for f in (e['faces'] or []))


def cnt(pat, cmc=3, nongold=True, alive=True):
    if pat == r'—':
        return []
    out = []
    for n, e in U.items():
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
    '① 咒语连发 Spells': dict(
        L1=r'[Ww]henever you cast a noncreature|Prowess|Flurry|Opus',
        L2=r'copy (this spell|that spell)|copies of that spell',
        L3=r'[Ww]henever you cast .{0,40}(draw|deal|create|copy|put)'),
    '② 坟场/磨牌 Graveyard-Mill': dict(
        L1=r'[Mm]ill \d|put .{0,25}into your graveyard',
        L2=r'for each .{0,30}card in your graveyard|cards? in your graveyard.{0,25}(instead|twice)',
        L3=r'(return|put) .{0,40}from your graveyard|[Ww]henever .{0,25}mill'),
    '③ 减费/大法术 Ramp': dict(
        L1=r'costs? \{.{1,3}\} less|add \{U\}|search your library for a (basic )?(Island|land)',
        L2=r'costs? \{.{1,3}\} less|add .{0,10}additional',
        L3=r'costs? \{.{1,3}\} less'),
    '④ 弹回/干扰 Tempo-bounce': dict(
        L1=r'[Rr]eturn .{0,30}to (its|their) owner\'s hand|[Cc]ounter target spell|[Tt]ap target creature',
        L2=r'[Rr]eturn .{0,20}(two|up to two) .{0,20}hand',
        L3=r'[Ww]henever (a|an|one or more) .{0,35}(return|leaves the battlefield)'),
    '⑤ 飞行/穿透 Evasion': dict(
        L1=r'[Ff]lying|[Cc]an\'t be blocked',
        L2=r'creatures? with flying you control get|creatures? you control with flying',
        L3=r'[Ww]henever .{0,35}with flying'),
    '⑥ 神器 Artifacts': dict(
        L1=r'[Aa]rtifact',
        L2=r'artifact spells? .{0,25}cost|copy .{0,20}artifact',
        L3=r'[Ww]henever an? (nontoken )?artifact'),
    '⑦ +1/+1 豆 Counters': dict(
        L1=r'\+1/\+1 counter',
        L2=r'twice that many \+1/\+1|additional \+1/\+1 counter',
        L3=r'[Ww]henever you put one or more \+1/\+1|creature you control with a \+1/\+1 counter'),
    '⑧ 刺探/选择 Surveil-Scry': dict(
        L1=r'[Ss]urveil|[Ss]cry|look at the top',
        L2=r'[Ss]urveil \d|[Ss]cry \d',
        L3=r'[Ww]henever you (surveil|scry)'),
}

FRA_SIGNALS = [
    (r'[Rr]eturn .{0,40}to (its|their) owner\'s hand', '弹回'),
    (r'[Cc]ounter target spell', '反击'),
    (r'costs? \{.{1,3}\} less', '减费'),
    (r'copy (this spell|that spell)', '复制咒语'),
    (r'[Ff]lying', '飞行'),
    (r'[Ss]urveil', '刺探'),
    (r'[Ww]henever you cast', '施放触发'),
]


def main():
    print('=' * 108)
    print('蓝池轴线三层重扫（非金 / cmc<=3 / 轮替存活）—— 不预设 tempo')
    print('蓝池可用牌名：%d' % len(U))
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
                          for _, n, _ in sorted(lst, key=lambda x: -PLAY.get(x[1], {}).get('deck_pct', 0))[:8])
            print('   %s: %s' % (lab, s))
        print()

    print('=' * 108)
    print('★ 用户提到的「FRA 危险单卡」核查：蓝色各机制在 FRA 里有什么')
    print('=' * 108)
    fra = {n: e for n, e in U.items() if any(p['set'] == 'fra' for p in e['prints'])}
    print('蓝池中 FRA 印刷的牌：%d 张' % len(fra))
    for pat, lab in FRA_SIGNALS:
        hits = [(e['cmc'], e['rarity'], n, e) for n, e in fra.items() if re.search(pat, tx(e), re.I)]
        hits.sort(key=lambda x: (x[1] in ('common', 'uncommon'), x[0]))
        if not hits:
            continue
        print()
        print('  [%s] FRA 蓝牌 %d 张' % (lab, len(hits)))
        for c, r, n, e in hits[:6]:
            tag = '★金' if r in ('rare', 'mythic') else '非金'
            print('     %-30s %-5s %-4s %s' % (n[:30], tag, c, (e['oracle'] or '').replace('\n', ' | ')[:66]))


if __name__ == '__main__':
    main()
