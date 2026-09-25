#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""地牌分析：按「能产的色组 × 野卡成本 × 轮替存活」分类，服务双色套牌的地源决策。

★ 纯 MTGA 口径：野卡成本看 arena_rarity（rare/mythic 才消耗野卡），基本地免费。
输出 data/land_report.md + 屏幕摘要。
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json, os, re, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, '..', 'data'))
M = json.load(open(os.path.join(DATA, 'rarity_map.json'), encoding='utf-8'))
WUBRG = ['W', 'U', 'B', 'R', 'G']
PAIRS = ['WU', 'UB', 'BR', 'RG', 'GW', 'WB', 'UR', 'BG', 'RW', 'GU']


def colors_of(txt):
    """返回该地能产出的颜色集合 + 是否任意色 + 是否无色专用。"""
    cols, anyc = set(), False
    for line in re.split(r'[\n.]', txt or ''):
        if 'Add' not in line:
            continue
        seg = line[line.index('Add'):]
        seg = seg.split('|')[0]
        if 'any color' in seg or 'any one color' in seg:
            anyc = True
        cols |= set(re.findall(r'\{([WUBRG])\}', seg))
    return cols, anyc


def land_kind(e):
    """判定进场是否横置 / 有无条件。"""
    t = e['oracle'] or ''
    if e['basic']:
        return '基本地'
    if re.search(r'enters (the battlefield )?tapped(?! unless)', t):
        return '横置进场'
    if 'unless' in t and 'tapped' in t:
        return '有条件(否则横置)'
    return '不横置'


def collect():
    out = []
    for n, e in M.items():
        if not e['arena']:
            continue
        if 'Land' not in (e['type_line'] or ''):
            continue
        if '//' in n:
            continue
        txt = (e['oracle'] or '') + '\n' + '\n'.join(f['oracle_text'] for f in (e['faces'] or []))
        cols, anyc = colors_of(txt)
        if not cols and not anyc:
            continue
        out.append({'name': n, 'rarity': e['rarity'], 'wc': e['wildcard'], 'alive': e['alive'],
                    'std': ','.join(e['std_sets']), 'print': e['arena_print'], 'basic': e['basic'],
                    'cols': sorted(cols), 'any': anyc, 'kind': land_kind(e), 'ci': ''.join(sorted(e['ci'])),
                    'txt': (e['oracle'] or '').replace('\n', ' | ')[:110]})
    return out


def main():
    lands = collect()
    L = []
    P = L.append
    P('# 标准牌池地牌分析（纯 MTGA 口径 · 2026-09-24）\n')
    P('> 野卡成本：rare/mythic 各计 1 张野卡；common/uncommon 不占稀有野卡；**基本地免费**。')
    P('> 轮替存活：2027-02-02 后是否仍有合法的非数字标准扩展印刷（与 `rot_audit.py` 同源）。\n')

    # ---- 一、各色组的双色地供应
    P('## 一、各色组双色地供应（金 vs 非金 × 存活 vs 将退）\n')
    P('| 色组 | 双色金地(存活) | 双色金地(将退) | 非金调色地 | 任意色非金地 |')
    P('|---|---|---|---|---|')
    for pair in PAIRS:
        a = [x for x in lands if x['wc'] and pair in pair and set(x['cols']) == set(pair) and x['alive']]
        b = [x for x in lands if x['wc'] and set(x['cols']) == set(pair) and not x['alive']]
        c = [x for x in lands if not x['wc'] and set(x['cols']) == set(pair)]
        s = lambda xs: '、'.join('%s(%s)' % (x['name'], x['print']) for x in xs) or '—'
        P('| %s | %s | %s | %s | |' % (pair, s(a), s(b), s(c)))
    P('')

    # ---- 二、任意色非金地
    P('## 二、任意色 / 无色辅助地（common-uncommon，不占稀有野卡）\n')
    P('| 牌名 | 稀有度 | 进场 | 存活 | 文本 |')
    P('|---|---|---|---|---|')
    for x in sorted([x for x in lands if x['any'] and not x['wc']], key=lambda x: (not x['alive'], x['rarity'])):
        P('| %s | %s | %s | %s | %s |' % (x['name'], x['rarity'], x['kind'], '✓' if x['alive'] else '✗', x['txt'][:90]))
    P('')

    # ---- 三、全部耗野卡的地（按存活排序）
    P('## 三、消耗稀有野卡的地牌（生存者优先）\n')
    P('| 牌名 | 稀有度 | 印刷 | 产色 | 进场 | 存活 | 标准系列 |')
    P('|---|---|---|---|---|---|---|')
    for x in sorted([x for x in lands if x['wc']], key=lambda x: (not x['alive'], x['name'])):
        P('| %s | %s | %s | %s | %s | %s | %s |' % (x['name'], x['rarity'], x['print'],
          '/'.join(x['cols']) or ('任意色' if x['any'] else '无色'), x['kind'], '✓' if x['alive'] else '✗', x['std']))
    P('')

    # ---- 四、无色功能地
    P('## 四、无色功能地（不产有色法力，供参考）\n')
    fun = [x for x in lands if not x['cols'] and not x['any']]
    P('数量 %d；存活 %d' % (len(fun), sum(1 for x in fun if x['alive'])))
    P('')

    txt = '\n'.join(L)
    open(os.path.join(DATA, 'land_report.md'), 'w', encoding='utf-8').write(txt)
    print(txt[:6000])
    print('\n[写入 data/land_report.md]')


if __name__ == '__main__':
    main()
