#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修正所有模拟器的调度实现：伦敦调度必须减手牌（7→6→5）

此前实现：每次调度重抽 7 张 ⇒ 调度完全免费 ⇒ 所有地数与卡地率数据偏乐观。

⚠ 已废弃（一次性迁移脚本，使命完成）：Phase 3 起调度逻辑统一收敛在
  goldfish/engine.py 的 GameBase.opening（sim_red 亦已借此修复），
  sim_*.py 均为无 opening 定义的兼容 shim，本脚本再跑只会全部 no-match。
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ['sim_black.py', 'sim_red_blind.py', 'sim_green.py', 'sim_blue.py',
         'sim_blue_spells.py', 'sim_white.py']
LANDVAR = {'sim_black.py': 'Swamp', 'sim_red_blind.py': 'Mountain', 'sim_green.py': 'Forest',
           'sim_blue.py': 'Island', 'sim_blue_spells.py': 'Island', 'sim_white.py': 'LAND'}

NEW = '''    def opening(self):
        """★ 伦敦调度（修正版）：起手 7 张；每次调度**手牌数 -1**（7→6→5）"""
        self.draw(7)
        size = 7
        for _ in range(2):
            if 2 <= sum(1 for c in self.hand if c %s) <= 5:
                return
            size -= 1
            self.lib += self.hand
            self.rng.shuffle(self.lib)
            self.hand = []
            self.draw(size)
'''


def patch(fn):
    p = os.path.join(HERE, fn)
    if not os.path.exists(p):
        return 'missing'
    s = open(p, encoding='utf-8').read()
    if '★ 伦敦调度（修正版）' in s:
        return 'already'
    lv = LANDVAR[fn]
    if lv == 'LAND':
        cond = 'c == LAND'
    else:
        cond = "c == '%s'" % lv
    # 匹配现有的 opening 或 mulligan
    pat = re.compile(r'    def (opening|mulligan)\(self\):\n(?:.*\n)*?(?=\n    def )')
    m = pat.search(s)
    if not m:
        return 'no-match'
    body = NEW % cond
    s = s[:m.start()] + body + s[m.end():]
    open(p, 'w', encoding='utf-8').write(s)
    return 'patched'


if __name__ == '__main__':
    for f in FILES:
        print('%-24s %s' % (f, patch(f)))
