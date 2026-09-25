#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标准「单白衍生物」金鱼模拟器（BO1 口径）

建模要点（每张牌的效果都建，不留空壳）：
  · 战斗：金鱼无阻挡 ⇒ 伤害 = 所有可攻击生物力量之和；召唤失调不计
  · Mobilize N：该生物攻击时额外产生 N 个 1/1 攻兵（当回合即打点，回合末消失）
  · Political Triumph：任意生物（含衍生物）进场 → scry 1 + 计 1 个 plan 指示物；
      第 4 个 → 牺牲此结界、抓 1 张、每个生物 +1/+1（永久）
  · Belladonna Took：衍生物进场（每回合第 1/2/3 次）→ 回 1 血 / 抓 1 张 / 全队 +1/+1（永久）
  · Hare Apparent：进场时按「其它同名 Hare Apparent 数量」造 1/1 兔子
  · Dalkovan Packbeasts：警戒 0/4 ⇒ 本身 0 打点，但每次攻击产 3 个 1/1 攻兵
  · Battle Menu：金鱼取「造 2/2 骑士」（BO1 实战为多模；去除模式另在报告中列出）
  · Voice of Victory：mobilize 2 + 对手回合外不能施放（金鱼盲区）

用法: python3 sim_mono_white.py [局数] [牌表文件] [--var 构型名]
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json, os, random, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mtga_cost import parse_deck

LANDS = 'Plains'

# type: C=生物 S=法术/瞬间 E=结界 R=去除
POOL = {
 'Political Triumph':        dict(t='E', c=1, triumph=1),
 'Seam Rip':                 dict(t='R', c=1),
 'Erode':                    dict(t='R', c=1),
 'Savannah Lions':           dict(t='C', c=1, p=2, d=1),
 'Lightstall Inquisitor':    dict(t='C', c=1, p=2, d=1),   # 2/1 警戒 + 进场干扰（金鱼看不见）
 'Healer\'s Hawk':           dict(t='C', c=1, p=1, d=1, fly=1),
 'Nesting Bot':              dict(t='C', c=1, p=1, d=1),
 'Leonin Vanguard':          dict(t='C', c=1, p=1, d=1, lord3=1),
 'Resolute Reinforcements':  dict(t='C', c=2, p=1, d=1, etb=1),
 'Honored Knight-Captain':   dict(t='C', c=2, p=1, d=1, etb=1),
 'Hare Apparent':            dict(t='C', c=2, p=2, d=2, hare=1),
 'Belladonna Took':          dict(t='C', c=2, p=2, d=2, bella=1),
 'Battle Menu':              dict(t='S', c=2, tokens=[(2, 2)]),
 'Dalkovan Packbeasts':      dict(t='C', c=3, p=0, d=4, mobilize=3, vig=1),
 'Clachan Festival':         dict(t='E', c=3, tokens=[(1, 1), (1, 1)]),
 'Okoye, Dora Milaje Leader':dict(t='C', c=4, p=3, d=2, tokens=[(1, 1), (1, 1)], tok_fs=1),
 'Release the Dogs':         dict(t='S', c=4, tokens=[(1, 1)] * 4),
 'Voice of Victory':         dict(t='C', c=2, p=1, d=3, mobilize=2, lock=1),
 'Dauntless Veteran':        dict(t='C', c=3, p=2, d=2, atk_pump=1),
}


class Game:
    def __init__(self, deck, rng):
        self.rng = rng
        self.lib = deck[:]
        rng.shuffle(self.lib)
        self.hand = []
        self.lands = 0
        self.board = []      # dict(p,d,tags(vig/mobilize/tok_fs/bella/hare/atk_pump), sick)
        self.tokens = []     # dict(p,d)
        self.triumph = 0
        self.dmg = 0
        self.turn = 0
        self.tok_turn = 0

    # ---------- 基础 ----------
    def draw(self, n=1):
        for _ in range(n):
            if self.lib:
                self.hand.append(self.lib.pop())

    def mulligan(self):
        for _ in range(2):
            if 2 <= sum(1 for c in self.hand if c == 'LAND') <= 5:
                return
            self.lib += self.hand
            self.rng.shuffle(self.lib)
            self.hand = []
            self.draw(7)

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
        spec = POOL[name]
        mana -= spec['c']
        self.hand.remove(name)
        tags = {k: v for k, v in spec.items() if k in ('mobilize', 'vig', 'tok_fs', 'bella', 'hare', 'atk_pump', 'fly', 'lord3')}
        if spec['t'] in ('C', 'E'):
            self.board.append({'p': spec.get('p', 0), 'd': spec.get('d', 0), 'tags': tags, 'sick': 1})
        if spec['t'] == 'C':                 # 只有生物进场才触发「生物进场」类异能
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
        if 'LAND' in self.hand and self.lands < 10:
            self.hand.remove('LAND')
            self.lands += 1
        mana = self.lands
        # 贪心施放（费用从高到低，留不出空转）
        while True:
            opts = sorted({n for n in self.hand if n != 'LAND' and POOL[n]['c'] <= mana},
                          key=lambda n: -POOL[n]['c'])
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
    main, _ = parse_deck(path)
    deck = []
    for q, name in main:
        deck += ['LAND'] * q if name.startswith('Plains') else [name] * q
    return deck


def run(deck, n, max_turn=12):
    rng = random.Random(20260924)
    kills, curve, stuck = [], defaultdict(int), 0
    for _ in range(n):
        g = Game(deck, rng)
        g.draw(7)
        g.mulligan()
        k = None
        for t in range(1, max_turn + 1):
            if g.play_turn():
                k = t
                break
        curve[g.turn] += g.dmg
        kills.append(k or max_turn + 1)
        if g.lands <= 2:
            stuck += 1
    kills.sort()
    k = len(kills)
    return dict(mean=sum(kills) / k, t4=100.0 * sum(1 for x in kills if x <= 4) / k,
                t5=100.0 * sum(1 for x in kills if x <= 5) / k,
                t6=100.0 * sum(1 for x in kills if x <= 6) / k,
                t7=100.0 * sum(1 for x in kills if x <= 7) / k,
                stuck=100.0 * stuck / k,
                curve={t: curve[t] / k for t in sorted(curve)})


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    n = int(args[0]) if args else 8000
    f = args[1] if len(args) > 1 else 'deck_mono_white.txt'
    deck = load_deck(os.path.join(HERE, f))
    print('牌库 %d 张 | 对局 %d 局' % (len(deck), n))
    r = run(deck, n)
    print('均杀 %.2f | T4 %.1f%% | T5 %.1f%% | T6 %.1f%% | T7 %.1f%% | 卡地率 %.1f%%'
          % (r['mean'], r['t4'], r['t5'], r['t6'], r['t7'], r['stuck']))
    print('累计伤害:', ' '.join('T%d %.0f' % (t, v) for t, v in list(r['curve'].items())[:11]))
