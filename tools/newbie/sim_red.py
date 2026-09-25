#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标准「单红」金鱼模拟器（BO1 口径 · 牌表驱动）

轴线：**咒语连发 / 燃烧** —— 三层链路
  L1 使能：廉价烧 + 廉价敏捷生物
  L2 增幅：Tomik（每个非战斗伤害事件 +1，非金）、Master of Barbs（非战斗伤害→全队+1/+0）
  L3 回报：Firebrand Archer / Thunderdrum Soloist / Devoted Duelist / Guttersnipe（每张咒语打点）
  咬合点：Firebrand Archer 触发 1 点 → Tomik 放大为 2 点

建模规范（沿用 rdw_v4.py 的历史修正）：
  · 战斗伤害与非战斗伤害**分开通道**；保守口径只缩放战斗通道
  · 非战斗伤害统一入口 nc()：先过 Tomik 的"+1 替换效应"，再触发 Master of Barbs
  · 敏捷（haste）当回合即可攻击；衍生物/普通生物有召唤失调
  · Ancestral Anger：+X/+0 践踏 + 抓一张（续航）
  · 金鱼盲区：去除、弃牌、对手阻挡、Plot/节奏 —— 报告单列

用法: python3 sim_red.py <局数> <牌表文件>
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import os, random, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mtga_cost import parse_deck

# kind: C=生物 S=法术/瞬间
POOL = {
    # ── L1 燃料：廉价烧 ──
    'Shock':              dict(k='S', c=1, burn=2),
    'Burst Lightning':    dict(k='S', c=1, burn=2),
    'Boltwave':           dict(k='S', c=1, burn=3),
    'Lightning Strike':   dict(k='S', c=2, burn=3),
    'Ancestral Anger':    dict(k='S', c=1, pump=1, draw=1),
    'Playful Shove':      dict(k='S', c=2, burn=1, draw=1),
    'Scorching Dragonfire': dict(k='S', c=2, burn=0),   # 只打生物 ⇒ 金鱼 0
    # ── L3 回报：每张咒语打点 ──
    'Firebrand Archer':   dict(k='C', c=2, p=2, d=1, archetype=1),
    'Thunderdrum Soloist': dict(k='C', c=2, p=1, d=3, opus_dmg=1),
    'Devoted Duelist':    dict(k='C', c=2, p=2, d=2, haste=1, flurry=1),
    'Guttersnipe':        dict(k='C', c=3, p=2, d=2, guttersnipe=2),
    'Expressive Firedancer': dict(k='C', c=2, p=2, d=2, opus_pump=1),
    # ── L2 增幅 ──
    'Tomik, Izzet Sparkmage': dict(k='C', c=2, p=1, d=3, prowess=1, tomik=1),
    'Master of Barbs':    dict(k='C', c=2, p=2, d=2, barbs=1),
    'Molten-Core Maestro': dict(k='C', c=2, p=2, d=2, opus_ctr=1),
    # ── 曲线 / 压制 ──
    'Stromkirk Noble':    dict(k='C', c=1, p=1, d=1, grow_combat=1),
    'Ghitu Lavarunner':   dict(k='C', c=1, p=1, d=2, lavarunner=1),
    'Fanatical Firebrand': dict(k='C', c=1, p=1, d=1, haste=1),
    'Fleeting Effigy':    dict(k='C', c=1, p=2, d=2, haste=1),
    'Viashino Pyromancer': dict(k='C', c=2, p=2, d=1, etb_ping=2),
    'Shocking Sharpshooter': dict(k='C', c=2, p=1, d=3, ally_ping=1),
    'Hired Claw':         dict(k='C', c=1, p=1, d=1, atk_ping=1),
    'Slickshot Show-Off': dict(k='C', c=2, p=1, d=2, haste=1, flying=1, pump2=2),
    'Emberheart Challenger': dict(k='C', c=2, p=2, d=2, haste=1, prowess=1),
    'Prowcatcher Specialist': dict(k='C', c=2, p=1, d=2, haste=1),
    'Swab Goblin':        dict(k='C', c=2, p=2, d=2),
    'Emeritus of Conflict': dict(k='C', c=2, p=2, d=2, first_strike=1, emeritus=1),
}
LAND = 'Mountain'


class Game:
    def __init__(self, deck, rng, penetrate=1.0):
        self.rng = rng
        self.pen = penetrate
        self.lib = deck[:]
        rng.shuffle(self.lib)
        self.hand = []
        self.lands = 0
        self.bf = []          # dict(n,p,d,tags,sick,ctr)
        self.dmg = 0.0
        self.gy_spell = 0
        self.spells = 0
        self.team_pump = 0    # Master of Barbs：本回合全队 +X/+0（临时）
        self.turn = 0
        self.anger = 0
        self.opening()

    def opening(self):
        self.draw(7)
        for _ in range(2):
            if 2 <= sum(1 for c in self.hand if c == LAND) <= 5:
                return
            self.lib += self.hand
            self.rng.shuffle(self.lib)
            self.hand = []
            self.draw(7)

    def draw(self, n=1):
        for _ in range(n):
            if self.lib:
                self.hand.append(self.lib.pop())

    # ---- 伤害入口 ----
    def nc(self, amt):
        """非战斗伤害：先过 Tomik(+1 替换)，再过 Master of Barbs(全队+1/+0 触发)"""
        if amt <= 0:
            return
        if any(b['tags'].get('tomik') for b in self.bf):
            amt += 1
        self.dmg += amt
        nb = sum(1 for b in self.bf if b['tags'].get('barbs'))
        if nb:
            self.team_pump += nb

    def emeritus_ready(self):
        return any(b['tags'].get('emeritus') for b in self.bf)

    def power_of(self, b):
        p = b['p'] + b.get('ctr', 0) + b.get('temp', 0)
        if b['tags'].get('lavarunner') and self.gy_spell >= 2:
            p += 1
        return p + self.team_pump

    # ---- 施放 ----
    def cast_spell(self, name):
        sp = POOL[name]
        self.hand.remove(name)
        self.spells += 1
        # 咒语触发（顺序：施放 → 各回报件）
        for b in self.bf:
            t = b['tags']
            if t.get('prowess'):
                b['temp'] = b.get('temp', 0) + 1
            if t.get('opus_pump'):
                b['temp'] = b.get('temp', 0) + 1
            if t.get('opus_ctr'):
                b['ctr'] = b.get('ctr', 0) + 1
            if t.get('pump2'):
                b['temp'] = b.get('temp', 0) + 2
        # Firebrand Archer：每张非生物咒语（本模拟里除生物外都是非生物）
        for b in self.bf:
            if b['tags'].get('archetype'):
                self.nc(1)
        for b in self.bf:
            if b['tags'].get('opus_dmg'):
                self.nc(1)
            if b['tags'].get('guttersnipe'):
                self.nc(b['tags']['guttersnipe'])
        # Emeritus：本回合第 3 张咒语 → 备法 → 免费闪电击（3 点）
        if self.spells == 3 and self.emeritus_ready():
            self.nc(3)
        # Flurry：本回合第 2 张咒语
        if self.spells == 2:
            for b in self.bf:
                if b['tags'].get('flurry'):
                    self.nc(1)
        # 咒语本体效果
        if sp.get('burn'):
            self.nc(sp['burn'])
        if sp.get('pump'):
            self.anger += 1
            cre = [x for x in self.bf if x['p'] > 0]
            if cre:
                cre[0]['temp'] = cre[0].get('temp', 0) + self.anger
        if sp.get('draw'):
            self.draw(sp['draw'])
        self.gy_spell += 1

    def cast_creature(self, name):
        sp = POOL[name]
        self.hand.remove(name)
        self.spells += 1
        b = dict(n=name, p=sp.get('p', 0), d=sp.get('d', 0), tags=sp,
                 sick=0 if sp.get('haste') else 1, ctr=0, temp=0)
        # 生物咒语也会触发"非生物咒语"类异能？不会 —— 这里只保留"施放咒语"通用触发
        for x in self.bf:
            x2 = x['tags']
            if x2.get('prowess'):
                x2 = None  # prowess 只认非生物咒语
        self.bf.append(b)
        if sp.get('etb_ping'):
            self.nc(sp['etb_ping'])
        if sp.get('ally_ping'):
            n = sum(1 for x in self.bf if x['tags'].get('ally_ping')) - 1
            for _ in range(max(0, n)):
                self.nc(1)

    # ---- 回合 ----
    def play_turn(self):
        self.turn += 1
        self.team_pump = 0
        self.spells = 0
        self.draw()
        if LAND in self.hand and self.lands < 12:
            self.hand.remove(LAND)
            self.lands += 1
        # 本回合结束步骤：清除临时膨胀
        for b in self.bf:
            b['temp'] = 0
        mana = self.lands
        # 贪心施放：优先最高费用（战斗前把法力用光）
        guard = 0
        while guard < 20:
            guard += 1
            opts = sorted({n for n in self.hand if n != LAND and POOL[n]['c'] <= mana},
                          key=lambda n: (-POOL[n]['c'], n))
            if not opts:
                break
            name = opts[0]
            mana -= POOL[name]['c']
            if POOL[name]['k'] == 'C':
                self.cast_creature(name)
            else:
                self.cast_spell(name)
        # 战斗
        dmg = 0
        for b in self.bf:
            if b['sick']:
                b['sick'] = 0
                continue
            v = self.power_of(b)
            dmg += v if b['tags'].get('flying') else v * self.pen
        self.dmg += dmg
        # 攻击触发的非战斗伤害
        for b in self.bf:
            if b['tags'].get('atk_ping') and b['sick'] == 0:
                self.nc(1)
            if b['tags'].get('grow_combat'):
                b['ctr'] = b.get('ctr', 0) + 1
        return self.dmg >= 20


def load_deck(path):
    main, _ = parse_deck(path)
    deck = []
    for q, name in main:
        deck += [LAND] * q if name.startswith('Mountain') else [name] * q
    return deck


def run(deck, n, max_turn=12, penetrate=1.0):
    rng = random.Random(20260924)
    kills, stuck, curve = [], 0, defaultdict(float)
    for _ in range(n):
        g = Game(deck, rng, penetrate)
        k = None
        for t in range(1, max_turn + 1):
            if g.play_turn():
                k = t
                break
        curve[g.turn] += g.dmg
        kills.append(k or max_turn + 1)
        if g.lands <= 2:
            stuck += 1
    kills.sort()
    m = len(kills)
    return dict(mean=sum(kills) / m,
                t3=100.0 * sum(1 for x in kills if x <= 3) / m,
                t4=100.0 * sum(1 for x in kills if x <= 4) / m,
                t5=100.0 * sum(1 for x in kills if x <= 5) / m,
                stuck=100.0 * stuck / m,
                curve={t: curve[t] / m for t in sorted(curve)})


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    f = sys.argv[2] if len(sys.argv) > 2 else 'deck_mono_red.txt'
    deck = load_deck(os.path.join(HERE, f) if not os.path.isabs(f) else f)
    r = run(deck, n)
    rc = run(deck, n, penetrate=0.6)
    print('%-24s N=%-6d 公平 均杀 %.2f T4 %5.1f%% | 保守 均杀 %.2f T4 %5.1f%% | 卡地 %.1f%%'
          % (os.path.basename(f), n, r['mean'], r['t4'], rc['mean'], rc['t4'], r['stuck']))
