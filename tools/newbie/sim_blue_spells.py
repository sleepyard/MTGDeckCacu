#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单蓝「低费咒语连发」金鱼模拟器（轴线重建版）

轴：**廉价瞬间/法术 × 减费增幅 × 每咒语回报**
  L1 燃料：Opt {U} / Fleeting Distraction {U} / Bounce Off {U} / Unending Whisper {U}
  L2 增幅：Mocking Sprite {2}{U}（瞬间与法术减 {1} ⇒ 1 费咒语变 0 费）
  L3 回报：Muse Seeker {1}{U}（每张瞬间/法术 → 抽 1 弃 1）、Illvoi Operative（第 2 个咒语 → 豆）
  打点来源：生物（Muse Seeker 1/2、Mocking Sprite 2/1 飞行、飞行打手）

⚠ 金鱼盲区（本轴尤其严重，报告须双口径）：
  · 弹回（Bounce Off / Into the Roil）对金鱼 = 0 值
  · Desculpting Blast 的"若攻击中则造 1/1"金鱼无法触发（无对手）⇒ 按 0 建
  · 闪现（Brineborn Cutthroat 等）需对手回合 ⇒ 0 值
  ⇒ 因此本模拟器给出的是**下界**；另给"乐观口径"（假设弹回=干扰成功、造兵触发）

用法: python3 sim_blue_spells.py <局数> <牌表文件>
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import os, random, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mtga_cost import parse_deck

POOL = {
    # ── L1 廉价咒语 ──
    'Opt':                 dict(k='S', c=1, draw=1),
    'Unending Whisper':    dict(k='S', c=1, draw=1),
    'Fleeting Distraction': dict(k='S', c=1, draw=1),
    'Bounce Off':          dict(k='S', c=1, bounce=1),
    "Into the Roil":       dict(k='S', c=2, bounce=1),
    'Desculpting Blast':   dict(k='S', c=2, bounce=1, drone_if_attacking=1),
    'Banishing Betrayal':  dict(k='S', c=2, bounce=1),
    # ── L2 增幅（减费）──
    'Mocking Sprite':      dict(k='C', c=3, p=2, d=1, fly=1, cost_reduce=1),
    'Highspire Bell-Ringer': dict(k='C', c=3, p=1, d=4, fly=1, cost_reduce2=1),
    # ── L3 每咒语回报 ──
    'Muse Seeker':         dict(k='C', c=2, p=1, d=2, opus_draw=1),
    'Diary of Dreams':     dict(k='E', c=2, page=1),
    'Illvoi Operative':    dict(k='C', c=2, p=2, d=1, second_spell_ctr=1),
    'Cryotheory Adept':    dict(k='C', c=2, p=2, d=1, prowess=1),
    'Elementalist Adept':  dict(k='C', c=2, p=2, d=1, prowess=1),
    'Sahagin':             dict(k='C', c=2, p=1, d=3, big_spell_ctr=1),
    # ── 打手 ──
    'Spectral Sailor':     dict(k='C', c=1, p=1, d=1, fly=1),
    'Illvoi Galeblade':    dict(k='C', c=1, p=1, d=1, fly=1),
    'Il Mheg Pixie':       dict(k='C', c=2, p=2, d=1, fly=1),
    'Thopter Fabricator':  dict(k='C', c=3, p=4, d=4, fly=1, sd_token=1),
    'Mysterio\'s Phantasm': dict(k='C', c=2, p=1, d=3, fly=1, vig=1),
}
LAND = 'Island'


class Game:
    def __init__(self, deck, rng, pen=1.0, optimistic=False):
        self.rng = rng
        self.pen = pen
        self.opt = optimistic
        self.lib = deck[:]
        rng.shuffle(self.lib)
        self.hand = []
        self.lands = 0
        self.bf = []
        self.tokens = []
        self.dmg = 0.0
        self.turn = 0
        self.spells = 0
        self.draws = 0
        self.pages = 0
        self.opening()

    def opening(self):
        """★ 伦敦调度（修正版）：起手 7 张；每次调度**手牌数 -1**（7→6→5）"""
        self.draw(7)
        size = 7
        for _ in range(2):
            if 2 <= sum(1 for c in self.hand if c == 'Island') <= 5:
                return
            size -= 1
            self.lib += self.hand
            self.rng.shuffle(self.lib)
            self.hand = []
            self.draw(size)

    def draw(self, n=1, count=True):
        for _ in range(n):
            if self.lib:
                self.hand.append(self.lib.pop())
                if count:
                    self.draws += 1

    def cost(self, name):
        sp = POOL[name]
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
            if t.get('big_spell_ctr') and POOL.get(self.last) and POOL[self.last]['c'] >= 4:
                b['ctr'] = b.get('ctr', 0) + 1
        if self.spells == 2:
            for b in self.bf:
                if b['tags'].get('second_spell_ctr'):
                    b['ctr'] = b.get('ctr', 0) + 1

    def cast(self, name, mana):
        sp = POOL[name]
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
        if LAND in self.hand and self.lands < 14:
            self.hand.remove(LAND)
            self.lands += 1
        mana = self.lands
        guard = 0
        while guard < 30:
            guard += 1
            opts = [n for n in set(self.hand) if n != LAND and self.cost(n) <= mana]
            if not opts:
                break
            # ★ 优先打非生物咒语（触发 Muse Seeker / Operative）
            opts.sort(key=lambda n: (0 if POOL[n]['k'] == 'S' else 1, -POOL[n]['c'], n))
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


def load_deck(path):
    main, _ = parse_deck(path)
    deck = []
    for q, name in main:
        deck += [LAND] * q if name.startswith('Island') else [name] * q
    return deck


def run(deck, n, max_turn=14, pen=1.0, opt=False):
    rng = random.Random(20260924)
    kills, stuck = [], 0
    agg = defaultdict(int)
    for _ in range(n):
        g = Game(deck, rng, pen, opt)
        k = None
        for t in range(1, max_turn + 1):
            if g.play_turn():
                k = t
                break
        kills.append(k or max_turn + 1)
        agg['spells'] += g.spells
        if g.lands <= 2:
            stuck += 1
    kills.sort()
    m = len(kills)
    return dict(mean=sum(kills) / m,
                t5=100.0 * sum(1 for x in kills if x <= 5) / m,
                t6=100.0 * sum(1 for x in kills if x <= 6) / m,
                stuck=100.0 * stuck / m,
                spells=agg['spells'] / n)



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
    f = sys.argv[2] if len(sys.argv) > 2 else 'deck.txt'
    deck = load_deck(resolve_deck_path(f))
    r = run(deck, n)
    rc = run(deck, n, pen=0.6)
    print('%-26s N=%-6d 公平 均杀 %.2f T5 %5.1f%% | 保守 均杀 %.2f | 卡地 %.1f%%'
          % (os.path.basename(f), n, r['mean'], r['t5'], rc['mean'], r['stuck']))
