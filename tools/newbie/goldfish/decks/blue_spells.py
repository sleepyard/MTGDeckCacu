#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单蓝「低费咒语连发」金鱼（廉价瞬间/法术 × 减费 × 每咒语回报）。
自 sim_blue_spells.py 逐字搬运。

optimistic（金鱼盲区的乐观口径）经 engine.run(..., optimistic=…) 传入；
每局咒语数经 collect 钩子聚合，run 包装把 spells 提到结果顶层（兼容原返回键）。
"""
import os
import random
import sys
from collections import defaultdict

from goldfish import mechanics  # noqa: F401  触发机制 tag 注册
from goldfish import engine
from goldfish.engine import GameBase

_HERE = os.path.dirname(os.path.abspath(__file__))
LAND, BASIC_PREFIX, POOL = engine.load_pool(
    os.path.join(_HERE, os.pardir, 'data', 'blue_spells.json'))


class Game(GameBase):
    POOL = POOL
    LAND = LAND

    def init_state(self, optimistic=False, **kw):
        self.opt = optimistic
        self.tokens = []
        self.spells = 0
        self.draws = 0
        self.pages = 0

    def draw(self, n=1, count=True):
        for _ in range(n):
            if self.lib:
                self.hand.append(self.lib.pop())
                if count:
                    self.draws += 1

    def play_land(self):
        if self.LAND in self.hand and self.lands < 14:
            self.hand.remove(self.LAND)
            self.lands += 1

    def cost(self, name):
        sp = self.POOL[name]
        c = sp['c']
        if sp['k'] == 'S':
            if c > 0 and any(b['tags'].get('cost_reduce') for b in self.bf):
                c -= 1
            if c > 0 and self.spells >= 1 and any(b['tags'].get('cost_reduce2') for b in self.bf):
                c -= 1
        return max(0, c)

    def power(self, b):
        return b['p'] + b.get('ctr', 0)

    def on_spell(self):
        self.spells += 1
        for b in self.bf:
            t = b['tags']
            if t.get('prowess'):
                b['ctr'] = b.get('ctr', 0) + 1
            if t.get('opus_draw'):
                self.draw(1)
                if len(self.hand) > 0 and self.rng.random() < 0.5:
                    self.hand.pop()          # 弃 1（近似：50% 概率弃掉一张）
            if t.get('page'):
                self.pages += 1
            if t.get('big_spell_ctr') and self.POOL.get(self.last) and self.POOL[self.last]['c'] >= 4:
                b['ctr'] = b.get('ctr', 0) + 1
        if self.spells == 2:
            for b in self.bf:
                if b['tags'].get('second_spell_ctr'):
                    b['ctr'] = b.get('ctr', 0) + 1

    def cast(self, name, mana):
        sp = self.POOL[name]
        cost = self.cost(name)
        if cost > mana:
            return None
        self.hand.remove(name)
        mana -= cost
        self.last = name
        self.on_spell()
        if sp['k'] == 'C':
            b = dict(n=name, p=sp.get('p', 0), d=sp.get('d', 0), tags=sp, ctr=0, sick=0)
            self.bf.append(b)
        else:
            if sp.get('draw'):
                self.draw(sp['draw'])
            if sp.get('drone_if_attacking') and self.opt:
                self.tokens.append({'p': 1, 'd': 1, 'fly': 0})
        return mana

    def play_turn(self):
        self.turn += 1
        self.spells = 0
        self.draws = 0
        self.draw()
        self.play_land()
        mana = self.lands
        guard = 0
        while guard < 30:
            guard += 1
            opts = [n for n in set(self.hand) if n != self.LAND and self.cost(n) <= mana]
            if not opts:
                break
            # ★ 优先打非生物咒语（触发 Muse Seeker / Operative）
            opts.sort(key=lambda n: (0 if self.POOL[n]['k'] == 'S' else 1, -self.POOL[n]['c'], n))
            r = self.cast(opts[0], mana)
            if r is None:
                break
            mana = r
        dmg = 0
        for b in self.bf:
            v = self.power(b)
            dmg += v if b['tags'].get('fly') else v * self.pen
        for t in self.tokens:
            dmg += t['p'] * self.pen
        self.dmg += dmg
        return self.dmg >= 20


def _collect(g, agg):
    agg['spells'] += g.spells


def load_deck(path):
    from mtga_cost import parse_deck
    main, _ = parse_deck(path)
    return engine.expand(main, LAND, BASIC_PREFIX)


def run(deck, n, max_turn=14, pen=1.0, opt=False):
    r = engine.run(Game, deck, n, max_turn=max_turn, pen=pen,
                   collect=_collect, optimistic=opt)
    r['spells'] = r['agg'].get('spells', 0.0)   # 兼容原 sim 的顶层返回键
    return r


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
