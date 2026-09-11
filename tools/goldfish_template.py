#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""金鱼蒙特卡洛模拟器模板（融合自外部 mtg-deck-builder v1.4.0 技能包）。

用途：对比不同构筑构型的铺场速度 / 累计伤害 / 法术力健康度。
口径与建模规范详见 MtgDeckCacuWorkFlow.md 阶段 3「金鱼蒙特卡洛构型对比」。

⚠️ 建模规范（历史重灾，务必遵守）：
  1. 每张牌的【每个效果】都要建模——禁止对某张牌只建一半/漏建。
     - 持续触发（每回合 / Whenever）→ 循环内逐回合结算；
     - 条件触发（"若 X 则 Y"）→ X、Y 分别建模；
     - 减费 → 动态按当前场面计算实际费用（costs {X} less 只减通用费用，
       最多减到有色符号为止，见工作流阶段 0c 第 2 条）；
     - 免费施放（Hideaway/发现等）→ 按"看 N 选 1"真实逻辑（生物/永久物优先于地）。
  2. 报告必须声明模拟局限（去除/咬/应对干扰无法被金鱼衡量），据此修正结论。
  3. 若对比"砍某牌 vs 保留某牌"，务必确认被对比的牌在模拟里真的有效果——
     否则会系统性低估"保留方"，得出错误结论。
  4. 金鱼是"法术力受限"模型：抓牌/赚牌引擎的分不能被它裁决，必须同时输出
     idle / hand6 / hand8 等 gas 指标；实测反馈优先于模拟分数。

用法：改 CARDS / LANDS / DECKS 三处，然后 `python tools/goldfish_template.py`。
"""
import random, collections, time, sys

# ============ 牌定义：name -> dict(cmc, type, power, tags) ============
CARDS = {}
def C(name, cmc, type_, power=0, tags=()):
    CARDS[name] = dict(cmc=cmc, type=type_, power=power, tags=set(tags))

# 示例（换成你的牌）：
C("Bonecrusher Giant", 3, "creature", 4)                 # 历险打2是互动，金鱼无对手→只算生物面
C("Slumbering Trudge", 4, "creature", 6, ("trudge",))    # X 费牌单独处理
C("Sarkhan's Unsealing", 4, "enchant")                    # 触发型引擎，在 resolve/combat 里结算
C("Fight Rigging", 3, "enchant", tags=("rigging",))       # 每回合+1/+1 + 免费放逐，两个效果都要建
C("Goreclaw, Terror of Qal Sisma", 4, "creature", 4, ("goreclaw",))  # 减费引擎

# ============ 地：name -> (色, 横置规则) ============
# 横置规则: always(不横置) / slow(需2块其他地) / fast(需≤2块其他地) / tapped(必横置) / pain(痛地)
LANDS = {
    "Stomping Ground": ("RG", "always"),
    "Rockfall Vale": ("RG", "slow"),
    "Forest": ("G", "always"),
    "Restless Ridgeline": ("RG", "tapped"),
}

class Game:
    def __init__(self, deck, rng):
        self.rng = rng
        self.lib = list(deck); rng.shuffle(self.lib)
        self.hand = [self.lib.pop() for _ in range(7)]
        self.lands = []            # [name, tapped]
        self.bf = []               # [name, turn_entered, extra]
        # —— 每张"状态型引擎"都要一个计数器 ——
        self.unsealing = 0
        self.goreclaw = 0
        # ... 新增引擎状态字段
        self.dmg_unseal = 0
        self.dmg_combat = 0
        self.dmg_other = 0
        self.mulls = 0
        self.idle = 0            # T3+ 空转回合数（有 3+ 未用费却无牌可打）
        self.hand_end = []       # 每回合结束手牌数（gas 代理）
        self.mulligan()

    def mulligan(self):
        for _ in range(3):
            nl = sum(1 for c in self.hand if c in LANDS)
            if 2 <= nl <= 5:
                return
            self.lib += self.hand
            self.rng.shuffle(self.lib)
            self.hand = [self.lib.pop() for _ in range(7)]
            self.mulls += 1

    def drawone(self, n=1):
        for _ in range(n):
            if self.lib:
                self.hand.append(self.lib.pop())

    # ---------- 法术力 ----------
    def free_lands(self):
        return [l for l, t in self.lands if not t]

    def can_cast(self, cost, need):
        free = self.free_lands()
        if len(free) < cost:
            return False
        g = sum(1 for l in free if "G" in LANDS[l][0])
        r = sum(1 for l in free if "R" in LANDS[l][0])
        ng, nr = need.count("G"), need.count("R")
        if ng + nr > len(free):
            return False
        dual = sum(1 for l in free if set(LANDS[l][0]) == {"R", "G"})
        return (g >= ng or g + dual >= ng) and (r >= nr or r + dual >= nr)

    def pay(self, cost, need):
        free = sorted(self.free_lands(), key=lambda l: 0 if (need and need[0] in LANDS[l][0]) else 1)
        for l in free[:cost]:
            for i, (ln, t) in enumerate(self.lands):
                if ln == l and not t:
                    self.lands[i][1] = True
                    break

    # ---------- 费用（减费要动态算） ----------
    def eff_cost(self, name):
        c = CARDS[name]
        cost = c["cmc"]
        if c["type"] == "creature" and c["power"] >= 4:
            cost -= 2 * self.goreclaw          # Goreclaw 减费
        # 其他减费（如 Ghalta 按总力量、Great Henge 按最大力量）在这里加
        return max(0, cost)

    def need_color(self, name):
        c = CARDS[name]
        if c["type"] == "creature":
            return "RR" if name == "Trumpeting Carnosaur" else "G"
        return "R" if name == "Sarkhan's Unsealing" else "G"

    # ---------- 施放：每个触发效果都在这结算 ----------
    def resolve(self, name, turn):
        c = CARDS[name]
        if name == "Sarkhan's Unsealing":
            self.unsealing += 1; return
        if c["type"] != "creature":
            self.bf.append([name, turn, 0]); return
        p = c["power"]
        if self.unsealing and p >= 4:          # 触发型：施放时结算
            self.dmg_unseal += 4 * self.unsealing
        if "goreclaw" in c["tags"]:
            self.goreclaw = 1
        self.bf.append([name, turn, 0])

    def cast_loop(self, turn):
        progressed = True
        while progressed:
            progressed = False
            for name in ("Sarkhan's Unsealing", "Fight Rigging"):   # 引擎优先
                if name in self.hand:
                    cost = self.eff_cost(name)
                    if self.can_cast(cost, self.need_color(name)):
                        self.hand.remove(name); self.pay(cost, self.need_color(name))
                        self.resolve(name, turn); progressed = True; break
            if progressed: continue
            cre = sorted([c for c in self.hand if c in CARDS and CARDS[c]["type"] == "creature"],
                         key=lambda n: CARDS[n]["cmc"])
            for name in cre:
                cost = self.eff_cost(name)
                if self.can_cast(cost, self.need_color(name)):
                    self.hand.remove(name); self.pay(cost, self.need_color(name))
                    self.resolve(name, turn); progressed = True; break

    # ---------- 战斗：持续触发（每回合）在战斗阶段结算 ----------
    def combat(self, turn):
        # 例：Fight Rigging 每回合 +1/+1 给最高力量生物；若≥7 免费放逐——都要建
        for b, t, e in self.bf:
            c = CARDS[b]
            if c["type"] != "creature":
                continue
            p = c["power"]
            sick = (t == turn)
            # haste 判定在这里加
            if sick:
                continue
            self.dmg_combat += p

    def play_turn(self, turn):
        if turn > 1:
            self.drawone(1)
        for i in range(len(self.lands)):
            self.lands[i][1] = False
        # 下地（优先不横置的地）
        lh = [c for c in self.hand if c in LANDS]
        if lh:
            def score(l):
                kind = LANDS[l][1]
                if kind == "tapped":
                    return 6
                if kind == "slow" and len(self.lands) < 2:
                    return 5
                if kind == "fast" and len(self.lands) > 2:
                    return 4
                return 0
            lh.sort(key=score)
            l = lh[0]; self.hand.remove(l)
            kind = LANDS[l][1]
            tapped = kind == "tapped" or (kind == "slow" and len(self.lands) < 2)
            self.lands.append([l, tapped])
        self.cast_loop(turn)
        self.combat(turn)

def run(deck, games=20000, turns=8, seed=20260910):
    rng = random.Random(seed)
    agg = collections.defaultdict(float)
    for _ in range(games):
        g = Game(deck, rng)
        snap = {}
        for turn in range(1, turns + 1):
            g.play_turn(turn)
            for k, t in (("T4", 4), ("T6", 6), ("T8", 8)):
                if turn == t:
                    snap[k] = g.dmg_unseal + g.dmg_combat + g.dmg_other
            # —— gas 指标：T3+ 若有 3+ 未用费＝手上没东西可打（"空开"）
            if turn >= 3 and len(g.free_lands()) >= 3:
                g.idle += 1
            g.hand_end.append(len(g.hand))     # 回合末手牌数
        for k in ("T4", "T6", "T8"):
            agg[k + "_dmg"] += snap.get(k, 0)
        agg["lands"] += len(g.lands)
        agg["cre"] += sum(1 for b, t, e in g.bf if CARDS[b]["type"] == "creature")
        # 【强制】抓牌引擎的价值不能用金鱼伤害分裁决（金鱼是法术力受限模型），
        #        必须同时输出 idle / hand6 / hand8 做 gas 代理。
        agg["idle"] += g.idle
        agg["hand6"] += g.hand_end[5] if len(g.hand_end) > 5 else 0
        agg["hand8"] += g.hand_end[7] if len(g.hand_end) > 7 else 0
    return {k: v / games for k, v in agg.items()}

# ============ 构型 ============
DECKS = {}
DECKS["示例A"] = ["Stomping Ground"]*4 + ["Rockfall Vale"]*4 + ["Forest"]*4 + \
    ["Bonecrusher Giant"]*4 + ["Sarkhan's Unsealing"]*4 + ["Fight Rigging"]*2

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"{'构型':20} {'T4伤害':>7} {'T6伤害':>7} {'T8伤害':>7} {'生物':>5} {'地':>5}")
    for name, deck in DECKS.items():
        t0 = time.time()
        r = run(deck, games=10000, turns=8)
        print(f"{name:20} {r['T4_dmg']:7.2f} {r['T6_dmg']:7.2f} {r['T8_dmg']:7.2f} "
              f"{r['cre']:5.2f} {r['lands']:5.2f}  ({time.time()-t0:.1f}s)")
