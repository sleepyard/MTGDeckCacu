#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纯绿金鱼模拟器（BO1 口径 · 低造价档）

轴线：**地落 → +1/+1 豆 → 转化**（三层链路）
  L1 使能：Sazh's Chocobo（地落放豆）、下地本身
  L2 增幅：Mossborn Hydra（自身豆数翻倍 = 指数）、Mightform Harmonizer（力量翻倍）、
           Icetill Explorer（每回合额外下地 = 地落触发翻倍）
  L3 回报：Inspiring Call（每个带豆生物抓一张 + 不灭）、Meltstrider Eulogist（带豆生物死亡→抓牌）

建模清单来源：green 池枚举 + 环境牌表观察（绿池无历史工程，真盲测）。
建模规范：
  · 地落按"本回合放进战场的地数"逐次触发（自然下地 1 次 + 找地咒语 + 额外下地）
  · 战斗伤害与非战斗分开；保守口径只缩放战斗通道
  · Cactuar：回合末若本回合未进场则回手 ⇒ 每回合 {G} 可重铸
  · Inspiring Call：按"带豆生物数"抓牌，并给它们不灭（本模拟只计抓牌与存活）
  · 排序键含牌名 tiebreaker（保证可复现）

用法: python3 sim_green.py <局数> <牌表文件>
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import os, random, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mtga_cost import parse_deck

# k: C=生物 S=法术 | land_ramp: 施放时放进战场的地数
POOL = {
    # ── L1 使能 ──
    "Sazh's Chocobo":       dict(k='C', c=1, p=0, d=1, landfall_ctr=1),
    'Llanowar Elves':       dict(k='C', c=1, p=1, d=1, dork=1),
    'Gene Pollinator':      dict(k='C', c=1, p=1, d=1, dork2=1),
    # ── L2 增幅 ──
    'Mossborn Hydra':       dict(k='C', c=3, p=0, d=0, trample=1, start_ctr=1, landfall_double=1),
    'Mightform Harmonizer': dict(k='C', c=4, p=4, d=4, landfall_dblpow=1),
    'Icetill Explorer':     dict(k='C', c=4, p=2, d=4, extra_land=1),
    # ── L3 回报 ──
    'Inspiring Call':       dict(k='S', c=3, inspire=1),
    'Meltstrider Eulogist': dict(k='C', c=3, p=3, d=3, eulogist=1),
    # ── 曲线 / 打手 ──
    'Cactuar':              dict(k='C', c=1, p=3, d=3, trample=1, bounce_back=1),
    'Jibbirik Omnivore':    dict(k='C', c=2, p=3, d=2),
    'Bejeweled Warg':       dict(k='C', c=2, p=3, d=2, trample=1),
    'Frenzied Baloth':      dict(k='C', c=2, p=3, d=2, trample=1, haste=1),
    'Marwyn, the Preserver': dict(k='C', c=2, p=3, d=2),
    'Afterburner Expert':   dict(k='C', c=3, p=4, d=2),
    'Champion of Dusan':    dict(k='C', c=3, p=4, d=2, trample=1),
    'Thrashing Brontodon':  dict(k='C', c=3, p=3, d=4),
    'Eager Trufflesnout':   dict(k='C', c=3, p=4, d=2, trample=1),
    'Beast-Kin Ranger':     dict(k='C', c=3, p=3, d=3, trample=1),
    'Crossroads Watcher':   dict(k='C', c=3, p=3, d=3, trample=1),
    'Attuned Hunter':       dict(k='C', c=3, p=3, d=3, trample=1),
    'Budding Insurgent':    dict(k='C', c=3, p=3, d=3),
    'Vinebred Brawler':     dict(k='C', c=3, p=4, d=2),
    'Sureshot Sower':       dict(k='C', c=2, p=3, d=1),
    'Wary Thespian':        dict(k='C', c=2, p=3, d=1),
    'Little Bear':          dict(k='C', c=3, p=3, d=2),
    'Skystinger':           dict(k='C', c=3, p=3, d=3),
    'Loporrit Scout':       dict(k='C', c=3, p=3, d=2),
    "Garruk's Uprising":    dict(k='E', c=3, mass_trample=1, power4_draw=1),
    'Elvish Archdruid':     dict(k='C', c=3, p=2, d=2, elf_lord=1, lord_dork=1),
    'Regal Imperiosaur':    dict(k='C', c=3, p=5, d=4, dino_lord=1),
    'Mutagen Man, Living Ooze': dict(k='C', c=4, p=2, d=3, trample=1, mutagen=2),
    'Surrak, Elusive Hunter': dict(k='C', c=3, p=4, d=3, trample=1),
    # ── 互动 / 保护 ──
    "Meltstrider's Resolve": dict(k='S', c=1, ctr_fight=1),
    'Snakeskin Veil':       dict(k='S', c=1, ctr_pump=1),
    # ── 找地（= 多一次地落）──
    'Shared Roots':         dict(k='S', c=2, land_ramp=1),
    'Escape Tunnel':        dict(k='S', c=0, land_ramp=1, from_land=1),
    'Bushwhack':            dict(k='S', c=1, land_ramp=1),
    'Glimpse the Core':     dict(k='S', c=2, land_ramp=1),
}
LAND = 'Forest'


class Game:
    def __init__(self, deck, rng, pen=1.0):
        self.rng = rng
        self.pen = pen
        self.lib = deck[:]
        rng.shuffle(self.lib)
        self.hand = []
        self.lands = 0
        self.bf = []
        self.dmg = 0.0
        self.turn = 0
        self.landfall = 0        # 本回合地落次数
        self.pending = []        # 本回合待结算的地落触发
        self.opening()

    def opening(self):
        """★ 伦敦调度（修正版）：起手 7 张；每次调度**手牌数 -1**（7→6→5）"""
        self.draw(7)
        size = 7
        for _ in range(2):
            if 2 <= sum(1 for c in self.hand if c == 'Forest') <= 5:
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

    # ---------- 地落 ----------
    def do_landfall(self, n=1):
        """每有一块地进场，所有地落触发件各触发一次"""
        for _ in range(n):
            self.landfall += 1
            for b in self.bf:
                t = b['tags']
                if t.get('landfall_ctr'):
                    b['ctr'] = b.get('ctr', 0) + 1
                if t.get('landfall_double'):
                    c = b.get('ctr', 0)
                    b['ctr'] = c * 2 if c else 1
                if t.get('landfall_dblpow'):
                    b['perm_pow'] = b.get('perm_pow', 0) + b['p'] + b.get('ctr', 0)

    def extra_lands(self):
        return sum(1 for b in self.bf if b['tags'].get('extra_land'))

    def has_power4(self):
        return any(self.power(x) >= 4 for x in self.bf)

    def has_trample(self, b):
        return bool(b['tags'].get('trample')) or any(x['tags'].get('mass_trample') for x in self.bf)

    def power(self, b):
        return b['p'] + b.get('ctr', 0) + b.get('perm_pow', 0)

    def play_land(self):
        if LAND in self.hand:
            self.hand.remove(LAND)
            self.lands += 1
            self.do_landfall(1)

    # ---------- 施放 ----------
    def cast(self, name, mana):
        sp = POOL[name]
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
            opts = [n for n in set(self.hand) if n != LAND and POOL[n]['c'] <= mana]
            if not opts:
                break
            opts.sort(key=lambda n: (-POOL[n]['c'], n))
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
    main, _ = parse_deck(path)
    deck = []
    for q, name in main:
        deck += [LAND] * q if name.startswith('Forest') else [name] * q
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
        if g.lands <= 2:
            stuck += 1
    kills.sort()
    m = len(kills)
    return dict(mean=sum(kills) / m,
                t5=100.0 * sum(1 for x in kills if x <= 5) / m,
                t6=100.0 * sum(1 for x in kills if x <= 6) / m,
                t7=100.0 * sum(1 for x in kills if x <= 7) / m,
                stuck=100.0 * stuck / m)



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
    f = sys.argv[2] if len(sys.argv) > 2 else 'deck_mono_green.txt'
    deck = load_deck(resolve_deck_path(f))
    r = run(deck, n)
    rc = run(deck, n, pen=0.6)
    print('%-26s N=%-6d 公平 均杀 %.2f T5 %5.1f%% T6 %5.1f%% | 保守 均杀 %.2f | 卡地 %.1f%%'
          % (os.path.basename(f), n, r['mean'], r['t5'], r['t6'], rc['mean'], r['stuck']))
