#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""轴线三层链路扫描（方法论 v2）

★ 用户补充的关键点：轴线**不能单打独斗**。一条轴线要强，必须三层能互相咬合：

    L1 使能件 (Enabler)   —— 产出轴线资源     "每次放地/每次回血/每造一个兵"
    L2 增幅件 (Amplifier) —— 把资源**倍增**     "改为两倍/额外一个/加倍"
    L3 响应奖励 (Payoff)  —— 把资源转成优势     "每当…则抓牌/灌豆/造成伤害"

判定：
    单层再厚也没用（散件）。
    真正的引擎 = L1 × L2 × L3 三层齐备，且**层与层引用同一个资源**（咬合）。
    ⇒ 每色每轴输出 (L1非金, L2非金, L3非金) 三元组，三层都≥阈值才算"可成引擎"。

用法: python3 axis_layers.py [颜色]     颜色 ∈ W/U/B/R/G/all
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, '..', 'data'))
M = json.load(open(os.path.join(DATA, 'rarity_map.json'), encoding='utf-8'))
GOLD = ('rare', 'mythic')
COLORS = ['W', 'U', 'B', 'R', 'G']

# 每条轴：L1 使能 / L2 增幅（真·倍增，排除系命这类"产出"）/ L3 响应奖励
AXES = {
    '生命获得': dict(
        en=r'you gain \d+ (or more )?life|gains? \d+ life',
        amp=r'gain (that much|twice|double) .{0,25}life|would gain life.{0,40}(instead|twice|double)|gain that much life plus|twice that much life',
        pa=r'[Ww]henever you gain life'),
    '+1/+1 豆': dict(
        en=r'\+1/\+1 counter',
        amp=r'twice that many \+1/\+1|double the number of \+1/\+1|additional \+1/\+1 counter|enters with (an additional|two) \+1/\+1',
        pa=r'[Ww]henever you put one or more \+1/\+1|[Ww]henever .{0,30}\+1/\+1 counter.{0,30}(draw|create|put)|creature you control with a \+1/\+1 counter'),
    '衍生物/铺场': dict(
        en=r'[Cc]reate .{0,40}token',
        amp=r'twice that many|double the number of tokens|create twice|those tokens.{0,20}instead',
        pa=r'[Ww]henever (a |one or more )?(creature )?tokens? .{0,35}(enter|attack)|tokens you control get \+'),
    '咒语连发': dict(
        en=r'[Pp]rowess|whenever you cast a noncreature|whenever you cast your (first|second|third)',
        amp=r'copy (this spell|that spell)|copies of that spell',
        pa=r'[Ww]henever you cast .{0,40}(copy|deal|draw|create|[Ww]henever you cast a noncreature)'),
    '地落': dict(
        en=r'[Ll]andfall|whenever a land you control enters',
        amp=r'play an additional land|two additional lands',
        pa=r'[Ll]andfall.{0,60}(draw|create|deal|\+1/\+1)'),
    '牺牲/贵族': dict(
        en=r'[Ss]acrifice (a|another|this|two) (creature|permanent|artifact)',
        amp=r'twice that many|sacrificed.{0,40}instead',
        pa=r'[Ww]henever you sacrifice|[Ww]henever (a|another) creature you control dies'),
    '坟场': dict(
        en=r'[Ff]rom your graveyard|[Mm]ill \d|put .{0,20}into your graveyard',
        amp=r'for each .{0,30}card in your graveyard|twice that many.{0,30}graveyard',
        pa=r'(return|put) .{0,40}from your graveyard|[Ww]henever .{0,30}card.{0,20}graveyard'),
    '系命': dict(
        en=r'[Ll]ifelink',
        amp=r'gains? lifelink.{0,30}(and|\+)|lifelink.{0,30}counters?',
        pa=r'[Ww]henever you gain life'),
    '减费/大兽': dict(
        en=r'costs? \{.{1,3}\} less|add \{.{1,4}\}|search your library for a (basic )?land',
        amp=r'costs? \{.{1,3}\} less|add .{0,10}additional',
        pa=r'costs? \{.{1,3}\} less'),
    '磨牌': dict(
        en=r'[Mm]ill (a|two|three|four|five|six|seven|X|\d)',
        amp=r'mill.{0,25}(twice|double|that many)',
        pa=r'[Ww]henever .{0,30}(mills|is put into .{0,15}graveyard)'),
    '弃牌': dict(
        en=r'[Dd]iscard (a|two|your)',
        amp=r'discard.{0,20}(twice|two|that many)',
        pa=r'[Ww]henever you discard|[Ii]f you discard'),
    '结界': dict(
        en=r'[Ee]nchantment',
        amp=r'each enchantment.{0,30}(additional|twice)|enchantment.{0,20}instead',
        pa=r'[Ww]henever an? enchantment|[Ee]nchantments you control'),
    '神器': dict(
        en=r'[Aa]rtifact',
        amp=r'each artifact.{0,30}(additional|twice)|artifacts? you control.{0,20}(instead|twice)',
        pa=r'[Ww]henever an? artifact|[Aa]rtifacts you control'),
}


def cards_for(color):
    if color == 'all':
        return {n: e for n, e in M.items() if e['arena'] and not e['basic']}
    return {n: e for n, e in M.items()
            if e['arena'] and not e['basic'] and set(e['ci']) <= {color}}


def text_of(e):
    return (e['oracle'] or '') + ' ' + ' '.join(f['oracle_text'] for f in (e['faces'] or []))


def count(pool, pat, cmc_max=3, nongold=True):
    hits = []
    for n, e in pool.items():
        if e['cmc'] > cmc_max:
            continue
        if nongold and e['rarity'] in GOLD:
            continue
        if re.search(pat, text_of(e), re.I):
            hits.append((e['cmc'], n, e))
    hits.sort()
    return hits


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else 'all'
    cols = COLORS if target == 'all' else [target]
    for c in cols:
        pool = cards_for(c)
        print('=' * 96)
        print('【%s 色】三层链路矩阵（cmc≤3、非金；三层齐备才算"可成引擎"）' % c)
        print('=' * 96)
        print('%-14s %8s %8s %8s   %s' % ('轴线', 'L1使能', 'L2增幅', 'L3回报', '判定'))
        print('-' * 96)
        rows = []
        for name, d in AXES.items():
            l1 = count(pool, d['en'])
            l2 = count(pool, d['amp'])
            l3 = count(pool, d['pa'])
            ok = len(l1) >= 6 and len(l2) >= 2 and len(l3) >= 3
            rows.append((ok, len(l1), len(l2), len(l3), name, l1, l2, l3))
        rows.sort(key=lambda r: (-int(r[0]), -(r[1] + r[2] * 3 + r[3] * 3)))
        for ok, n1, n2, n3, name, l1, l2, l3 in rows:
            mark = '★★ 三层齐备' if ok else ('◇ 缺层' if (n1 and n3) else '✗ 散件')
            print('%-14s %8d %8d %8d   %s' % (name, n1, n2, n3, mark))
        print()
        # 打印最强轴的实例
        best = [r for r in rows if r[0]][:2]
        for ok, n1, n2, n3, name, l1, l2, l3 in best:
            print('  ┌─ 【%s】三层实例' % name)
            print('  │ L1 使能: %s' % '、'.join(n for _, n, _ in l1[:5]))
            print('  │ L2 增幅: %s' % ('、'.join(n for _, n, _ in l2[:4]) or '（无）'))
            print('  │ L3 回报: %s' % '、'.join(n for _, n, _ in l3[:5]))
            print('  └─')
        print()


if __name__ == '__main__':
    main()
