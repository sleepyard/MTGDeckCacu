#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双色金鱼模拟器（BO1 口径 · 低造价档）—— 共享工具，5 个色组通用

★ 双色独有：**卡色率**（有地但颜色不对）
   · 地源支持：基本地 + 公会门/生命地（common，横置）+ 稀有双色地（不横置）
   · 每张牌带颜色需求；施放前检查是否已凑齐

★ 伤害通道（沿用本项目历史修正）
   · **非战斗通道**：燃烧（burn）+ 生命流失（drain）→ 统一过 nc()，可被 Tomik 放大
   · **战斗通道**：只缩放战斗伤害；威胁/飞行按闪避系数
   · 伦敦调度必须减手牌（C8）

用法: python3 sim_dual.py <局数> <牌表文件> [--landspec 'guildgate:4,shock:0']
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import os, random, re, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mtga_cost import parse_deck

# ══════════ 地源（自由组合） ══════════
# 公会门/生命地：common，横置进场，产 2 色
# 稀有双色地（电震地类）：rare，付 2 血可不横置
LAND_DEF = {
    'guildgate': dict(kind='dual', tapped=True, cost=0, colors=None),   # None = 该色组两色
    'shock':     dict(kind='dual', tapped='life2', cost=1, colors=None),
    'temple':    dict(kind='dual', tapped=True, cost=1, colors=None),
    'basic':     dict(kind='basic', tapped=False, cost=0, colors=None),
}

# ══════════ 卡池（按色组补充；键=英文牌名） ══════════
# need: 需要的颜色（'B'/'R' 等）；k: C=生物 S=咒语 E=结界
POOL = {}


def C(name, cmc, kind, need, p=0, d=0, **tags):
    POOL[name] = dict(c=cmc, k=kind, need=need, p=p, d=d, tags=tags)


# ── BR 拉铎司（黑红）──
# 燃烧（非战斗通道）
C('Burst Lightning', 1, 'S', ('R',), burn=2)
C('Shock', 1, 'S', ('R',), burn=2)
C('Firebending Lesson', 1, 'S', ('R',), burn=2)
C('Channeled Dragonfire', 1, 'S', ('R',), burn=2)
C('Lightning Strike', 2, 'S', ('R',), burn=3)
C('Sear', 2, 'S', ('R',), burn=0)          # 只打生物 ⇒ 金鱼 0
C('Thunder Magic', 1, 'S', ('R',), burn=2)
C('Thunderdrum Soloist', 2, 'C', ('R',), p=1, d=3, per_instant=1)
# 生命流失（非战斗通道）
C('Dream Beavers', 1, 'C', ('B',), p=1, d=1, fly=1, etb_drain=1)
C('Pulse Tracker', 1, 'C', ('B',), p=1, d=1, atk_drain=1)
C('Vengeful Bloodwitch', 2, 'C', ('B',), p=1, d=1, ally_drain=1)
C('Gollum the Abandoned', 2, 'C', ('B',), p=2, d=2, etb_drain=1)
C('Dissection Practice', 1, 'S', ('B',), drain=1)
# 闪避威胁
C('Callous Inspector', 1, 'C', ('B',), p=1, d=1, menace=1)
C('Nighthowl Pursuer', 1, 'C', ('B',), p=1, d=1, menace=1, ferocious=1)
C('Desolation Prowler', 2, 'C', ('B',), p=2, d=2, pay_pump=1)
C('Umbral Collar Zealot', 2, 'C', ('B',), p=3, d=2)
C('Sanguine Syphoner', 2, 'C', ('B',), p=1, d=3, atk_drain=1)
C('Vampire Gourmand', 2, 'C', ('B',), p=2, d=2)
# 放大器
C('Tomik, Izzet Sparkmage', 2, 'C', ('R',), p=1, d=3, tomik=1, leg=1)
C('Master of Barbs', 2, 'C', ('R',), p=2, d=2, barbs=1)
C('Sunset Saboteur', 2, 'C', ('B',), p=4, d=1, menace=1)
C('Molten-Core Maestro', 2, 'C', ('R',), p=2, d=2, per_instant_ctr=1)
C('Slickshot Show-Off', 2, 'C', ('R',), p=1, d=2, fly=1, haste=1, pump2=2)
C('Hired Claw', 1, 'C', ('R',), p=1, d=1, atk_ping=1)


class Game:
    def __init__(self, deck, rng, landspec, pen=1.0, mpen=0.9):
        self.rng = rng
        self.pen = pen
        self.mpen = mpen
        self.lib = []
        self.lands_bf = []          # [{'colors':set,'tapped':bool}]
        self.hand = []
        self.bf = []
        self.dmg = 0.0
        self.turn = 0
        self.spells = 0
        self.colors = set()         # 当前可用颜色
        self.manasource = []        # 未横置地的产色
        self.color_screw = False
        self.hp = 20
        self.spec = landspec
        for name, q in deck:
            self.lib += [name] * q
        rng.shuffle(self.lib)
        self.opening()

    # ---- 起手（伦敦调度，减手牌）----
    def draw(self, n=1):
        for _ in range(n):
            if self.lib:
                self.hand.append(self.lib.pop())

    def opening(self):
        self.draw(7)
        size = 7
        for _ in range(2):
            nl = sum(1 for c in self.hand if self.is_land(c))
            if 2 <= nl <= 4:
                return
            size -= 1
            self.lib += self.hand
            self.rng.shuffle(self.lib)
            self.hand = []
            self.draw(size)

    # ★ 真实双色地 → 内部规格（α=免费横置 / β=稀有电震地）
    REAL_LAND = {
        # BR
        'Blood Crypt': 'Dual:shock_BR', 'Bloodfell Caves': 'Dual:guildgate_BR',
        # RG
        'Stomping Ground': 'Dual:shock_RG', 'Rugged Highlands': 'Dual:guildgate_RG',
        # GW
        'Temple Garden': 'Dual:shock_GW', 'Blossoming Sands': 'Dual:guildgate_GW',
        # UB
        'Watery Grave': 'Dual:shock_UB', 'Dismal Backwater': 'Dual:guildgate_UB',
        # WU
        'Hallowed Fountain': 'Dual:shock_WU', 'Tranquil Cove': 'Dual:guildgate_WU',
        # 其它常用
        'Sacred Foundry': 'Dual:shock_RW', 'Wind-Scarred Crag': 'Dual:guildgate_RW',
        'Godless Shrine': 'Dual:shock_WB', 'Scoured Barrens': 'Dual:guildgate_WB',
        'Steam Vents': 'Dual:shock_UR', 'Swiftwater Cliffs': 'Dual:guildgate_UR',
        'Overgrown Tomb': 'Dual:shock_BG', 'Jungle Hollow': 'Dual:guildgate_BG',
        'Breeding Pool': 'Dual:shock_GU', 'Thornwood Falls': 'Dual:guildgate_GU',
    }

    @classmethod
    def is_land(cls, n):
        return (n in ('Swamp', 'Mountain', 'Forest', 'Island', 'Plains')
                or n.startswith('Dual:') or n in cls.REAL_LAND)

    @classmethod
    def norm_land(cls, n):
        return cls.REAL_LAND.get(n, n)

    def land_colors(self, name):
        name = self.norm_land(name)
        if name == 'Swamp':
            return {'B'}
        if name == 'Mountain':
            return {'R'}
        if name == 'Forest':
            return {'G'}
        if name == 'Island':
            return {'U'}
        if name == 'Plains':
            return {'W'}
        if name.startswith('Dual:'):
            body = name[5:]
            kind, pair = body.split('_', 1)
            return set(pair)
        return set()

    # ---- 伤害入口 ----
    def nc(self, amt):
        if amt <= 0:
            return
        if any(b['tags'].get('tomik') for b in self.bf):
            amt += 1
        self.dmg += amt
        nb = sum(1 for b in self.bf if b['tags'].get('barbs'))
        self.team_pump = getattr(self, 'team_pump', 0) + nb

    def drain(self, n=1):
        """★ 规则要点：生命流失（'each opponent loses N life'）**不是伤害**。
        因此它 **不被 Tomik 放大**（Tomik 只改"非战斗伤害"），
        也 **不触发 Master of Barbs**（它要"被造成非战斗伤害"）。
        它的优势是：完全绕过阻挡与伤害防止。"""
        self.dmg += n

    def life_pay_ok(self):
        """电震地：付 2 血可不横置（模型取「生命 > 14 就付」）"""
        return getattr(self, 'hp', 20) > 14

    def power(self, b):
        return b['p'] + b.get('ctr', 0) + b.get('temp', 0)

    # ---- 回合 ----
    def play_turn(self):
        self.turn += 1
        self.spells = 0
        self.team_pump = 0
        for b in self.bf:
            b['temp'] = 0
        self.draw()
        # 下地
        land_idx = next((i for i, c in enumerate(self.hand) if self.is_land(c)), None)
        if land_idx is not None and len(self.lands_bf) < 12:
            name = self.hand.pop(land_idx)
            norm = self.norm_land(name)
            spec = LAND_DEF.get(norm[5:].split('_')[0], {}) if norm.startswith('Dual:') else LAND_DEF['basic']
            ta = spec.get('tapped', False)
            if ta == 'life2':
                # ★ 电震地：付 2 血 → **不横置**；不付则横置
                if self.life_pay_ok():
                    self.hp -= 2
                    enters_tapped = False
                else:
                    enters_tapped = True
            else:
                enters_tapped = bool(ta)
            self.lands_bf.append(dict(name=name, colors=self.land_colors(name),
                                      tapped=enters_tapped, fresh=True))
        # 上一回合的地重置为未横置
        for L in self.lands_bf:
            if not L.get('fresh'):
                L['tapped'] = False
        for L in self.lands_bf:
            L['fresh'] = False
        # 本回合可支付的颜色（按色计源数）
        self.sources = defaultdict(int)
        for L in self.lands_bf:
            if not L['tapped']:
                for c in L['colors']:
                    self.sources[c] += 1
        mana = len(self.lands_bf)
        # 贪心施放（按色检查需求）
        guard = 0
        while guard < 20:
            guard += 1
            opts = []
            for n in set(self.hand):
                if self.is_land(n) or n not in POOL:
                    continue
                sp = POOL[n]
                if sp['c'] > mana:
                    continue
                need = defaultdict(int)
                for c in sp['need']:
                    need[c] += 1
                if any(self.sources[c] < v for c, v in need.items()):
                    continue
                if sp.get('leg') and any(x['n'] == n for x in self.bf):
                    continue
                opts.append(n)
            if not opts:
                break
            opts.sort(key=lambda n: (-POOL[n]['c'], n))
            name = opts[0]
            sp = POOL[name]
            mana -= sp['c']
            for c in sp['need']:
                self.sources[c] -= 1
            self.hand.remove(name)
            self.spells += 1
            r = self.resolve(name, sp)
            if r == 'stop':
                break
        # T3 卡色检查：有至少 3 块地却凑不出任一主色
        if self.turn == 3 and len(self.lands_bf) >= 3 and not self.sources:
            self.color_screw = True
        # 攻击前：付血膨胀（Desolation Prowler：2 血换 +2/+2）
        for b in self.bf:
            if b['tags'].get('pay_pump') and self.hp > 6:
                self.hp -= 2
                b['temp'] += 2
        # 攻击触发流失
        drain_n = 0
        for b in self.bf:
            if b['tags'].get('atk_drain'):
                drain_n += 1
        if drain_n:
            self.drain(drain_n)
        # 战斗通道
        has4 = any(self.power(x) >= 4 for x in self.bf)
        dmg = 0
        for b in self.bf:
            v = self.power(b)
            if b['tags'].get('ferocious') and has4:
                v += 2
            if b['tags'].get('fly') or b['tags'].get('menace'):
                dmg += v * self.mpen
            else:
                dmg += v * self.pen
        self.dmg += dmg
        return self.dmg >= 20

    def resolve(self, name, sp):
        t = sp['tags']
        # 施放触发
        for b in self.bf:
            if b['tags'].get('per_instant') and sp['k'] != 'C':
                self.nc(b['tags']['per_instant'])
            if b['tags'].get('per_instant_ctr') and sp['k'] != 'C':
                b['ctr'] = b.get('ctr', 0) + 1
            if b['tags'].get('pump2') and sp['k'] != 'C':
                b['temp'] = b.get('temp', 0) + 2
        if t.get('atk_ping') and False:
            pass
        if sp['k'] == 'C':
            self.bf.append(dict(n=name, p=sp.get('p', 0), d=sp.get('d', 0), tags=t, ctr=0, temp=0))
            if t.get('etb_drain'):
                self.drain(t['etb_drain'])
            if t.get('ally_drain'):
                n = sum(1 for x in self.bf if x['tags'].get('ally_drain'))
                self.drain(n)
        else:
            if t.get('burn'):
                self.nc(t['burn'])
            if t.get('drain'):
                self.drain(t['drain'])
        return None


def run(deck, n, landspec, pen=1.0, max_turn=14):
    rng = random.Random(20260924)
    kills, cs = [], 0
    for _ in range(n):
        g = Game(deck, rng, landspec, pen)
        k = None
        for t in range(1, max_turn + 1):
            if g.play_turn():
                k = t
                break
        kills.append(k or max_turn + 1)
        if g.color_screw:
            cs += 1
    kills.sort()
    m = len(kills)
    return dict(mean=sum(kills) / m,
                t4=100.0 * sum(1 for x in kills if x <= 4) / m,
                t5=100.0 * sum(1 for x in kills if x <= 5) / m,
                cs=100.0 * cs / m)


def load(path):
    main, _ = parse_deck(path)
    out = []
    for q, n in main:
        out.append((n, q))
    return out



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
    f = sys.argv[2]
    deck = load(resolve_deck_path(f))
    r = run(deck, n, None)
    rc = run(deck, n, None, pen=0.6)
    print('%-26s N=%-6d 公平 均杀 %.2f T4 %5.1f%% | 保守 均杀 %.2f | 卡色 %.1f%%'
          % (os.path.basename(f), n, r['mean'], r['t4'], rc['mean'], r['cs']))
