#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""轴线发现器（自上而下方法论的第一步）

方法论：**先测量牌池支持哪些轴线，再决定做哪套牌** —— 而不是先选牌型再找牌。

对每条轴线测量四个量：
  E 使能件(enabler)：产生该轴线资源/事件的牌
  P 回报件(payoff) ：把该轴线资源转换成胜势的牌
  **非金密度**      ：common+uncommon 的 E+P 数量（★「4 金」预算下最关键的指标）
  临界量           ：E≥4 且 P≥3 才算"池子撑得住"

用法: python3 axis_scan.py [色组] e.g. W / UB / all
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json, os, re, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, '..', 'data'))
M = json.load(open(os.path.join(DATA, 'rarity_map.json'), encoding='utf-8'))
GOLD = ('rare', 'mythic')

# 轴线定义：(名称, 使能件正则, 回报件正则, 说明)
AXES = [
    ('生命获得 Lifegain',
     r'you gain \d+ life|gains? \d+ life',
     r'[Ww]henever you gain life|if you (would )?gain life|gained \d+ or more life',
     '回血事件 → 放大器'),
    ('+1/+1 豆 Counters',
     r'\+1/\+1 counter',
     r'\+1/\+1 counters? on (each|it|target)|put a \+1/\+1 counter on each',
     '灌豆 → 身材放大'),
    ('衍生物/铺场 Tokens',
     r'[Cc]reate .{0,50}token',
     r'[Ww]henever (a|one or more) (creature )?token|tokens you control (get|have)|[Ww]henever another creature you control enters',
     '铺场 → 数量压制'),
    ('飞行/穿透 Evasion',
     r'[Ff]lying|[Cc]an\'t be blocked',
     r'[Ww]henever .*with flying|[Cc]reatures? with flying you control',
     '穿透 → 稳定打点'),
    ('系命 Lifelink',
     r'[Ll]ifelink|gains lifelink',
     r'[Ww]henever you gain life',
     '系命 = 攻击型回血源'),
    ('咒语连发 Spells',
     r'[Pp]rowess|whenever you cast (a|your) (second|third)|[Ff]lurry|magecraft',
     r'[Ww]henever you cast a noncreature|second spell each turn',
     '连咒 → 触发回报'),
    ('地落 Landfall',
     r'[Ll]andfall|whenever a land .*enters',
     r'[Ll]andfall|additional land',
     '放地 → 触发回报'),
    ('牺牲/贵族 Sacrifice',
     r'[Ss]acrifice (a|another|this) (creature|permanent)|[Ss]acrifice a creature',
     r'[Ww]henever you sacrifice|when .*dies',
     '牺牲 → 死亡回报'),
    ('坟场 Graveyard',
     r'[Ff]rom your graveyard|[Gg]raveyard',
     r'[Ff]rom your graveyard',
     '坟场 → 资源回收'),
    ('神器 Artifacts',
     r'[Aa]rtifact',
     r'[Aa]rtifacts you control|[Ww]henever an artifact',
     '神器 → 协同'),
    ('结界 Enchantments',
     r'[Ee]nchantment',
     r'[Ee]nchantments you control|[Ww]henever an enchantment',
     '结界 → 协同'),
    ('进场触发 ETB/Blink',
     r'[Ww]hen this creature enters|[Ww]hen .* enters',
     r'[Ee]xile .*return|[Bb]link',
     'ETB → 重复利用'),
    ('弃牌 Discard',
     r'[Dd]iscard',
     r'[Ww]henever .*discard|[Ii]f you discard',
     '弃牌 → 回报'),
    ('磨牌 Mill',
     r'[Mm]ill ',
     r'mills? .*cards',
     '磨牌 → 牌库耗尽'),
    ('能量 Energy',
     r'\{E\}|energy counter',
     r'energy counter',
     '能量 → 免费资源'),
    ('单体攻击 Alone',
     r'attacks alone',
     r'attacks alone',
     '单独攻击 → 回报'),
    ('减费/大兽 Ramp',
     r'costs? \{.{1,3}\} less|add \{.{1,4}\}|search your library for a (basic )?land',
     r'costs? \{.{1,3}\} less',
     '加速 → 抢先落地'),
]


def main():
    filt = sys.argv[1] if len(sys.argv) > 1 else 'all'
    def ok(e):
        if not e['arena'] or e['basic']:
            return False
        if filt == 'all':
            return True
        want = set(filt)
        return set(e['ci']) <= want           # 只保留色身份在该色组内的牌
    pool = {n: e for n, e in M.items() if ok(e)}
    print('色组筛选: %s | 池内牌名 %d' % (filt, len(pool)))
    print()
    rows = []
    for name, en_re, pa_re, note in AXES:
        en, pa = [], []
        for n, e in pool.items():
            t = (e['oracle'] or '') + ' ' + ' '.join(f['oracle_text'] for f in (e['faces'] or []))
            is_en = bool(re.search(en_re, t))
            is_pa = bool(re.search(pa_re, t))
            if is_en:
                en.append((n, e))
            if is_pa:
                pa.append((n, e))
        en_nongold = [x for x in en if x[1]['rarity'] not in GOLD]
        pa_nongold = [x for x in pa if x[1]['rarity'] not in GOLD]
        # 临界量判定
        viable = len(en_nongold) >= 4 and len(pa_nongold) >= 3
        rows.append(dict(name=name, note=note, e=len(en), p=len(pa),
                         eng=len(en_nongold), pg=len(pa_nongold),
                         viable=viable, en=en_nongold, pa=pa_nongold))
    rows.sort(key=lambda r: (-(r['eng'] + r['pg']), -(r['e'] + r['p'])))
    print('%-26s %5s %5s %7s %7s %8s  %s' % ('轴线', 'E', 'P', 'E(非金)', 'P(非金)', '非金合计', '判定'))
    print('-' * 100)
    for r in rows:
        mark = '✅ 池子撑得住' if r['viable'] else ('◇ 勉强' if r['eng'] + r['pg'] >= 5 else '✗ 太薄')
        print('%-26s %5d %5d %7d %7d %8d  %s'
              % (r['name'], r['e'], r['p'], r['eng'], r['pg'], r['eng'] + r['pg'], mark))
    print()
    print('=' * 100)
    print('★ Top 6 轴线的非金支撑牌（构成引擎的候选）')
    print('=' * 100)
    for r in rows[:6]:
        print()
        print('【%s】%s' % (r['name'], r['note']))
        print('  使能件(非金 %d): %s' % (len(r['en']), '、'.join(n for n, _ in r['en'][:10])))
        print('  回报件(非金 %d): %s' % (len(r['pa']), '、'.join(n for n, _ in r['pa'][:10])))


if __name__ == '__main__':
    main()
