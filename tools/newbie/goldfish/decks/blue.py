#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纯蓝金鱼（每回合第 2 次抽牌触发链 vs tempo 假设）。自 sim_blue.py 逐字搬运。

draw 带 count 参数（二抽判定）故覆写；触发统计（sd/ss/lyra）经 engine.run
的 collect 钩子聚合到结果["agg"]。全部 tag 为纯标记位，下方内联消费。
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
    os.path.join(_HERE, os.pardir, 'data', 'blue.json'))


class Game(GameBase):
    POOL = POOL
    LAND = LAND

    def init_state(self, **kw):
        self.tokens = []
        self.draws = 0          # 本回合抽牌数（二抽判定）
        self.reduced = False    # 本回合是否已有减费源
        self.stat = {}
        self.last_spell = None

    def draw(self, n=1, count=True):
        for _ in range(n):
            if self.lib:
                self.hand.append(self.lib.pop())
                if count:
                    self.draws += 1

    def play_land(self):
        if self.LAND in self.hand and self.lands < 12:
            self.hand.remove(self.LAND)
            self.lands += 1

    # ---------- 第二抽触发 ----------
    def second_draw_triggers(self):
        """本回合抽到第 2 张时触发一次；用 flag 保证每回合只触发一次"""
        if self.draws != 2:
            return
        for b in self.bf:
            t = b['tags']
            if t.get('sd_ctr'):
                b['ctr'] = b.get('ctr', 0) + 1
            if t.get('sd_token'):
                self.tokens.append({'p': 1, 'd': 1, 'fly': 1})
            if t.get('sd_temp'):
                b['temp'] = b.get('temp', 0) + 1
                b['temp_d'] = b.get('temp_d', 0) + 2
            if t.get('sd_copy'):
                self.tokens.append({'p': b['p'], 'd': b['d'], 'fly': 0})

    def cost(self, name):
        c = self.POOL[name]['c']
        if c > 0 and any(b['tags'].get('cost_reduce') for b in self.bf):
            if self.POOL[name]['k'] != 'C':       # 只减非生物咒语
                c = max(0, c - 1)
        return c

    def power(self, b):
        return b['p'] + b.get('ctr', 0) + b.get('temp', 0)

    def toughness(self, b):
        return b['d'] + b.get('ctr', 0) + b.get('temp_d', 0)

    def second_spell_triggers(self):
        """本回合第 2 张咒语结算"""
        for b in self.bf:
            t = b['tags']
            if t.get('second_spell_ctr'):
                b['ctr'] = b.get('ctr', 0) + 1
            if t.get('second_spell_token'):
                self.tokens.append({'p': 1, 'd': 1, 'fly': 1})
        if self.copied and any(x['tags'].get('flurry_copy') for x in self.bf):
            sp = self.POOL.get(self.copied) or {}
            if sp.get('draw'):
                self.draw(sp['draw'])

    def cast(self, name, mana):
        sp = self.POOL[name]
        cost = self.cost(name)
        if cost > mana:
            return None
        self.hand.remove(name)
        mana -= cost
        self.spells += 1
        is_creature = (sp['k'] == 'C')
        # ── 施放触发（先结算站场件）──
        if not is_creature:
            for b in self.bf:
                if b['tags'].get('prowess'):
                    b['temp'] = b.get('temp', 0) + 1
        if self.spells == 2 and not is_creature:
            self.copied = name
            self.second_spell_triggers()
            self.stat['ss'] = self.stat.get('ss', 0) + 1
        # ── 咒语本体效果 ──
        if is_creature:
            b = dict(n=name, p=sp.get('p', 0), d=sp.get('d', 0), tags=sp, ctr=0, temp=0, temp_d=0)
            self.bf.append(b)
            if sp.get('etb_draw'):
                self.draw(sp['etb_draw'])
        else:
            if sp.get('draw'):
                self.draw(sp['draw'])
        return mana

    def play_turn(self):
        self.turn += 1
        self.draws = 0
        self.spells = 0          # ★ 必须每回合重置（否则"第二咒语"只触发一次/局）
        for b in self.bf:
            b['temp'] = 0
            b['temp_d'] = 0
        self.draw()                              # 回合自然抽 1 → draws=1
        self.play_land()
        mana = self.lands
        guard = 0
        while guard < 24:
            guard += 1
            opts = [n for n in set(self.hand) if n != self.LAND and self.cost(n) <= mana]
            if not opts:
                break
            opts.sort(key=lambda n: (-self.cost(n), n))
            before = self.draws
            mana = self.cast(opts[0], mana)
            if mana is None:
                break
            if self.draws == 2 and before < 2:
                self.second_draw_triggers()
                self.stat['sd'] = self.stat.get('sd', 0) + 1
        # 回合末：Lyra（本回合抽满 3 张 → 造 3/3 飞行天使）
        if self.draws >= 3:
            for b in self.bf:
                if b['tags'].get('draw3_token'):
                    self.tokens.append({'p': 3, 'd': 3, 'fly': 1})
                    self.stat['lyra'] = self.stat.get('lyra', 0) + 1
        self.stat_second = self.stat.get('sd', 0)
        self.stat2 = self.stat.get('ss', 0)
        # 战斗
        dmg = 0
        for b in self.bf:
            if b['tags'].get('blank'):
                continue
            v = self.power(b)
            dmg += v if b['tags'].get('fly') else v * self.pen
        for t in self.tokens:
            dmg += t['p'] if t.get('fly') else t['p'] * self.pen
        self.dmg += dmg
        return self.dmg >= 20


def _collect(g, agg):
    for kk, vv in g.stat.items():
        agg[kk] += vv


def load_deck(path):
    from mtga_cost import parse_deck
    main, _ = parse_deck(path)
    return engine.expand(main, LAND, BASIC_PREFIX)


def run(deck, n, max_turn=14, pen=1.0):
    return engine.run(Game, deck, n, max_turn=max_turn, pen=pen, collect=_collect)


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
