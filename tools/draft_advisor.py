#!/usr/bin/env python3
"""轮抓 pick 推荐：机器七轴 + LLM 两个定性轴。

模块不负责 HTTP 或文件写入。调用方通过 ``llm_request(prompt)`` 注入 LLM，失败时
明确返回离线状态；排序仍使用评分表锚点，不制造缺失数据。
"""

import json
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import deck_core
import roles


MACHINE_AXES = ("curve_fit", "color_fit", "color_openness", "signal", "fixer",
                "removal", "rarity")
GRADE_ORDER = tuple(deck_core.GRADE_EQ)


@dataclass(frozen=True)
class PickRecommendation:
    card: Mapping
    scores: Mapping[str, float]
    total: float
    reason: str


@dataclass(frozen=True)
class AdviceResult:
    recommendations: Tuple[PickRecommendation, ...]
    status: str
    prompt: Optional[str] = None
    response: Optional[str] = None
    error: Optional[str] = None


def _name(card: Mapping) -> str:
    return str(card.get("name") or "").strip()


def _cmc(card: Mapping) -> float:
    try:
        return float(card.get("cmc") or 0)
    except (TypeError, ValueError):
        return 0.0


def _colors(card: Mapping) -> Tuple[str, ...]:
    values = card.get("colors") or []
    return tuple(sorted({str(value).upper() for value in values if str(value).upper() in "WUBRG"}))


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


def grade_anchor(card: Mapping, table=None) -> float:
    """将评分表等级映射到 0..1，作为 LLM 离线时的 RawPower 锚点。"""
    grade = _grade(card, table)
    if grade not in GRADE_ORDER:
        return 0.5
    return 1.0 - GRADE_ORDER.index(grade) / (len(GRADE_ORDER) - 1)


def power_anchor(card: Mapping, table=None) -> float:
    """RawPower 离线锚点：card 带 17Lands GIH 归一化值（gih_norm）时按
    0.6 等级锚点 + 0.4 GIH 混合；缺失或非法时退回纯等级锚点。"""
    gih_norm = card.get("gih_norm")
    if gih_norm is not None:
        try:
            return 0.6 * grade_anchor(card, table) + 0.4 * float(gih_norm)
        except (TypeError, ValueError):
            pass
    return grade_anchor(card, table)


def _tags(card: Mapping) -> List[roles.RoleTag]:
    supplied = card.get("role_tags")
    if supplied is not None:
        return [tag for tag in supplied if isinstance(tag, roles.RoleTag)]
    return roles.classify_card(card)


def _signal_score(card: Mapping, signals: Mapping[str, float], pick_number: Optional[int],
                  table=None) -> float:
    alsa = card.get("alsa")
    if alsa is not None and pick_number is not None:
        try:
            delta = pick_number - float(alsa)
        except (TypeError, ValueError):
            delta = 0.0
        if delta > deck_core.ALSA_MARGIN:
            return 0.8
        if delta < -deck_core.ALSA_MARGIN:
            return 0.2
        return 0.5
    if alsa is None:
        # 无 ALSA 时沿用设计稿规定的高等级锚点降级，不猜顺位。
        return grade_anchor(card, table)
    return 0.5


def machine_axes(card: Mapping, picked: Sequence[Mapping], signals: Mapping[str, float],
                 table=None, pick_number: Optional[int] = None) -> Dict[str, float]:
    """计算不依赖 LLM 的七个轴。"""
    picked_counts = {}
    picked_color_counts = {}
    for item in picked:
        slot = deck_core.cmc_slot(_cmc(item))
        picked_counts[slot] = picked_counts.get(slot, 0) + 1
        for color in _colors(item):
            picked_color_counts[color] = picked_color_counts.get(color, 0) + 1
    picked_colors = set(picked_color_counts)
    card_colors = _colors(card)
    tags = _tags(card)
    return {
        "curve_fit": deck_core.curve_fit_score(picked_counts, _cmc(card)),
        "color_fit": deck_core.color_fit_score(card_colors, picked_color_counts),
        "color_openness": deck_core.color_openness_score(signals, card_colors),
        "signal": _signal_score(card, signals, pick_number, table),
        "fixer": deck_core.fixer_score(
            card_colors, card.get("produces_colors") or [], picked_colors),
        "removal": 1.0 if roles.has_root(tags, "removal") else 0.0,
        "rarity": deck_core.rarity_score(card.get("rarity")),
    }


def build_prompt(pack: Sequence[Mapping], picked: Sequence[Mapping], table=None) -> str:
    """构造只要求两项定性分的单次 prompt（已抓牌池只给摘要，压 prompt 体积）。"""
    if not pack:
        raise ValueError("当前包为空")
    rows = []
    for card in pack:
        entry = _entry(card, table)
        row = {
            "name": _name(card),
            "mana_cost": card.get("mana_cost") or card.get("cost") or "",
            "type_line": card.get("type_line") or card.get("type") or "",
            "oracle_text": str(card.get("oracle_text") or "")[:300],
            "grade_anchor": entry.get("grade") or card.get("grade") or "unknown",
        }
        gih = card.get("gih_wr")
        if isinstance(gih, (int, float)) and not isinstance(gih, bool):
            # 原始 17Lands 数据是 0-1 小数，面板注入的已是百分比；统一归一为百分比
            row["gih_wr_pct"] = round(gih * 100, 1) if gih <= 1 else round(float(gih), 1)
        rows.append(row)
    picked_colors = {}
    picked_curve = {}
    key_bombs = []   # 高等级炸弹优先给 LLM 看（协同判断的关键件）
    key_rares = []
    for card in picked:
        for color in _colors(card):
            picked_colors[color] = picked_colors.get(color, 0) + 1
        slot = str(deck_core.cmc_slot(_cmc(card)))
        picked_curve[slot] = picked_curve.get(slot, 0) + 1
        entry = _entry(card, table)
        grade = str(entry.get("grade") or card.get("grade") or "")
        name = _name(card)
        if not name:
            continue
        if grade in ("S", "A", "A-", "B+"):
            key_bombs.append(name)
        elif str(card.get("rarity") or "").lower() in ("rare", "mythic"):
            key_rares.append(name)
    summary = {"colors": picked_colors, "curve": picked_curve,
               "key_cards": (key_bombs + key_rares)[:10]}
    return "\n".join([
        "你是万智牌限制赛选牌评审员。只评价当前包内的牌，不要计算费用、牌数、曲线或法术力。",
        "请严格返回 JSON 对象，picks 数组覆盖当前包每张牌：",
        '{"picks":[{"name":"当前牌名","raw_power":0到1,"synergy":0到1,"reason":"一句话理由"}]}',
        "raw_power 必须参考 grade_anchor，给出 gih_wr_pct（17Lands 在手胜率百分比）时"
        "同时参考；synergy 只根据已抓牌池摘要判断，与主色（colors 计数前二）完全脱色的牌"
        " synergy 不得超过 0.3。name 必须与输入完全一致。",
        "已抓牌池摘要：" + json.dumps(summary, ensure_ascii=False),
        "当前包：" + json.dumps(rows, ensure_ascii=False),
    ])


def parse_llm_scores(text: str, expected_names: Iterable[str]) -> Dict[str, Mapping]:
    """严格解析完整 picks 列表；缺牌、重复牌、越界分数均视为无效响应。
    兼容两种顶层形态：裸 JSON 数组，或 json_object 模式的对象（取 "picks"
    键，缺失时取唯一的 list 值）。"""
    if not isinstance(text, str):
        raise ValueError("LLM 响应不是文本")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM 响应不是 JSON: {exc}")
    if isinstance(data, dict):
        items = data.get("picks")
        if items is None:
            lists = [value for value in data.values() if isinstance(value, list)]
            items = lists[0] if len(lists) == 1 else None
        if not isinstance(items, list):
            raise ValueError("LLM 响应缺少 picks 数组")
        data = items
    names = list(dict.fromkeys(str(name) for name in expected_names if str(name)))
    if not isinstance(data, list) or {item.get("name") for item in data
                                      if isinstance(item, dict)} != set(names):
        raise ValueError("LLM 响应未完整覆盖当前包，拒绝使用部分结果")
    parsed = {}
    for item in data:
        if not isinstance(item, dict) or item.get("name") in parsed:
            raise ValueError("LLM 响应包含重复或非法牌名")
        name = item.get("name")
        raw = item.get("raw_power")
        synergy = item.get("synergy")
        reason = str(item.get("reason") or "").strip()
        if not isinstance(name, str) or name not in names or \
                isinstance(raw, bool) or isinstance(synergy, bool):
            raise ValueError("LLM 响应字段类型无效")
        try:
            raw = float(raw)
            synergy = float(synergy)
        except (TypeError, ValueError):
            raise ValueError("LLM 分数不是数字")
        if not 0.0 <= raw <= 1.0 or not 0.0 <= synergy <= 1.0 or not reason:
            raise ValueError("LLM 分数越界或缺少理由")
        parsed[name] = {"raw_power": raw, "synergy": synergy, "reason": reason}
    return parsed


def _machine_reason(card: Mapping, scores: Mapping[str, float], table=None) -> str:
    reasons = []
    if scores["curve_fit"] >= 1.0:
        reasons.append("补曲线缺口")
    if scores["color_fit"] >= 1.0:
        reasons.append("贴合主色")
    elif scores["color_fit"] <= 0.15:
        reasons.append("脱离主色")
    if scores["removal"] >= 1.0:
        reasons.append("规则命中去除")
    if scores["color_openness"] >= 0.7:
        reasons.append("颜色开放")
    if scores["rarity"] >= 0.7:
        reasons.append("高稀有度")
    return "、".join(reasons) or "评分表锚点"


def recommend_pick(pack: Sequence[Mapping], picked: Sequence[Mapping],
                   signals: Optional[Mapping[str, float]] = None, table=None,
                   llm_request=None, pick_number: Optional[int] = None) -> AdviceResult:
    """生成当前包排名；``llm_request`` 接收 prompt 并返回文本。"""
    if not pack:
        raise ValueError("当前包为空")
    signals = signals or {}
    prompt = None
    response = None
    llm_scores = None
    status = "disabled"
    error = None
    if llm_request is not None:
        prompt = build_prompt(pack, picked, table)
        try:
            response = llm_request(prompt)
            llm_scores = parse_llm_scores(response, [_name(card) for card in pack])
            status = "ok"
        except Exception as exc:
            status = "offline"
            error = str(exc)

    recommendations = []
    for card in pack:
        machine = machine_axes(card, picked, signals, table, pick_number)
        name = _name(card)
        if llm_scores is not None:
            raw_power = llm_scores[name]["raw_power"]
            synergy = llm_scores[name]["synergy"]
            reason = llm_scores[name]["reason"]
        else:
            raw_power = power_anchor(card, table)
            synergy = 0.5
            reason = _machine_reason(card, machine, table)
            if llm_request is not None:
                reason += "；LLM 离线"
        scores = dict(machine)
        scores.update({"raw_power": raw_power, "synergy": synergy})
        recommendations.append(PickRecommendation(
            card=card, scores=scores, total=deck_core.waspas(scores),
            reason=reason,
        ))
    recommendations.sort(key=lambda item: (-item.total, -item.scores["raw_power"], _name(item.card)))
    return AdviceResult(tuple(recommendations), status, prompt, response, error)
