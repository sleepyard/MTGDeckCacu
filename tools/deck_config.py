#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略参数数据化（底层架构强化计划 Phase 2）。

把散落在各模块里的策略/阈值常量集中到本模块的 DEFAULTS，并允许用户用
`tools/data/config/strategy_params.json` 叠加覆盖（仓库只跟踪
`strategy_params.example.json` 示例；真实 JSON 由用户自建，gitignored）。

对账策略（只读，绝不自动写回 JSON）：
  - JSON 缺失/损坏/根节点非对象 → 全部默认值 + 一条 warning（stderr）；
  - 未知节 / 未知键 → warning（stderr）且不生效；
  - 值类型与默认不符（int/float 视为同型）→ warning 且保持默认；
  - 缺键静默用默认；覆盖按"节内键"整体替换，不做深合并。

消费方式：各模块 import 时调一次 `load_params()` 存模块级，原常量名保留为
兼容别名（如 deck_core.GRADE_EQ）。默认路径的加载结果进程内缓存一次；
测试用 `load_params(临时路径)` 注入，不走缓存。

JSON 顶层按消费方分节："deck_core" / "mtga_log_tool" / "rot_audit"。
"""

import copy
import json
import sys
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "data" / "config" / "strategy_params.json"

# 默认值 = 迁移前各模块常量的原值（行为零变化）。形状即 JSON 形状：
# 集合/元组以 list 表示、int 键以 str 表示，消费方在别名绑定处自行转型。
DEFAULTS = {
    "deck_core": {
        # 字母等级 -> 等效数值
        "GRADE_EQ": {
            "S": 0.60, "A": 0.57, "A-": 0.56, "B+": 0.55, "B": 0.545,
            "B-": 0.54, "C+": 0.53, "C": 0.525, "C-": 0.52, "D": 0.51,
            "F": 0.48,
        },
        "HIGH_GRADES": ["S", "A", "A-", "B+", "B"],
        "RARITY_SCORE": {"mythic": 1.0, "rare": 0.7, "uncommon": 0.45, "common": 0.2},
        # 九轴 WASPAS
        "AXES": {
            "raw_power": 0.20, "synergy": 0.15, "curve_fit": 0.15,
            "color_fit": 0.15, "color_openness": 0.10, "signal": 0.10,
            "fixer": 0.05, "removal": 0.05, "rarity": 0.05,
        },
        "WASPAS_LAMBDA": 0.5,
        # 曲线
        "CURVE_TARGET": {"1": [2, 4], "2": [5, 7], "3": [4, 6], "4": [3, 5], "5": [2, 4]},
        # curve_rating 评级档：首个命中档生效（原 if/elif 链语义）
        "CURVE_RATING": {
            "TIERS": [
                {"label": "优秀", "ratio": 0.40, "mid": 3, "delta": 5},
                {"label": "良好", "ratio": 0.30, "mid": 2, "delta": 2},
                {"label": "偏慢", "ratio": 0.20, "mid": 0, "delta": -3},
            ],
            "FALLBACK": {"label": "不足", "delta": -5},
        },
        # 轮抓信号
        "SIGNAL_OPEN_DELTA": 0.3,
        "SIGNAL_CLOSED_DELTA": -0.2,
        "ALSA_MARGIN": 1.5,
        "FALLBACK_PER_HIGH": 0.1,
        # 颜色契合
        "COLOR_FIT_MAIN_COLORS": 2,   # 主色取已抓颜色计数前二
        "COLOR_FIT_NEUTRAL_PICKS": 5,  # 已抓有色计数低于此值视为方向未明
        # 组牌骨架
        "TARGET_NON_LANDS": 23,
        "LAND_MIN": 16,
        "LAND_MAX": 19,
        "STRATEGY_TARGETS": {
            "aggro": {"creature": 16, "removal": 3},
            "mid": {"creature": 13, "removal": 3},
            "control": {"creature": 10, "removal": 6},
        },
        "DEPTH_MONO_MIN": 14,
        "DEPTH_DUAL_MIN": 8,
        "SPLASH_MAX_CARDS": 3,
        "SPLASH_DISCOUNT": 0.3,
        "SPLASH_IWD_THRESHOLD": 0.03,
        "SPLASH_SCORE_THRESHOLD": 6.0,
        # land_count 内联阈值：CMC_STEPS 为 [比较符, cmc, 增量]，首个命中生效
        # （原 if/elif 链语义）；CAPS 为 [cmc符, cmc, splash符, splash, 上限]，逐条应用
        "LAND_COUNT": {
            "BASE": 17,
            "CMC_STEPS": [[">", 4.0, 2], [">", 3.4, 1], ["<", 2.5, -2], ["<", 2.8, -1]],
            "RAMP_MIN": 4,
            "RAMP_DELTA": -1,
            "SPLASH_PER": 0.5,
            "SPLASH_MAX_ADD": 2,
            "CAPS": [["<=", 2.5, "<=", 2, 16], ["<", 2.8, "<=", 1, 17]],
        },
        # land_check 概率门槛：T3 至少 2 地、T5 至少 4 地
        "LAND_CHECK": {
            "P3_DRAWS": 9, "P3_K": 2, "P3_MIN": 0.90,
            "P5_DRAWS": 11, "P5_K": 4, "P5_MIN": 0.70,
        },
    },
    "mtga_log_tool": {
        # risk 模式标记阈值
        "RISK_TURN3_LANDS": 3,    # 自己第 3 个回合结束时应已下的地数，不足则标记
        "RISK_MULLIGAN_LIMIT": 2,  # 单局调度达到此次数则标记
        "RISK_STUCK_NONLAND": 4,   # 终局手牌中未打出的非地牌达到此数量则标记
        # ZoneTransfer category → 动作
        "CATEGORY_ACTIONS": {
            "PlayLand": "下地",
            "CastSpell": "施放",
            "Put": "放进战场",
            "Draw": "抓牌",
            "DrawCard": "抓牌",
        },
    },
    "rot_audit": {
        # 当前窗口的下一次轮替日（随《诺克提斯：沉沦之境》售前赛）
        "ROTATION_DATE": "2027-02-02",
        # 报告头里的退出系列展示串
        "ROTATION_SUMMARY": "WOE LCI MKM OTJ(+BIG) BLB DSK",
        # 本次轮替退出的系列代码
        "ROTATING_SETS": ["woe", "woc", "lci", "lcc", "mkm", "mkc", "otj",
                          "otc", "big", "blb", "blc", "dsk", "dsc"],
    },
}

_CACHE = None


def _type_ok(default, value):
    """int/float 视为同型；bool 不与 int 混同。"""
    if isinstance(default, bool) or isinstance(value, bool):
        return isinstance(default, bool) and isinstance(value, bool)
    if isinstance(default, (int, float)) and isinstance(value, (int, float)):
        return True
    return type(default) is type(value)


def _merge(defaults, override, warnings):
    params = copy.deepcopy(defaults)
    for section, keys in override.items():
        if section not in defaults:
            warnings.append(f"未知参数节: {section}")
            continue
        if not isinstance(keys, dict):
            warnings.append(f"参数节类型不符，整节保持默认: {section}")
            continue
        for key, value in keys.items():
            if key not in defaults[section]:
                warnings.append(f"未知参数键: {section}.{key}")
                continue
            if not _type_ok(defaults[section][key], value):
                warnings.append(f"参数类型不符，保持默认: {section}.{key}")
                continue
            params[section][key] = copy.deepcopy(value)
    return params


def _load(path):
    """返回 (params, warnings)；纯读取，不打印、不写回。"""
    warnings = []
    if not path.is_file():
        warnings.append(f"参数文件不存在，使用内置默认值: {path}")
        return copy.deepcopy(DEFAULTS), warnings
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        warnings.append(f"参数文件损坏（{exc}），使用内置默认值: {path}")
        return copy.deepcopy(DEFAULTS), warnings
    if not isinstance(raw, dict):
        warnings.append(f"参数文件根节点不是对象，使用内置默认值: {path}")
        return copy.deepcopy(DEFAULTS), warnings
    return _merge(DEFAULTS, raw, warnings), warnings


def _emit(warnings):
    for w in warnings:
        print(f"[deck_config] {w}", file=sys.stderr)


def load_params(path=None):
    """加载策略参数：内置默认值 → JSON 叠加覆盖。

    path=None 时用默认位置 tools/data/config/strategy_params.json，结果进程内
    缓存一次（各消费模块 import 时共享）；传入路径则每次现读（测试注入用）。
    返回深拷贝，调用方改动不影响缓存与默认值。
    """
    global _CACHE
    if path is None:
        if _CACHE is None:
            params, warnings = _load(DEFAULT_PATH)
            _emit(warnings)
            _CACHE = params
        return copy.deepcopy(_CACHE)
    params, warnings = _load(Path(path))
    _emit(warnings)
    return params
