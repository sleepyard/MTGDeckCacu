#!/usr/bin/env python3
"""构筑赛套牌构造策略（纯函数层）。

候选牌应来自 ``mtg_tool.py search --out`` 的规范化 JSON。种子牌必须存在于候选
池中并按原数量保留；模块配额用于补位，不替代人工主题研究。
"""

from collections import Counter
from dataclasses import dataclass, field
import re
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import deck_core
import roles
import constructed_synergy


MODULES = ("M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9")
REQUIRED_MODULES = ("M1", "M2", "M3", "M5", "M8")
MAIN_MODULES = {"M1", "M2", "M3", "M4", "M5", "M8"}
NORMAL_SIZE = 60
NORMAL_LANDS = 24
SIDEBOARD_SIZE = 15
BRAWL_SIZE = 99
BRAWL_LANDS = 37
BRAWL_FORMATS = {"brawl", "standard_brawl", "competitive_brawl"}
MODULE_QUOTAS = {
    "M1": (4, 8, 14),
    "M2": (3, 6, 12),
    "M3": (2, 5, 10),
    "M4": (0, 2, 6),
    "M5": (5, 9, 16),
    "M6": (0, 0, SIDEBOARD_SIZE),
    "M7": (0, 0, 1),
    "M8": (3, 6, 14),
    "M9": (0, 0, 1),
}


@dataclass(frozen=True)
class SeedSet:
    main: Tuple[Tuple[int, str], ...]
    sideboard: Tuple[Tuple[int, str], ...] = ()
    commander: Tuple[Tuple[int, str], ...] = ()
    companion: Tuple[Tuple[int, str], ...] = ()


@dataclass(frozen=True)
class ConstructedEntry:
    card: Mapping
    count: int
    module: str
    reason: str


@dataclass
class ConstructedDeck:
    format: str
    main: List[ConstructedEntry]
    sideboard: List[ConstructedEntry]
    commander: List[ConstructedEntry]
    modules: Dict[str, int]
    colors: Tuple[str, ...]
    valid: bool
    violations: List[str] = field(default_factory=list)
    report: List[str] = field(default_factory=list)
    companion: List[ConstructedEntry] = field(default_factory=list)


def parse_seed_lines(lines: Iterable[str]) -> SeedSet:
    """解析种子文件；支持 Deck/Sideboard/Commander/Companion 分区。"""
    sections = {"main": [], "sideboard": [], "commander": [], "companion": []}
    current = "main"
    headers = {"deck": "main", "sideboard": "sideboard",
               "commander": "commander", "companion": "companion"}
    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        low = line.lower()
        if low in headers:
            current = headers[low]
            continue
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            quantity, name = int(parts[0]), parts[1].strip()
        else:
            quantity, name = 1, line
        if quantity <= 0 or not name:
            raise ValueError(f"种子第 {lineno} 行数量或牌名无效: {line!r}")
        sections[current].append((quantity, name))
    if not sections["main"] and not sections["commander"]:
        raise ValueError("种子文件没有主牌或指挥官")
    return SeedSet(*(tuple(sections[key]) for key in ("main", "sideboard", "commander", "companion")))


def parse_seed_file(path: str) -> SeedSet:
    with open(path, "r", encoding="utf-8") as handle:
        return parse_seed_lines(handle)


def _name(card: Mapping) -> str:
    return str(card.get("name") or "").strip()


def _colors(card: Mapping) -> Set[str]:
    values = card.get("color_identity") or card.get("colors") or []
    return {str(value).upper() for value in values if str(value).upper() in "WUBRG"}


def _type_line(card: Mapping) -> str:
    return str(card.get("type_line") or card.get("type") or "")


def _is_land(card: Mapping) -> bool:
    type_line = _type_line(card).lower()
    # Transform DFCs with a land back are spells in the opening deck. Modal
    # DFCs whose front face is a land remain playable as lands.
    front = type_line.split(" // ", 1)[0]
    return "land" in front


def _is_basic(card: Mapping) -> bool:
    return "basic" in _type_line(card).lower() and _is_land(card)


def _is_commander_candidate(card: Mapping) -> bool:
    if card.get("is_commander"):
        return True
    types = _type_line(card).lower()
    return "legendary" in types and ("creature" in types or "planeswalker" in types)


def _cmc(card: Mapping) -> float:
    try:
        return float(card.get("cmc") or 0)
    except (TypeError, ValueError):
        return 0.0


def _legal(card: Mapping, fmt: str, platform: Optional[str] = None) -> bool:
    legalities = card.get("legalities")
    if not isinstance(legalities, Mapping):
        return False
    lookup = {"explorer": "pioneer"}.get(fmt.lower(), fmt.lower())
    if legalities.get(lookup) != "legal":
        return False
    if platform and platform.lower() not in (card.get("games") or []):
        return False
    return True


def _module(card: Mapping) -> str:
    explicit = str(card.get("module") or "").upper()
    if explicit in MODULES:
        return explicit
    tags = roles.classify_card(card)
    if card.get("companion") or card.get("is_companion"):
        return "M7"
    if card.get("is_commander"):
        return "M9"
    if _is_land(card) or card.get("layout") in {"modal_dfc", "adventure"}:
        return "M4"
    if roles.has_root(tags, "removal") or roles.has_root(tags, "tempo") or \
            roles.has_root(tags, "control"):
        return "M5"
    if roles.has_root(tags, "mana_development") or \
            roles.has_root(tags, "card_advantage"):
        return "M2"
    if roles.has_mechanic(tags, "big_creature") or \
            roles.has_mechanic(tags, "high_cost_threat"):
        return "M3"
    if roles.has_root(tags, "protection"):
        return "M8"
    if roles.has_root(tags, "threat") or roles.has_root(tags, "aggro"):
        return "M1"
    if roles.has_root(tags, "hate"):
        return "M6"
    return ""


def _score_parts(card: Mapping, module: str, strategy: str):
    base = {"M1": 5, "M2": 4, "M3": 4, "M4": 2, "M5": 4, "M8": 3}.get(module, 0)
    cmc = _cmc(card)
    if strategy == "aggro":
        tempo = max(0.0, 3.0 - cmc)
    elif strategy == "control":
        tempo = min(cmc, 6.0) * 0.3
    else:
        tempo = 1.0 if 2.0 <= cmc <= 4.0 else 0.0
    return base, tempo


def _strategy_score(card: Mapping, module: str, strategy: str, context=()) -> float:
    return sum(_score_parts(card, module, strategy)) + constructed_synergy.score_candidate(card, context)["score"]


def _selection_reason(card, module, strategy, purpose, context=()):
    base, tempo = _score_parts(card, module, strategy)
    synergy = constructed_synergy.score_candidate(card, context)
    details = "；".join(item["label"] + "：" + "、".join(item["cards"]) for item in synergy["evidence"])
    return (f"{purpose}；模块分 {base:.2f} + 节奏分 {tempo:.2f} + 协同分 {synergy['score']:.2f}"
            f" = {base + tempo + synergy['score']:.2f}（结构启发式）" + ("；依据 " + details if details else ""))


def _weighted_pips(entries):
    result = Counter()
    for item in entries:
        pips = deck_core.parse_mana_pips(
            str(item.card.get("mana_cost") or item.card.get("cost") or "").split(" // ")[0])
        for color, count in pips.items():
            result[color] += count * item.count
    return result


def _basic_card(name: str, color: str) -> Mapping:
    type_line = "Basic Land — " + name
    return {"name": name, "colors": [color] if color != "C" else [],
            "color_identity": [color] if color != "C" else [],
            "type_line": type_line, "mana_cost": "", "oracle_text": "",
            "legalities": {}, "games": ["arena", "paper", "mtgo"]}


def _basic_for_color(color: str) -> Mapping:
    return _basic_card({"W": "Plains", "U": "Island", "B": "Swamp",
                        "R": "Mountain", "G": "Forest", "C": "Wastes"}[color], color)


def _index_candidates(candidates: Sequence[Mapping]) -> Dict[str, Mapping]:
    result = {}
    for card in candidates:
        name = _name(card)
        if not name:
            raise ValueError("候选池包含缺少 name 的记录")
        if name in result:
            raise ValueError(f"候选池存在重复牌名: {name}")
        result[name] = card
    return result


def _seed_requirements(seed: SeedSet, index: Mapping[str, Mapping]) -> Dict[str, int]:
    required = Counter()
    for section in (seed.main, seed.sideboard, seed.commander, seed.companion):
        for quantity, name in section:
            if type(quantity) is not int or quantity < 1:
                raise ValueError("种子数量必须是正整数: " + str(name))
            if name not in index:
                raise ValueError(f"种子牌不在候选池: {name}")
            required[name] += quantity
    return dict(required)


def _allowed_colors(seed_cards: Iterable[Mapping], commander: Sequence[Mapping],
                    companion: Sequence[Mapping] = ()) -> Set[str]:
    source = list(commander) or list(seed_cards) or list(companion)
    return {color for card in source for color in _colors(card)}


def _max_copies(card: Mapping, brawl: bool) -> int:
    if _is_basic(card):
        return 99 if brawl else 60
    if brawl:
        return 1
    try:
        return max(1, int(card.get("max_copies", 4)))
    except (TypeError, ValueError):
        return 4


def _entry(card: Mapping, count: int, module: Optional[str], reason: str) -> ConstructedEntry:
    return ConstructedEntry(card, count, module or "other", reason)


def _group_entries(entries: Iterable[ConstructedEntry]) -> List[ConstructedEntry]:
    grouped = {}
    for item in entries:
        key = _name(item.card)
        if key in grouped:
            old = grouped[key]
            grouped[key] = _entry(old.card, old.count + item.count,
                                   old.module, old.reason)
        else:
            grouped[key] = item
    return list(grouped.values())


def _select_nonlands(candidates: Sequence[Mapping], seed_entries: Sequence[ConstructedEntry],
                     target: int, brawl: bool, allowed: Set[str], strategy: str,
                     reserved=None, theme_cards=()):
    reserved = reserved or {}
    selected = list(seed_entries)
    selected_names = {_name(item.card) for item in selected}
    counts = Counter()
    for item in selected:
        counts[item.module] += item.count
    available = [card for card in candidates
                 if not _is_land(card) and not _is_basic(card)
                 and _colors(card).issubset(allowed)
                 and _max_copies(card, brawl) > reserved.get(_name(card), 0)
                 and _name(card) not in selected_names]
    required_order = REQUIRED_MODULES + ("M4",)
    for position, module in enumerate(required_order):
        _lo, wanted, maximum = MODULE_QUOTAS[module]
        while counts[module] < wanted and sum(item.count for item in selected) < target:
            choices = [card for card in available if _module(card) == module]
            if not choices:
                break
            context = list(theme_cards) + [item.card for item in selected]
            card = max(choices, key=lambda item: (_strategy_score(item, module, strategy, context), _name(item)))
            capacity = min(_max_copies(card, brawl) - reserved.get(_name(card), 0),
                           max(0, wanted - counts[module]),
                           target - sum(item.count for item in selected))
            later_minimum = sum(
                max(0, MODULE_QUOTAS[later][0] - counts[later])
                for later in required_order[position + 1:]
            )
            capacity = min(capacity, max(0, target - sum(item.count for item in selected)
                            - later_minimum))
            if capacity <= 0:
                break
            available.remove(card)
            selected.append(_entry(card, capacity, module,
                                   _selection_reason(card, module, strategy, f"补足 {module} 配额", context)))
            counts[module] += capacity

    while sum(item.count for item in selected) < target and available:
        context = list(theme_cards) + [item.card for item in selected]
        choices = []
        for card in available:
            module = _module(card)
            if module not in MAIN_MODULES:
                continue
            _lo, wanted, maximum = MODULE_QUOTAS.get(module, (0, 0, target))
            if counts[module] >= maximum:
                continue
            if target - sum(item.count for item in selected) <= 0:
                break
            deficit = max(0, wanted - counts[module])
            choices.append((deficit, _strategy_score(card, module, strategy, context), card, module))
        if not choices:
            break
        _deficit, score, card, module = max(choices, key=lambda item: (item[0], item[1], _name(item[2])))
        available.remove(card)
        maximum = MODULE_QUOTAS.get(module, (0, 0, target))[2]
        capacity = min(_max_copies(card, brawl) - reserved.get(_name(card), 0),
                       max(0, maximum - counts[module]),
                       target - sum(item.count for item in selected))
        if capacity <= 0:
            continue
        selected.append(_entry(card, capacity, module,
                               _selection_reason(card, module, strategy, "候选补位", context)))
        counts[module] += capacity
    return _group_entries(selected), available, counts


def _land_entries(candidates: Sequence[Mapping], seed_entries: Sequence[ConstructedEntry],
                  nonlands: Sequence[ConstructedEntry], target: int, brawl: bool,
                  allowed: Set[str], reserved=None) -> List[ConstructedEntry]:
    reserved = reserved or {}
    selected = list(seed_entries)
    selected_names = {_name(item.card) for item in selected}
    available = [card for card in candidates if _is_land(card) and not _is_basic(card)
                 and _colors(card).issubset(allowed) and _name(card) not in selected_names]
    def land_key(card):
        text = str(card.get("oracle_text") or "").lower()
        mana_land = bool(re.search(r"\{t\}\s*:\s*add", text))
        aligned = bool(set(_colors(card)) & set(allowed))
        if not aligned:
            aligned = any("add {" + color.lower() + "}" in text for color in allowed)
            aligned = aligned or "any color" in text
        fixing = "any color" in text or "one mana of any color" in text
        color_span = len(set(_colors(card)) & set(allowed))
        return (not mana_land, not fixing, not aligned, -color_span, _name(card))

    candidate_limit = 12 if brawl else 2
    for card in sorted(available, key=land_key)[:candidate_limit]:
        text = str(card.get("oracle_text") or "").lower()
        if not re.search(r"\{t\}\s*:\s*add", text):
            continue
        if sum(item.count for item in selected) >= target:
            break
        quantity = min(_max_copies(card, brawl) - reserved.get(_name(card), 0),
                       target - sum(item.count for item in selected))
        if quantity > 0:
            selected.append(_entry(card, quantity, "M4", "保留可用非基本地"))

    pip_counts = _weighted_pips(nonlands)
    desired = deck_core.mana_base(dict(pip_counts), target)
    source_counts = Counter()
    flexible_sources = 0
    for item in selected:
        produces = (item.card.get("produced_mana") or item.card.get("produces_colors")
                    or item.card.get("colors") or [])
        # produced_mana lists potential colors, including restricted sources.
        text = "\n".join(line for line in str(item.card.get("oracle_text") or "").lower().splitlines()
                         if re.search(r"\{t\}\s*:\s*add", line))
        if re.search(r"spend this mana|an opponent|for each|commander|chosen color", text):
            produces = []
        for color in produces:
            if color in allowed:
                source_counts[color] += item.count
        if ("any color" in text or "one mana of any color" in text) and not re.search(
                r"spend this mana|an opponent|for each|commander|chosen color", text):
            flexible_sources += item.count
    remaining = max(0, target - sum(item.count for item in selected))
    deficits = {color: max(0, quantity - source_counts[color])
                for color, quantity in desired.items()}
    weights = (dict(pip_counts) if flexible_sources or not any(deficits.values())
               else {color: value for color, value in deficits.items() if value})
    if remaining < len(weights):
        weights = dict(sorted(weights.items(), key=lambda item: (-item[1], item[0]))[:remaining])
    basic_targets = (desired if not selected and sum(desired.values()) <= remaining
                     else deck_core.mana_base(weights, remaining))
    for color, quantity in sorted(basic_targets.items()):
        if quantity:
            selected.append(_entry(_basic_for_color(color), quantity, "M4", "按加权符号及已有色源补基础地"))
    while sum(item.count for item in selected) < target:
        color = sorted(allowed)[0] if allowed else "C"
        selected.append(_entry(_basic_for_color(color),
                              target - sum(item.count for item in selected),
                              "M4", "填充剩余地牌槽位"))
    return _group_entries(selected)


def _sideboard(candidates: Sequence[Mapping], selected: Sequence[ConstructedEntry],
               size: int, brawl: bool, allowed: Set[str], strategy: str,
               seed_entries=()) -> List[ConstructedEntry]:
    if size <= 0 or brawl:
        return []
    used = Counter()
    for item in list(selected) + list(seed_entries):
        used[_name(item.card)] += item.count
    seed_names = {_name(item.card) for item in seed_entries}
    available = [card for card in candidates if _name(card) not in seed_names
                 and not _is_land(card) and _colors(card).issubset(allowed)]
    available.sort(key=lambda card: (_module(card) != "M6",
                                     -_strategy_score(card, _module(card), strategy), _name(card)))
    result = list(seed_entries)
    slots = size - sum(item.count for item in result)
    for card in available:
        if slots <= 0:
            break
        quantity = min(_max_copies(card, False) - used[_name(card)], slots)
        if quantity <= 0:
            continue
        result.append(_entry(card, quantity, _module(card), "备牌候选"))
        slots -= quantity
    return result


def validate_constructed(deck: ConstructedDeck, seed: SeedSet, platform: Optional[str] = None) -> List[str]:
    violations = []
    brawl = deck.format.lower() in BRAWL_FORMATS
    main_count = sum(item.count for item in deck.main)
    side_count = sum(item.count for item in deck.sideboard)
    companion_count = sum(item.count for item in deck.companion)
    if companion_count > 1:
        violations.append(f"Companion {companion_count} > 1")
    if brawl:
        if len(deck.commander) != 1 or sum(item.count for item in deck.commander) != 1:
            violations.append("Brawl 必须恰好有 1 名指挥官")
        elif not _is_commander_candidate(deck.commander[0].card):
            violations.append("Brawl 指挥官必须标记为指挥官或为传奇生物/鹏洛客")
        if main_count != BRAWL_SIZE:
            violations.append(f"Brawl 牌库应为 {BRAWL_SIZE} 张，实际 {main_count} 张")
        if side_count:
            violations.append("Brawl 不允许备牌")
    else:
        if main_count < NORMAL_SIZE:
            violations.append(f"主牌 {main_count} 张 < {NORMAL_SIZE}")
        if side_count > SIDEBOARD_SIZE:
            violations.append(f"备牌 {side_count} 张 > {SIDEBOARD_SIZE}")
        if side_count + companion_count > SIDEBOARD_SIZE:
            violations.append(f"备牌含行侣 {side_count + companion_count} 张 > {SIDEBOARD_SIZE}")
        if deck.commander:
            violations.append("普通构筑不应包含 Commander 分区")

    totals = Counter()
    for section in (deck.main, deck.sideboard, deck.commander, deck.companion):
        for item in section:
            name = _name(item.card)
            if type(item.count) is not int or item.count < 1:
                violations.append(f"{name} 数量必须是正整数")
            totals[name] += item.count
            if not _legal(item.card, deck.format, platform) and not _is_basic(item.card):
                violations.append(f"{name} 缺少 {deck.format} 合法性或不合法")
    for name, total in totals.items():
        item = next(item for section in (deck.main, deck.sideboard, deck.commander,
                                         deck.companion)
                    for item in section if _name(item.card) == name)
        if not _is_basic(item.card):
            maximum = _max_copies(item.card, brawl)
            if total > maximum:
                violations.append(f"{name} 总数 {total} > {maximum}")
    for section_name in ("main", "sideboard", "commander", "companion"):
        required = Counter()
        for quantity, name in getattr(seed, section_name):
            required[name] += quantity
        actual = Counter()
        for item in getattr(deck, section_name):
            actual[_name(item.card)] += item.count
        for name, quantity in required.items():
            if actual[name] < quantity:
                violations.append(f"{section_name} 种子牌未完整保留: {name}（需要 {quantity}，实际 {actual[name]}）")
    for quantity, name in seed.commander:
        if sum(item.count for item in deck.commander if _name(item.card) == name) < quantity:
            violations.append(f"种子指挥官未完整保留: {name}")
    for quantity, name in seed.companion:
        if sum(item.count for item in deck.companion if _name(item.card) == name) < quantity:
            violations.append(f"Companion seed not preserved: {name}")
    return sorted(set(violations))


def build_constructed_deck(candidates: Sequence[Mapping], seed: SeedSet,
                           fmt: str, bo3: bool = False, strategy: str = "mid",
                           platform: Optional[str] = None) -> ConstructedDeck:
    """构建普通 60/15 或 Brawl 1+99 套牌，并返回结构门禁结果。"""
    if fmt.lower() == "alchemy":
        raise ValueError("Alchemy 不在当前开发与构筑范围内")
    if strategy not in deck_core.STRATEGY_TARGETS:
        raise ValueError(
            f"strategy 必须是 {'、'.join(deck_core.STRATEGY_TARGETS)} 之一")
    index = _index_candidates(candidates)
    required = _seed_requirements(seed, index)
    brawl = fmt.lower() in BRAWL_FORMATS
    for name, quantity in required.items():
        if quantity > _max_copies(index[name], brawl):
            raise ValueError("种子主备合计超出同名上限: " + name)
    side_count = sum(quantity for quantity, _ in seed.sideboard)
    companion_count = sum(quantity for quantity, _ in seed.companion)
    if brawl and side_count:
        raise ValueError("Brawl 不允许备牌种子")
    if not brawl and side_count + companion_count > SIDEBOARD_SIZE:
        raise ValueError("备牌种子与行侣合计超过15张")
    commander = [_entry(index[name], quantity, "M9", "种子指挥官")
                 for quantity, name in seed.commander]
    companion = [_entry(index[name], quantity, "M7", "companion seed")
                 for quantity, name in seed.companion]
    seed_main = [_entry(index[name], quantity, _module(index[name]), "主题种子必留")
                 for quantity, name in seed.main]
    allowed = _allowed_colors([item.card for item in seed_main],
                              [item.card for item in commander],
                              [item.card for item in companion])
    all_cards = [card for card in candidates if _legal(card, fmt, platform)
                 or _is_basic(card)]
    seed_side = _group_entries([_entry(index[name], quantity, _module(index[name]), "指定备牌必留")
                               for quantity, name in seed.sideboard])
    missing_seed = [_name(item.card) for item in seed_main + seed_side + commander + companion
                    if item.card not in all_cards and not _is_basic(item.card)]
    if missing_seed:
        raise ValueError("种子牌不满足目标赛制或平台: " + ", ".join(missing_seed))
    if any(not _colors(item.card).issubset(allowed) for item in seed_side):
        raise ValueError("备牌种子超出本次种子确定的色组")

    target_size = BRAWL_SIZE if brawl else NORMAL_SIZE
    land_target = BRAWL_LANDS if brawl else NORMAL_LANDS
    nonland_target = target_size - land_target
    commander_names = {_name(item.card) for item in commander}
    companion_names = {_name(item.card) for item in companion}
    selection_cards = [card for card in all_cards
                       if _name(card) not in commander_names | companion_names]
    seed_nonlands = [item for item in seed_main if not _is_land(item.card)]
    reserved = Counter()
    for item in seed_side:
        reserved[_name(item.card)] += item.count
    selected_nonlands, available, modules = _select_nonlands(
        selection_cards, seed_nonlands, nonland_target, brawl, allowed, strategy,
        reserved, [item.card for item in seed_main + commander])
    seed_lands = [_entry(index[name], quantity, "M4", "种子地牌必留")
                  for quantity, name in seed.main if _is_land(index[name])]
    selected_nonlands = [item for item in selected_nonlands if not _is_land(item.card)]
    selected_lands = _land_entries(selection_cards, seed_lands, selected_nonlands,
                                   land_target, brawl, allowed, reserved)
    main = _group_entries(selected_nonlands + selected_lands)
    sideboard = _sideboard(all_cards, main + commander + companion,
                           SIDEBOARD_SIZE - companion_count if bo3 else side_count,
                           brawl, allowed, strategy, seed_side)
    colors = tuple(sorted(allowed))
    modules = dict(modules)
    modules["M7"] = sum(item.count for item in companion)
    modules["M9"] = sum(item.count for item in commander)
    deck = ConstructedDeck(fmt, main, sideboard, commander, modules, colors, True,
                           companion=companion)
    deck.violations = validate_constructed(deck, seed, platform)
    deck.valid = not deck.violations
    deck.report = [
        f"格式: {fmt}{' BO3' if bo3 else ''}",
        f"颜色身份: {''.join(colors) or '无色'}",
        f"主牌 {sum(item.count for item in main)} 张，备牌 {sum(item.count for item in sideboard)} 张",
        "模块: " + " / ".join(f"{module}×{modules.get(module, 0)}" for module in MODULES),
        "有色符号需求（按张数加权、仅正面费用）: " + " / ".join(
            f"{color} {count:g}" for color, count in sorted(_weighted_pips(selected_nonlands).items())),
        "评估口径: 配额和节奏分是结构启发式，未模拟对手，不代表胜率或单卡强度排名",
        "门禁: " + ("通过" if deck.valid else "失败: " + "；".join(deck.violations)),
    ]
    return deck
