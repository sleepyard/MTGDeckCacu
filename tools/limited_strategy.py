#!/usr/bin/env python3
"""限制模式的确定性组牌策略。

输入是已解析的牌池和可选的评分表对象；本模块不读文件、不联网、不调用 LLM。
评分表只负责提供 grade/IWD 等事实，所有数量、曲线和法术力计算交给纯函数内核。
"""

from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import deck_core
import roles


COLORS = tuple("WUBRG")
CURVE_FACTORS = {1.0: 1.0, 0.5: 0.85, 0.1: 0.6}
STRATEGIES = tuple(deck_core.STRATEGY_TARGETS)
LIMITED_DECK_SIZE = 40


@dataclass(frozen=True)
class SelectedCard:
    card: Mapping
    count: int
    score: float
    reason: str


@dataclass(frozen=True)
class ColorPlan:
    colors: Tuple[str, ...]
    score: float
    depth: Mapping[str, int]
    depth_ok: bool
    depth_note: str
    curve: Mapping[int, int]
    curve_label: str
    curve_bonus: int


@dataclass
class LimitedDeck:
    colors: Tuple[str, ...]
    strategy: str
    splash: List[SelectedCard]
    main: List[SelectedCard]
    lands: Dict[str, int]
    sideboard: List[SelectedCard]
    curve: Dict[int, int]
    average_cmc: float
    depth_ok: bool
    depth_note: str
    land_check: Tuple[float, float, bool]
    cuts: List[str] = field(default_factory=list)
    report: List[str] = field(default_factory=list)
    valid: bool = True
    violations: List[str] = field(default_factory=list)


def _name(card: Mapping) -> str:
    return str(card.get("name") or "").strip()


def _colors(card: Mapping) -> Tuple[str, ...]:
    values = card.get("colors") or []
    return tuple(sorted({str(value).upper() for value in values if str(value).upper() in COLORS}))


def _type_line(card: Mapping) -> str:
    return str(card.get("type_line") or card.get("type") or "")


def _is_land(card: Mapping) -> bool:
    return "land" in _type_line(card).lower()


def _is_creature(card: Mapping) -> bool:
    return "creature" in _type_line(card).lower()


def _cmc(card: Mapping) -> float:
    try:
        return float(card.get("cmc") or 0)
    except (TypeError, ValueError):
        return 0.0


def _quantity(card: Mapping) -> int:
    value = card.get("count", 1)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _copies(pool: Iterable[Mapping]) -> List[Mapping]:
    result = []
    for card in pool:
        result.extend([card] * _quantity(card))
    return result


def _entry(card: Mapping, table=None) -> Mapping:
    if table is not None:
        lookup = getattr(table, "lookup", None)
        if lookup is None:
            raise TypeError("评分表必须提供 lookup(name) 方法")
        found = lookup(_name(card))
        if found is not None:
            return found
    return card


def _grade(card: Mapping, table=None) -> str:
    return str(_entry(card, table).get("grade") or card.get("grade") or "")


def _score(card: Mapping, table=None) -> float:
    return deck_core.grade_eq(_grade(card, table))


def _tags(card: Mapping) -> List[roles.RoleTag]:
    supplied = card.get("role_tags")
    if supplied is not None:
        return [tag for tag in supplied if isinstance(tag, roles.RoleTag)]
    return roles.classify_card(card)


def _playable(card: Mapping, colors: Sequence[str]) -> bool:
    card_colors = set(_colors(card))
    return not card_colors or card_colors.issubset(set(colors))


def _depth(pool: Iterable[Mapping], colors: Sequence[str], table=None) -> Dict[str, int]:
    result = {color: 0 for color in colors}
    for card in _copies(pool):
        if not _playable(card, colors) or _is_land(card):
            continue
        if _grade(card, table) not in deck_core.HIGH_GRADES:
            continue
        for color in _colors(card):
            if color in result:
                result[color] += 1
    return result


def _plan_mode(colors: Sequence[str]) -> str:
    return "mono" if len(colors) == 1 else "dual"


def evaluate_color_plan(pool: Iterable[Mapping], colors: Sequence[str], table=None) -> ColorPlan:
    """评估单色/双色组合：top-23 等效分 + 曲线评级，并返回深度缺口。"""
    normalized = tuple(str(color).upper() for color in colors)
    if len(normalized) not in (1, 2) or any(color not in COLORS for color in normalized):
        raise ValueError("限制赛只支持 1 或 2 个 WUBRG 颜色")
    if len(set(normalized)) != len(normalized):
        raise ValueError("颜色组合不能重复")

    playable = [card for card in _copies(pool)
                if not _is_land(card) and _playable(card, normalized)]
    ranked = sorted(playable, key=lambda card: (-_score(card, table), _name(card)))
    top = ranked[:deck_core.TARGET_NON_LANDS]
    curve = Counter(deck_core.cmc_slot(_cmc(card)) for card in top)
    curve_label, curve_bonus = deck_core.curve_rating(dict(curve))
    depth = _depth(pool, normalized, table)
    mode = _plan_mode(normalized)
    depth_ok, depth_note = deck_core.color_depth_ok(
        depth, (mode, list(normalized)))
    return ColorPlan(
        colors=normalized,
        score=sum(_score(card, table) for card in top) + curve_bonus,
        depth=depth,
        depth_ok=depth_ok,
        depth_note=depth_note,
        curve=dict(curve),
        curve_label=curve_label,
        curve_bonus=curve_bonus,
    )


def enumerate_color_plans(pool: Iterable[Mapping], table=None) -> List[ColorPlan]:
    """枚举 5 个单色和 10 个双色组合，优先保留满足深度的方案。"""
    plans = [evaluate_color_plan(pool, combo, table)
             for size in (1, 2) for combo in combinations(COLORS, size)]
    return sorted(plans, key=lambda plan: (plan.depth_ok, plan.score), reverse=True)


def choose_color_plan(pool: Iterable[Mapping], table=None,
                      forced_colors: Optional[Sequence[str]] = None) -> ColorPlan:
    if forced_colors is not None:
        return evaluate_color_plan(pool, forced_colors, table)
    plans = enumerate_color_plans(pool, table)
    if not plans:
        raise ValueError("牌池没有可评估的颜色组合")
    return plans[0]


def _off_color_pips(card: Mapping, colors: Sequence[str]) -> float:
    pips = deck_core.parse_mana_pips(str(card.get("cost") or card.get("mana_cost") or ""))
    return sum(value for color, value in pips.items() if color not in set(colors))


def find_splash_cards(pool: Iterable[Mapping], plan: ColorPlan, table=None) -> List[Mapping]:
    """按设计稿的强度、单异色 pip 和主色深度门槛选择最多 3 张 splash。"""
    if not plan.depth_ok:
        return []
    candidates = []
    main_colors = set(plan.colors)
    seen = set()
    for card in _copies(pool):
        name = _name(card)
        if not name or name in seen or _is_land(card):
            continue
        card_colors = set(_colors(card))
        extra = card_colors - main_colors
        if len(extra) != 1 or card_colors.issubset(main_colors):
            continue
        if _off_color_pips(card, plan.colors) != 1:
            continue
        entry = _entry(card, table)
        iwd = entry.get("iwd", card.get("iwd"))
        effective = entry.get("effective_score", card.get("effective_score"))
        if not deck_core.splash_ok(1, iwd=iwd, effective_score=effective):
            continue
        if _grade(card, table) not in deck_core.HIGH_GRADES and \
                _score(card, table) < deck_core.GRADE_EQ["B+"]:
            continue
        candidates.append(card)
        seen.add(name)
    candidates.sort(key=lambda card: (-_score(card, table), _name(card)))
    return candidates[:deck_core.SPLASH_MAX_CARDS]


def _curve_factor(value: float) -> float:
    return CURVE_FACTORS[value]


def _adjusted_score(card: Mapping, table, curve: Mapping[int, int],
                    creatures: int, removal: int, strategy: str) -> Tuple[float, str]:
    targets = deck_core.STRATEGY_TARGETS[strategy]
    base = _score(card, table)
    slot = deck_core.cmc_slot(_cmc(card))
    fit = deck_core.curve_fit_score(curve, _cmc(card))
    score = base * _curve_factor(fit)
    reasons = []
    tags = _tags(card)
    if _is_creature(card) and creatures < targets["creature"]:
        score *= 1.2
        reasons.append("生物配额")
    if roles.has_root(tags, "removal") and removal < targets["removal"]:
        score *= 1.3
        reasons.append("去除配额")
    if slot >= 4 and curve.get(slot, 0) >= 5:
        score *= 0.7
        reasons.append("高费溢出")
    if fit == 1.0:
        reasons.append("曲线缺口")
    return score, "、".join(reasons) or "评分优选"


def _group(selections: Iterable[SelectedCard]) -> List[SelectedCard]:
    grouped = {}
    for selection in selections:
        name = _name(selection.card)
        if name in grouped:
            old = grouped[name]
            grouped[name] = SelectedCard(old.card, old.count + selection.count,
                                         max(old.score, selection.score), old.reason)
        else:
            grouped[name] = selection
    return list(grouped.values())


def _select_nonlands(pool: Iterable[Mapping], plan: ColorPlan, table,
                     strategy: str, splash_cards: Sequence[Mapping], target: int):
    available = [card for card in _copies(pool)
                 if not _is_land(card) and _playable(card, plan.colors)]
    splash_names = {_name(card) for card in splash_cards}
    selected: List[SelectedCard] = [
        SelectedCard(card, 1, _score(card, table), "splash 准入")
        for card in splash_cards
    ]
    available = [card for card in available if _name(card) not in splash_names]
    curve = Counter(deck_core.cmc_slot(_cmc(selection.card))
                    for selection in selected)
    creatures = sum(1 for selection in selected if _is_creature(selection.card))
    removal = sum(1 for selection in selected if roles.has_root(_tags(selection.card), "removal"))
    decisions = []
    while len(selected) < target and available:
        candidates = []
        for card in available:
            score, reason = _adjusted_score(card, table, curve, creatures, removal, strategy)
            candidates.append((score, _score(card, table), card, reason))
        score, _base, card, reason = max(
            candidates, key=lambda item: (item[0], item[1], _name(item[2])))
        available.remove(card)
        selected.append(SelectedCard(card, 1, score, reason))
        slot = deck_core.cmc_slot(_cmc(card))
        curve[slot] += 1
        creatures += int(_is_creature(card))
        removal += int(roles.has_root(_tags(card), "removal"))
        decisions.append((card, score))
    return _group(selected), available, decisions


def _sideboard(pool: Iterable[Mapping], main: Sequence[SelectedCard]) -> List[SelectedCard]:
    remaining = Counter(_name(card) for card in _copies(pool) if not _is_land(card))
    for selection in main:
        remaining[_name(selection.card)] -= selection.count
    result = []
    by_name = {_name(card): card for card in _copies(pool)}
    for name, count in remaining.items():
        if count > 0:
            result.append(SelectedCard(by_name[name], count, 0.0, "未进主牌"))
    return result


def build_limited_deck(pool: Sequence[Mapping], table=None,
                       forced_colors: Optional[Sequence[str]] = None,
                       strategy: str = "mid") -> LimitedDeck:
    """从已解析牌池构建限制赛套牌，不负责输入/输出文件。"""
    if strategy not in STRATEGIES:
        raise ValueError("strategy 必须是 aggro、mid 或 control")
    if not pool:
        raise ValueError("牌池为空")
    plan = choose_color_plan(pool, table, forced_colors)
    splash_cards = find_splash_cards(pool, plan, table)
    target_nonlands = deck_core.TARGET_NON_LANDS
    main, _available, decisions = [], [], []
    main_copies = []
    avg_cmc = 0.0
    draw_ramp = 0
    lands_count = deck_core.LAND_MIN
    for _ in range(4):
        main, _available, decisions = _select_nonlands(
            pool, plan, table, strategy, splash_cards, target_nonlands)
        main_copies = [selection.card for selection in main
                       for _ in range(selection.count)]
        avg_cmc = (sum(_cmc(card) for card in main_copies) / len(main_copies)
                   if main_copies else 0.0)
        draw_ramp = sum(1 for card in main_copies
                        if roles.has_root(_tags(card), "card_advantage") or
                        roles.has_root(_tags(card), "mana_development"))
        lands_count = deck_core.land_count(avg_cmc, draw_ramp_count=draw_ramp,
                                           splash_count=len(splash_cards))
        next_target = LIMITED_DECK_SIZE - lands_count
        if next_target == target_nonlands:
            break
        target_nonlands = next_target
    pip_counts = Counter()
    for card in main_copies:
        pip_counts.update(deck_core.parse_mana_pips(
            str(card.get("cost") or card.get("mana_cost") or "")))
    splash_colors = sorted({color for card in splash_cards for color in _colors(card)} - set(plan.colors))
    lands = deck_core.mana_base(dict(pip_counts), lands_count, splash_colors=splash_colors)
    curve = dict(Counter(deck_core.cmc_slot(_cmc(card)) for card in main_copies))
    risk = deck_core.land_check(lands_count)
    sideboard = _sideboard(pool, main)

    cuts = []
    if _available:
        replacement = min(decisions, key=lambda item: item[1])[0] if decisions else None
        replacement_name = _name(replacement) if replacement else "已选牌"
        cut_counts = Counter(_name(card) for card in _available)
        cuts = [f"{name} ×{count}：被 {replacement_name} 挤掉"
                for name, count in sorted(cut_counts.items())]
    report = [
        f"颜色: {'+'.join(plan.colors)}" +
        (f"，splash {'+'.join(splash_colors)}" if splash_colors else ""),
        f"深度: {'通过' if plan.depth_ok else '不足'}"
        + (f"（{plan.depth_note}）" if plan.depth_note else ""),
        f"策略: {strategy}；非地 {len(main_copies)}/{target_nonlands}；"
        f"平均 CMC {avg_cmc:.2f}；地 {lands_count}",
        "曲线: " + " ".join(f"{slot}费×{curve.get(slot, 0)}" for slot in range(1, 6))
        + f" → {deck_core.curve_rating(curve)[0]}",
        "法术力: " + (" / ".join(f"{color}{count}" for color, count in sorted(lands.items())) or "无有色 pip"),
        f"爆地/卡地自检: 第3回合≥2地 {risk[0]:.1%}，第5回合≥4地 {risk[1]:.1%}，"
        f"{'通过' if risk[2] else '未通过'}",
        "淘汰: " + ("；".join(cuts) if cuts else "无"),
    ]
    total_cards = len(main_copies) + sum(lands.values())
    violations = []
    if len(main_copies) != target_nonlands:
        violations.append(f"牌池不足：非地 {len(main_copies)} 张，目标 {target_nonlands} 张")
    if total_cards != LIMITED_DECK_SIZE:
        violations.append(f"总张数 {total_cards} != {LIMITED_DECK_SIZE}")
    report.append("门禁: " + ("通过" if not violations else "失败: " + "；".join(violations)))
    return LimitedDeck(
        colors=plan.colors,
        strategy=strategy,
        splash=[selection for selection in main if selection.reason == "splash 准入"],
        main=main,
        lands=lands,
        sideboard=sideboard,
        curve=curve,
        average_cmc=avg_cmc,
        depth_ok=plan.depth_ok,
        depth_note=plan.depth_note,
        land_check=risk,
        cuts=cuts,
        report=report,
        valid=not violations,
        violations=violations,
    )
