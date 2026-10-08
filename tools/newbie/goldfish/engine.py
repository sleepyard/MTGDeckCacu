#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""金鱼模拟引擎（底层架构强化计划 Phase 3）。

newbie/ 下 8 个 sim_*.py 的同构骨架（洗牌 → 调度 → 回合循环 → 击杀判定 →
统计）收敛于此；机制差异通过【注册表 + 每牌组 Game 子类】注入：

  register_handler(tag, fn)   机制注册表。fn 签名 (game, card, value)，
                              在通用触发点（如地落）按 tag 分发；
                              fn=None 表示纯数据标记位——由牌组代码内联消费
                              （与原 sim 一致），注册仅为 data JSON 的 schema
                              校验与自我描述。
  GameBase                    同构骨架：洗牌、伦敦调度（7→6→5）、draw、
                              play_land、is_stuck。牌组特有状态（gy_spell/
                              spells/team_pump/tokens…）经 init_state() 钩子
                              以动态属性挂载——与历史代码同构，降低搬运失真。
  run(game_cls, deck, n, ...) 回合循环 + 击杀判定（dmg>=20）+ 统计。
  load_pool(path)             data/<deck>.json 加载与 schema 校验。
  expand(main_pairs, ...)     牌表主牌 [(qty,name)] → [name]*qty 展开
                              （基本地前缀映射为地哨兵）。

data/<deck>.json schema：
  {"land": "Forest",           # 牌库里的地哨兵（mono_white/white 为 "LAND"）
   "basic_prefix": "Forest",   # load_deck 时按此前缀把基本地名映射为哨兵
   "pool": {name: {"k": "C",   # 类别（C=生物 S=咒语 E=结界 R=互动…，牌组自定义）
                   "c": 3,     # 费用（int >= 0）
                   "p": 2,     # 力量（int >= 0，非生物为 0）
                   "d": 2,     # 防御（int >= 0，非生物为 0）
                   <tag>: …}}  # 机制标记，必须已在注册表（未知 tag 报错）
  }
"""

import json
import os
import random
import sys
from collections import defaultdict
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))      # tools/newbie/goldfish
NEWBIE = os.path.dirname(HERE)                         # tools/newbie
TOOLS = os.path.dirname(NEWBIE)                        # tools
for _p in (TOOLS, NEWBIE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

HANDLERS = {}
DATA_DIR = Path(__file__).resolve().parent / "data"


def register_handler(tag, fn=None):
    """注册机制 tag。fn 为 None 时登记纯标记位；作装饰器用时注册实体 handler。"""
    if fn is None:
        HANDLERS.setdefault(tag, None)
        return lambda f: register_handler(tag, f)
    HANDLERS[tag] = fn
    return fn


# ---------------------------------------------------------------- 数据加载
_POOL_REQUIRED = (("k", str), ("c", int), ("p", int), ("d", int))


def load_pool(path):
    """加载 data/<deck>.json 并做 schema 校验，返回 (land_token, basic_prefix, pool)。

    校验：必有键 k/c/p/d 类型正确（bool 不算 int）；额外键必须已注册。
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data.get("pool"), dict):
        raise ValueError(f"{path}: 缺 pool 对象")
    if not isinstance(data.get("land"), str) or not isinstance(data.get("basic_prefix"), str):
        raise ValueError(f"{path}: land / basic_prefix 必须是字符串")
    pool = {}
    for name, entry in data["pool"].items():
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: {name} 的条目必须是对象")
        for key, typ in _POOL_REQUIRED:
            value = entry.get(key)
            if not isinstance(value, typ) or isinstance(value, bool):
                raise ValueError(f"{path}: {name} 缺键或类型错误: {key}")
        if entry["c"] < 0 or entry["p"] < 0 or entry["d"] < 0:
            raise ValueError(f"{path}: {name} 的 c/p/d 不能为负")
        for tag in entry:
            if tag not in dict(_POOL_REQUIRED) and tag not in HANDLERS:
                raise ValueError(f"{path}: {name} 含未注册的机制 tag: {tag!r}")
        pool[name] = dict(entry)
    return data["land"], data["basic_prefix"], pool


def expand(main_pairs, land_token, basic_prefix):
    """主牌 [(qty, name)] → [name]*qty 展开，基本地前缀映射为地哨兵。"""
    deck = []
    for q, name in main_pairs:
        deck += [land_token] * q if name.startswith(basic_prefix) else [name] * q
    return deck


# ---------------------------------------------------------------- 对局基类
class GameBase:
    """同构骨架；牌组差异由子类 play_turn/init_state 与注册机制注入。

    类属性：POOL（data JSON 加载）、LAND（地哨兵）、KEEP_LO/KEEP_HI（留牌地数
    区间）、MULLIGANS（免费调度次数）、LONDON（True=伦敦 7→6→5，现役牌组
    全部统一于此；False=老式重抓满 7，仅作兼容开关保留）。
    """

    POOL = {}
    LAND = None
    KEEP_LO, KEEP_HI = 2, 5
    MULLIGANS = 2
    LONDON = True

    def __init__(self, deck, rng, pen=1.0, **kw):
        self.rng = rng
        self.pen = pen
        self.lib = list(deck)
        rng.shuffle(self.lib)
        self.hand = []
        self.lands = 0
        self.bf = []
        self.dmg = 0.0
        self.turn = 0
        self.init_state(**kw)
        self.opening()

    def init_state(self, **kw):
        """牌组钩子：挂动态状态口袋（tokens/gy_spell/team_pump/stat 等）。"""

    # ---- 起手 ----
    def lands_in_hand(self):
        return sum(1 for c in self.hand if c == self.LAND)

    def opening(self):
        """起手 7 张；伦敦调度每次手牌数 -1（7→6→5）。
        LONDON=False 时每次重抓满 7（兼容开关，现役牌组已不用）。"""
        self.draw(7)
        size = 7
        for _ in range(self.MULLIGANS):
            if self.KEEP_LO <= self.lands_in_hand() <= self.KEEP_HI:
                return
            size -= 1
            self.lib += self.hand
            self.rng.shuffle(self.lib)
            self.hand = []
            self.draw(size if self.LONDON else 7)

    # ---- 基础动作 ----
    def draw(self, n=1):
        for _ in range(n):
            if self.lib:
                self.hand.append(self.lib.pop())

    def play_land(self):
        if self.LAND in self.hand:
            self.hand.remove(self.LAND)
            self.lands += 1
            return True
        return False

    # ---- 统计钩子 ----
    def is_stuck(self):
        return self.lands <= 2

    def play_turn(self):
        """推进一个回合；返回 True 表示本回合击杀（dmg >= 20）。"""
        raise NotImplementedError


# ---------------------------------------------------------------- 对局驱动
def run(game_cls, deck, n, max_turn=14, pen=1.0, seed=20260924,
        collect=None, **game_kw):
    """跑 n 局金鱼，返回统计 dict。

    collect(g, agg)：每局结束的牌组自定义聚合钩子（agg 值最终按 n 平均，
    放入结果["agg"]）。curve 为按回合累计伤害均值。
    """
    rng = random.Random(seed)
    kills, stuck = [], 0
    curve = defaultdict(float)
    agg = defaultdict(float)
    for _ in range(n):
        g = game_cls(deck, rng, pen, **game_kw)
        k = None
        for t in range(1, max_turn + 1):
            if g.play_turn():
                k = t
                break
        curve[g.turn] += g.dmg
        kills.append(k or max_turn + 1)
        if g.is_stuck():
            stuck += 1
        if collect is not None:
            collect(g, agg)
    kills.sort()
    m = len(kills)
    return dict(mean=sum(kills) / m,
                t3=100.0 * sum(1 for x in kills if x <= 3) / m,
                t4=100.0 * sum(1 for x in kills if x <= 4) / m,
                t5=100.0 * sum(1 for x in kills if x <= 5) / m,
                t6=100.0 * sum(1 for x in kills if x <= 6) / m,
                t7=100.0 * sum(1 for x in kills if x <= 7) / m,
                t8=100.0 * sum(1 for x in kills if x <= 8) / m,
                stuck=100.0 * stuck / m,
                curve={t: curve[t] / m for t in sorted(curve)},
                agg={k: v / n for k, v in agg.items()})
