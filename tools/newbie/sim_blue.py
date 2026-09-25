#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纯蓝金鱼模拟器（BO1 口径）—— 用于对比"tempo 假设" vs "数据支持的轴"

★ 用户假设：纯蓝 tempo（弹回/反击 + 低费打手）
★ 数据结论：蓝池的真轴是「每回合第 2 次抽牌」触发链（L1 廉价抽牌 / L2 减费 / L3 二抽回报）
本模拟器把两条路线都建出来，用同一套码尺比较。

建模清单（全部来自 blue 池枚举，非任何前作）：
  L1 抽牌：Opt / Quick Study / Sphinx's Approach / Divining Duelist
  L2 增幅：Geist of Saint Thalia（非生物咒语减 {1}）；Seasoned Cryomancer（进场抽 2）
  L3 回报：Mischievous Mystic / Knowledge Seeker / Lakeshore Apothecary / Atlantean Cavalry /
           Erudite Wizard / Thopter Fabricator / Homunculus Horde / Lyra, Tolarian Archangel
  Tempo 侧：Elementalist Adept / Cryotheory Adept / Diversion Unit / Unsummon（金鱼 0 值）

⚠ 金鱼对蓝色的系统性偏差（报告须单列）：
  · 弹回（Unsummon）、反击（Countersculpt）、闪现 —— **对金鱼完全无价值**（没有对手/回合概念）
  · 因此 tempo 路线在金鱼里会被**严重低估**；二抽路线（造 token / 灌豆）能被如实测量
  · 结论必须结合"哪些价值金鱼看不见"来读

用法: python3 sim_blue.py <局数> <牌表文件>
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import os, random, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mtga_cost import parse_deck

# k: C=生物 S=法术/瞬间 | draw=n: 施放时抽 n 张（用于触发"第二抽"）
POOL = {
    # ── L1 抽牌 / 扳机 ──
    'Opt':                 dict(k='S', c=1, draw=1),
    'Unending Whisper':    dict(k='S', c=1, draw=1),
    'Fleeting Distraction': dict(k='S', c=1, draw=1),
    # ── 自身即有价值的低费生物 ──
    'Illvoi Galeblade':    dict(k='C', c=1, p=1, d=1, fly=1, sac_draw=1),
    'Spectral Sailor':     dict(k='C', c=1, p=1, d=1, fly=1),
    'Veteran Ice Climber': dict(k='C', c=2, p=1, d=3, vig=1, unblockable=1),
    "Mysterio's Phantasm": dict(k='C', c=2, p=1, d=3, fly=1, vig=1),
    'Elementalist Adept':  dict(k='C', c=2, p=2, d=1, prowess=1),
    # ── 「第二咒语」回报（触发率高于第二抽）──
    'Illvoi Operative':    dict(k='C', c=2, p=2, d=1, second_spell_ctr=1),
    'Wingblade Disciple':  dict(k='C', c=3, p=2, d=2, fly=1, second_spell_token=1),
    'Glen Elendra Guardian': dict(k='C', c=3, p=3, d=4, fly=1),
    'Sphinx of False Conclusions': dict(k='C', c=4, p=4, d=2, fly=1, atk_loot=1),
    'Kang the Conqueror':  dict(k='C', c=4, p=4, d=5, fly=1),
    'Beetle, Legacy Criminal': dict(k='C', c=4, p=3, d=3, fly=1),
    'Il Mheg Pixie':       dict(k='C', c=2, p=2, d=1, fly=1),
    'Justice, Vance Astrovik': dict(k='C', c=3, p=2, d=2, fly=1),
    'Ray Fillet, Man Ray': dict(k='C', c=4, p=3, d=3, fly=1),
    'Rook Turret':         dict(k='C', c=4, p=3, d=3, fly=1),
    'Aegis Sculptor':      dict(k='C', c=4, p=2, d=3, fly=1),
    'Giant-Sized Flying Ant': dict(k='C', c=4, p=3, d=2, fly=1),
    'Taigam, Master Opportunist': dict(k='C', c=2, p=2, d=2, flurry_copy=1, leg=1),
    'Quick Study':         dict(k='S', c=3, draw=2),
    "Sphinx's Approach":   dict(k='S', c=3, draw=2),
    'Flow State':          dict(k='S', c=2, dig=1),
    'Divining Duelist':    dict(k='C', c=3, p=3, d=2, etb_draw=1),
    # ── L3 二抽回报 ──
    'Mischievous Mystic':  dict(k='C', c=2, p=2, d=1, fly=1, sd_token=1),
    'Knowledge Seeker':    dict(k='C', c=2, p=2, d=1, vig=1, sd_ctr=1),
    'Lakeshore Apothecary': dict(k='C', c=2, p=1, d=2, vig=1, sd_ctr=1),
    'Otter-Penguin':       dict(k='C', c=2, p=2, d=1, sd_temp=1),
    'Atlantean Cavalry':   dict(k='C', c=3, p=3, d=2, vig=1, sd_ctr=1),
    'Erudite Wizard':      dict(k='C', c=3, p=2, d=3, sd_ctr=1),
    'Thopter Fabricator':  dict(k='C', c=3, p=4, d=4, fly=1, sd_token=1, leg=0),
    'Homunculus Horde':    dict(k='C', c=4, p=2, d=2, sd_copy=1),
    # ── L2 增幅 ──
    'Geist of Saint Thalia': dict(k='C', c=2, p=1, d=2, fly=1, cost_reduce=1),
    'Seasoned Cryomancer': dict(k='C', c=3, p=2, d=2, etb_draw=2),
    'Lyra, Tolarian Archangel': dict(k='C', c=3, p=3, d=3, fly=1, draw3_token=1, leg=1),
    # ── Tempo 侧（金鱼盲区）──
    'Elementalist Adept':  dict(k='C', c=2, p=2, d=1, prowess=1),
    'Brineborn Cutthroat': dict(k='C', c=2, p=2, d=1),
    'Cryotheory Adept':    dict(k='C', c=2, p=2, d=1, prowess=1),
    'Diversion Unit':      dict(k='C', c=2, p=2, d=1, fly=1),
    'Unsummon':            dict(k='S', c=1, blank=1),
    'Countersculpt':       dict(k='S', c=2, blank=1),
    'Geist of Saint Traft': dict(k='C', c=3, p=2, d=2, fly=1),
}
LAND = 'Island'


class Game:
    def __init__(self, deck, rng, pen=1.0):
        self.rng = rng
        self.pen = pen
        self.lib = deck[:]
        rng.shuffle(self.lib)
        self.hand = []
        self.lands = 0
        self.bf = []
        self.tokens = []
        self.dmg = 0.0
        self.turn = 0
        self.draws = 0          # 本回合抽牌数（二抽判定）
        self.reduced = False    # 本回合是否已有减费源
        self.stat = {}
        self.last_spell = None
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
        c = POOL[name]['c']
        if c > 0 and any(b['tags'].get('cost_reduce') for b in self.bf):
            if POOL[name]['k'] != 'C':       # 只减非生物咒语
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
            sp = POOL.get(self.copied) or {}
            if sp.get('draw'):
                self.draw(sp['draw'])

    def cast(self, name, mana):
        sp = POOL[name]
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
        if LAND in self.hand and self.lands < 12:
            self.hand.remove(LAND)
            self.lands += 1
        mana = self.lands
        guard = 0
        while guard < 24:
            guard += 1
            opts = [n for n in set(self.hand) if n != LAND and self.cost(n) <= mana]
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


def load_deck(path):
    main, _ = parse_deck(path)
    deck = []
    for q, name in main:
        deck += [LAND] * q if name.startswith('Island') else [name] * q
    return deck


def run(deck, n, max_turn=14, pen=1.0):
    rng = random.Random(20260924)
    kills, stuck = [], 0
    agg = defaultdict(int)
    for _ in range(n):
        g = Game(deck, rng, pen)
        k = None
        for t in range(1, max_turn + 1):
            if g.play_turn():
                k = t
                break
        kills.append(k or max_turn + 1)
        for kk, vv in g.stat.items():
            agg[kk] += vv
        if g.lands <= 2:
            stuck += 1
    kills.sort()
    m = len(kills)
    return dict(agg={k: v / n for k, v in agg.items()}, mean=sum(kills) / m,
                t5=100.0 * sum(1 for x in kills if x <= 5) / m,
                t6=100.0 * sum(1 for x in kills if x <= 6) / m,
                t8=100.0 * sum(1 for x in kills if x <= 8) / m,
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
    f = sys.argv[2] if len(sys.argv) > 2 else 'deck_mono_blue.txt'
    deck = load_deck(resolve_deck_path(f))
    r = run(deck, n)
    rc = run(deck, n, pen=0.6)
    print('%-26s N=%-6d 公平 均杀 %.2f T5 %5.1f%% T6 %5.1f%% | 保守 均杀 %.2f | 卡地 %.1f%%'
          % (os.path.basename(f), n, r['mean'], r['t5'], r['t6'], rc['mean'], r['stuck']))
    if r['agg']:
        print('      触发统计/局：第二抽 %.2f 次 ｜ 第二咒语 %.2f 次 ｜ Lyra造天使 %.2f 个'
              % (r['agg'].get('sd', 0), r['agg'].get('ss', 0), r['agg'].get('lyra', 0)))
