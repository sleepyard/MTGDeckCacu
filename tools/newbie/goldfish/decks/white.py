#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单白金鱼 v2（衍生物铺场 × 回血+豆 双轴）。自 sim_white.py 逐字搬运。

地哨兵为字面量 'LAND'；max_turn=12；penetrate 经 pen 传入。
全部 tag 为纯标记位，下方内联消费（与原 sim_white.py 判定顺序逐行一致）。
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
    os.path.join(_HERE, os.pardir, 'data', 'white.json'))

_TAGS = ('life_src', 'life_ctr', 'ctr_draw', 'mobilize', 'vig', 'tok_fs',
         'hare', 'atk_pump', 'life_draw', 'fly', 'lifelink')


class Game(GameBase):
    POOL = POOL
    LAND = LAND            # 地哨兵为字面量 'LAND'

    def init_state(self, **kw):
        self.board = []       # dict(k=名称,p,d,sick,tags)
        self.tokens = []
        self.triumph = 0
        self.tok_turn = 0
        self.ctr_drawn = False
        self.life = 20

    def play_land(self):
        if self.LAND in self.hand and self.lands < 10:
            self.hand.remove(self.LAND)
            self.lands += 1

    # ── 事件：获得生命 ──
    def gain_life(self, n=1):
        self.life += n
        for b in self.board:
            if b['tags'].get('life_ctr'):
                b['p'] += 1
                if b['tags'].get('ctr_draw') and not self.ctr_drawn:
                    self.ctr_drawn = True
                    self.draw(1)

    # ── 事件：生物进场（含衍生物）──
    def on_etb(self, is_token=False, self_idx=None):
        # self_idx: 刚进场的 board 下标（事件源自身进场不应触发自己）
        # 政治胜利
        if self.triumph < 4:
            self.triumph += 1
            if self.triumph >= 4:
                self.triumph = 0
                self.bump_all(1)
                self.draw(1)
        # 回血源：每个「每当另一个生物进场回 1 血」各触发一次
        srcs = sum(1 for i, b in enumerate(self.board)
                   if b['tags'].get('life_src') and not b.get('self_etb') and i != self_idx)
        for _ in range(srcs):
            self.gain_life(1)
        # Haliya 自身也触发（进场时）
        # Haliya 类「自身或另一个生物进场」：自身进场也触发
        if self_idx is not None and self.board[self_idx]['tags'].get('life_src'):
            self.gain_life(1)
        # Belladonna 类（衍生物计数）—— 本版未用

    def bump_all(self, n=1):
        for b in self.board:
            b['p'] += n
        for t in self.tokens:
            t['p'] += n

    def make_tokens(self, k, specs=None, sick=True):
        for _ in range(k):
            self.tokens.append({'p': 1, 'd': 1, 'sick': 1 if sick else 0})
            self.on_etb(is_token=True)

    def cast(self, name, mana):
        sp = self.POOL[name]
        mana -= sp['c']
        self.hand.remove(name)
        tags = {k: v for k, v in sp.items() if k in _TAGS}
        # trick：Honor（给豆 + 抓牌）
        if sp.get('give_ctr'):
            target = max(self.board + self.tokens, key=lambda x: x['p'], default=None)
            if target is not None:
                target['p'] += 1
                if target in self.board:
                    for b in self.board:
                        if b['tags'].get('ctr_draw') and not self.ctr_drawn:
                            self.ctr_drawn = True
                            self.draw(1)
        if sp.get('draw'):
            self.draw(sp['draw'])
        if sp.get('big'):        # Battle Menu：造 2/2 骑士
            self.tokens.append({'p': 2, 'd': 2, 'sick': 1})
            self.on_etb(is_token=True)
        elif sp['k'] in ('C', 'E'):
            b = {'k': name, 'p': sp.get('p', 0), 'd': sp.get('d', 0), 'sick': 1, 'tags': tags}
            self.board.append(b)
            idx = len(self.board) - 1
            if name == 'Haliya, Guided by Light':
                b['self_etb'] = 1
            if sp['k'] == 'C':
                self.on_etb(is_token=False, self_idx=idx)
            if 'hare' in tags:
                cnt = sum(1 for x in self.board if x['tags'].get('hare')) - 1
                if cnt > 0:
                    self.make_tokens(cnt)
                self.on_etb(is_token=True)
            if sp.get('tokens'):
                self.make_tokens(sp['tokens'])
            if sp.get('give_ctr') is None and sp.get('tokens'):
                pass
        elif sp.get('tokens'):
            self.make_tokens(sp['tokens'])
        return mana

    def play_turn(self):
        self.turn += 1
        self.ctr_drawn = False
        self.draw()
        self.play_land()
        mana = self.lands
        while True:
            # ★ 排序键必须带牌名做 tiebreaker：否则同 cmc 牌的顺序取决于 set 迭代顺序
            #   （受 PYTHONHASHSEED 影响）⇒ 结果不可复现
            opts = sorted({n for n in self.hand if n != self.LAND and self.POOL[n]['c'] <= mana},
                          key=lambda n: (-self.POOL[n]['c'], n))
            if not opts:
                break
            mana = self.cast(opts[0], mana)
        # 战斗
        dmg = 0
        attackers = 0
        for b in self.board:
            if b['sick']:
                b['sick'] = 0
                continue
            attackers += 1
            v = b['p'] + b['tags'].get('mobilize', 0)
            dmg += v if b['tags'].get('fly') else v * self.pen
        for t in self.tokens:
            if t.get('sick'):
                t['sick'] = 0
            else:
                attackers += 1
                dmg += t['p'] * self.pen
        if any(b['tags'].get('atk_pump') for b in self.board):
            dmg += attackers
        # 系命：攻击打点 → 回等量生命（= 回血事件源，每次攻击各触发一次）
        for b in self.board:
            if b['tags'].get('lifelink') and not b['sick'] and b['p'] > 0:
                self.gain_life(b['p'])
        for t in self.tokens:
            if t.get('lifelink') and t['p'] > 0:
                self.gain_life(t['p'])
        self.dmg += dmg
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
