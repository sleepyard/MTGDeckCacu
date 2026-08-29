#!/usr/bin/env python3
"""限制赛九根角色标签的纯函数实现。

规则标签只读取卡牌字段，不访问数据库、网络或 LLM。AI 标签可以由上层传入，
这里只做白名单过滤、冲突处理和五折评分，便于测试与复盘。
"""

import re
from dataclasses import dataclass
from typing import Iterable, List, Mapping, Optional, Sequence, Set


ROOTS = (
    "removal", "card_advantage", "mana_development", "threat", "protection",
    "tempo", "aggro", "control", "hate",
)
ROOT_WEIGHTS = {
    "removal": 1.5,
    "card_advantage": 1.2,
    "mana_development": 0.7,
    "threat": 0.8,
    "protection": 0.5,
    "tempo": 0.6,
    "aggro": 0.3,
    "control": 0.3,
    "hate": 0.0,
}
MECHANIC_MODIFIERS = {
    "board_wipe": 0.4,
    "counterspell": 0.4,
    "mass_draw": 0.3,
    "etb_value": 0.3,
    "evasion": 0.2,
    "treasure": 0.2,
    "mana_fixing": 0.2,
}
AI_DISCOUNT = 0.5
MAX_TAG_SCORE = 4.0

# 这些机制可能被旧标签系统放在错误的根下，评分时统一到规范根。
CANONICAL_MECHANIC_ROOT = {
    "lifelink": "threat",
    "vigilance": "threat",
    "reach": "threat",
    "haste": "aggro",
    "prowess": "aggro",
    "low_cost_creature": "aggro",
}
ROLE_PRIORITY = (
    "removal", "card_advantage", "threat", "mana_development", "protection",
    "tempo", "control", "aggro", "hate",
)


@dataclass(frozen=True)
class RoleTag:
    root: str
    mechanic: str
    source: str = "rule"
    weight: float = 1.0


def _text(card: Mapping) -> str:
    values = [card.get("oracle_text"), card.get("english_oracle_text")]
    return (" ".join(str(value) for value in values if value)
            .replace("’", "'").replace("‘", "'").strip().lower())


def _type_line(card: Mapping) -> str:
    return str(card.get("type_line") or card.get("type") or "").lower()


def _keywords(card: Mapping) -> Set[str]:
    values = card.get("keywords") or []
    return {str(value).strip().lower() for value in values if value}


def _cmc(card: Mapping) -> float:
    try:
        return float(card.get("cmc") or 0)
    except (TypeError, ValueError):
        return 0.0


def _power(card: Mapping) -> Optional[float]:
    try:
        return float(card.get("power"))
    except (TypeError, ValueError):
        return None


def _is_creature(card: Mapping) -> bool:
    return "creature" in _type_line(card)


def _is_land(card: Mapping) -> bool:
    return "land" in _type_line(card)


def _is_fast_spell(card: Mapping) -> bool:
    types = _type_line(card)
    return "instant" in types or "flash" in _keywords(card)


def _add(tags: List[RoleTag], root: str, mechanic: str) -> None:
    if root not in ROOTS or any(t.root == root and t.mechanic == mechanic for t in tags):
        return
    tags.append(RoleTag(root, mechanic))


def classify_card(card: Mapping) -> List[RoleTag]:
    """按卡牌文本和类型返回规则标签。

    只记录白名单内的明确命中；缺少字段或没有命中时返回空列表。
    """
    text = _text(card)
    types = _type_line(card)
    keywords = _keywords(card)
    creature = _is_creature(card)
    land = _is_land(card)
    tags: List[RoleTag] = []

    # removal: 排除地牌，并避免把单纯坟场驱逐误算成场面去除。
    if not land:
        if re.search(r"destroy (?:target|all|each)\b", text):
            _add(tags, "removal", "destroy")
        if re.search(r"exile (?:target|all|each)\b", text) and "graveyard" not in text:
            _add(tags, "removal", "exile")
        if re.search(r"\bdeals?\b.*\bdamage to (?:target )?(?:creature|planeswalker|any target)", text):
            _add(tags, "removal", "damage")
        if "deathtouch" in keywords and creature:
            _add(tags, "removal", "deathtouch")
        if re.search(r"\bfights?\b", text) and creature:
            _add(tags, "removal", "fight")
        if re.search(r"target .* gets -\d+/-\d+", text):
            _add(tags, "removal", "minus_effect")
        if re.search(r"(?:destroy|exile) (?:all|each)\b", text):
            _add(tags, "removal", "board_wipe")
        if re.search(r"return target .* to (?:its|their) owner.?'s hand", text):
            _add(tags, "removal", "bounce")

    # card_advantage
    draws = bool(re.search(r"\b(?:you|each player) draw\b|\bdraw (?:a|one|two|three|four|five|six|x|cards?)\b", text))
    if draws:
        _add(tags, "card_advantage", "draw")
        if re.search(r"draw (?:two|three|four|five|six|x|\d+) cards?|draw cards equal", text):
            _add(tags, "card_advantage", "mass_draw")
        if re.search(r"(?:upkeep|draw step|beginning of your turn)", text):
            _add(tags, "card_advantage", "draw_per_turn")
    if re.search(r"exile the top .* you may (?:play|cast)", text):
        _add(tags, "card_advantage", "impulse_draw")
    if "scry" in text:
        _add(tags, "card_advantage", "scry")
    if "surveil" in text:
        _add(tags, "card_advantage", "surveil")
    if "cycling" in text or "cycling" in keywords:
        _add(tags, "card_advantage", "cycling")
    if re.search(r"(?:draw then discard|discard .* then draw|rummage)", text):
        _add(tags, "card_advantage", "loot")
    if "search your library" in text:
        _add(tags, "card_advantage", "tutor")

    # mana_development
    if re.search(r"search your library for .*land|put .*land.*battlefield|add (?:one|two) mana|add \{c\}", text):
        _add(tags, "mana_development", "ramp")
    if "any color" in text or "any one color" in text:
        _add(tags, "mana_development", "mana_fixing")
    if "treasure token" in text:
        _add(tags, "mana_development", "treasure")
    if re.search(r"\badd\s+\{[wubrgc]\}", text):
        if creature:
            _add(tags, "mana_development", "mana_dork")
        elif "artifact" in types and _cmc(card) <= 3:
            _add(tags, "mana_development", "mana_rock")

    # threat
    evasion = ("flying", "trample", "menace", "unblockable", "intimidate", "fear", "shadow")
    if creature:
        if any(value in keywords for value in evasion):
            _add(tags, "threat", "evasion")
        for value in evasion:
            if value in keywords:
                _add(tags, "threat", value)
        if (_power(card) or 0) >= 4:
            _add(tags, "threat", "big_creature")
        if _cmc(card) >= 6:
            _add(tags, "threat", "high_cost_threat")
    if "enters" in text and re.search(r"\b(draw|create|destroy|return|gain|exile)\b", text):
        _add(tags, "threat", "etb_value")
    if "create" in text and "token" in text:
        _add(tags, "threat", "token")
    if "haste" in keywords:
        _add(tags, "threat", "haste")
    if "prowess" in keywords:
        _add(tags, "threat", "prowess")

    # protection
    if re.search(r"gain(?:s)? life|lifelink", text) or "lifelink" in keywords:
        _add(tags, "protection", "lifegain")
    if "hexproof" in keywords or "hexproof" in text or "shroud" in keywords:
        _add(tags, "protection", "hexproof")
    if "ward" in keywords or "ward" in text:
        _add(tags, "protection", "ward")
    if "indestructible" in keywords:
        _add(tags, "protection", "indestructible")
    if "prevent all combat damage" in text or "fog" in keywords:
        _add(tags, "protection", "fog")
    if _is_fast_spell(card) and re.search(r"[+-]\d+/[+-]\d+", text):
        _add(tags, "protection", "pump")

    # tempo / control
    bounce = bool(re.search(r"return target .* to (?:its|their) owner.?'s hand", text))
    if bounce:
        _add(tags, "tempo", "bounce")
        _add(tags, "control", "bounce")
    if re.search(r"tap target|doesn't untap", text):
        _add(tags, "tempo", "tap")
        _add(tags, "control", "tap")
    if re.search(r"can't attack|can't block|doesn't untap", text):
        _add(tags, "tempo", "freeze")
    if _is_fast_spell(card) and re.search(r"[+-]\d+/[+-]\d+|gains? [a-z]+", text):
        _add(tags, "tempo", "combat_trick")
    if re.search(r"counter target|counterspell", text):
        _add(tags, "control", "counterspell")
    if "flash" in keywords:
        _add(tags, "control", "flash")
    if "target opponent discards" in text:
        _add(tags, "control", "discard")

    # aggro
    if "haste" in keywords:
        _add(tags, "aggro", "haste")
    if "prowess" in keywords:
        _add(tags, "aggro", "prowess")
    if creature and _cmc(card) <= 2:
        _add(tags, "aggro", "low_cost_creature")

    # hate is kept separate because it is primarily a sideboard signal.
    if "graveyard" in text and re.search(r"exile|remove", text):
        _add(tags, "hate", "graveyard_hate")
    if re.search(r"(?:destroy|exile) target artifact", text):
        _add(tags, "hate", "artifact_hate")
    if re.search(r"(?:destroy|exile) target enchantment", text):
        _add(tags, "hate", "enchantment_hate")
    if "fog" in text or "prevent all combat damage" in text or "gain life" in text:
        _add(tags, "hate", "anti_aggro")
    if "discard" in text or "counter target" in text:
        _add(tags, "hate", "anti_control")

    return tags


def _coerce_ai_tag(value) -> Optional[RoleTag]:
    if isinstance(value, RoleTag):
        return value
    if not isinstance(value, Mapping):
        return None
    root = value.get("root") or value.get("RootTag")
    mechanic = value.get("mechanic") or value.get("MechanicTag")
    if root not in ROOTS or not mechanic:
        return None
    try:
        weight = float(value.get("weight", value.get("Weight", 1.0)))
    except (TypeError, ValueError):
        return None
    return RoleTag(root, str(mechanic), str(value.get("source", "ai")), weight)


def merge_ai_tags(rule_tags: Sequence[RoleTag], ai_tags: Iterable) -> List[RoleTag]:
    """将上层传入的 AI 标签作为规则标签的补充。

    同一根标签已有规则命中时，AI 不覆盖该根；不同根仍可补充。非法根或坏数据直接
    丢弃，不生成默认标签。
    """
    merged = list(rule_tags)
    rule_roots = {CANONICAL_MECHANIC_ROOT.get(tag.mechanic, tag.root) for tag in rule_tags}
    for value in ai_tags or []:
        tag = _coerce_ai_tag(value)
        if tag is None:
            continue
        canonical_root = CANONICAL_MECHANIC_ROOT.get(tag.mechanic, tag.root)
        if canonical_root in rule_roots:
            continue
        if any(item.root == tag.root and item.mechanic == tag.mechanic for item in merged):
            continue
        merged.append(tag)
    return merged


def _score_root(tag: RoleTag, discount_ai: bool) -> float:
    root = CANONICAL_MECHANIC_ROOT.get(tag.mechanic, tag.root)
    value = ROOT_WEIGHTS.get(root, 0.0) + MECHANIC_MODIFIERS.get(tag.mechanic, 0.0)
    if discount_ai and tag.source.lower() == "ai":
        value *= AI_DISCOUNT
    return value * tag.weight


def score_tags(tags: Iterable[RoleTag], discount_ai: bool = True) -> float:
    """每个根只取最高机制分，合计封顶 4.0。"""
    best = {}
    for tag in tags or []:
        if not isinstance(tag, RoleTag):
            continue
        root = CANONICAL_MECHANIC_ROOT.get(tag.mechanic, tag.root)
        value = _score_root(tag, discount_ai)
        best[root] = max(value, best.get(root, 0.0))
    return min(MAX_TAG_SCORE, sum(best.values()))


def has_root(tags: Iterable[RoleTag], root: str) -> bool:
    return any(CANONICAL_MECHANIC_ROOT.get(tag.mechanic, tag.root) == root for tag in tags or [])


def has_mechanic(tags: Iterable[RoleTag], mechanic: str) -> bool:
    return any(tag.mechanic == mechanic for tag in tags or [])


def primary_role(tags: Iterable[RoleTag], card: Optional[Mapping] = None) -> str:
    """按限制赛评分优先级返回主要根标签；无命中时不伪造标签。"""
    tag_list = list(tags or [])
    for root in ROLE_PRIORITY:
        if has_root(tag_list, root):
            return root
    if card and _is_creature(card):
        return "threat"
    return ""
