#!/usr/bin/env python3
"""轮抓驾驶舱纯函数内核：8 轴 WASPAS pick 评分 + 组牌骨架数字。

设计先验见 tools/draft_methodology.md（§2/§3/§4）。本模块只含确定性计算：
费用、曲线、颜色开放度、张数计数全部机器算；LLM 只出 RawPower/Synergy
两个定性轴的分（实测教训：LLM 在费用与计数上幻觉严重，不给它算的机会）。

仅 Python 标准库；无任何 I/O，可独立单测。
"""

from math import comb

# ---------------------------------------------------------------- §0 字母等级 → 等效数值
# 评分表只有字母等级（17Lands 已死，无真实 GIH），映射仅用于排序，
# 不对用户展示伪精确胜率。
GRADE_EQ = {
    "S": 0.60, "A": 0.57, "A-": 0.56, "B+": 0.55, "B": 0.545, "B-": 0.54,
    "C+": 0.53, "C": 0.525, "C-": 0.52, "D": 0.51, "F": 0.48,
}
HIGH_GRADES = {"S", "A", "A-", "B+", "B"}  # 信号降级口径的"高等级牌"

RARITY_SCORE = {"mythic": 1.0, "rare": 0.7, "uncommon": 0.45, "common": 0.2}


def grade_eq(grade):
    """字母等级 → 等效 GIH 近似值；未知等级给 C 档中位。"""
    return GRADE_EQ.get((grade or "").strip(), 0.525)


# ---------------------------------------------------------------- §2 八轴 WASPAS
AXES = {
    "raw_power": 0.25,       # LLM 定性（有评分表先验）
    "synergy": 0.20,         # LLM 定性（给已 pick 牌池）
    "curve_fit": 0.15,       # 机器
    "color_openness": 0.15,  # 机器（§3 信号累计）
    "signal": 0.10,          # 机器（§3 本包信号）
    "fixer": 0.05,           # 机器
    "removal": 0.05,         # 机器（标签命中）
    "rarity": 0.05,          # 机器
}
_WASPAS_LAMBDA = 0.5
_EPS = 1e-6  # WPM 防零塌缩：任一轴 0 分不应直接抹杀整卡


def waspas(scores):
    """WASPAS 综合分：λ×加权求和 + (1−λ)×加权乘积。
    scores: {轴名: 0..1}，缺轴按 0.5 中性处理。返回 0..1。"""
    wsm, wpm = 0.0, 1.0
    for axis, w in AXES.items():
        s = scores.get(axis, 0.5)
        s = max(0.0, min(1.0, s))
        wsm += w * s
        wpm *= max(s, _EPS) ** w
    return _WASPAS_LAMBDA * wsm + (1 - _WASPAS_LAMBDA) * wpm


def rarity_score(rarity):
    return RARITY_SCORE.get((rarity or "").strip().lower(), 0.2)


def removal_score(tags):
    """tags 含 removal 即满分（removal 是限制赛最贵标签）。"""
    return 1.0 if "removal" in {t.strip().lower() for t in (tags or [])} else 0.0


def fixer_score(card_colors, produces_colors, picked_colors):
    """调色轴：多色/产多色法术力的牌在我方已混色时得分高。
    produces_colors: 该牌可产出的颜色集合（含自身无色法术力则空）。"""
    if not picked_colors:
        return 0.5  # 尚未定色，调色价值中性
    extra = set(produces_colors or ()) - set(picked_colors)
    if set(picked_colors) & set(produces_colors or ()) and len(picked_colors) > 1:
        return 0.8  # 能产出我方已混的颜色
    if extra:
        return 0.6  # 产出新颜色，为 splash 留余地
    if not card_colors:
        return 0.4  # 纯无色牌不调色但也不添需求
    return 0.2


# ---------------------------------------------------------------- §4 曲线
# 健康曲线目标（教学笔记口径）：slot → (下限, 上限)，5 代表 5+ 费
CURVE_TARGET = {1: (2, 4), 2: (5, 7), 3: (4, 6), 4: (3, 5), 5: (2, 4)}


def cmc_slot(cmc):
    return min(max(int(cmc or 0), 1), 5)


def curve_fit_score(picked_counts, cmc):
    """候选牌对曲线的契合度：补缺口 1.0 / 在区间内 0.5 / 已溢出 0.1。
    picked_counts: {slot: 已 pick 张数}。"""
    slot = cmc_slot(cmc)
    lo, hi = CURVE_TARGET[slot]
    cur = picked_counts.get(slot, 0)
    if cur < lo:
        return 1.0
    if cur < hi:
        return 0.5
    return 0.1


def curve_rating(cmc_counts):
    """曲线评级 → (标签, 加减分)。口径：低费(≤2)占比 ≥40% 且中费(3-4) ≥3 张为优秀。
    cmc_counts: {slot: 张数}（非地牌）。"""
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


# ---------------------------------------------------------------- §3 信号读取
SIGNAL_OPEN_DELTA = 0.3
SIGNAL_CLOSED_DELTA = -0.2
ALSA_MARGIN = 1.5
_FALLBACK_PER_HIGH = 0.1  # 无 ALSA 时降级：每张剩余高等级牌 +0.1，单包封顶 +0.3


def update_signals(signals, pack_remaining, pick_number):
    """按本包剩余牌更新颜色开放度（就地修改并返回，值 clamp [-1, 1]）。
    signals: {颜色: 累计值}；pack_remaining: [{colors, alsa?, grade?}]；
    pick_number: 当前是第几 pick（1 起）。
    有 alsa 走顺位比较（坑：ALSA=avg_seen，不是 avg_pick/ATA，别混）；
    无 alsa 降级为"该色剩余高等级牌计数"。"""
    for card in pack_remaining:
        colors = card.get("colors") or []
        alsa = card.get("alsa")
        grade = card.get("grade")
        for color in colors:
            if alsa is not None:
                if pick_number > alsa + ALSA_MARGIN:
                    signals[color] = signals.get(color, 0.0) + SIGNAL_OPEN_DELTA
                elif pick_number < alsa - ALSA_MARGIN:
                    signals[color] = signals.get(color, 0.0) + SIGNAL_CLOSED_DELTA
    # 降级口径：没有 alsa 的牌按高等级计数（每张每色 +0.1，单卡封顶 0.3）
    for card in pack_remaining:
        if card.get("alsa") is not None:
            continue
        if (card.get("grade") or "") not in HIGH_GRADES:
            continue
        for color in (card.get("colors") or []):
            signals[color] = signals.get(color, 0.0) + _FALLBACK_PER_HIGH
    for color in signals:
        signals[color] = max(-1.0, min(1.0, signals[color]))
    return signals


def color_openness_score(signals, card_colors):
    """候选牌颜色与我方累计开放度的契合（0..1）；无色牌中性 0.5。"""
    if not card_colors:
        return 0.5
    vals = [signals.get(c, 0.0) for c in card_colors]
    return (sum(vals) / len(vals) + 1.0) / 2.0


# ---------------------------------------------------------------- §4 组牌骨架
TARGET_NON_LANDS = 23
LAND_MIN, LAND_MAX = 16, 19

# 策略配额：生物/去除目标张数（教学口径：进攻 16 / 控制 10 / 默认 13；去除 3-6）
STRATEGY_TARGETS = {
    "aggro": {"creature": 16, "removal": 3},
    "mid": {"creature": 13, "removal": 3},
    "control": {"creature": 10, "removal": 6},
}

# 颜色深度标准：单色需 14+ 张优质牌；双色各 ≥8；splash 仅 1-3 张
DEPTH_MONO_MIN = 14
DEPTH_DUAL_MIN = 8
SPLASH_MAX_CARDS = 3
SPLASH_DISCOUNT = 0.3       # splash 色法术力需求打 3 折
SPLASH_IWD_THRESHOLD = 0.03
SPLASH_SCORE_THRESHOLD = 6.0


def land_count(avg_cmc, draw_ramp_count=0, splash_count=0):
    """动态地数，clamp [16, 19]。
    采信教学口径：抓牌/加速 ≥4 张 → 减 1 地
    （坑：旧项目代码写成加地，文档/实现分歧，勿照抄代码）。"""
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
    """颜色深度检查。good_by_color: {颜色: 优质牌张数}；
    plan: ("mono"|"dual"|"splash", 主色列表[, splash色列表]) → (是否达标, 缺口说明)。"""
    mode = plan[0]
    mains = plan[1]
    splashes = plan[2] if len(plan) > 2 else []
    if mode == "mono":
        need = {c: DEPTH_MONO_MIN for c in mains}
    else:
        need = {c: DEPTH_DUAL_MIN for c in mains}
    short = [f"{c} 缺 {need[c] - good_by_color.get(c, 0)} 张"
             for c in mains if good_by_color.get(c, 0) < need[c]]
    for c in splashes:
        if good_by_color.get(c, 0) > SPLASH_MAX_CARDS:
            short.append(f"{c} splash 超 {SPLASH_MAX_CARDS} 张上限")
    return (not short, "；".join(short))


def splash_ok(off_color_pips, iwd=None, effective_score=None):
    """splash 准入：只需 1 个异色符号 +（有数据 IWD≥0.03 / 无数据有效分≥6.0）。
    第三条"主色法术力基础稳固"由 mana_base 结果另行判断。"""
    if off_color_pips != 1:
        return False
    if iwd is not None:
        return iwd >= SPLASH_IWD_THRESHOLD
    return (effective_score or 0.0) >= SPLASH_SCORE_THRESHOLD


def mana_base(pip_counts, lands, splash_colors=()):
    """法术力配比：每色保底 1 张来源，其余按 pip 占比分配（splash 色需求 3 折）。
    pip_counts: {颜色: 有色 pip 数}；lands: 地总数。返回 {颜色: 来源数}。"""
    weights = {}
    for color, pips in (pip_counts or {}).items():
        if pips <= 0:
            continue
        w = float(pips)
        if color in splash_colors:
            w *= SPLASH_DISCOUNT
        weights[color] = w
    if not weights or lands <= 0:
        return {}
    base = {c: 1 for c in weights}
    remaining = lands - len(base)
    if remaining <= 0:
        return base
    total_w = sum(weights.values())
    alloc = dict(base)
    fracs = []
    for color, w in weights.items():
        exact = remaining * w / total_w
        whole = int(exact)
        alloc[color] += whole
        fracs.append((exact - whole, color))
    left = lands - sum(alloc.values())
    for _frac, color in sorted(fracs, reverse=True)[:left]:
        alloc[color] += 1
    return alloc


# ---------------------------------------------------------------- §4 爆地/卡地自检
def hypergeom_at_least(deck_size, lands, draws, k):
    """超几何概率：deck_size 张库 lands 张地，抽 draws 张时 ≥k 张地的概率。"""
    if lands < k or draws < k:
        return 0.0
    total = comb(deck_size, draws)
    fav = sum(comb(lands, i) * comb(deck_size - lands, draws - i)
              for i in range(k, min(lands, draws) + 1))
    return fav / total


def land_check(lands, deck_size=40):
    """自检线：第 3 回合 ≥2 地概率 >90%、第 5 回合 ≥4 地概率 >70%。
    简化口径：起手 7 + 每回合抽 1（先手，不调度）。返回 (p3, p5, 是否达标)。"""
    p3 = hypergeom_at_least(deck_size, lands, 7 + 2, 2)
    p5 = hypergeom_at_least(deck_size, lands, 7 + 4, 4)
    return p3, p5, (p3 > 0.90 and p5 > 0.70)
