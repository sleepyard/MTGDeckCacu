#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单白衍生物金鱼。自 sim_mono_white.py 逐字搬运，含两处修复：

  · ★ 修复：贪心施放排序补牌名 tiebreaker（原键 -c 在 set 迭代序上受
    PYTHONHASHSEED 影响，结果跨进程不可复现；与 sim_white 已有修复同款）；
  · ★ 调度：原 sim_mono_white.mulligan 为老式"重抓满 7"，迁移初期按历史
    口径保留（LONDON=False），现已与全系列统一为伦敦调度（7→6→5）。
    两处修复均使黄金值重钉（见 tools/test_goldfish_engine.py 的旧值对照）。
  · 保留 max_turn=12、无 pen（伤害不折算）的原口径。
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
    os.path.join(_HERE, os.pardir, 'data', 'mono_white.json'))

_TAGS = ('mobilize', 'vig', 'tok_fs', 'bella', 'hare', 'atk_pump', 'fly', 'lord3')


class Game(GameBase):
    POOL = POOL
    LAND = LAND            # 地哨兵为字面量 'LAND'
    # LONDON 默认 True：与全系列统一的伦敦调度（原老式重抓 7 已废弃）

    def init_state(self, **kw):
        self.board = []      # dict(p,d,tags(vig/mobilize/tok_fs/bella/hare/atk_pump), sick)
        self.tokens = []     # dict(p,d)
        self.triumph = 0
        self.tok_turn = 0

    def play_land(self):
        if self.LAND in self.hand and self.lands < 10:
            self.hand.remove(self.LAND)
            self.lands += 1

    def bump_all(self, n=1):
        for b in self.board:
            b['p'] += n
        for t in self.tokens:
            t['p'] += n

    # ---------- 触发 ----------
    def on_creature_enter(self, is_token=False):
        if self.triumph < 4:
            self.triumph += 1
            if self.triumph >= 4:
                self.triumph = 0
                self.bump_all(1)
                self.draw(1)
        if is_token:
            self.tok_turn += 1
            if any(b['tags'].get('bella') for b in self.board):
                if self.tok_turn == 2:
                    self.draw(1)
                elif self.tok_turn >= 3:
                    self.bump_all(1)

    def make_tokens(self, specs, sick=True):
        for (p, d) in specs:
            self.tokens.append({'p': p, 'd': d, 'sick': 1 if sick else 0})
            self.on_creature_enter(is_token=True)

    # ---------- 出牌 ----------
    def cast(self, name, mana):
        spec = self.POOL[name]
        mana -= spec['c']
        self.hand.remove(name)
        tags = {k: v for k, v in spec.items() if k in _TAGS}
        if spec['k'] in ('C', 'E'):
            self.board.append({'p': spec.get('p', 0), 'd': spec.get('d', 0), 'tags': tags, 'sick': 1})
        if spec['k'] == 'C':                 # 只有生物进场才触发「生物进场」类异能
            self.on_creature_enter(is_token=False)
        if 'hare' in tags:
            cnt = sum(1 for b in self.board if b['tags'].get('hare')) - 1
            if cnt > 0:
                self.make_tokens([(1, 1)] * cnt)
        for n in range(spec.get('etb', 0)):
            self.make_tokens([(1, 1)])
        if 'tokens' in spec:
            self.make_tokens(spec['tokens'])
        return mana

    def play_turn(self):
        self.turn += 1
        self.tok_turn = 0
        self.draw()
        self.play_land()
        mana = self.lands
        # 贪心施放（费用从高到低，留不出空转）
        while True:
            opts = sorted({n for n in self.hand if n != self.LAND and self.POOL[n]['c'] <= mana},
                          key=lambda n: (-self.POOL[n]['c'], n))   # ★ tiebreaker 修复
            if not opts:
                break
            mana = self.cast(opts[0], mana)
        # 战斗
        dmg = 0
        for b in self.board:
            if b['sick']:
                b['sick'] = 0
                continue
            if b['tags'].get('atk_pump') and self.board:
                pass                      # 攻击时全队 +1/+1（直到回合结束，不入永久）
            dmg += b['p'] + (b['tags'].get('mobilize', 0))
        for t in self.tokens:
            if t.get('sick'):
                t['sick'] = 0
            else:
                dmg += t['p']
        # 攻击时的临时增益（Dauntless Veteran）
        if any(b['tags'].get('atk_pump') for b in self.board):
            atk = sum(1 for b in self.board if not b['sick']) + sum(1 for t in self.tokens if not t.get('sick'))
            dmg += atk
        self.dmg += dmg
        # mobilize 攻兵回合末消失（这里只影响当回合打点，已计入）
        return self.dmg >= 20


def load_deck(path):
    from mtga_cost import parse_deck
    main, _ = parse_deck(path)
    return engine.expand(main, LAND, BASIC_PREFIX)


def run(deck, n, max_turn=12):
    return engine.run(Game, deck, n, max_turn=max_turn)


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
