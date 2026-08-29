#!/usr/bin/env python3
"""MTGA 自动化测试 CLI：纯日志驱动的对局监听、局内决策辅助与采样循环。

定位：半自动副驾。后台实时增量监听 Player.log，重建对局状态并给出决策建议
（调度/阶段提醒）；**局内操作一律由人执行**，本工具不做任何鼠标键盘模拟、
不读取对手非公开信息——仅日志读写，规避 WotC 对局内自动化（botting）红线。

子命令：
- watch  实时监听：检测比赛开始/结束，场终自动执行 scan + opponent + replay + risk 回收
- advise 局内决策辅助：实时简报（回合/生命/手牌/阶段）+ 基于牌表地数的调度建议 + 下地提醒
- run    采样循环：等满 N 场对局（人手工排队与对局），逐场自动回收，结束输出聚合报告
- draft  轮抓副驾：--record 录样；--watch 实时 pick 排名面板（Web，默认端口 8643）

前置同 mtga_log_tool.py：MTGA 需开启 Detailed Logs (Plugin Support)。
仅 Python 标准库（3.7+）；grpId 解析复用 mtga_log_tool/mtg_tool 的 Scryfall 缓存。
"""

import argparse
import html
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
from urllib.parse import urlparse
import urllib.request
from collections import Counter
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mtg_tool import MtgToolError, fetch_chinese_name, parse_deckfile, scryfall_get  # noqa: E402
import mtga_log_tool as MLT  # noqa: E402
import deck_core  # noqa: E402  纯函数内核（无 I/O、无反向依赖，可顶层导入）
import draft_advisor as DRAFT_ADVISOR  # noqa: E402  轮抓八轴推荐（纯函数）

LOG_TOOL = Path(__file__).resolve().parent / "mtga_log_tool.py"
DEFAULT_LOG = MLT.DEFAULT_LOG
SESSIONS_ROOT = Path(__file__).resolve().parent / "auto" / "sessions"

PROMPT_MATCH_START = "GREMessageType_ConnectResp"


class AutoToolError(Exception):
    pass


# ---------------------------------------------------------------- 增量日志读取
class LogTailer:
    """按偏移量增量读取日志文件；文件被截断/重建（MTGA 重启）时自动重置。"""

    def __init__(self, path, from_start=False):
        self.path = Path(path)
        if not self.path.is_file():
            raise AutoToolError(f"日志不存在: {path}")
        self.offset = 0 if from_start else self.path.stat().st_size

    def read_new(self):
        """返回 (新增文本, 是否发生截断重置)。无新增返回 ("", False)。"""
        size = self.path.stat().st_size
        truncated = size < self.offset
        if truncated:
            self.offset = 0
        if size == self.offset:
            return "", truncated
        with open(self.path, "r", encoding="utf-8", errors="replace") as fh:
            fh.seek(self.offset)
            data = fh.read()
            self.offset = fh.tell()
        return data, truncated


class PayloadFeeder:
    """增量 JSON 载荷提取：喂入新文本，产出完整解析的 JSON 对象。
    宽容策略同 mtga_log_tool.iter_json_payloads；日志末尾的半行/半段 JSON
    保留到下次补全；单起点累积超过 max_lines 仍失败则丢弃该起点防卡死。"""

    def __init__(self, max_lines=1000):
        self.max_lines = max_lines
        self._remnant = ""   # 未遇到换行的尾部残片
        self._lines = []     # 已就绪但尚未消费完的完整行
        self._decoder = json.JSONDecoder()

    def feed(self, text):
        if text:
            data = self._remnant + text
            parts = data.split("\n")
            self._remnant = parts.pop()  # 最后一段可能是不完整行
            self._lines.extend(parts)
        out = []
        lines = self._lines
        i = 0
        while i < len(lines):
            brace = lines[i].find("{")
            if brace < 0:
                i += 1
                continue
            buf = lines[i][brace:]
            j = i
            incomplete = False
            parsed = False
            while True:
                try:
                    obj, end = self._decoder.raw_decode(buf)
                    out.append(obj)
                    i += buf[:end].count("\n") + 1
                    parsed = True
                    break
                except json.JSONDecodeError:
                    j += 1
                    if j >= len(lines):
                        incomplete = True  # 日志还在写，保留起点等补全
                        break
                    if j - i > self.max_lines:
                        break  # 超限丢弃该起点，防损坏数据卡死
                    buf += "\n" + lines[j]
            if incomplete:
                break
            if not parsed:
                i += 1
        self._lines = lines[i:]
        return out

    def flush(self):
        """收尾：把残余半行也尝试解析（用于 from_start 一次性处理）。"""
        return self.feed("\n") if self._remnant else []


# ---------------------------------------------------------------- 实时对局状态跟踪
class LiveGameTracker:
    """逐载荷增量重建最新一场对局状态（advise 用）。
    口径与 mtga_log_tool.build_match_context 一致：本家座位取最近 ConnectResp。"""

    def __init__(self):
        self.self_seat = None
        self.match_id = None
        self.deck_message = None  # ConnectResp 携带的本局实际提交牌表
        self.game_number = None
        self.stage = None
        self.turn = {}          # 前向填充的 turnInfo
        self.life = {}          # seat -> lifeTotal（增量前向填充）
        self.zones = {}         # zoneId -> {"type","ownerSeatId"}
        self.objects = {}       # instanceId -> 物件
        self.hand_zone_ids = set()   # 本家手牌区
        self.land_played_turn = None  # 本家最近一次下地的 turnNumber
        self.game_over = False
        self.game_state_id = None
        self.actions = None        # 最近一条 ActionsAvailableReq 的合法动作列表

    def feed(self, payload):
        event = payload.get("greToClientEvent")
        if not isinstance(event, dict):
            return
        for msg in event.get("greToClientMessages") or []:
            if msg.get("type") == "GREMessageType_ConnectResp" and msg.get("systemSeatIds"):
                self.self_seat = msg["systemSeatIds"][0]
                self._reset_game()
                # ConnectResp 携带本局实际提交牌表（每场比赛都会重连一次）——
                # 牌表事实源，比外部 --deck 文件可靠（实测踩坑：陈旧牌表文件
                # 与快照矛盾，直接毒化 LLM 推理，被误判为"上下文污染"）
                dm = (msg.get("connectResp") or {}).get("deckMessage")
                if isinstance(dm, dict) and dm.get("deckCards"):
                    self.deck_message = dm
                continue
            # 服务器判定的合法动作列表（施放/下地/异能，含法力费用）——
            # 决策合法性的唯一事实锚点，比让 LLM 自己推法术力可靠
            if msg.get("type") == "GREMessageType_ActionsAvailableReq":
                req = msg.get("actionsAvailableReq")
                if isinstance(req, dict):
                    self.actions = req.get("actions") or []
                continue
            gsm = msg.get("gameStateMessage")
            if isinstance(gsm, dict):
                sid = msg.get("gameStateId") or gsm.get("gameStateId")
                if sid is not None:
                    self.game_state_id = sid
                self._apply_gsm(gsm)

    def _reset_round(self):
        """单局（game）级状态清空；Bo3 换局时 zoneId/instanceId 会跨局复用，
        不清空就会把上一局的物件映射进新一局（跨局污染）。"""
        self.game_number = None
        self.stage = None
        self.turn = {}
        self.life = {}
        self.zones = {}
        self.objects = {}
        self.hand_zone_ids = set()
        self.land_played_turn = None
        self.game_over = False
        self.game_state_id = None
        self.actions = None

    def _reset_game(self):
        # 注意：deck_message 不能在这里清——实测每场开局的消息序是
        # ConnectResp（带牌表）→ 新 matchID 的首条 gameInfo，若此处清空，
        # 牌表刚捕获就被抹掉；下一场的 ConnectResp 自会覆盖它
        self._reset_round()
        self.match_id = None

    def _apply_gsm(self, gsm):
        info = gsm.get("gameInfo")
        if isinstance(info, dict):
            if info.get("matchID"):
                if info["matchID"] != self.match_id:
                    self._reset_game()
                    self.match_id = info["matchID"]
                gn = info.get("gameNumber")
                if (gn is not None and self.game_number is not None
                        and gn != self.game_number):
                    self._reset_round()  # Bo3 换局：局内状态不跨局残留
                if gn is not None:
                    self.game_number = gn
            if info.get("stage"):
                self.stage = info["stage"]
            if str(self.stage) == "GameStage_GameOver":
                self.game_over = True
        ti = gsm.get("turnInfo")
        if isinstance(ti, dict):
            self.turn.update(ti)
            # 主阶段没有 step；MTGA 增量消息的 turnInfo 是前向填充的 diff，
            # 过期的 "Draw"/"EndCombat" 会残留成 Main1/Draw 这种自相矛盾的
            # 回合状态误导 LLM（实测踩坑）——处于主阶段时无条件清除 step
            if self.turn.get("phase") in ("Phase_Main1", "Phase_Main2"):
                self.turn.pop("step", None)
        for p in gsm.get("players") or []:
            if p.get("systemSeatNumber") is not None and p.get("lifeTotal") is not None:
                self.life[p["systemSeatNumber"]] = p["lifeTotal"]
        for z in gsm.get("zones") or []:
            if z.get("zoneId") is not None:
                self.zones[z["zoneId"]] = {"type": z.get("type"),
                                           "ownerSeatId": z.get("ownerSeatId")}
                if (z.get("type") == "ZoneType_Hand"
                        and z.get("ownerSeatId") == self.self_seat):
                    self.hand_zone_ids.add(z["zoneId"])
        for o in gsm.get("gameObjects") or []:
            if o.get("instanceId") is not None:
                self.objects[o["instanceId"]] = o
        for a in gsm.get("annotations") or []:
            types = a.get("type") or []
            if "AnnotationType_ObjectIdChanged" in types:
                orig = MLT._anno_value(a, "orig_id")
                new = MLT._anno_value(a, "new_id")
                if orig in self.objects and new is not None:
                    self.objects[new] = self.objects.pop(orig)
                    self.objects[new]["instanceId"] = new
            elif "AnnotationType_ZoneTransfer" in types:
                dest = MLT._anno_value(a, "zone_dest")
                cat = MLT._anno_value(a, "category")
                for iid in a.get("affectedIds") or []:
                    if iid in self.objects and dest is not None:
                        self.objects[iid] = dict(self.objects[iid], zoneId=dest)
                        if (cat == "PlayLand"
                                and self.objects[iid].get("ownerSeatId") == self.self_seat):
                            self.land_played_turn = self.turn.get("turnNumber")
        for iid in gsm.get("diffDeletedInstanceIds") or []:
            self.objects.pop(iid, None)

    # ---- 快照 ----
    @staticmethod
    def _is_subobject(o):
        """历险/MDFC 子物件（type=Adventure 或带 parentId）是主牌的影子物件，
        与主牌同区同显，渲染时必须排除——否则战场/手牌被幽灵物件污染（实测踩坑：
        历险出去的 Bonecrusher 在场上留下 <grpId 70488> 影子）。"""
        return bool(o.get("parentId")) or o.get("type") == "GameObjectType_Adventure"

    def hand_cards(self):
        """本家手牌物件（GameObjectType_Card，排除子物件），按 grpId 可见性区分。"""
        return [o for o in self.objects.values()
                if o.get("zoneId") in self.hand_zone_ids
                and o.get("ownerSeatId") == self.self_seat
                and o.get("type") == "GameObjectType_Card"
                and not self._is_subobject(o)]

    def hand_land_count(self):
        n = 0
        for o in self.hand_cards():
            if "CardType_Land" in (o.get("cardTypes") or []):
                n += 1
        return n

    def my_turn(self):
        return self.turn.get("activePlayer") == self.self_seat

    def brief_line(self):
        ti = self.turn
        if not ti.get("turnNumber"):
            return None
        side = "我方" if self.my_turn() else "对方"
        phase = str(ti.get("phase") or "").replace("Phase_", "")
        s = self.life.get(self.self_seat)
        others = [v for k, v in self.life.items() if k != self.self_seat]
        o = others[-1] if others else None
        return (f"[T{ti['turnNumber']} {side} {phase}] "
                f"生命 {'?' if s is None else s}:{'?' if o is None else o} "
                f"手牌 {len(self.hand_cards())} 张")


# ---------------------------------------------------------------- 局面快照渲染（LLM 输入）
_oracle_mem = {}


def card_oracle(grp_id):
    """grpId → {"name","mana_cost","type_line","oracle_text"}（MDFC 拼接双面）。
    走 mtg_tool 的 Scryfall HTTP 磁盘缓存，重复查询零网络成本；失败回退只有牌名。"""
    if grp_id is None:
        return None
    if grp_id in _oracle_mem:
        return _oracle_mem[grp_id]
    info = None
    try:
        card = scryfall_get(f"/cards/arena/{grp_id}")
        if card.get("card_faces"):
            faces = card["card_faces"]
            info = {
                "name": card.get("name"),
                "mana_cost": " // ".join(f.get("mana_cost") or "" for f in faces),
                "type_line": card.get("type_line"),
                "oracle_text": "\n".join(f.get("oracle_text") or "" for f in faces),
            }
        else:
            info = {"name": card.get("name"), "mana_cost": card.get("mana_cost"),
                    "type_line": card.get("type_line"),
                    "oracle_text": card.get("oracle_text")}
    except (MtgToolError, KeyError):
        pass
    if not info or not info.get("name"):
        fallback = MLT.resolve_grp_card(grp_id)
        info = {"name": fallback or f"<grpId {grp_id}>", "mana_cost": "",
                "type_line": "", "oracle_text": ""}
    _oracle_mem[grp_id] = info
    return info


_MANA_SYMBOLS = {"ManaColor_White": "W", "ManaColor_Blue": "U", "ManaColor_Black": "B",
                 "ManaColor_Red": "R", "ManaColor_Green": "G", "ManaColor_Colorless": "C",
                 "ManaColor_X": "X", "ManaColor_Generic": ""}


def _fmt_mana_cost(mana_cost):
    """actionsAvailableReq 的结构化费用 → {2}{G} 文本。"""
    out = []
    for part in mana_cost or []:
        for color in part.get("color") or []:
            sym = _MANA_SYMBOLS.get(color, color.replace("ManaColor_", ""))
            count = part.get("count", 1)
            if color == "ManaColor_Generic":
                out.append(f"{{{count}}}")
            else:
                out.extend(f"{{{sym}}}" * max(1, count))
    return "".join(out)


def _mana_available(tracker):
    """我方未横置地数/总地数（tapState 缺失视为未横置）。"""
    bf_ids = _zone_ids(tracker, "ZoneType_Battlefield")
    my_lands = [ob for ob in tracker.objects.values()
                if ob.get("zoneId") in bf_ids
                and not tracker._is_subobject(ob)
                and ob.get("controllerSeatId") == tracker.self_seat
                and "CardType_Land" in (ob.get("cardTypes") or [])]
    untapped = sum(1 for ob in my_lands
                   if not str(ob.get("tapState") or "").endswith("Tapped"))
    return untapped, len(my_lands)


def _action_total_cost(mana_cost):
    """结构化费用的总法术力值；含 X 返回 None（X 可缩放，不做不足标注）。"""
    total = 0
    for part in mana_cost or []:
        if "ManaColor_X" in (part.get("color") or []):
            return None
        total += part.get("count", 1)
    return total


def _fmt_actions(tracker):
    """服务器动作列表 → 文本行。无数据返回 None。
    注意：ActionsAvailableReq 不按可用法术力过滤（实测 3 地也列出 {4}{R}{R}），
    费用为减费后数值——affordability 由我们按未横置地数标注「费用不足」。
    Activate_Mana/FloatMana 是法术力操作噪音（法术力行已覆盖），过滤；
    历险施放的 grpId 是子面 id（查不到），instanceId 直接指向主牌物件。"""
    if tracker.actions is None:
        return None
    untapped, _total_lands = _mana_available(tracker)
    parts = []
    for a in tracker.actions:
        t = str(a.get("actionType") or "").replace("ActionType_", "")
        if t in ("Activate_Mana", "FloatMana"):
            continue
        label = {"Cast": "施放", "Play": "下地", "Pass": "让过",
                 "CastAdventure": "历险施放",
                 "ActivateAbility": "起动异能"}.get(t, t)
        if a.get("grpId"):
            name = card_oracle(a["grpId"])["name"]
            if name.startswith("<grpId") and a.get("instanceId") is not None:
                obj = tracker.objects.get(a["instanceId"]) or {}
                if obj.get("grpId"):
                    pname = card_oracle(obj["grpId"])["name"]
                    if not pname.startswith("<grpId"):
                        name = pname
            label += " " + name
        cost = _fmt_mana_cost(a.get("manaCost"))
        if cost:
            label += f" {cost}"
        total = _action_total_cost(a.get("manaCost"))
        if total is not None and total > untapped:
            label += "（费用不足）"
        parts.append(label)
    return "当前可选动作（含费用不足标注）：" + ("；".join(parts) or "仅让过")


def _fallback_label(o):
    """grpId 未解析时按物件自带类型/类别推导描述（实测：Arena 内部 id 的基本地
    Scryfall 查不到，但 subtypes 里有 SubType_Forest——显示"未解析 基本地·Forest"
    而不是裸 id，防 LLM 拿场上别处的牌名脑补）。"""
    supers = [s.replace("SuperType_", "") for s in o.get("superTypes") or []]
    types = [t.replace("CardType_", "") for t in o.get("cardTypes") or []]
    subs = [s.replace("SubType_", "") for s in o.get("subtypes") or []]
    desc = " ".join(supers + types + subs) or str(o.get("type") or "?")
    return f"<未解析 {desc} #{o.get('grpId')}>"


def _fmt_obj(o, with_oracle=False, oracle_limit=800):
    """单个物件的快照文本：牌名（费用，P/T，横置，指示物）。token/未知件降级显示。
    with_oracle=True 时附 oracle 文本（战场永久物的异能对决策至关重要——实测教训 1：
    只给牌名导致 LLM 低估场上 Sarkhan's Unsealing 的触发收益；实测教训 2：150 字符
    截断把 The Great Henge 的抓牌触发器切掉；实测教训 3：400 截断把 Hunter's Talent
    三级的抓牌异能切掉，LLM 因此漏认场面抓牌引擎——上限放宽到 800）。"""
    grp = o.get("grpId")
    info = card_oracle(grp) if grp else None
    if info and not info["name"].startswith("<grpId"):
        label = info["name"]
        if info["mana_cost"]:
            label += f" {info['mana_cost']}"
    elif grp:
        label = _fallback_label(o)
    else:
        info = None
        label = f"<token/未知物件 {o.get('instanceId')}>"
    power, tough = (o.get("power") or {}).get("value"), (o.get("toughness") or {}).get("value")
    if power is not None and tough is not None:
        label += f" {power}/{tough}"
    if str(o.get("tapState") or "").endswith("Tapped"):
        label += "（已横置）"
    counters = o.get("counters") or []
    if counters:
        label += "（" + "、".join(f"{c.get('type', '?')}×{c.get('count', '?')}"
                                 for c in counters) + "）"
    if with_oracle and info and info.get("oracle_text"):
        text = info["oracle_text"].replace("\n", "；")
        if len(text) > oracle_limit:
            text = text[:oracle_limit] + "…"
        label += f"：{text}"
    return label


def _zone_ids(tracker, zone_type, owner=None):
    return {zid for zid, z in tracker.zones.items()
            if z["type"] == zone_type and (owner is None or z["ownerSeatId"] == owner)}


def render_snapshot(tracker, graveyard_limit=10):
    """当前局面 → 结构化中文文本（LLM prompt 主体）。
    对手手牌只报张数并显式标注未知，防模型脑补。"""
    self_seat = tracker.self_seat
    ti = tracker.turn
    lines = []
    if ti.get("turnNumber"):
        side = "我方" if tracker.my_turn() else "对方"
        phase = str(ti.get("phase") or "").replace("Phase_", "")
        step = str(ti.get("step") or "").replace("Step_", "")
        lines.append(f"回合：T{ti['turnNumber']} {side}回合 {phase}"
                     + (f"/{step}" if step else ""))
    s = tracker.life.get(self_seat)
    others = [v for k, v in tracker.life.items() if k != self_seat]
    o = others[-1] if others else None
    lines.append(f"生命：我方 {'?' if s is None else s} / 对方 {'?' if o is None else o}")

    bf_ids = _zone_ids(tracker, "ZoneType_Battlefield")
    bf = [ob for ob in tracker.objects.values() if ob.get("zoneId") in bf_ids
          and not tracker._is_subobject(ob)]
    mine = [ob for ob in bf if ob.get("controllerSeatId") == self_seat]
    theirs = [ob for ob in bf if ob.get("controllerSeatId") != self_seat]
    # 法术力估计：约束 LLM 的费用/X 值推算（实测：3 地建议 6 费 Carnosaur）
    untapped, land_total = _mana_available(tracker)
    if land_total:
        lines.append(f"我方法术力：{untapped}/{land_total} 地未横置"
                     f"（本回合{'已' if tracker.land_played_turn == ti.get('turnNumber') else '未'}下地）")
    actions_line = _fmt_actions(tracker)
    if actions_line:
        lines.append(actions_line)
    lines.append("我方战场：" + ("、".join(_fmt_obj(ob, with_oracle=True) for ob in mine)
                                or "（空）"))
    lines.append("对方战场：" + ("、".join(_fmt_obj(ob, with_oracle=True) for ob in theirs)
                                or "（空）"))

    stack_ids = _zone_ids(tracker, "ZoneType_Stack")
    stack = [ob for ob in tracker.objects.values() if ob.get("zoneId") in stack_ids
             and not tracker._is_subobject(ob)]
    lines.append("堆叠：" + ("、".join(_fmt_obj(ob) for ob in stack) or "（空）"))

    hand = tracker.hand_cards()
    hand_desc = []
    for ob in hand:
        info = card_oracle(ob.get("grpId"))
        entry = info["name"]
        if info["mana_cost"]:
            entry += f" {info['mana_cost']}"
        if info["type_line"]:
            entry += f"（{info['type_line']}）"
        if info["oracle_text"]:
            entry += f"：{info['oracle_text']}"
        hand_desc.append(entry)
    lines.append(f"我方手牌（{len(hand)}）：" + ("；".join(hand_desc) or "（空）"))

    opp_hand = _zone_ids(tracker, "ZoneType_Hand")
    opp_hand -= tracker.hand_zone_ids
    opp_count = sum(1 for ob in tracker.objects.values() if ob.get("zoneId") in opp_hand)
    lines.append(f"对方手牌：{opp_count} 张（身份未知，禁止假设具体牌）")

    for label, seat in (("我方", self_seat), ("对方", None)):
        gy_owner = seat if label == "我方" else None
        gy_ids = _zone_ids(tracker, "ZoneType_Graveyard", owner=gy_owner)
        if label == "对方":
            gy_ids = {zid for zid in gy_ids
                      if tracker.zones[zid]["ownerSeatId"] != self_seat}
        gy = [ob for ob in tracker.objects.values()
              if ob.get("zoneId") in gy_ids and ob.get("type") == "GameObjectType_Card"]
        names = [_fmt_obj(ob) for ob in gy[-graveyard_limit:]]
        more = f"（另 {len(gy) - graveyard_limit} 张略）" if len(gy) > graveyard_limit else ""
        lines.append(f"{label}坟墓场（{len(gy)}）：" + ("、".join(names) or "（空）") + more)
    return "\n".join(lines)


# ---------------------------------------------------------------- LLM 后端
LLM_CONFIG_JSON = Path(__file__).resolve().parent / "llm_config.json"

LLM_SYSTEM_PROMPT = (
    "你是万智牌（Magic: The Gathering）竞技教练。用户输入是 MTGA 日志精确重建的"
    "对局局面快照。规则：1) 只基于快照信息分析；对手手牌/牌库内容未知时视为未知，"
    "禁止假设具体牌；2) 快照中 <未解析 ...#N> 是身份未能解析的对象，按其类型描述对待，"
    "禁止给它安任何具体牌名；3) 牌面异能以快照中的 oracle 文本为唯一事实来源——"
    "文本没写'enters tapped'的地就是未横置进场，凭记忆改效果是大忌；"
    "4) 建议动作（施放/下地/攻击/阻挡/让过等）只能来自快照「当前可选动作」行，"
    "其中标注「费用不足」的不可选；含 X 的咒语 X 值不得超过未横置地数；"
    "减费类咒语（如按场面力量减费的 Ghalta）的实际费用以该行服务器标注为准，"
    "禁止自行按场面重算；"
    "5) 「我方牌表」可能与实际牌表版本不符，牌表与局面快照矛盾时一律以快照为准；"
    "6) 给出当前决策点的建议动作，附一句关键理由；7) 简体中文回答，不超过 150 字。"
)


def load_llm_config(path=None):
    """读取 tools/llm_config.json（含 api_key，已被 .gitignore 排除）；
    环境变量 DEEPSEEK_API_KEY 可覆盖 api_key。"""
    config_path = Path(path) if path else LLM_CONFIG_JSON
    if not config_path.is_file():
        raise AutoToolError(
            f"LLM 配置不存在: {config_path}（需含 base_url/model/api_key）")
    with open(config_path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg["api_key"] = os.environ.get("DEEPSEEK_API_KEY") or cfg.get("api_key")
    if not cfg.get("api_key"):
        raise AutoToolError("LLM api_key 缺失（llm_config.json 或 DEEPSEEK_API_KEY）")
    cfg.setdefault("base_url", "https://api.deepseek.com")
    cfg.setdefault("model", "deepseek-chat")
    return cfg


def llm_config_status(path=None):
    """返回可展示的配置状态，绝不包含 API key 本身。"""
    config_path = Path(path) if path else LLM_CONFIG_JSON
    result = {
        "path": str(config_path),
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "has_api_key": False,
        "api_key_source": "missing",
        "error": None,
    }
    try:
        if config_path.is_file():
            with open(config_path, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            result["base_url"] = cfg.get("base_url") or result["base_url"]
            result["model"] = cfg.get("model") or result["model"]
            if cfg.get("api_key"):
                result["has_api_key"] = True
                result["api_key_source"] = "file"
        env_key = os.environ.get("DEEPSEEK_API_KEY")
        if env_key:
            result["has_api_key"] = True
            result["api_key_source"] = "environment"
        if not config_path.is_file():
            result["error"] = "配置文件不存在"
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        result["error"] = str(exc)
    return result


def save_llm_config(base_url, model, api_key=None, path=None):
    """保存端点配置；空 api_key 保留已有文件值并由环境变量优先覆盖。"""
    config_path = Path(path) if path else LLM_CONFIG_JSON
    base_url = str(base_url or "").strip().rstrip("/")
    model = str(model or "").strip()
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AutoToolError("LLM base_url 必须是完整的 http(s) URL")
    if not model or len(model) > 200:
        raise AutoToolError("LLM model 不能为空且长度不能超过 200")
    cfg = {}
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise AutoToolError(f"无法读取现有 LLM 配置: {exc}")
        if not isinstance(cfg, dict):
            raise AutoToolError("LLM 配置必须是 JSON 对象")
    cfg["base_url"] = base_url
    cfg["model"] = model
    if str(api_key or "").strip():
        cfg["api_key"] = str(api_key).strip()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return llm_config_status(config_path)


def llm_chat(cfg, messages, timeout=60):
    """OpenAI 兼容 /chat/completions 调用；失败抛 AutoToolError。"""
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    body = json.dumps({"model": cfg["model"], "messages": messages,
                       "temperature": 0.2}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise AutoToolError(f"LLM HTTP {exc.code}: {exc.read()[:200]!r}")
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise AutoToolError(f"LLM 请求失败: {exc}")
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        raise AutoToolError(f"LLM 响应格式异常: {str(data)[:200]}")


def build_llm_prompt(tracker, deck_text=None):
    parts = []
    if deck_text:
        parts.append("我方牌表：\n" + deck_text.strip())
    parts.append("当前局面快照：\n" + render_snapshot(tracker))
    parts.append("当前是我方决策点，请给出建议。")
    return "\n\n".join(parts)


# ---------------------------------------------------------------- 前端监控台
def hand_labels_cn(objects):
    """手牌物件 → 监控台显示名："中文名（English）"，无中文名回退英文。
    mtgch 查询走磁盘缓存，首次后零网络成本。"""
    labels = []
    for ob in objects:
        if not ob.get("grpId"):
            continue
        en = MLT.card_label(ob["grpId"])
        cn = None
        if not en.startswith("<"):
            cn, _err = fetch_chinese_name(en.split(" // ")[0])
        labels.append(f"{cn}（{en}）" if cn else en)
    return labels


LLM_ADVICE_LOG = Path(__file__).resolve().parent / "auto" / "llm_advice.jsonl"
DRAFT_ADVICE_LOG = Path(__file__).resolve().parent / "auto" / "draft_advice.jsonl"


def record_llm_advice(match_id, game_state_id, brief, suggestion, prompt=None):
    """LLM 建议落盘（jsonl，含完整快照 prompt 供事后诊断），
    供赛后 AI 建议 vs 玩家实际操作差异分析。"""
    LLM_ADVICE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LLM_ADVICE_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                             "match_id": match_id, "game_state_id": game_state_id,
                             "brief": brief, "suggestion": suggestion,
                             "prompt": prompt},
                            ensure_ascii=False) + "\n")


def record_draft_advice(event_name, pack_number, pick_number, result):
    """轮抓推荐落盘完整 prompt/结果，供赛后复盘；仅由 --llm 面板调用。"""
    DRAFT_ADVICE_LOG.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "event_name": event_name,
        "pack_number": pack_number,
        "pick_number": pick_number,
        "status": result.status,
        "error": result.error,
        "prompt": result.prompt,
        "response": result.response,
        "recommendations": [
            {"name": row.card.get("name"), "scores": dict(row.scores),
             "total": row.total, "reason": row.reason}
            for row in result.recommendations
        ],
    }
    with open(DRAFT_ADVICE_LOG, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


class StatusBoard:
    """监控台共享状态：局面字段 + 滚动事件日志。advise 循环写，HTTP 线程读。"""

    MAX_LOGS = 200

    def __init__(self):
        self.fields = {"deck": None, "brief": None, "hand": [], "llm": None,
                       "updated": None}
        self.logs = []

    def set(self, **kw):
        self.fields.update(kw)
        self.fields["updated"] = datetime.now().strftime("%H:%M:%S")

    def log(self, text, kind="info"):
        self.logs.append({"ts": datetime.now().strftime("%H:%M:%S"),
                          "kind": kind, "text": text})
        del self.logs[:-self.MAX_LOGS]

    def snapshot(self):
        return {"fields": dict(self.fields), "logs": list(self.logs)}


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>MTGA 辅助驾驶监控台</title>
<style>
  body { background:#0d1117; color:#c9d1d9; font-family:Consolas,'Microsoft YaHei',monospace;
         margin:0; padding:16px; }
  h1 { font-size:18px; color:#58a6ff; margin:0 0 12px; }
  .panel { background:#161b22; border:1px solid #30363d; border-radius:6px;
           padding:12px 16px; margin-bottom:12px; }
  .panel h2 { font-size:13px; color:#8b949e; margin:0 0 8px; font-weight:normal; }
  #status { font-size:15px; } #status b { color:#f0883e; }
  #hand { line-height:1.8; } #hand span { background:#21262d; border-radius:4px;
           padding:2px 8px; margin-right:6px; display:inline-block; }
  #llm { border-color:#d29922; color:#e3b341; white-space:pre-wrap; font-size:14px; }
  #log { height:300px; overflow-y:auto; font-size:13px; line-height:1.6; }
  .k-llm { color:#e3b341; } .k-warn { color:#f85149; } .k-game { color:#3fb950; }
  .ts { color:#484f58; margin-right:8px; }
</style>
</head>
<body>
<h1>MTGA 辅助驾驶监控台</h1>
<div class="panel"><h2>局面</h2><div id="status">等待对局…</div></div>
<div class="panel"><h2>我方手牌</h2><div id="hand">—</div></div>
<div class="panel" id="llmPanel"><h2>LLM 建议</h2><div id="llm">（决策点静默后生成）</div></div>
<div class="panel"><h2>事件流</h2><div id="log"></div></div>
<script>
const seen = new Set();
async function tick() {
  try {
    const r = await fetch('/status.json');
    const d = await r.json();
    const f = d.fields;
    document.getElementById('status').innerHTML =
      (f.deck ? '牌表 <b>' + f.deck + '</b>　' : '') +
      (f.brief || '等待对局…') +
      (f.updated ? '　<span class="ts">更新 ' + f.updated + '</span>' : '');
    document.getElementById('hand').innerHTML =
      f.hand.length ? f.hand.map(c => '<span>' + c + '</span>').join('') : '—';
    if (f.llm) document.getElementById('llm').textContent = f.llm;
    const log = document.getElementById('log');
    for (const e of d.logs) {
      const key = e.ts + e.text;
      if (seen.has(key)) continue;
      seen.add(key);
      const div = document.createElement('div');
      div.className = 'k-' + e.kind;
      div.innerHTML = '<span class="ts">' + e.ts + '</span>' +
        e.text.replace(/</g, '&lt;');
      log.appendChild(div);
    }
    log.scrollTop = log.scrollHeight;
  } catch (e) {}
}
setInterval(tick, 2000); tick();
</script>
</body>
</html>
"""


def start_dashboard(board, port):
    """起本地监控台 HTTP 服务（守护线程），返回 (server, 实际端口)。"""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/status.json"):
                body = json.dumps(board.snapshot(), ensure_ascii=False).encode("utf-8")
                ctype = "application/json; charset=utf-8"
            else:
                body = DASHBOARD_HTML.encode("utf-8")
                ctype = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass  # 静音访问日志

    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


# ---------------------------------------------------------------- 调度建议
def _land_weight(type_line):
    """type_line 的地当量：纯地 1；MDFC 任一面含 Land 记 0.5（保守口径）；否则 0。"""
    if not type_line or "Land" not in type_line:
        return 0.0
    if " // " in type_line and not type_line.startswith("Land") \
            and not type_line.split(" // ")[0].strip().endswith("Land"):
        return 0.5
    return 1.0


def _card_type_line(card):
    tl = card.get("type_line") or ""
    if not tl and card.get("card_faces"):
        tl = " // ".join(f.get("type_line") or "" for f in card["card_faces"])
    return tl


def deck_land_stats(deck_path):
    """牌表地数统计：parse_deckfile 主牌+指挥官，逐牌 Scryfall 判 Land
    （MDFC 当量见 _land_weight）。返回 (地数, 主牌总数)。失败抛 AutoToolError。"""
    try:
        sections = parse_deckfile(deck_path)
    except MtgToolError as exc:
        raise AutoToolError(f"牌表解析失败: {exc}")
    entries = sections["main"] + sections["commander"]
    if not entries:
        raise AutoToolError(f"牌表主牌为空: {deck_path}")
    total = sum(q for q, _ in entries)
    lands = 0.0
    unresolved = []
    for qty, name in sorted(set(entries)):
        try:
            card = scryfall_get("/cards/named", params={"exact": name})
        except MtgToolError:
            unresolved.append(name)
            continue
        lands += qty * _land_weight(_card_type_line(card))
    if unresolved:
        print(f"[警告] {len(unresolved)} 张牌未能解析类型，未计入地数: "
              f"{', '.join(unresolved)}", file=sys.stderr)
    return lands, total


def course_deck_stats(course):
    """courseDeck 载荷 → {"name","lands","total","text"}（text 为 MTGA 导入格式
    牌表文本，供 LLM 上下文）。逐 arena_id 走 Scryfall 磁盘缓存解析。"""
    lands = 0.0
    total = 0
    lines = []
    unresolved = 0
    for entry in course.get("mainDeck") or []:
        qty = entry.get("quantity", 1)
        total += qty
        name = None
        try:
            card = scryfall_get(f"/cards/arena/{entry.get('cardId')}")
            name = card.get("name")
            lands += qty * _land_weight(_card_type_line(card))
        except (MtgToolError, KeyError):
            unresolved += 1
        label = (name or "<arena_id %s>" % entry.get("cardId")).split(" // ")[0]
        lines.append(f"{qty} {label}")
    if unresolved:
        print(f"[警告] 提交牌表 {unresolved} 个 arena_id 未解析", file=sys.stderr)
    return {"name": course.get("name") or "(未命名牌表)", "lands": lands,
            "total": total, "text": "\n".join(sorted(lines))}


def latest_course_deck(log_path):
    """日志中最后一个 courseDeck 载荷的统计；无则 None。"""
    found = None
    for payload, _ln, _ts in MLT.iter_json_payloads(str(log_path)):
        course = MLT.find_key(payload, "courseDeck")
        if isinstance(course, dict) and course.get("mainDeck"):
            found = course
    return course_deck_stats(found) if found else None


def deck_message_stats(deck_msg):
    """ConnectResp.deckMessage（本局实际提交牌表，arena id 扁平列表）→
    {"name","lands","total","text"}，口径同 course_deck_stats，text 附 Sideboard 段。
    这是牌表的最高优先级事实源：每场比赛 ConnectResp 都带，--deck 文件可能陈旧。"""
    lands = 0.0
    total = 0
    lines = []
    unresolved = 0
    for aid, qty in sorted(Counter(deck_msg.get("deckCards") or []).items()):
        total += qty
        name = None
        try:
            card = scryfall_get(f"/cards/arena/{aid}")
            name = card.get("name")
            lands += qty * _land_weight(_card_type_line(card))
        except (MtgToolError, KeyError):
            unresolved += 1
        label = (name or "<arena_id %s>" % aid).split(" // ")[0]
        lines.append(f"{qty} {label}")
    sb_lines = []
    for aid, qty in sorted(Counter(deck_msg.get("sideboardCards") or []).items()):
        try:
            name = scryfall_get(f"/cards/arena/{aid}").get("name")
        except MtgToolError:
            name = None
        label = (name or "<arena_id %s>" % aid).split(" // ")[0]
        sb_lines.append(f"{qty} {label}")
    if unresolved:
        print(f"[警告] 本局提交牌表 {unresolved} 个 arena_id 未解析", file=sys.stderr)
    text = "\n".join(lines)
    if sb_lines:
        text += "\n\nSideboard\n" + "\n".join(sb_lines)
    return {"name": "(本局提交牌表)", "lands": lands, "total": total, "text": text}


def mulligan_advice(hand_size, land_count, lands_in_deck, deck_size,
                    land_min=None, land_max=None):
    """返回 (建议文本, 是否建议留)。阈值缺省按超几何期望推导：
    期望地数 = 手牌数 × 地数/牌库数，留牌区间 [期望四舍五入-1, 期望+2]（下限至少 2）。"""
    expected = hand_size * lands_in_deck / deck_size if deck_size else 0
    lo = land_min if land_min is not None else max(2, round(expected) - 1)
    hi = land_max if land_max is not None else round(expected) + 2
    keep = lo <= land_count <= hi
    verdict = "留" if keep else "调度"
    return (f"起手 {hand_size} 张 / 地 {land_count} 张"
            f"（牌表地当量 {lands_in_deck:g}/{deck_size}，期望 {expected:.1f}，"
            f"留牌区间 {lo}-{hi} 地）→ 建议：{verdict}", keep)


# ---------------------------------------------------------------- 场终回收
def collect_match(log_path, match_id, deck_tag=None):
    """场终自动回收：scan + opponent + replay + risk（复用 mtga_log_tool 子命令）。"""
    cmds = [[sys.executable, str(LOG_TOOL), "scan", "--log", str(log_path)]]
    if deck_tag:
        cmds[0] += ["--deck", deck_tag]
    for sub in ("opponent", "replay", "risk"):
        cmds.append([sys.executable, str(LOG_TOOL), sub,
                     "--match-id", match_id, "--log", str(log_path)])
    for cmd in cmds:
        print(f"[回收] {' '.join(cmd[2:3])} ...", file=sys.stderr)
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
        out = (proc.stdout or "") + (proc.stderr or "")
        for line in out.splitlines():
            print(f"  {line}", file=sys.stderr)
        if proc.returncode not in (0,):
            print(f"[警告] 回收子命令退出码 {proc.returncode}", file=sys.stderr)


def iter_events(payloads):
    """从载荷列表提取 (事件类型, match_id)：match_start / match_end。"""
    events = []
    for payload in payloads:
        final = MLT.find_key(payload, "finalMatchResult")
        if isinstance(final, dict) and final.get("matchId"):
            events.append(("match_end", final["matchId"]))
        event = payload.get("greToClientEvent")
        if isinstance(event, dict):
            for msg in event.get("greToClientMessages") or []:
                if msg.get("type") == PROMPT_MATCH_START:
                    events.append(("match_start", None))
    return events


# ---------------------------------------------------------------- watch
def cmd_watch(args):
    try:
        tailer = LogTailer(args.log, from_start=args.from_start)
    except AutoToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    feeder = PayloadFeeder()
    seen_ends = set()
    print(f"[watch] 监听 {args.log}（{'从头' if args.from_start else '从当前位置'}，"
          f"轮询 {args.poll}s，Ctrl+C 停止）", file=sys.stderr)
    polls = 0
    try:
        while True:
            text, truncated = tailer.read_new()
            if truncated:
                print("[watch] 检测到日志截断/重建（MTGA 重启？），已重置读取位置",
                      file=sys.stderr)
            if text:
                for kind, mid in iter_events(feeder.feed(text)):
                    if kind == "match_start":
                        print(f"[watch] {datetime.now():%H:%M:%S} 比赛开始（ConnectResp）")
                    elif mid not in seen_ends:
                        seen_ends.add(mid)
                        print(f"[watch] {datetime.now():%H:%M:%S} 比赛结束 {mid}，开始回收")
                        collect_match(args.log, mid, deck_tag=args.deck)
            polls += 1
            if args.max_polls and polls >= args.max_polls:
                break
            time.sleep(args.poll)
    except KeyboardInterrupt:
        print("\n[watch] 已停止", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- advise
def cmd_advise(args):
    lands_in_deck, deck_size = args.lands, args.deck_size
    if args.deckfile:
        try:
            lands_in_deck, deck_size = deck_land_stats(args.deckfile)
        except AutoToolError as exc:
            print(f"[错误] {exc}", file=sys.stderr)
            return 2
        print(f"[advise] 牌表地当量 {lands_in_deck:g} / {deck_size} 张", file=sys.stderr)
    deck_text = None
    active_deck_name = None
    if args.deckfile:
        deck_text = Path(args.deckfile).read_text(encoding="utf-8")
    if not lands_in_deck or not deck_size:
        # 未给牌表参数时，从日志最近提交的 courseDeck 自动识别牌表与地数
        auto = latest_course_deck(args.log) if Path(args.log).is_file() else None
        if auto:
            lands_in_deck, deck_size = auto["lands"], auto["total"]
            deck_text = deck_text or auto["text"]
            active_deck_name = auto["name"]
            print(f"[advise] 从日志识别提交牌表「{auto['name']}」："
                  f"地当量 {lands_in_deck:g} / {deck_size} 张", file=sys.stderr)
        else:
            print("[advise] 未给牌表参数且日志中暂无 courseDeck——进入待识别模式，"
                  "等你提交牌表参赛时自动识别", file=sys.stderr)
    try:
        # advise 始终从头追平既有日志（静默），再增量监听——否则中途启动会漏掉
        # 比赛开局的 ConnectResp/gameInfo，整场对局都失明（实测踩坑）
        tailer = LogTailer(args.log, from_start=True)
    except AutoToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    feeder = PayloadFeeder()
    tracker = LiveGameTracker()
    n_caught = 0
    catchup_text, _ = tailer.read_new()
    for payload in feeder.feed(catchup_text):
        tracker.feed(payload)
        n_caught += 1
    if tracker.match_id:
        print(f"[advise] 已追平既有日志（{n_caught} 条载荷），attach 到对局 "
              f"{tracker.match_id}：{tracker.brief_line() or '开局阶段'}", file=sys.stderr)
    elif n_caught:
        print(f"[advise] 已追平既有日志（{n_caught} 条载荷），当前无进行中对局",
              file=sys.stderr)
    # 追平后若已见 ConnectResp.deckMessage（本局实际提交牌表），覆盖牌表口径——
    # 这是事实源，--deck 文件可能是陈旧版本
    if tracker.deck_message:
        stats = deck_message_stats(tracker.deck_message)
        active_deck_name = stats["name"]
        lands_in_deck, deck_size = stats["lands"], stats["total"]
        deck_text = stats["text"]
        deck_msg_handled = tracker.deck_message
        print(f"[advise] 采用日志本局提交牌表：地当量 {lands_in_deck:g} / "
              f"{deck_size} 张", file=sys.stderr)
    else:
        deck_msg_handled = None
    llm_cfg = None
    if args.llm:
        try:
            llm_cfg = load_llm_config()
        except AutoToolError as exc:
            print(f"[错误] {exc}", file=sys.stderr)
            return 5
        print(f"[advise] LLM 后端：{llm_cfg['base_url']} / {llm_cfg['model']}，"
              f"日志静默 {args.llm_quiet}s 且我方决策点时触发", file=sys.stderr)
    print(f"[advise] 监听 {args.log}（轮询 {args.poll}s，Ctrl+C 停止；"
          f"局内操作仍由人执行）", file=sys.stderr)
    board = None
    if args.dashboard is not None:
        board = StatusBoard()
        _srv, port = start_dashboard(board, args.dashboard)
        print(f"[advise] 监控台已启动: http://127.0.0.1:{port}", file=sys.stderr)
        if tracker.match_id:  # 追平 attach 的进行中对局立刻上监控台
            board.set(brief=tracker.brief_line(),
                      hand=hand_labels_cn(tracker.hand_cards()))
            board.log(f"追平 attach 对局 {tracker.match_id}", "game")

    def emit(msg, kind="info"):
        print(msg, flush=True)  # flush：后台运行时 stdout 是块缓冲，不冲看不到
        if board:
            board.log(msg, kind)

    last_brief = None
    advised_games = set()       # 已给过调度建议的 (match, game, hand_size)
    land_reminded_turn = None
    last_activity = time.monotonic()  # 最近一次日志有新增载荷的时间
    last_llm_state = None             # 已请求过 LLM 的 (match_id, gameStateId)
    last_match_end = None             # 已回收的 finalMatchResult matchId
    llm_failures = 0
    polls = 0
    try:
        while True:
            text, truncated = tailer.read_new()
            if truncated:
                print("[advise] 日志截断，重置状态", file=sys.stderr)
                tracker = LiveGameTracker()
                last_brief = None
                advised_games = set()
                deck_msg_handled = None
                last_llm_state = None
            payloads = feeder.feed(text) if text else []
            if payloads:
                last_activity = time.monotonic()
            for payload in payloads:
                tracker.feed(payload)
                # 对局结束检测：finalMatchResult 出现即回收并播报胜负
                # （只处理增量载荷；启动追平的历史载荷不走这里，避免重复回收）
                final = MLT.find_key(payload, "finalMatchResult")
                if (isinstance(final, dict) and final.get("matchId")
                        and final["matchId"] != last_match_end):
                    last_match_end = final["matchId"]
                    collect_match(args.log, final["matchId"],
                                  deck_tag=active_deck_name)
                    rec = next((m for m in MLT.load_matches()
                                if m.get("match_id") == final["matchId"]), None)
                    if rec:
                        verdict = ("胜" if rec["won"] else
                                   ("负" if rec["won"] is False else "未知"))
                        emit(f"[advise] 对局结束：{rec['game_wins']}:{rec['game_losses']} "
                             f"{verdict}（对手 {rec['opponent_name']}）", "game")
                        if board:
                            board.set(brief=f"对局结束 {rec['game_wins']}:"
                                            f"{rec['game_losses']} {verdict}")
                # 对局中检测到新提交牌表 → 自动切换地数口径与 LLM 上下文
                course = MLT.find_key(payload, "courseDeck")
                if isinstance(course, dict) and course.get("mainDeck"):
                    stats = course_deck_stats(course)
                    if stats["name"] != active_deck_name:
                        active_deck_name = stats["name"]
                        lands_in_deck, deck_size = stats["lands"], stats["total"]
                        deck_text = stats["text"]
                        advised_games = set()  # 换牌表后调度建议重新评估
                        emit(f"[advise] 检测到提交牌表「{active_deck_name}」："
                             f"地当量 {lands_in_deck:g} / {deck_size} 张", "game")
                        if board:
                            board.set(deck=active_deck_name)
                # ConnectResp.deckMessage = 本局实际提交牌表，优先级高于 --deck 文件
                dm = tracker.deck_message
                if dm is not None and dm is not deck_msg_handled:
                    deck_msg_handled = dm
                    stats = deck_message_stats(dm)
                    active_deck_name = stats["name"]
                    lands_in_deck, deck_size = stats["lands"], stats["total"]
                    deck_text = stats["text"]
                    advised_games = set()  # 换牌表后调度建议重新评估
                    emit(f"[advise] 采用日志本局提交牌表："
                         f"地当量 {lands_in_deck:g} / {deck_size} 张", "game")
                    if board:
                        board.set(deck=active_deck_name)
            if tracker.self_seat is not None and tracker.match_id:
                tn = tracker.turn.get("turnNumber") or 0
                hand = tracker.hand_cards()
                # 调度建议：第 1 回合前，手牌可见且张数变化即重新评估（伦敦调度）
                if tn < 1 and hand and lands_in_deck and deck_size:
                    key = (tracker.match_id, tracker.game_number, len(hand))
                    if key not in advised_games:
                        advised_games.add(key)
                        named = [MLT.card_label(o.get("grpId")) for o in hand
                                 if o.get("grpId")]
                        text_line, _keep = mulligan_advice(
                            len(hand), tracker.hand_land_count(),
                            lands_in_deck, deck_size,
                            args.land_min, args.land_max)
                        emit(f"[advise] 起手：{'、'.join(named) or '（牌面不可见）'}", "game")
                        emit(f"[advise] {text_line}", "game")
                brief = tracker.brief_line()
                if brief and brief != last_brief and tn >= 1:
                    last_brief = brief
                    emit(f"[advise] {brief}")
                    if board:
                        board.set(brief=brief, hand=hand_labels_cn(hand))
                # 下地提醒：我方回合且尚未下地、手牌有地
                if (tracker.my_turn() and tn >= 1
                        and tracker.land_played_turn != tn
                        and tracker.hand_land_count() > 0
                        and land_reminded_turn != tn):
                    land_reminded_turn = tn
                    emit(f"[advise] 提示：T{tn} 我方回合尚未下地，手牌中有地", "warn")
            # LLM 增强分析：我方决策点 + 日志静默超阈值 + 该局面未问过
            # （gameStateId 跨比赛从 0 重计，去重键必须带 match_id——否则新比赛
            # 撞上前一场已问过的 gs 号会被错误跳过）
            if (llm_cfg and tracker.self_seat is not None and tracker.match_id
                    and not tracker.game_over
                    and tracker.turn.get("decisionPlayer") == tracker.self_seat
                    and tracker.game_state_id is not None
                    and (tracker.match_id, tracker.game_state_id) != last_llm_state
                    and time.monotonic() - last_activity >= args.llm_quiet):
                last_llm_state = (tracker.match_id, tracker.game_state_id)
                print(f"[advise] 局面静默，请求 LLM 分析"
                      f"（gameState {tracker.game_state_id}）...", file=sys.stderr)
                try:
                    prompt = build_llm_prompt(tracker, deck_text)
                    suggestion = llm_chat(llm_cfg, [
                        {"role": "system", "content": LLM_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ])
                    emit(f"[advise/LLM] {suggestion}", "llm")
                    record_llm_advice(tracker.match_id, tracker.game_state_id,
                                      tracker.brief_line(), suggestion, prompt=prompt)
                    if board:
                        board.set(llm=suggestion)
                    llm_failures = 0
                except AutoToolError as exc:
                    llm_failures += 1
                    print(f"[警告] LLM 调用失败（{llm_failures} 次）: {exc}",
                          file=sys.stderr)
                    if llm_failures >= 3:
                        print("[警告] LLM 连续失败，本轮仅保留规则建议", file=sys.stderr)
                        llm_cfg = None
            polls += 1
            if args.max_polls and polls >= args.max_polls:
                break
            time.sleep(args.poll)
    except KeyboardInterrupt:
        print("\n[advise] 已停止", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- run：采样循环
def cmd_run(args):
    try:
        tailer = LogTailer(args.log, from_start=args.from_start)
    except AutoToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    feeder = PayloadFeeder()
    session_dir = SESSIONS_ROOT / datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir.mkdir(parents=True, exist_ok=True)
    session_log = session_dir / "session.log"

    def slog(msg):
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
        print(f"[run] {msg}")
        with open(session_log, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    print("=" * 60, file=sys.stderr)
    print("MTGA 采样循环：人负责排队与全部局内操作；本工具只做日志监听与场终回收。",
          file=sys.stderr)
    print(f"目标 {args.games} 场；单场等待上限 {args.timeout} 分钟；"
          f"会话目录 {session_dir}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    done = 0
    deadline = time.monotonic() + args.timeout * 60
    polls = 0
    try:
        while done < args.games:
            text, truncated = tailer.read_new()
            if truncated:
                slog("日志截断/重建，已重置读取位置")
            for kind, mid in iter_events(feeder.feed(text) if text else []):
                if kind == "match_start":
                    slog(f"检测到比赛开始（第 {done + 1}/{args.games} 场进行中）")
                elif kind == "match_end":
                    done += 1
                    slog(f"第 {done}/{args.games} 场结束 {mid}，开始回收")
                    collect_match(args.log, mid, deck_tag=args.deck)
                    deadline = time.monotonic() + args.timeout * 60
            if done < args.games and time.monotonic() > deadline:
                slog(f"等待超过 {args.timeout} 分钟未完成对局，中止")
                return 7
            polls += 1
            if args.max_polls and polls >= args.max_polls:
                break
            time.sleep(args.poll)
    except KeyboardInterrupt:
        slog("用户中断")
    slog(f"采样结束：完成 {done}/{args.games} 场")
    if done:
        report_cmd = [sys.executable, str(LOG_TOOL), "report"]
        if args.deck:
            report_cmd += ["--deck", args.deck]
        proc = subprocess.run(report_cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)
        (session_dir / "report.md").write_text(proc.stdout, encoding="utf-8")
        slog(f"聚合报告已写入 {session_dir / 'report.md'}")
    return 0 if done >= args.games else (0 if done else 7)


# ---------------------------------------------------------------- 轮抓录样
DRAFT_SAMPLE_DIR = Path(__file__).resolve().parent / "auto" / "draft_samples"


def payload_draft_keys(payload):
    """宽容探测载荷中的轮抓特征键（键名含 draft 或为 pack/pick 计数字段，
    大小写不敏感；只匹配键不匹配值，避开事件列表里 QuickDraft_xxx 这类噪声）。
    返回排序后的命中键名列表，供录样器与赛后确认。"""
    exact = {"packcards", "pickedcards", "selfpick", "packnumber", "picknumber"}
    found = set()

    def walk(node, depth=0):
        if depth > 6:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                kl = k.lower()
                if "draft" in kl or kl in exact:
                    found.add(k)
                walk(v, depth + 1)
        elif isinstance(node, list):
            for v in node:
                walk(v, depth + 1)
        elif isinstance(node, str) and node[:1] in "{[":
            # 实测：BotDraftDraftStatus 把轮抓状态（DraftPack/PickedCards 等）
            # 以字符串化 JSON 塞进 Payload 字段，需解一层才能命中特征键
            try:
                walk(json.loads(node), depth + 1)
            except (json.JSONDecodeError, ValueError):
                pass

    walk(payload)
    return sorted(found)


def cmd_draft_record(args):
    """轮抓载荷录样：宽匹配任何含轮抓特征键的载荷，整条原样落盘 jsonl。
    Draft.Notify 确切 schema 以真实录样为准——先保证任何形态都有据可依。"""
    try:
        tailer = LogTailer(args.log, from_start=args.from_start)
    except AutoToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    DRAFT_SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = DRAFT_SAMPLE_DIR / f"{stamp}.jsonl"
    feeder = PayloadFeeder()
    print(f"[draft] 录样监听 {args.log} → {out_path}"
          f"（轮询 {args.poll}s，Ctrl+C 停止）", file=sys.stderr)
    n = 0
    polls = 0
    try:
        while True:
            text, truncated = tailer.read_new()
            if truncated:
                print("[draft] 日志截断，继续监听", file=sys.stderr)
            for payload in (feeder.feed(text) if text else []):
                keys = payload_draft_keys(payload)
                if not keys:
                    continue
                n += 1
                with open(out_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(
                        {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                         "keys": keys, "payload": payload},
                        ensure_ascii=False) + "\n")
                print(f"[draft] 命中 #{n}: {', '.join(keys)}", file=sys.stderr)
            polls += 1
            if args.max_polls and polls >= args.max_polls:
                break
            time.sleep(args.poll)
    except KeyboardInterrupt:
        print("\n[draft] 已停止", file=sys.stderr)
    print(f"[draft] 共录 {n} 条载荷 → {out_path}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- 轮抓 pick 排名面板（--watch）
# 实测 schema（Quick Draft，2026-08 实测确认）：日志响应行的外层 JSON
# {"CurrentModule":"BotDraft","Payload":"<字符串化JSON>"}，解一层得内层：
# DraftStatus("PickNext")/EventName("QuickDraft_HOB_20260820")/
# PackNumber(0起，共3包)/PickNumber(0起，包内递增)/DraftPack(当前包剩余
# grpId 字符串)/PickedCards(已抓 grpId 累计)。每条新响应 = 一次状态更新。
DRAFT_PANEL_PORT = 8643  # 避开 advise 监控台的 8642
DRAFT_GRADES = list(deck_core.GRADE_EQ)  # S→F 强度序，与 mtga_draft_tool.GRADES 同序
_DRAFT_SET_RE = re.compile(r"QuickDraft_([A-Z0-9]+)_")


def load_card_table(set_code):
    """延迟导入 mtga_draft_tool 读本地评分表（其顶层反向 import 本模块，
    顶层导入会循环）。无评分表文件返回 None（面板降级为全 "?"）。"""
    import mtga_draft_tool as MDT
    return MDT.load_card_table(set_code)


def parse_draft_status(payload):
    """外层载荷 → BotDraftDraftStatus 内层 dict；非轮抓状态返回 None。"""
    if not isinstance(payload, dict):
        return None
    inner = payload.get("Payload")
    if not isinstance(inner, str) or inner[:1] != "{":
        return None
    try:
        data = json.loads(inner)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or "DraftStatus" not in data:
        return None
    return data


class DraftPickPanel:
    """实时 pick 排名面板状态机：逐条喂内层 BotDraftDraftStatus dict，
    重建当前包排名快照（牌名/cmc/评分在状态更新时解析并缓存，渲染零 I/O）。
    排名：主键等级（S→F），次键社区分；curve_fit 作第三参考提示。"""

    def __init__(self, set_code=None, llm=False, llm_config_path=None):
        self._lock = threading.Lock()
        self.event_name = ""
        self.set_code = set_code
        self.llm_enabled = bool(llm)
        self.llm_config_path = Path(llm_config_path) if llm_config_path else LLM_CONFIG_JSON
        self.status = None
        self.pack_number = 0
        self.pick_number = 0
        self.pack = []      # 当前包剩余 grpId（字符串）
        self.picked = []    # 已抓 grpId（字符串，日志自带累计值）
        self.rows = []           # 当前包排名快照
        self.picked_grades = {}  # 已抓牌池：等级 → [牌名]
        self.picked_curve = {}   # 已抓曲线：slot → 张数
        self._table = None
        self._table_loaded = False
        self._info_cache = {}    # grpId → name/cn/确定性卡牌元数据
        self._signals = {}
        self._signal_key = None
        self.advice_status = "disabled" if not self.llm_enabled else "pending"
        self.advice_error = None
        self.advice_rows = []
        self._advice_key = None

    def feed(self, data):
        """喂内层 BotDraftDraftStatus dict；是轮抓状态返回 True，否则 False。"""
        if not isinstance(data, dict) or "DraftStatus" not in data:
            return False
        with self._lock:
            event = data.get("EventName")
            if event:
                self.event_name = event
                if not self.set_code:
                    m = _DRAFT_SET_RE.search(event)
                    if m:
                        self.set_code = m.group(1)
            self.status = data.get("DraftStatus") or self.status
            for key, attr in (("PackNumber", "pack_number"),
                              ("PickNumber", "pick_number")):
                val = data.get(key)
                if isinstance(val, int):
                    setattr(self, attr, val)
            if isinstance(data.get("DraftPack"), list):
                self.pack = [str(g) for g in data["DraftPack"]]
            if isinstance(data.get("PickedCards"), list):
                self.picked = [str(g) for g in data["PickedCards"]]
            self._rebuild()
        return True

    def _ensure_table(self):
        if not self._table_loaded and self.set_code:
            self._table = load_card_table(self.set_code)
            self._table_loaded = True
        return self._table

    def _card_info(self, grp_id):
        """grpId → {name, cn, cmc}（进程内缓存；name 走 grp 磁盘缓存，
        cn/cmc 走 HTTP 磁盘缓存；解析失败给 None，渲染降级 <grpId N>）。"""
        if grp_id in self._info_cache:
            return self._info_cache[grp_id]
        name = MLT.resolve_grp_meta(grp_id).get("name")
        cn = None
        if name:
            cn, _err = fetch_chinese_name(name)
        raw = {}
        cmc = None
        try:
            raw = scryfall_get(f"/cards/arena/{grp_id}")
            cmc = raw.get("cmc")
        except MtgToolError:
            pass
        info = {"name": name or raw.get("name"), "cn": cn, "cmc": cmc,
                "colors": raw.get("colors") or [],
                "rarity": raw.get("rarity") or "",
                "mana_cost": raw.get("mana_cost") or "",
                "type_line": raw.get("type_line") or "",
                "oracle_text": raw.get("oracle_text") or "",
                "keywords": raw.get("keywords") or []}
        self._info_cache[grp_id] = info
        return info

    def _card_label(self, grp_id, info):
        name = info.get("name")
        if not name:
            return f"<grpId {grp_id}>"
        return f"{info['cn']}（{name}）" if info.get("cn") else name

    @staticmethod
    def _slot_label(slot):
        return "5+费" if slot >= 5 else f"{slot}费"

    def _llm_request(self, prompt):
        cfg = load_llm_config(self.llm_config_path)
        return llm_chat(cfg, [{"role": "user", "content": prompt}], timeout=60)

    def update_llm_config(self, values):
        if not isinstance(values, dict):
            raise AutoToolError("配置请求必须是 JSON 对象")
        result = save_llm_config(
            values.get("base_url"), values.get("model"), values.get("api_key"),
            self.llm_config_path)
        with self._lock:
            self.advice_status = "pending" if self.llm_enabled else "disabled"
            self.advice_error = None
            self._advice_key = None
        return result

    def snapshot(self):
        """返回本地 UI/API 使用的可序列化状态，不含任何密钥。"""
        with self._lock:
            return {
                "event_name": self.event_name,
                "set_code": self.set_code,
                "status": self.status,
                "pack_number": self.pack_number,
                "pick_number": self.pick_number,
                "pack_count": len(self.pack),
                "picked_count": len(self.picked),
                "rows": [dict(row) for row in self.rows],
                "picked_grades": {key: list(value)
                                   for key, value in self.picked_grades.items()},
                "picked_curve": dict(self.picked_curve),
                "signals": dict(self._signals),
                "llm_enabled": self.llm_enabled,
                "advice_status": self.advice_status,
                "advice_error": self.advice_error,
                "llm_config": llm_config_status(self.llm_config_path),
            }

    def _apply_advice(self, rows, counts, table):
        """在显式 --llm 时生成一次当前 pick 的八轴推荐并重排可解析牌。"""
        if not self.llm_enabled:
            return rows
        state_key = (self.pack_number, self.pick_number, tuple(self.pack))
        if state_key == self._advice_key:
            advice_by_name = {
                row.card.get("name"): row for row in self.advice_rows
            }
        else:
            cards = []
            for row in rows:
                info = self._info_cache.get(row["grp_id"], {})
                if not info.get("name"):
                    continue
                card = dict(info)
                card.update({"name": info["name"], "grade": row["grade"],
                             "community_score": row["score"], "note": row["note"],
                             "grp_id": row["grp_id"]})
                cards.append(card)
            if not cards:
                self.advice_status = "offline"
                self.advice_error = "当前包没有可解析牌名"
                self.advice_rows = []
                self._advice_key = state_key
                return rows

            if state_key != self._signal_key:
                signal_cards = [{"colors": card.get("colors") or [],
                                 "grade": card.get("grade") or ""}
                                for card in cards]
                deck_core.update_signals(self._signals, signal_cards,
                                         self.pick_number + 1)
                self._signal_key = state_key
            picked_cards = []
            for gid in self.picked:
                info = self._info_cache.get(gid) or self._card_info(gid)
                if info.get("name"):
                    picked_cards.append(dict(info))
            result = DRAFT_ADVISOR.recommend_pick(
                cards, picked_cards, signals=self._signals, table=table,
                llm_request=self._llm_request, pick_number=self.pick_number + 1)
            self.advice_status = result.status
            self.advice_error = result.error
            self.advice_rows = list(result.recommendations)
            self._advice_key = state_key
            record_draft_advice(self.event_name, self.pack_number,
                                self.pick_number, result)
            advice_by_name = {
                row.card.get("name"): row for row in self.advice_rows
            }

        for row in rows:
            recommendation = advice_by_name.get(self._info_cache.get(row["grp_id"], {}).get("name"))
            if recommendation is not None:
                row["recommendation_score"] = recommendation.total
                row["advice_reason"] = recommendation.reason
            else:
                row["recommendation_score"] = None
                row["advice_reason"] = "未解析，未参与推荐"
        rows.sort(key=lambda row: (
            row["recommendation_score"] is None,
            -(row["recommendation_score"] or 0.0), row["label"]))
        return rows

    def _rebuild(self):
        table = self._ensure_table()
        counts = {}
        for gid in self.picked:
            cmc = self._card_info(gid).get("cmc")
            if cmc is None:
                continue
            slot = deck_core.cmc_slot(cmc)
            counts[slot] = counts.get(slot, 0) + 1
        self.picked_curve = counts
        rows = []
        for gid in self.pack:
            info = self._card_info(gid)
            entry = table.lookup(info["name"]) if (table and info["name"]) else None
            entry = entry or {}
            grade = entry.get("grade") or ""
            if grade not in DRAFT_GRADES:
                grade = ""
            hint = ""
            if info["cmc"] is not None:
                fit = deck_core.curve_fit_score(counts, info["cmc"])
                label = self._slot_label(deck_core.cmc_slot(info["cmc"]))
                if fit >= 1.0:
                    hint = f"补{label}缺口"
                elif fit <= 0.1:
                    hint = f"{label}已溢出"
            rows.append({"grp_id": gid, "label": self._card_label(gid, info),
                         "grade": grade, "score": entry.get("community_score"),
                         "note": entry.get("note") or "", "hint": hint})
        if self.llm_enabled and self.status == "PickNext":
            rows = self._apply_advice(rows, counts, table)
        else:
            rows.sort(key=lambda r: (DRAFT_GRADES.index(r["grade"])
                                     if r["grade"] in DRAFT_GRADES else len(DRAFT_GRADES),
                                     -(r["score"] or 0), r["label"]))
        self.rows = rows
        groups = {}
        for gid in self.picked:
            info = self._card_info(gid)
            entry = table.lookup(info["name"]) if (table and info["name"]) else None
            grade = (entry or {}).get("grade") or "?"
            if grade not in DRAFT_GRADES:
                grade = "?"
            groups.setdefault(grade, []).append(self._card_label(gid, info))
        self.picked_grades = groups

    def render_html(self):
        """格式化当前快照为自刷新页面（纯字符串拼接，全量转义，无 I/O）。"""
        with self._lock:
            esc = html.escape
            config = llm_config_status(self.llm_config_path)
            head = (f"{esc(self.event_name) or '（等待轮抓状态…）'}"
                    f"　系列 {esc(self.set_code or '?')}")
            key_state = ("已配置（" + str(config["api_key_source"]) + ")"
                         if config["has_api_key"] else "未配置")
            config_error = (f"；{config['error']}" if config["error"] else "")
            parts = [
                "<header class=\"topbar\"><div><h1>轮抓 Pick 控制台</h1>"
                f"<p class=\"meta\">{head}</p></div>"
                "<a href=\"/api/state\" target=\"_blank\">状态 JSON</a></header>",
                "<section class=\"config panel\"><div class=\"section-title\">LLM 端点配置</div>"
                "<form id=\"llm-config\"><label>Endpoint"
                f"<input id=\"llm-endpoint\" value=\"{esc(str(config['base_url']))}\" required></label>"
                f"<label>Model<input id=\"llm-model\" value=\"{esc(str(config['model']))}\" required></label>"
                "<label>API key<input id=\"llm-key\" type=\"password\" autocomplete=\"new-password\""
                " placeholder=\"留空则保留当前值\"></label>"
                "<button type=\"submit\">保存配置</button><span id=\"config-result\"></span></form>"
                f"<p class=\"config-meta\">Key: {esc(key_state)}{esc(config_error)}；"
                f"配置文件: {esc(str(config['path']))}</p></section>",
            ]
            if self.status and self.status != "PickNext":
                parts.append(f"<p class=\"status\">状态：{esc(self.status)}</p>")
            if self.status == "PickNext":
                parts.append(
                    f"<h2>P{self.pack_number + 1} Pick{self.pick_number + 1}"
                    f"　当前包 {len(self.rows)} 张（按强度排序）</h2>")
                if self.llm_enabled:
                    state = esc(self.advice_status)
                    if self.advice_error:
                        state += f"：{esc(self.advice_error)}"
                    parts.append(f"<p class=\"advice-status\">推荐状态：{state}</p>")
                    parts.append("<table><tr><th>#</th><th>等级</th><th>牌名</th>"
                                 "<th>社区分</th><th>综合</th><th>曲线</th>"
                                 "<th>推荐理由</th><th>短评</th></tr>")
                else:
                    parts.append("<table><tr><th>#</th><th>等级</th><th>牌名</th>"
                                 "<th>社区分</th><th>曲线</th><th>短评</th></tr>")
                for i, r in enumerate(self.rows, 1):
                    score = "-" if r["score"] is None else esc(str(r["score"]))
                    if self.llm_enabled:
                        total = ("-" if r["recommendation_score"] is None else
                                 esc(f"{r['recommendation_score']:.3f}"))
                        parts.append(
                            f"<tr><td>{i}</td><td class=\"g\">{esc(r['grade'] or '?')}</td>"
                            f"<td>{esc(r['label'])}</td><td>{score}</td><td>{total}</td>"
                            f"<td>{esc(r['hint'])}</td><td>{esc(r['advice_reason'])}</td>"
                            f"<td>{esc(r['note'])}</td></tr>")
                    else:
                        parts.append(
                            f"<tr><td>{i}</td><td class=\"g\">{esc(r['grade'] or '?')}</td>"
                            f"<td>{esc(r['label'])}</td><td>{score}</td>"
                            f"<td>{esc(r['hint'])}</td><td>{esc(r['note'])}</td></tr>")
                parts.append("</table>")
            total = sum(len(v) for v in self.picked_grades.values())
            parts.append(f"<h2>已抓 {total} 张</h2>")
            for grade in DRAFT_GRADES + ["?"]:
                labels = self.picked_grades.get(grade)
                if labels:
                    parts.append(f"<p><b>{esc(grade)}</b> ×{len(labels)}："
                                 f"{esc('、'.join(labels))}</p>")
            curve = "　".join(f"{self._slot_label(s)}×{self.picked_curve.get(s, 0)}"
                              for s in (1, 2, 3, 4, 5))
            parts.append(f"<p>曲线：{curve}</p>")
            signals = "　".join(f"{esc(color)} {value:+.2f}"
                                for color, value in sorted(self._signals.items())) or "暂无"
            parts.append(f"<p class=\"signals\">颜色信号：{signals}</p>")
            body = "\n".join(parts)
        return DRAFT_PANEL_HTML.replace("{body}", body)


DRAFT_PANEL_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="3">
<title>DeckPooper Draft Console</title>
<style>
body { font-family: "Microsoft YaHei", sans-serif; margin: 0; background: #11161d; color: #d7dee8; }
.topbar { display:flex; justify-content:space-between; align-items:center; padding:18px 22px; border-bottom:1px solid #2b3542; }
.topbar a { color:#8bd5ff; text-decoration:none; font-size:13px; }
h1 { font-size: 22px; margin:0; color:#f2f6fa; } h2 { font-size: 16px; color: #8bd5ff; margin:18px 0 8px; }
.meta, .config-meta { color: #8793a1; font-size:13px; margin:5px 0 0; }
.status { font-size: 18px; color: #ffc857; padding:0 22px; }
.panel { margin:16px 22px; padding:14px 16px; border:1px solid #2b3542; background:#18202a; border-radius:6px; }
.section-title { color:#8bd5ff; font-size:14px; margin-bottom:10px; text-transform:uppercase; letter-spacing:0.04em; }
form { display:flex; flex-wrap:wrap; gap:10px; align-items:end; }
label { display:flex; flex-direction:column; gap:5px; color:#aeb9c6; font-size:12px; min-width:190px; }
input { box-sizing:border-box; width:100%; border:1px solid #3a4755; border-radius:4px; background:#0f141a; color:#e5edf5; padding:8px 9px; }
button { border:1px solid #4a9fca; border-radius:4px; background:#1b6688; color:white; padding:8px 12px; cursor:pointer; }
#config-result { min-height:18px; color:#8ee6a6; font-size:12px; }
table { border-collapse: collapse; margin:0 22px; width:calc(100% - 44px); }
th, td { border: 1px solid #34404d; padding: 7px 9px; text-align: left; }
th { background: #202b37; color:#aeb9c6; font-size:12px; } td.g { font-weight: bold; color: #8bd5ff; }
.advice-status { margin:0 22px 10px; color:#ffc857; } .signals { color:#aeb9c6; margin:10px 22px; }
body > h2, body > p { margin-left:22px; margin-right:22px; }
@media (max-width: 800px) { .topbar { padding:14px; } .panel { margin:12px 14px; } table { margin:0 14px; width:calc(100% - 28px); font-size:12px; } th,td { padding:5px; } label { min-width:100%; } }
</style>
</head>
<body>
{body}
<script>
const form = document.getElementById('llm-config');
if (form) form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const result = document.getElementById('config-result');
  result.textContent = '保存中...';
  try {
    const response = await fetch('/api/config', { method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({base_url: document.getElementById('llm-endpoint').value,
        model: document.getElementById('llm-model').value, api_key: document.getElementById('llm-key').value}) });
    const data = await response.json();
    result.textContent = data.ok ? '已保存' : (data.error || '保存失败');
    if (data.ok) document.getElementById('llm-key').value = '';
  } catch (error) { result.textContent = '保存失败: ' + error; }
});
</script>
</body>
</html>
"""


def start_draft_panel(panel, port):
    """pick 控制台 HTTP 服务（守护线程，页面 meta refresh 3s）。
    独立实现不复用 advise 监控台（8642），返回 (server, 实际端口)。"""
    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            route = urlparse(self.path).path
            if route == "/api/state":
                self._send_json(200, panel.snapshot())
                return
            if route == "/api/config":
                self._send_json(200, panel.snapshot()["llm_config"])
                return
            if route not in {"/", "/index.html"}:
                self._send_json(404, {"ok": False, "error": "not found"})
                return
            body = panel.render_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if urlparse(self.path).path != "/api/config":
                self._send_json(404, {"ok": False, "error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                config = panel.update_llm_config(payload)
            except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError,
                    AutoToolError, OSError) as exc:
                self._send_json(400, {"ok": False, "error": str(exc)})
                return
            self._send_json(200, {"ok": True, "config": config})

        def log_message(self, *args):
            pass  # 静音访问日志

    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def _draft_backscan(path, panel, bytes_back=200 * 1024):
    """启动时往回扫日志最后 bytes_back 字节，只喂最后一条 BotDraftDraftStatus
    以恢复当前包状态（中间状态不逐条重建，避免无谓的牌名解析）。"""
    try:
        size = os.path.getsize(path)
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            fh.seek(max(0, size - bytes_back))
            text = fh.read()
    except OSError:
        return False
    feeder = PayloadFeeder()
    last = None
    for payload in feeder.feed(text) + feeder.flush():
        inner = parse_draft_status(payload)
        if inner is not None:
            last = inner
    if last is None:
        return False
    return panel.feed(last)


def _draft_console_line(panel):
    if panel.status == "PickNext":
        return (f"[draft] P{panel.pack_number + 1}Pick{panel.pick_number + 1}"
                f" 包内 {len(panel.pack)} 张 | 已抓 {len(panel.picked)} 张")
    return f"[draft] 状态：{panel.status}"


def cmd_draft_watch(args):
    """实时 pick 排名面板：tail BotDraftDraftStatus → 排名快照 → http 面板。"""
    try:
        tailer = LogTailer(args.log, from_start=args.from_start)
    except AutoToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    panel = DraftPickPanel(
        set_code=args.set,
        llm=getattr(args, "llm", False),
        llm_config_path=getattr(args, "llm_config", None),
    )
    if _draft_backscan(args.log, panel):
        print(_draft_console_line(panel) + "（回扫恢复）", file=sys.stderr)
    try:
        _srv, port = start_draft_panel(panel, args.port)
    except OSError as exc:
        print(f"[错误] 面板端口 {args.port} 不可用: {exc}", file=sys.stderr)
        return 2
    print(f"[draft] pick 面板 http://127.0.0.1:{port}/（轮询 {args.poll}s，"
          f"Ctrl+C 停止）", file=sys.stderr)
    feeder = PayloadFeeder()
    polls = 0
    try:
        while True:
            text, truncated = tailer.read_new()
            if truncated:
                print("[draft] 日志截断，继续监听", file=sys.stderr)
            for payload in (feeder.feed(text) if text else []):
                inner = parse_draft_status(payload)
                if inner is not None and panel.feed(inner):
                    print(_draft_console_line(panel), file=sys.stderr)
            polls += 1
            if args.max_polls and polls >= args.max_polls:
                break
            time.sleep(args.poll)
    except KeyboardInterrupt:
        print("\n[draft] 已停止", file=sys.stderr)
    return 0


def cmd_draft(args):
    """draft 子命令分发：--watch 面板模式 / 缺省（或 --record）录样模式。"""
    if getattr(args, "watch", False):
        return cmd_draft_watch(args)
    return cmd_draft_record(args)


# ---------------------------------------------------------------- main
def build_parser():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--log", default=str(DEFAULT_LOG), help="Player.log 路径")
        sp.add_argument("--poll", type=float, default=2.0, help="轮询间隔秒（默认 2）")
        sp.add_argument("--from-start", action="store_true",
                        help="从头处理整个日志（默认只监听新增内容）")
        sp.add_argument("--max-polls", type=int,
                        help="最多轮询次数后退出（测试/冒烟用，默认无限）")

    pw = sub.add_parser("watch", help="实时监听日志，场终自动 scan+opponent+replay+risk")
    pw.add_argument("--deck", help="给新比赛记录统一打上牌表名标签")
    common(pw)
    pw.set_defaults(func=cmd_watch)

    pa = sub.add_parser("advise", help="局内决策辅助：实时简报 + 调度建议 + 下地提醒")
    pa.add_argument("--deck", dest="deckfile",
                        help="牌表文件（缺省时从日志最近提交的 courseDeck 自动识别）")
    pa.add_argument("--lands", type=float, help="牌表地数（跳过牌表解析）")
    pa.add_argument("--deck-size", type=int, help="牌库总数（配合 --lands）")
    pa.add_argument("--land-min", type=int, help="留牌地数下限（覆盖自动推导）")
    pa.add_argument("--land-max", type=int, help="留牌地数上限（覆盖自动推导）")
    pa.add_argument("--llm", action="store_true",
                    help="启用 LLM 增强分析（读 tools/llm_config.json）")
    pa.add_argument("--llm-quiet", type=float, default=2.0,
                    help="日志静默多少秒后触发 LLM（默认 2，快速对局可调低）")
    pa.add_argument("--dashboard", type=int, nargs="?", const=8642, default=None,
                    metavar="PORT", help="启动 Web 监控台（默认端口 8642）")
    common(pa)
    pa.set_defaults(func=cmd_advise)

    pr = sub.add_parser("run", help="采样循环：等满 N 场（人工对局），逐场回收并出聚合报告")
    pr.add_argument("--games", type=int, required=True, help="目标场数")
    pr.add_argument("--deck", help="牌表名标签（scan 打标 + report 过滤）")
    pr.add_argument("--timeout", type=float, default=40.0,
                    help="单场等待上限分钟（默认 40）")
    common(pr)
    pr.set_defaults(func=cmd_run)

    pd_ = sub.add_parser("draft", help="快速轮抓驾驶舱：--record 录样 / --watch 实时 pick 排名面板")
    mode = pd_.add_mutually_exclusive_group()
    mode.add_argument("--record", action="store_true",
                      help="录样模式：宽匹配轮抓载荷整条落盘 tools/auto/draft_samples/（缺省模式）")
    mode.add_argument("--watch", action="store_true",
                      help="实时 pick 排名面板：tail BotDraftDraftStatus，排名快照出 Web 面板")
    pd_.add_argument("--set", metavar="CODE",
                     help="--watch：系列码覆盖（缺省从 EventName QuickDraft_<CODE>_ 解析）")
    pd_.add_argument("--llm", action="store_true",
                     help="--watch：启用八轴 LLM pick 推荐（失败时显示离线并保留机器排名）")
    pd_.add_argument("--llm-config", metavar="PATH",
                     help="--watch：LLM 端点配置 JSON 路径（默认 tools/llm_config.json）")
    pd_.add_argument("--port", type=int, default=DRAFT_PANEL_PORT,
                     help="--watch：面板端口（默认 8643，避开 advise 监控台 8642）")
    common(pd_)
    pd_.set_defaults(func=cmd_draft)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
