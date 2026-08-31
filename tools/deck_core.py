#!/usr/bin/env python3
"""DeckPooper 的确定性组牌内核。

本模块只负责可复现计算：评分映射、WASPAS、曲线、轮抓信号、颜色深度、
splash 准入、法术力配比和爆地/卡地检查。它不读文件、不联网，也不调用 LLM。
"""

import re
from math import comb


# ---------------------------------------------------------------- 字母等级 -> 等效数值
GRADE_EQ = {
    "S": 0.60, "A": 0.57, "A-": 0.56, "B+": 0.55, "B": 0.545, "B-": 0.54,
    "C+": 0.53, "C": 0.525, "C-": 0.52, "D": 0.51, "F": 0.48,
}
HIGH_GRADES = {"S", "A", "A-", "B+", "B"}
RARITY_SCORE = {"mythic": 1.0, "rare": 0.7, "uncommon": 0.45, "common": 0.2}


def grade_eq(grade):
    """字母等级转为排序用的等效值；未知等级按 C 档中位处理。"""
    return GRADE_EQ.get((grade or "").strip(), 0.525)


# ---------------------------------------------------------------- 八轴 WASPAS
AXES = {
    "raw_power": 0.25,
    "synergy": 0.20,
    "curve_fit": 0.15,
    "color_openness": 0.15,
    "signal": 0.10,
    "fixer": 0.05,
    "removal": 0.05,
    "rarity": 0.05,
}
_WASPAS_LAMBDA = 0.5
_EPS = 1e-6


def waspas(scores):
    """计算 0..1 的 WASPAS 综合分，缺失轴按 0.5 处理中性值。"""
    wsm, wpm = 0.0, 1.0
    for axis, weight in AXES.items():
        score = scores.get(axis, 0.5)
        score = max(0.0, min(1.0, score))
        wsm += weight * score
        wpm *= max(score, _EPS) ** weight
    return _WASPAS_LAMBDA * wsm + (1 - _WASPAS_LAMBDA) * wpm


def rarity_score(rarity):
    return RARITY_SCORE.get((rarity or "").strip().lower(), 0.2)


def removal_score(tags):
    return 1.0 if "removal" in {t.strip().lower() for t in (tags or [])} else 0.0


def fixer_score(card_colors, produces_colors, picked_colors):
    """计算候选牌对已选颜色的调色价值。"""
    if not picked_colors:
        return 0.5
    extra = set(produces_colors or ()) - set(picked_colors)
    if set(picked_colors) & set(produces_colors or ()) and len(picked_colors) > 1:
        return 0.8
    if extra:
        return 0.6
    if not card_colors:
        return 0.4
    return 0.2


# ---------------------------------------------------------------- 曲线
CURVE_TARGET = {1: (2, 4), 2: (5, 7), 3: (4, 6), 4: (3, 5), 5: (2, 4)}


def cmc_slot(cmc):
    return min(max(int(cmc or 0), 1), 5)


def curve_fit_score(picked_counts, cmc):
    """候选牌对曲线的契合度：缺口 1.0、区间内 0.5、溢出 0.1。"""
    slot = cmc_slot(cmc)
    lo, hi = CURVE_TARGET[slot]
    current = picked_counts.get(slot, 0)
    if current < lo:
        return 1.0
    if current < hi:
        return 0.5
    return 0.1


def curve_rating(cmc_counts):
    """返回 (评级, 调整分)。低费占比和中费数量共同决定评级。"""
    total = sum(cmc_counts.values())
    if total <= 0:
        return "不足", -5
    low = cmc_counts.get(1, 0) + cmc_counts.get(2, 0)
    mid = cmc_counts.get(3, 0) + cmc_counts.get(4, 0)
    ratio = low / total
    if ratio >= 0.40 and mid >= 3:
        return "优秀", +5
    if ratio >= 0.30 and mid >= 2:
        return "良好", +2
    if ratio >= 0.20:
        return "偏慢", -3
    return "不足", -5


# ---------------------------------------------------------------- 轮抓信号
SIGNAL_OPEN_DELTA = 0.3
SIGNAL_CLOSED_DELTA = -0.2
ALSA_MARGIN = 1.5
_FALLBACK_PER_HIGH = 0.1


def update_signals(signals, pack_remaining, pick_number):
    """按 ALSA 更新颜色开放度；没有 ALSA 时按高等级牌数量降级。"""
    for card in pack_remaining:
        colors = card.get("colors") or []
        alsa = card.get("alsa")
        for color in colors:
            if alsa is None:
                continue
            if pick_number > alsa + ALSA_MARGIN:
                signals[color] = signals.get(color, 0.0) + SIGNAL_OPEN_DELTA
            elif pick_number < alsa - ALSA_MARGIN:
                signals[color] = signals.get(color, 0.0) + SIGNAL_CLOSED_DELTA

    for card in pack_remaining:
        if card.get("alsa") is not None:
            continue
        if (card.get("grade") or "") not in HIGH_GRADES:
            continue
        for color in card.get("colors") or []:
            signals[color] = signals.get(color, 0.0) + _FALLBACK_PER_HIGH

    for color in signals:
        signals[color] = max(-1.0, min(1.0, signals[color]))
    return signals


def color_openness_score(signals, card_colors):
    """候选牌颜色与累计开放度的契合度（0..1）。"""
    if not card_colors:
        return 0.5
    values = [signals.get(color, 0.0) for color in card_colors]
    return (sum(values) / len(values) + 1.0) / 2.0


# ---------------------------------------------------------------- 组牌骨架
TARGET_NON_LANDS = 23
LAND_MIN, LAND_MAX = 16, 19
STRATEGY_TARGETS = {
    "aggro": {"creature": 16, "removal": 3},
    "mid": {"creature": 13, "removal": 3},
    "control": {"creature": 10, "removal": 6},
}
DEPTH_MONO_MIN = 14
DEPTH_DUAL_MIN = 8
SPLASH_MAX_CARDS = 3
SPLASH_DISCOUNT = 0.3
SPLASH_IWD_THRESHOLD = 0.03
SPLASH_SCORE_THRESHOLD = 6.0


def land_count(avg_cmc, draw_ramp_count=0, splash_count=0):
    """动态地数，按教学口径 clamp 到 [16, 19]。"""
    base = 17
    if avg_cmc > 4.0:
        base += 2
    elif avg_cmc > 3.4:
        base += 1
    elif avg_cmc < 2.5:
        base -= 2
    elif avg_cmc < 2.8:
        base -= 1
    if draw_ramp_count >= 4:
        base -= 1
    base += min(2, splash_count * 0.5)
    if avg_cmc <= 2.5 and splash_count <= 2:
        base = min(base, 16)
    if avg_cmc < 2.8 and splash_count <= 1:
        base = min(base, 17)
    return int(round(max(LAND_MIN, min(LAND_MAX, base))))


def color_depth_ok(good_by_color, plan):
    """检查单色、双色和 splash 的优质牌深度。"""
    mode = plan[0]
    mains = plan[1]
    splashes = plan[2] if len(plan) > 2 else []
    required = DEPTH_MONO_MIN if mode == "mono" else DEPTH_DUAL_MIN
    short = [f"{color} 缺 {required - good_by_color.get(color, 0)} 张"
             for color in mains if good_by_color.get(color, 0) < required]
    for color in splashes:
        if good_by_color.get(color, 0) > SPLASH_MAX_CARDS:
            short.append(f"{color} splash 超 {SPLASH_MAX_CARDS} 张上限")
    return not short, "；".join(short)


def splash_ok(off_color_pips, iwd=None, effective_score=None):
    """检查 splash 的单异色符号和强度门槛。"""
    if off_color_pips != 1:
        return False
    if iwd is not None:
        return iwd >= SPLASH_IWD_THRESHOLD
    return (effective_score or 0.0) >= SPLASH_SCORE_THRESHOLD


def parse_mana_pips(mana_cost):
    """解析费用中的有色 pip。

    普通有色符号计 1；混合/非瑞混合符号的可选颜色平均分摊；通用、无色、X
    不计。返回只包含正数颜色的 dict，供所有策略共享。
    """
    result = {}
    for symbol in re.findall(r"\{([^}]+)\}", mana_cost or ""):
        options = [part for part in symbol.upper().split("/") if part in "WUBRG"]
        if not options:
            continue
        share = 1.0 / len(options)
        for color in options:
            result[color] = result.get(color, 0.0) + share
    return result


def mana_base(pip_counts, lands, splash_colors=()):
    """按 pip 比例分配地牌，每种需求颜色至少保留 1 个来源。"""
    weights = {}
    for color, pips in (pip_counts or {}).items():
        if pips <= 0:
            continue
        weight = float(pips)
        if color in splash_colors:
            weight *= SPLASH_DISCOUNT
        weights[color] = weight
    if not weights or lands <= 0:
        return {}
    base = {color: 1 for color in weights}
    remaining = lands - len(base)
    if remaining <= 0:
        return base
    total_weight = sum(weights.values())
    allocation = dict(base)
    fractions = []
    for color, weight in weights.items():
        exact = remaining * weight / total_weight
        whole = int(exact)
        allocation[color] += whole
        fractions.append((exact - whole, color))
    left = lands - sum(allocation.values())
    for _fraction, color in sorted(fractions, reverse=True)[:left]:
        allocation[color] += 1
    return allocation


# ---------------------------------------------------------------- 爆地/卡地自检
def hypergeom_at_least(deck_size, lands, draws, k):
    """超几何概率：抽 draws 张时至少有 k 张地。"""
    if lands < k or draws < k:
        return 0.0
    total = comb(deck_size, draws)
    favorable = sum(comb(lands, i) * comb(deck_size - lands, draws - i)
                    for i in range(k, min(lands, draws) + 1))
    return favorable / total


def land_check(lands, deck_size=40):
    """检查第 3 回合至少 2 地、第 5 回合至少 4 地的概率门槛。"""
    p3 = hypergeom_at_least(deck_size, lands, 7 + 2, 2)
    p5 = hypergeom_at_least(deck_size, lands, 7 + 4, 4)
    return p3, p5, (p3 > 0.90 and p5 > 0.70)
