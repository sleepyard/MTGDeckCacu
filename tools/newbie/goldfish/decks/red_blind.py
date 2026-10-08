#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单红「燃烧」金鱼（盲测重写版，建模清单仅来自 red_enum.py 枚举）。
自 sim_red_blind.py 逐字搬运。

非战斗伤害走 mechanics.nc_channel（Tomik +1 → Rollercrusher 翻倍 → Barbs），
与原 nc() 逐步一致。全部其余 tag 为纯标记位，下方内联消费。
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
    os.path.join(_HERE, os.pardir, 'data', 'red_blind.json'))


class Game(GameBase):
    POOL = POOL
    LAND = LAND

    def init_state(self, **kw):
        self.gy = 0
        self.spells = 0
        self.team_pump = 0
        self.anger = 0

    def play_land(self):
        if self.LAND in self.hand and self.lands < 12:
            self.hand.remove(self.LAND)
            self.lands += 1

    def legends(self):
        return {b['n'] for b in self.bf if self.POOL[b['n']].get('leg')}

    def nc(self, amt):
        mechanics.nc_channel(self, amt)

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
        sp = self.POOL[name]
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
        sp = self.POOL[name]
        self.hand.remove(name)
        self.on_spell(is_creature=True)
        b = dict(n=name, p=sp.get('p', 0), d=sp.get('d', 0), tags=sp,
                 sick=0 if sp.get('haste') else 1, ctr=0, temp=0)
        self.bf.append(b)
        if sp.get('etb_ping'):
            self.nc(sp['etb_ping'])

    def cast_other(self, name):
        sp = self.POOL[name]
        self.hand.remove(name)
        self.on_spell(is_creature=False)
        self.bf.append(dict(n=name, p=0, d=0, tags=sp, sick=1, ctr=0, temp=0))

    def play_turn(self):
        self.turn += 1
        self.team_pump = 0
        self.spells = 0
        self.draw()
        self.play_land()
        for b in self.bf:
            b['temp'] = 0
        mana = self.lands
        guard = 0
        while guard < 24:
            guard += 1
            leg = self.legends()
            opts = [n for n in set(self.hand)
                    if n != self.LAND and self.POOL[n]['c'] <= mana
                    and not (self.POOL[n].get('leg') and n in leg)]
            if not opts:
                break
            # 排序键带牌名做 tiebreaker（否则同费牌顺序受 hash 随机化影响 → 不可复现）
            opts.sort(key=lambda n: (-self.POOL[n]['c'], n))
            name = opts[0]
            mana -= self.POOL[name]['c']
            k = self.POOL[name]['k']
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
    from mtga_cost import parse_deck
    main, _ = parse_deck(path)
    return engine.expand(main, LAND, BASIC_PREFIX)


def run(deck, n, max_turn=12, pen=1.0):
    return engine.run(Game, deck, n, max_turn=max_turn, pen=pen)


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
