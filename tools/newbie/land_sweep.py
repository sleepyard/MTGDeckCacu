#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""地数重扫（修正调度后）：对五副牌各扫 19-25 地，找出真实最优地数

关注两个指标：
  · 公平均杀（速度）
  · T2<2费 / T3<3费（卡地率，按套牌曲线的正确门槛）
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
NB = os.path.normpath(os.path.join(HERE, '..'))

JOBS = [
    ('单黑', 'mono_black/deck_mono_black.txt', 'sim_black.py', 'Swamp'),
    ('单白', 'mono_white/deck_mono_white.txt', 'sim_white.py', 'Plains'),
    ('单红', 'mono_red_blind/deck_mono_red_blind.txt', 'sim_red_blind.py', 'Mountain'),
    ('单蓝', 'mono_blue_v2/deck_mono_blue_v2.txt', 'sim_blue.py', 'Island'),
    ('单绿', 'mono_green/deck_mono_green.txt', 'sim_green.py', 'Forest'),
]


def make_variant(deckpath, land, nlands, out):
    lines = [l.strip() for l in open(deckpath, encoding='utf-8') if l.strip()]
    spells = [l for l in lines if not re.match(r'^\d+\s+%s$' % land, l)]
    # 保持总张数 = 60：地变多则按比例削减咒语（从数量 4 的牌里减）
    cur = sum(int(l.split(' ', 1)[0]) for l in spells)
    target = 60 - nlands
    delta = cur - target          # 需要削减的张数（正数=削减）
    out_lines = []
    if delta > 0:
        pool = sorted(spells, key=lambda l: -int(l.split(' ', 1)[0]))
        left = delta
        for l in pool:
            q, nm = l.split(' ', 1)
            if left > 0 and int(q) > 1:
                q2 = int(q) - 1
                left -= 1
                out_lines.append('%d %s' % (q2, nm))
            else:
                out_lines.append(l)
    elif delta < 0:
        pool = sorted(spells, key=lambda l: int(l.split(' ', 1)[0]))
        left = -delta
        for l in pool:
            q, nm = l.split(' ', 1)
            if left > 0:
                q2 = int(q) + 1
                left -= 1
                out_lines.append('%d %s' % (q2, nm))
            else:
                out_lines.append(l)
    else:
        out_lines = spells
    out_lines.append('%d %s' % (nlands, land))
    open(out, 'w', encoding='utf-8').write('\n'.join(out_lines) + '\n')
    return sum(int(l.split(' ', 1)[0]) for l in out_lines)


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    tmp = '/tmp/landsweep'
    os.makedirs(tmp, exist_ok=True)
    for label, deck, sim, land in JOBS:
        print('=' * 100)
        print('【%s】%s  （模拟器 %s）' % (label, os.path.basename(deck), sim))
        print('=' * 100)
        for L in range(19, 26):
            out = os.path.join(tmp, '%s_%d.txt' % (label, L))
            tot = make_variant(os.path.join(NB, deck), land, L, out)
            r = subprocess.run(['python3', os.path.join(HERE, sim), str(n), out],
                               capture_output=True, text=True)
            line = [x for x in r.stdout.strip().split('\n') if x.strip()]
            if not line:
                print('  地%-3d %d 张  ERROR: %s' % (L, tot, r.stderr.strip()[-80:]))
                continue
            print('  地%-3d %d 张  %s' % (L, tot, line[-1].split(None, 1)[-1]))
        print()
