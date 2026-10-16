"""Evaluation request validation and frozen card preparation for the workbench."""
import copy

import deck_evaluate as evaluation
import deck_model
import mtg_tool

MAX_RUNS = 5000
MAX_NAMES = 150


def parse_request(body):
    allowed = {"format", "runs", "turns", "seed", "on_draw", "max_mulligans", "free_mulligans",
               "keep_min", "keep_max", "targets", "cards", "baseline_text"}
    if set(body) - allowed:
        raise ValueError("未知评测参数: " + ", ".join(sorted(set(body) - allowed)))
    fmt = body.get("format", "pioneer")
    if fmt not in evaluation.FORMATS:
        raise ValueError("不支持的评测赛制（Alchemy已排除）")
    defaults = {"runs": 2000, "turns": 5, "seed": 20261016, "on_draw": fmt == "commander",
                "max_mulligans": 2, "free_mulligans": 1 if fmt in
                ("commander", "brawl", "standard_brawl", "competitive_brawl") else 0,
                "keep_min": 2, "keep_max": 5}
    options = {key: body.get(key, value) for key, value in defaults.items()}
    for key, value in options.items():
        if type(value) is not (bool if key == "on_draw" else int):
            raise ValueError(key + " 类型错误")
    if not 1 <= options["runs"] <= MAX_RUNS or not 1 <= options["turns"] <= 8:
        raise ValueError("网页评测支持1至5000次抽样、1至8回合")
    if not 0 <= options["free_mulligans"] <= options["max_mulligans"] <= 5:
        raise ValueError("调度次数需满足 0 ≤ 免费次数 ≤ 总次数 ≤ 5")
    if not 0 <= options["keep_min"] <= options["keep_max"] <= 7:
        raise ValueError("留牌地数需满足 0 ≤ 最少 ≤ 最多 ≤ 7")
    targets = body.get("targets", [])
    if (not isinstance(targets, list) or len(targets) > 12
            or any(not isinstance(name, str) or not name.strip() for name in targets)):
        raise ValueError("关键咒语需为最多12个非空牌名")
    options["targets"] = [name.strip() for name in targets]
    cards = body.get("cards")
    if cards is not None:
        evaluation.card_index(cards)
    text = body.get("baseline_text", "")
    if not isinstance(text, str) or len(text) > 80000:
        raise ValueError("对照牌表必须是有效文本，且不超过80000字符")
    baseline = deck_model.parse_text(text, strict=True) if text.strip() else None
    return fmt, options, copy.deepcopy(cards), baseline


def prepare_cards(decks, cards, fetch_card=None, progress=None):
    """Only fetch missing exact cards; supplied offline snapshots never need HTTP."""
    cards = copy.deepcopy(cards)
    index = evaluation.card_index(cards)
    names = sorted({name for deck in decks for _, name, _ in deck.entries()})
    if len(names) > MAX_NAMES:
        raise ValueError("单次评测最多150个不同牌名")
    progress = progress or (lambda *args: None)
    unresolved = []
    for number, name in enumerate(names):
        progress("核对牌面：" + name, number, len(names))
        try:
            evaluation.resolve(name, index)
        except ValueError:
            if fetch_card is None:
                unresolved.append(name)
                continue
            try:
                card = fetch_card(name)
                if not isinstance(card, dict) or not mtg_tool.name_matches(name, card):
                    raise ValueError("未精确命中")
                cards.append(copy.deepcopy(card))
                index = evaluation.card_index(cards)
            except (ValueError, OSError, mtg_tool.MtgToolError) as exc:
                unresolved.append(name + "：" + str(exc))
    if unresolved:
        raise ValueError("牌面证据不完整，未生成评测：" + "；".join(unresolved))
    progress("牌面已核对，开始抽样", len(names), len(names))
    return cards
