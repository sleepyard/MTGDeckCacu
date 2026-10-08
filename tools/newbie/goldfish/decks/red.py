#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单红「咒语连发 / 燃烧」金鱼。自 sim_red.py 逐字搬运，含一处修复：

  ★ 调度修复：原 sim_red.opening 为老式"重抓满 7"（与其余 sim 的伦敦调度
    7→6→5 不一致，系历史遗留）；迁移后统一走 GameBase 伦敦调度。
    因此本模块黄金值相对旧 sim_red 重钉。

  非战斗伤害走 mechanics.nc_channel（Tomik +1 → double_nc 翻倍 → Barbs；
  red 池无 double_nc 牌，与原 nc() 等价）。
"""
import os
import random
import sys
from collections import defaultdict

from goldfish import mechanics
from goldfish import engine
from goldfish.engine import GameBase

_HERE = os.path.dirname(os.path.abspath(__file__))
LAND, BASIC_PREFIX, POOL = engine.load_pool(
    os.path.join(_HERE, os.pardir, 'data', 'red.json'))


class Game(GameBase):
    POOL = POOL
    LAND = LAND

    def init_state(self, **kw):
        self.gy_spell = 0
        self.spells = 0
        self.team_pump = 0    # Master of Barbs：本回合全队 +X/+0（临时）
        self.anger = 0

    # ---- 伤害入口 ----
    def nc(self, amt):
        mechanics.nc_channel(self, amt)

    def play_land(self):
        if self.LAND in self.hand and self.lands < 12:
            self.hand.remove(self.LAND)
            self.lands += 1

    def emeritus_ready(self):
        return any(b['tags'].get('emeritus') for b in self.bf)

    def power_of(self, b):
        p = b['p'] + b.get('ctr', 0) + b.get('temp', 0)
        if b['tags'].get('lavarunner') and self.gy_spell >= 2:
            p += 1
        return p + self.team_pump

    # ---- 施放 ----
    def cast_spell(self, name):
        sp = self.POOL[name]
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
        sp = self.POOL[name]
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
        self.play_land()
        # 本回合结束步骤：清除临时膨胀
        for b in self.bf:
            b['temp'] = 0
        mana = self.lands
        # 贪心施放：优先最高费用（战斗前把法力用光）
        guard = 0
        while guard < 20:
            guard += 1
            opts = sorted({n for n in self.hand if n != self.LAND and self.POOL[n]['c'] <= mana},
                          key=lambda n: (-self.POOL[n]['c'], n))
            if not opts:
                break
            name = opts[0]
            mana -= self.POOL[name]['c']
            if self.POOL[name]['k'] == 'C':
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
    from mtga_cost import parse_deck
    main, _ = parse_deck(path)
    return engine.expand(main, LAND, BASIC_PREFIX)


def run(deck, n, max_turn=12, penetrate=1.0):
    return engine.run(Game, deck, n, max_turn=max_turn, pen=penetrate)


def resolve_deck_path(f):
    """依次尝试 绝对路径 / 当前目录 / newbie 目录 / tools 目录"""
    if os.path.isabs(f):
        return f
    cands = [f, os.path.join(os.getcwd(), f), os.path.join(engine.NEWBIE, f),
             os.path.join(engine.TOOLS, f)]
    for c in cands:
        if os.path.exists(c):
            return c
    return f
