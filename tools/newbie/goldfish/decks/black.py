#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单黑金鱼（廉价闪避威胁 + 生命流失）。自 sim_black.py 逐字搬运。

menace_pen 经 engine.run(..., menace_pen=…) 传入 init_state；卡地口径为
T3 未达 3 地（is_stuck 覆写为 t3_short）。全部 tag 为纯标记位，下方内联消费。
"""
import os
import random
import sys

from goldfish import mechanics  # noqa: F401  触发机制 tag 注册
from goldfish import engine
from goldfish.engine import GameBase

_HERE = os.path.dirname(os.path.abspath(__file__))
LAND, BASIC_PREFIX, POOL = engine.load_pool(
    os.path.join(_HERE, os.pardir, 'data', 'black.json'))


class Game(GameBase):
    POOL = POOL
    LAND = LAND

    def init_state(self, menace_pen=0.9, **kw):
        self.mpen = menace_pen
        self.spells = 0
        self.life = 20
        self.t3_short = False

    def is_stuck(self):
        return self.t3_short

    def play_land(self):
        if self.LAND in self.hand and self.lands < 12:
            self.hand.remove(self.LAND)
            self.lands += 1

    def drain(self, n=1):
        """生命流失 = 无条件直伤（非战斗通道）"""
        self.dmg += n
        self.life += n

    def power(self, b):
        p = b['p'] + b.get('ctr', 0) + b.get('temp', 0)
        return p

    def cast(self, name, mana):
        sp = self.POOL[name]
        if sp['c'] > mana:
            return None
        self.hand.remove(name)
        mana -= sp['c']
        self.spells += 1
        if sp.get('drain'):
            self.drain(1)
            return mana
        if sp.get('removal'):
            return mana                       # 金鱼 0 值
        b = dict(n=name, p=sp.get('p', 0), d=sp.get('d', 0), tags=sp, ctr=0, temp=0)
        self.bf.append(b)
        if sp.get('etb_drain'):
            self.drain(1)
        if sp.get('repartee_drain'):
            self.drain(1)
        return mana

    def play_turn(self):
        self.turn += 1
        self.spells = 0
        for b in self.bf:
            b['temp'] = 0
        self.draw()
        self.play_land()
        if self.turn == 3 and self.lands < 3:
            self.t3_short = True
        mana = self.lands
        guard = 0
        while guard < 20:
            guard += 1
            opts = [n for n in set(self.hand) if n != self.LAND and self.POOL[n]['c'] <= mana]
            if not opts:
                break
            opts.sort(key=lambda n: (-self.POOL[n]['c'], n))
            r = self.cast(opts[0], mana)
            if r is None:
                break
            mana = r
        # 回合开始效果（Desolation Prowler：付 2 血 → +2/+2，每回合一次）
        for b in self.bf:
            if b['tags'].get('pay_pump'):
                b['temp'] += 2
        # 攻击触发：生命流失
        atk_drain = 0
        for b in self.bf:
            if b['tags'].get('atk_drain'):
                atk_drain += 1
            if b['tags'].get('atk_drain_cond') and any(x.get('ctr', 0) > 0 for x in self.bf):
                atk_drain += 1
        if atk_drain:
            self.drain(atk_drain)
        # 战斗通道
        has4 = any(self.power(x) >= 4 for x in self.bf)
        dmg = 0
        for b in self.bf:
            v = self.power(b)
            if b['tags'].get('ferocious') and has4:
                v += 2
            if b['tags'].get('fly') or b['tags'].get('menace'):
                dmg += v * self.mpen          # 闪避：穿透率高
            else:
                dmg += v * self.pen
        self.dmg += dmg
        return self.dmg >= 20


def load_deck(path):
    from mtga_cost import parse_deck
    main, _ = parse_deck(path)
    return engine.expand(main, LAND, BASIC_PREFIX)


def run(deck, n, max_turn=14, pen=1.0):
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
