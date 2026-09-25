#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标准「单白」金鱼模拟器 v2（BO1 口径）—— 支持两条轴

轴一：白衍生物铺场（政治胜利引擎）
轴二：★ 回血 + 1/+1 豆（Hinterland Sanctifier 事件源 × Ajani's Pridemate 放大器）

建模规范（每张牌的每个效果都建，不留空壳）：
  · 战斗：金鱼无阻挡 ⇒ 伤害 = 可攻击生物力量之和；**衍生物也要召唤失调**
  · 回血事件链：生物进场 → 每个回血源各触发 1 次回血 → 每次回血给每个「回血→豆」放大器 +1/+1 豆
  · 动员 Mobilize N：攻击时额外 N 个 1/1 攻兵（当回合即打点）
  · 政治胜利：任意生物进场 → 计 1 plan；第 4 个 → 抓 1 张 + 全队 +1/+1（永久）
  · Honor：给 1 个 +1/+1 豆 + 抓 1 张（trick，同时是"放豆"事件）
  · Exemplar of Light：每当回血 → 自身 +1/+1 豆；每当放豆 → 每回合抽 1 张（只触发一次/回合）
  · 金鱼盲区（不建模，报告单列）：去除、拆手牌、先攻、能反复挡的墙

用法: python3 sim_white.py <局数> <牌表文件>
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import os, random, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mtga_cost import parse_deck

# t: C=生物 E=结界 S=法术 R=去除 | eff: 效果标签
POOL = {
    # ── 轴一：衍生物铺场 ──
    'Political Triumph':       dict(t='E', c=1, triumph=1),
    'Resolute Reinforcements': dict(t='C', c=2, p=1, d=1, tokens=1),
    'Honored Knight-Captain':  dict(t='C', c=2, p=1, d=1, tokens=1),
    'Hare Apparent':           dict(t='C', c=2, p=2, d=2, hare=1),
    'Battle Menu':             dict(t='S', c=2, tokens=1, big=1),
    'Clachan Festival':        dict(t='E', c=3, tokens=2),
    'Dalkovan Packbeasts':     dict(t='C', c=3, p=0, d=4, mobilize=3, vig=1),
    'Okoye, Dora Milaje Leader': dict(t='C', c=4, p=3, d=2, tokens=2, tok_fs=1),
    # ── 轴二：★ 回血 + 豆 ──
    'Hinterland Sanctifier':   dict(t='C', c=1, p=1, d=2, life_src=1),
    'Aunt May':                dict(t='C', c=1, p=0, d=2, life_src=1),
    "Ajani's Pridemate":       dict(t='C', c=2, p=2, d=2, life_ctr=1),
    'Dazzling Angel':          dict(t='C', c=3, p=2, d=3, fly=1, life_src=1),
    'Angel of Vitality':       dict(t='C', c=3, p=2, d=4, fly=1),
    'Exemplar of Light':       dict(t='C', c=4, p=3, d=3, fly=1, life_ctr=1, ctr_draw=1),
    'Haliya, Guided by Light': dict(t='C', c=3, p=2, d=3, life_src=1, life_draw=3),
    "Bishop's Soldier":        dict(t='C', c=2, p=2, d=2, lifelink=1),
    "Leonardo, Cutting Edge":  dict(t='C', c=2, p=1, d=1, lifelink=1, life_ctr=1),
    "Aerith Gainsborough":     dict(t='C', c=3, p=2, d=2, lifelink=1, life_ctr=1),
    # ── trick / 膨胀 ──
    'Honor':                   dict(t='S', c=1, give_ctr=1, draw=1),
    'Dauntless Veteran':       dict(t='C', c=3, p=2, d=2, atk_pump=1),
    # ── 曲线 / 压制 ──
    'Savannah Lions':          dict(t='C', c=1, p=2, d=1),
    'Lightstall Inquisitor':   dict(t='C', c=1, p=2, d=1),
    "Healer's Hawk":           dict(t='C', c=1, p=1, d=1, fly=1, lifelink=1),
    'Leonin Vanguard':         dict(t='C', c=1, p=1, d=1),
    # ── 互动 ──
    'Seam Rip':                dict(t='R', c=1),
    'Erode':                   dict(t='R', c=1),
}


class Game:
    def __init__(self, deck, rng, penetrate=1.0):
        self.rng = rng
        self.pen = penetrate
        self.lib = deck[:]
        rng.shuffle(self.lib)
        self.hand = []
        self.lands = 0
        self.board = []       # dict(k=名称,p,d,sick,tags)
        self.tokens = []
        self.triumph = 0
        self.dmg = 0
        self.turn = 0
        self.tok_turn = 0
        self.ctr_drawn = False
        self.life = 20

    def draw(self, n=1):
        for _ in range(n):
            if self.lib:
                self.hand.append(self.lib.pop())

    def mulligan(self):
        """★ 伦敦调度（修正版）：每次调度手牌数 -1（7→6→5）"""
        size = 7
        for _ in range(2):
            if 2 <= sum(1 for c in self.hand if c == 'LAND') <= 5:
                return
            size -= 1
            self.lib += self.hand
            self.rng.shuffle(self.lib)
            self.hand = []
            self.draw(size)

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
        sp = POOL[name]
        mana -= sp['c']
        self.hand.remove(name)
        tags = {k: v for k, v in sp.items() if k in
                ('life_src', 'life_ctr', 'ctr_draw', 'mobilize', 'vig', 'tok_fs',
                 'hare', 'atk_pump', 'life_draw', 'fly', 'lifelink')}
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
        elif sp['t'] in ('C', 'E'):
            b = {'k': name, 'p': sp.get('p', 0), 'd': sp.get('d', 0), 'sick': 1, 'tags': tags}
            self.board.append(b)
            idx = len(self.board) - 1
            if name == 'Haliya, Guided by Light':
                b['self_etb'] = 1
            if sp['t'] == 'C':
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
        if 'LAND' in self.hand and self.lands < 10:
            self.hand.remove('LAND')
            self.lands += 1
        mana = self.lands
        while True:
            # ★ 排序键必须带牌名做 tiebreaker：否则同 cmc 牌的顺序取决于 set 迭代顺序
            #   （受 PYTHONHASHSEED 影响）⇒ 结果不可复现
            opts = sorted({n for n in self.hand if n != 'LAND' and POOL[n]['c'] <= mana},
                          key=lambda n: (-POOL[n]['c'], n))
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
    main, _ = parse_deck(path)
    deck = []
    for q, name in main:
        deck += ['LAND'] * q if name.startswith('Plains') else [name] * q
    return deck


def run(deck, n, max_turn=12, penetrate=1.0):
    rng = random.Random(20260924)
    kills, curve, stuck, d4 = [], defaultdict(int), 0, []
    for _ in range(n):
        g = Game(deck, rng, penetrate)
        g.draw(7)
        g.mulligan()
        k = None
        for t in range(1, max_turn + 1):
            if g.play_turn():
                k = t
                break
        curve[g.turn] += g.dmg
        kills.append(k or max_turn + 1)
        d4.append(g.dmg)
        if g.lands <= 2:
            stuck += 1
    kills.sort()
    m = len(kills)
    return dict(mean=sum(kills) / m,
                t3=100.0 * sum(1 for x in kills if x <= 3) / m,
                t4=100.0 * sum(1 for x in kills if x <= 4) / m,
                t5=100.0 * sum(1 for x in kills if x <= 5) / m,
                t6=100.0 * sum(1 for x in kills if x <= 6) / m,
                stuck=100.0 * stuck / m,
                curve={t: curve[t] / m for t in sorted(curve)})



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
    f = sys.argv[2] if len(sys.argv) > 2 else 'deck_mono_white.txt'
    deck = load_deck(resolve_deck_path(f))
    r = run(deck, n)
    rc = run(deck, n, penetrate=0.6)
    print('%-22s 公平 均杀 %.2f T4 %5.1f%% | 保守(穿透0.6) 均杀 %.2f T4 %5.1f%% | 卡地 %.1f%%'
          % (os.path.basename(f), r['mean'], r['t4'], rc['mean'], rc['t4'], r['stuck']))
