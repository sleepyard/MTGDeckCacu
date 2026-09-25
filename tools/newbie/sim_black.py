#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单黑金鱼模拟器（BO1 口径 · 低造价档）

轴线：**廉价闪避威胁 + 生命流失**
  L1 威胁：1-2 费打手（威胁 menace / 飞行 / 死触）
  L2「增幅」：★ 本轴特殊 —— **生命流失本身就是伤害**（非战斗通道），
             另有 Desolation Prowler（付 2 血 → +2/+2）与 Ferocious（力量 4+ → +2/+2）
  L3 射程：生命流失（每对手失 1 血）≈ 红的燃烧，提供**非战斗直伤**

★ 建模要点（沿用本项目历史修正）：
  · 战斗通道 vs 非战斗通道**分开**；保守口径只缩放战斗通道
  · **威胁（menace）** = 需要 2 个阻挡者 ⇒ 保守口径下穿透率高于普通生物
  · **生命流失**是无条件直伤（金鱼可全额计入）—— 这是黑优于蓝的地方
  · 排序键含牌名 tiebreaker（可复现）
  · 金鱼盲区：去除（Requiting Hex 等）= 0 值；死亡触发、牺牲抽牌未建模

用法: python3 sim_black.py <局数> <牌表文件>
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
    # ── 1 费威胁 ──
    'Dream Beavers':        dict(k='C', c=1, p=1, d=1, fly=1, etb_drain=1),
    'Callous Inspector':    dict(k='C', c=1, p=1, d=1, menace=1),
    'Nighthowl Pursuer':    dict(k='C', c=1, p=1, d=1, menace=1, ferocious=1),
    'Pulse Tracker':        dict(k='C', c=1, p=1, d=1, atk_drain=1),
    'Burrog Banemaker':     dict(k='C', c=1, p=1, d=1, deathtouch=1, pump_self=1),
    'Engine Rat':           dict(k='C', c=1, p=1, d=1, deathtouch=1),
    # ── 2 费 ──
    'Desolation Prowler':   dict(k='C', c=2, p=2, d=2, pay_pump=1),
    'Sanguine Syphoner':    dict(k='C', c=2, p=1, d=3, atk_drain=1),
    'Umbral Collar Zealot': dict(k='C', c=2, p=3, d=2),
    'Vampire Gourmand':     dict(k='C', c=2, p=2, d=2, sac_draw_unblock=1),
    'Delta Bloodflies':     dict(k='C', c=2, p=1, d=2, fly=1, atk_drain_cond=1),
    'Agents of HYDRA':      dict(k='C', c=2, p=1, d=1, dies_token=1),
    'Knight of Malice':     dict(k='C', c=2, p=2, d=2, first_strike=1),
    'Merciless Enforcers':  dict(k='C', c=2, p=2, d=1, lifelink=1, sink_drain=1),
    'Gollum, Riddle Master': dict(k='C', c=2, p=3, d=1, leg=1),
    # ── 3 费 ──
    'Vampire Nighthawk':    dict(k='C', c=3, p=2, d=3, fly=1, deathtouch=1, lifelink=1),
    'Nullpriest of Oblivion': dict(k='C', c=2, p=2, d=1, menace=1, lifelink=1),
    'Sunset Saboteur':      dict(k='C', c=2, p=4, d=1, menace=1, atk_ctr=1),
    'Hunted Bonebrute':     dict(k='C', c=3, p=6, d=2, menace=1),
    'Sengir Vampire':       dict(k='C', c=4, p=4, d=4, fly=1),
    # ── 去除（金鱼 0 值，仅占位）──
    'Requiting Hex':        dict(k='S', c=1, removal=1),
    'Deadly Precision':     dict(k='S', c=1, removal=1),
    'Heartless Act':        dict(k='S', c=2, removal=1),
    'Dissection Practice':  dict(k='S', c=1, drain=1, pump1=1),
    'Melancholic Poet':     dict(k='C', c=2, p=2, d=2, repartee_drain=1),
}
LAND = 'Swamp'


class Game:
    def __init__(self, deck, rng, pen=1.0, menace_pen=0.9):
        self.rng = rng
        self.pen = pen
        self.mpen = menace_pen
        self.lib = deck[:]
        rng.shuffle(self.lib)
        self.hand = []
        self.lands = 0
        self.bf = []
        self.dmg = 0.0
        self.turn = 0
        self.spells = 0
        self.life = 20
        self.t3_short = False
        self.opening()

    def opening(self):
        """★ 伦敦调度（修正版）：起手 7 张；每次调度**手牌数 -1**（7→6→5）"""
        self.draw(7)
        size = 7
        for _ in range(2):
            if 2 <= sum(1 for c in self.hand if c == 'Swamp') <= 5:
                return
            size -= 1
            self.lib += self.hand
            self.rng.shuffle(self.lib)
            self.hand = []
            self.draw(size)

    def draw(self, n=1):
        for _ in range(n):
            if self.lib:
                self.hand.append(self.lib.pop())

    def drain(self, n=1):
        """生命流失 = 无条件直伤（非战斗通道）"""
        self.dmg += n
        self.life += n

    def power(self, b):
        p = b['p'] + b.get('ctr', 0) + b.get('temp', 0)
        return p

    def cast(self, name, mana):
        sp = POOL[name]
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
        if LAND in self.hand and self.lands < 12:
            self.hand.remove(LAND)
            self.lands += 1
        if self.turn == 3 and self.lands < 3:
            self.t3_short = True
        mana = self.lands
        guard = 0
        while guard < 20:
            guard += 1
            opts = [n for n in set(self.hand) if n != LAND and POOL[n]['c'] <= mana]
            if not opts:
                break
            opts.sort(key=lambda n: (-POOL[n]['c'], n))
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
    main, _ = parse_deck(path)
    deck = []
    for q, name in main:
        deck += [LAND] * q if name.startswith('Swamp') else [name] * q
    return deck


def run(deck, n, max_turn=14, pen=1.0):
    rng = random.Random(20260924)
    kills, stuck = [], 0
    for _ in range(n):
        g = Game(deck, rng, pen)
        k = None
        for t in range(1, max_turn + 1):
            if g.play_turn():
                k = t
                break
        kills.append(k or max_turn + 1)
        if g.t3_short:
            stuck += 1
    kills.sort()
    m = len(kills)
    return dict(mean=sum(kills) / m,
                t4=100.0 * sum(1 for x in kills if x <= 4) / m,
                t5=100.0 * sum(1 for x in kills if x <= 5) / m,
                t6=100.0 * sum(1 for x in kills if x <= 6) / m,
                stuck=100.0 * stuck / m)   # 卡地率 = T3 时未达 3 块地



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
    f = sys.argv[2] if len(sys.argv) > 2 else 'deck_mono_black.txt'
    deck = load_deck(resolve_deck_path(f))
    r = run(deck, n)
    rc = run(deck, n, pen=0.6)
    print('%-24s N=%-6d 公平 均杀 %.2f T4 %5.1f%% T5 %5.1f%% | 保守 均杀 %.2f | T3<3费 %.1f%%'
          % (os.path.basename(f), n, r['mean'], r['t4'], r['t5'], rc['mean'], r['stuck']))
