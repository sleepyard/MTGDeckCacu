#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纯绿金鱼（地落 → +1/+1 豆 → 转化）。自 sim_green.py 逐字搬运。

机制注入：地落系 3 tag 经注册表分发（mechanics.py 实体 handler）；
其余 tag（dork/inspire/mutagen/trample…）为纯标记位，下方内联消费，
与原 sim_green.py 判定顺序逐行一致。
"""
import os
import random
import sys

from goldfish import mechanics  # noqa: F401  触发机制 tag 注册
from goldfish import engine
from goldfish.engine import GameBase, HANDLERS

_HERE = os.path.dirname(os.path.abspath(__file__))
LAND, BASIC_PREFIX, POOL = engine.load_pool(
    os.path.join(_HERE, os.pardir, 'data', 'green.json'))

# 地落 tag 的注册表分发顺序 = 原 sim_green.do_landfall 的判定顺序
_LANDFALL_TAGS = ('landfall_ctr', 'landfall_double', 'landfall_dblpow')


class Game(GameBase):
    POOL = POOL
    LAND = LAND

    def init_state(self, **kw):
        self.landfall = 0        # 本回合地落次数
        self.pending = []        # 本回合待结算的地落触发

    # ---------- 地落 ----------
    def do_landfall(self, n=1):
        """每有一块地进场，所有地落触发件各触发一次"""
        for _ in range(n):
            self.landfall += 1
            for b in self.bf:
                for tag in _LANDFALL_TAGS:
                    v = b['tags'].get(tag)
                    if v:
                        HANDLERS[tag](self, b, v)

    def extra_lands(self):
        return sum(1 for b in self.bf if b['tags'].get('extra_land'))

    def has_power4(self):
        return any(self.power(x) >= 4 for x in self.bf)

    def has_trample(self, b):
        return bool(b['tags'].get('trample')) or any(x['tags'].get('mass_trample') for x in self.bf)

    def power(self, b):
        return b['p'] + b.get('ctr', 0) + b.get('perm_pow', 0)

    def play_land(self):
        if self.LAND in self.hand:
            self.hand.remove(self.LAND)
            self.lands += 1
            self.do_landfall(1)

    # ---------- 施放 ----------
    def cast(self, name, mana):
        sp = self.POOL[name]
        if sp['c'] > mana:
            return None
        self.hand.remove(name)
        mana -= sp['c']
        # Mutagen Man：进场产 Mutagen token，每个可牺牲换 1 颗豆（本回合结算）
        if sp.get('mutagen'):
            for _ in range(sp['mutagen']):
                cre = [x for x in self.bf if x['p'] > 0]
                if cre:
                    t = max(cre, key=lambda x: self.power(x))
                    t['ctr'] = t.get('ctr', 0) + 1
        if sp.get('land_ramp'):
            self.lands += 1                       # 找地（简化：直接+1 地并触发地落）
            self.do_landfall(1)
            return mana
        if sp.get('ctr_fight'):
            cre = [x for x in self.bf if x['p'] > 0]
            if cre:
                t = max(cre, key=lambda x: self.power(x))
                t['ctr'] = t.get('ctr', 0) + 1
            return mana
        if sp.get('ctr_pump'):
            cre = [x for x in self.bf if x['p'] > 0]
            if cre:
                t = max(cre, key=lambda x: self.power(x))
                t['ctr'] = t.get('ctr', 0) + 1
            return mana
        if sp.get('inspire'):
            n = sum(1 for x in self.bf if (x.get('ctr', 0) > 0))
            self.draw(n)
            return mana
        if sp.get('k') == 'E':
            self.bf.append(dict(n=name, p=0, d=0, tags=sp, ctr=0, sick=1, perm_pow=0, entered_turn=self.turn))
            if sp.get('power4_draw') and self.has_power4():
                self.draw(1)
            return mana
        # 生物
        b = dict(n=name, p=sp.get('p', 0), d=sp.get('d', 0), tags=sp,
                 ctr=sp.get('start_ctr', 0), sick=0 if sp.get('haste') else 1,
                 perm_pow=0, entered_turn=self.turn)
        self.bf.append(b)
        return mana

    def play_turn(self):
        self.turn += 1
        self.landfall = 0
        for b in self.bf:
            b['perm_pow'] = 0
        self.draw()
        # 下地（1 + 额外下地）
        self.play_land()
        for _ in range(self.extra_lands()):
            self.play_land()
        # 可用的法力（含 mana dork）
        mana = self.lands + sum(1 for b in self.bf if b['tags'].get('dork') or b['tags'].get('dork2'))
        # 贪心施放
        guard = 0
        while guard < 24:
            guard += 1
            opts = [n for n in set(self.hand) if n != self.LAND and self.POOL[n]['c'] <= mana]
            if not opts:
                break
            opts.sort(key=lambda n: (-self.POOL[n]['c'], n))
            r = self.cast(opts[0], mana)
            if r is None:
                break
            mana = r
        # 战斗通道：★ 践踏的生物伤害基本全额穿透（被挡也能打穿），
        #            非践踏生物按 penetrate 系数折算（这是本副最关键的建模差别）
        dmg = 0
        for b in self.bf:
            if b['sick']:
                b['sick'] = 0
                continue
            v = self.power(b)
            if b['p'] == 0 and not b.get('ctr'):
                continue                      # 无力量的支援件（Uprising 等）不打点
            dmg += v * (max(self.pen, 0.95) if self.has_trample(b) else self.pen)
        self.dmg += dmg
        # Cactuar：回合末若本回合未进场则回手（可下回合重铸）
        for b in list(self.bf):
            if b['tags'].get('bounce_back') and b.get('entered_turn') != self.turn:
                self.bf.remove(b)
                self.hand.append('Cactuar')
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
