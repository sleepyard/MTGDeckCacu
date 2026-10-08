#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""金鱼蒙特卡洛模拟器模板（Phase 3 起为薄壳：指向 goldfish 引擎写法）。

★ 标准做法（单色 / 单地哨兵马纳基）：复用 tools/newbie/goldfish/ 引擎——
  1. 在 tools/newbie/goldfish/data/<deck>.json 写牌池
     （schema 见 goldfish/engine.py docstring；机制 tag 须已在
     goldfish/mechanics.py 注册，纯标记位也由牌组代码内联消费）；
  2. 在 tools/newbie/goldfish/decks/<deck>.py 写一个 GameBase 子类，
     只需实现 init_state（状态口袋）与 play_turn（回合逻辑），
     洗牌/伦敦调度/抽牌/下地/击杀判定/统计全部继承；
  3. 用 goldfish.engine.run(Game, deck, n) 跑统计。
  下方 __main__ 给出一个不落盘的最小可运行示例。

★ 超出手册范围需自建时（如 sim_dual 的双色法术力源/痛地生命），
  仍按本文件 modeling spec 逐牌逐效果建模，并在报告声明模拟局限。

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
  4. 金鱼是"法术力受限"模型：抓牌/赚牌引擎的分不能被它裁决——引擎 run 的
     curve（按回合累计伤害）可用于 gas 观察，需要 idle/handN 等指标时经
     collect 钩子自行聚合；实测反馈优先于模拟分数。
  5. 贪心施放的排序键必须带牌名 tiebreaker（key=(-c, name)），否则同费牌
     顺序受 PYTHONHASHSEED 影响、结果跨进程不可复现（sim_mono_white 踩过）。

用法：python tools/goldfish_template.py  （运行下方最小示例）
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "newbie"))
from goldfish import mechanics  # noqa: F401,E402  触发机制 tag 注册
from goldfish.engine import GameBase, run  # noqa: E402


class DemoGame(GameBase):
    """最小示例：1 费 2/2 与 2 费 3/3 的纯打手（机制全部为内联标记位）。"""

    POOL = {
        "Savannah Lions": dict(k="C", c=1, p=2, d=2),
        "Jibbirik Omnivore": dict(k="C", c=2, p=3, d=3),
    }
    LAND = "Forest"

    def play_turn(self):
        self.turn += 1
        self.draw()
        self.play_land()
        mana = self.lands
        while True:
            opts = sorted({n for n in self.hand
                           if n != self.LAND and self.POOL[n]["c"] <= mana},
                          key=lambda n: (-self.POOL[n]["c"], n))   # ★ tiebreaker 必带
            if not opts:
                break
            name = opts[0]
            mana -= self.POOL[name]["c"]
            self.hand.remove(name)
            self.bf.append(dict(n=name, p=self.POOL[name]["p"], sick=1))
        dmg = 0
        for b in self.bf:
            if b["sick"]:
                b["sick"] = 0
                continue
            dmg += b["p"] * self.pen
        self.dmg += dmg
        return self.dmg >= 20


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    deck = ["Savannah Lions"] * 4 + ["Jibbirik Omnivore"] * 4 + ["Forest"] * 16
    r = run(DemoGame, deck, 8000)
    print("示例牌库（4×2/2 + 4×3/3 + 16 Forest）：均杀 %.2f T5 %.1f%% T6 %.1f%% 卡地 %.1f%%"
          % (r["mean"], r["t5"], r["t6"], r["stuck"]))
