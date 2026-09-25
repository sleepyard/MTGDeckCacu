#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盲测：单红「燃烧」金鱼模拟器（重写版 · 建模清单仅来自 red_enum.py 的枚举结果）

★ 本文件按《盲测协议》重写，用于替代被污染的 sim_red.py。
   建模清单的每一张牌都可追溯到本次枚举输出（见 red_enum.py 的角色清单）。

轴的语义（三层链路）：
  L1 燃料 = 廉价烧（产生"伤害事件"）与廉价生物（产生战斗打点）
  L2 增幅 = 把**单个伤害事件**放大（Tomik +1 / Barbs 群膨胀 / Rollercrusher 翻倍）
  L3 回报 = 把"施放咒语"转成打点或身材（Firebrand Archer / Guttersnipe / Firedancer…）

建模规范：
  · 非战斗 vs 战斗**两条通道**；保守口径只缩放战斗通道
  · 非战斗伤害统一入口 nc()：先过 Tomik 的 "+1 替换效应"，再触发 Master of Barbs
  · 传说牌同名只能有 1 张在场
  · 敏捷（haste）当回合可攻击；其余生物与衍生物有召唤失调
  · 临时膨胀（until end of turn）每回合开始清零

用法: python3 sim_red_blind.py <局数> <牌表文件>
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import os, random, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mtga_cost import parse_deck

# kind: S=非生物咒语 C=生物
POOL = {
    # ── L1 燃料：廉价烧 ──
    'Shock':                dict(k='S', c=1, burn=2),
    'Burst Lightning':      dict(k='S', c=1, burn=2),
    'Boltwave':             dict(k='S', c=1, burn=3),
    'Channeled Dragonfire': dict(k='S', c=1, burn=2),
    'Plasma Bolt':          dict(k='S', c=1, burn=2),
    'Lightning Strike':     dict(k='S', c=2, burn=3),
    'Ancestral Anger':      dict(k='S', c=1, pump=1, draw=1),
    'Playful Shove':        dict(k='S', c=2, burn=1, draw=1),
    # ── L1 燃料：廉价生物 ──
    'Fleeting Effigy':      dict(k='C', c=1, p=2, d=2, haste=1, effigy=1),
    'Ghitu Lavarunner':     dict(k='C', c=1, p=1, d=2, lavarunner=1),
    'Fanatical Firebrand':  dict(k='C', c=1, p=1, d=1, haste=1),
    'Embereth Veteran':     dict(k='C', c=1, p=2, d=1),
    'Viashino Pyromancer':  dict(k='C', c=2, p=2, d=1, etb_ping=2),
    'Stromkirk Noble':      dict(k='C', c=1, p=1, d=1, grow_combat=1),
    # ── L3 回报：每张咒语 → 打点/身材 ──
    'Firebrand Archer':     dict(k='C', c=2, p=2, d=1, per_noncreature=1),
    'Thunderdrum Soloist':  dict(k='C', c=2, p=1, d=3, per_instant=1),
    'Devoted Duelist':      dict(k='C', c=2, p=2, d=1, haste=1, flurry=1),
    'Guttersnipe':          dict(k='C', c=3, p=2, d=2, per_instant=2),
    'Expressive Firedancer': dict(k='C', c=2, p=2, d=2, temp_pump=1),
    'Molten-Core Maestro':  dict(k='C', c=2, p=2, d=2, perm_ctr=1),
    # ── L2 增幅 ──
    'Tomik, Izzet Sparkmage': dict(k='C', c=2, p=1, d=3, prowess=1, tomik=1, leg=1),
    'Master of Barbs':      dict(k='C', c=2, p=2, d=2, barbs=1),
    'The Rollercrusher Ride': dict(k='E', c=3, double_nc=1),
}
LAND = 'Mountain'


class Game:
    def __init__(self, deck, rng, pen=1.0):
        self.rng = rng
        self.pen = pen
        self.lib = deck[:]
        rng.shuffle(self.lib)
        self.hand = []
        self.lands = 0
        self.bf = []
        self.dmg = 0.0
        self.gy = 0
        self.spells = 0
        self.team_pump = 0
        self.turn = 0
        self.anger = 0
        self.opening()

    def opening(self):
        """★ 伦敦调度（修正版）：起手 7 张；每次调度**手牌数 -1**（7→6→5）"""
        self.draw(7)
        size = 7
        for _ in range(2):
            if 2 <= sum(1 for c in self.hand if c == 'Mountain') <= 5:
                return
            size -= 1
            self.lib += self.hand
            self.rng.shuffle(self.lib)
            self.hand = []
            self.draw(size)

    def draw(self, n=1):
        for _ in range(n):
            if self.lib:
                self.hand.append(self.lib.pop())

    def legends(self):
        return {b['n'] for b in self.bf if POOL[b['n']].get('leg')}

    def nc(self, amt):
        """非战斗伤害入口：Tomik(+1 替换) → 翻倍 → Master of Barbs 触发"""
        if amt <= 0:
            return
        if any(b['tags'].get('tomik') for b in self.bf):
            amt += 1
        if any(b['tags'].get('double_nc') for b in self.bf):
            amt *= 2
        self.dmg += amt
        nb = sum(1 for b in self.bf if b['tags'].get('barbs'))
        if nb:
            self.team_pump += nb

    def power(self, b):
        p = b['p'] + b.get('ctr', 0) + b.get('temp', 0)
        if b['tags'].get('lavarunner') and self.gy >= 2:
            p += 1
        return p + self.team_pump

    def on_spell(self, is_creature):
        """每张咒语施放后的触发结算（顺序：先增幅件自身的 prowess，再回报件）"""
        self.spells += 1
        for b in self.bf:
            t = b['tags']
            if t.get('prowess') and not is_creature:
                b['temp'] = b.get('temp', 0) + 1
            if t.get('temp_pump') and not is_creature:
                b['temp'] = b.get('temp', 0) + 1
            if t.get('perm_ctr') and not is_creature:
                b['ctr'] = b.get('ctr', 0) + 1
        if not is_creature:
            for b in self.bf:
                if b['tags'].get('per_noncreature'):
                    self.nc(b['tags']['per_noncreature'])
            for b in self.bf:
                if b['tags'].get('per_instant'):
                    self.nc(b['tags']['per_instant'])
        if self.spells == 2:
            for b in self.bf:
                if b['tags'].get('flurry'):
                    self.nc(1)

    def cast_spell(self, name):
        sp = POOL[name]
        self.hand.remove(name)
        self.on_spell(is_creature=False)
        if sp.get('burn'):
            self.nc(sp['burn'])
        if sp.get('pump'):
            self.anger += 1
            cre = [x for x in self.bf if x['p'] > 0]
            if cre:
                cre[0]['temp'] = cre[0].get('temp', 0) + self.anger
        if sp.get('draw'):
            self.draw(sp['draw'])
        self.gy += 1

    def cast_creature(self, name):
        sp = POOL[name]
        self.hand.remove(name)
        self.on_spell(is_creature=True)
        b = dict(n=name, p=sp.get('p', 0), d=sp.get('d', 0), tags=sp,
                 sick=0 if sp.get('haste') else 1, ctr=0, temp=0)
        self.bf.append(b)
        if sp.get('etb_ping'):
            self.nc(sp['etb_ping'])

    def cast_other(self, name):
        sp = POOL[name]
        self.hand.remove(name)
        self.on_spell(is_creature=False)
        self.bf.append(dict(n=name, p=0, d=0, tags=sp, sick=1, ctr=0, temp=0))

    def play_turn(self):
        self.turn += 1
        self.team_pump = 0
        self.spells = 0
        self.draw()
        if LAND in self.hand and self.lands < 12:
            self.hand.remove(LAND)
            self.lands += 1
        for b in self.bf:
            b['temp'] = 0
        mana = self.lands
        guard = 0
        while guard < 24:
            guard += 1
            leg = self.legends()
            opts = [n for n in set(self.hand)
                    if n != LAND and POOL[n]['c'] <= mana
                    and not (POOL[n].get('leg') and n in leg)]
            if not opts:
                break
            # 排序键带牌名做 tiebreaker（否则同费牌顺序受 hash 随机化影响 → 不可复现）
            opts.sort(key=lambda n: (-POOL[n]['c'], n))
            name = opts[0]
            mana -= POOL[name]['c']
            k = POOL[name]['k']
            if k == 'C':
                self.cast_creature(name)
            elif k == 'E':
                self.cast_other(name)
            else:
                self.cast_spell(name)
        # 战斗通道
        dmg = 0
        for b in self.bf:
            if b['sick']:
                b['sick'] = 0
                continue
            v = self.power(b)
            dmg += v * self.pen
        self.dmg += dmg
        for b in self.bf:
            if b['tags'].get('grow_combat') and not b['sick']:
                b['ctr'] = b.get('ctr', 0) + 1
        return self.dmg >= 20


def load_deck(path):
    main, _ = parse_deck(path)
    deck = []
    for q, name in main:
        deck += [LAND] * q if name.startswith('Mountain') else [name] * q
    return deck


def run(deck, n, max_turn=12, pen=1.0):
    rng = random.Random(20260924)
    kills, stuck = [], 0
    for _ in range(n):
        g = Game(deck, rng, pen)
        k = None
        for t in range(1, max_turn + 1):
            if g.play_turn():
                k = t
                break
        kills.append(k or max_turn + 1)
        if g.lands <= 2:
            stuck += 1
    kills.sort()
    m = len(kills)
    return dict(mean=sum(kills) / m,
                t4=100.0 * sum(1 for x in kills if x <= 4) / m,
                t5=100.0 * sum(1 for x in kills if x <= 5) / m,
                stuck=100.0 * stuck / m)



def resolve_deck_path(f):
    """★ 迁移友好：依次尝试 绝对路径 / 当前目录 / tools 目录"""
    if os.path.isabs(f):
        return f
    cands = [f, os.path.join(os.getcwd(), f), os.path.join(HERE, f),
             os.path.join(os.path.dirname(HERE), f)]
    for c in cands:
        if os.path.exists(c):
            return c
    return f

if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    f = sys.argv[2] if len(sys.argv) > 2 else 'deck_mono_red_blind.txt'
    deck = load_deck(resolve_deck_path(f))
    r = run(deck, n)
    rc = run(deck, n, pen=0.6)
    print('%-26s N=%-6d 公平 均杀 %.2f T4 %5.1f%% | 保守 均杀 %.2f T4 %5.1f%% | 卡地 %.1f%%'
          % (os.path.basename(f), n, r['mean'], r['t4'], rc['mean'], rc['t4'], r['stuck']))
