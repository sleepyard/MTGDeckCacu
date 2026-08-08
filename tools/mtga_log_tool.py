#!/usr/bin/env python3
"""MTGA 对局日志解析 CLI：离线读取 Player.log，提取比赛结果、聚合胜率、导出提交牌表。

前置：MTGA 内 选项 → 账户 → Detailed Logs (Plugin Support) 必须开启，
否则日志只有客户端高层事件，没有 GRE 比赛数据（Untapped 等追踪器同样依赖此开关）。

数据落盘：MatchRecord/matches.json（比赛记录，按 matchId 去重）、MatchRecord/decks/（提交牌表）、
MatchRecord/grp_cache.json（grpId→牌名缓存）、MatchRecord/opponents/（对手已见牌）、
MatchRecord/replays/（逐回合复盘）、MatchRecord/risk_*.md（风险点归纳）。
仅 Python 标准库（3.7+）。
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mtg_tool import MtgToolError, scryfall_get  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORD_DIR = REPO_ROOT / "MatchRecord"
MATCHES_JSON = RECORD_DIR / "matches.json"
DECKS_DIR = RECORD_DIR / "decks"

DEFAULT_LOG = Path.home() / "AppData" / "LocalLow" / "Wizards of the Coast" / "MTGA" / "Player.log"

TIMESTAMP_PATTERN = re.compile(r"(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2}(?:\s*[AP]M)?)")


class LogToolError(Exception):
    pass


# ---------------------------------------------------------------- 日志 JSON 提取
def iter_json_payloads(path, max_lines=1000):
    """宽容扫描日志：逐行寻找 '{' 起点并尝试 raw_decode，失败则累积后续行；
    超长仍失败则丢弃该起点继续。产出 (payload, 行号, 该行之前最近的时间戳)。"""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    decoder = json.JSONDecoder()
    last_ts = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        ts = TIMESTAMP_PATTERN.search(line)
        if ts:
            last_ts = ts.group(1)
        brace = line.find("{")
        if brace < 0:
            i += 1
            continue
        buf = line[brace:]
        j = i
        parsed = False
        while True:
            try:
                obj, end = decoder.raw_decode(buf)
                yield obj, i, last_ts
                i = i + buf[:end].count("\n") + 1
                parsed = True
                break
            except json.JSONDecodeError:
                j += 1
                if j >= len(lines) or j - i > max_lines:
                    break
                buf += "\n" + lines[j]
        if not parsed:
            i += 1


def find_key(obj, key, depth=0):
    """递归查找字典键（大小写不敏感），返回第一个命中的值。"""
    if depth > 12:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() == key.lower():
                return v
        for v in obj.values():
            hit = find_key(v, key, depth + 1)
            if hit is not None:
                return hit
    elif isinstance(obj, list):
        for item in obj:
            hit = find_key(item, key, depth + 1)
            if hit is not None:
                return hit
    return None


# ---------------------------------------------------------------- 比赛记录
def find_local_name(path):
    """从 AuthenticateResponse 提取本机账号 screenName（实测：seat 1 不一定是本家，
    不能靠 systemSeatId 猜）。找不到返回 None。"""
    pattern = re.compile(r'"screenName"\s*:\s*"([^"]+)"')
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = pattern.search(line)
            if m:
                return m.group(1)
    return None


def parse_match(payload, timestamp, local_name=None):
    """从 MatchGameRoomStateChangedEvent 载荷提取比赛记录；无最终结果返回 None。"""
    event = find_key(payload, "matchGameRoomStateChangedEvent")
    if not isinstance(event, dict):
        return None
    # 载荷自带 epoch 毫秒时间戳，优先于日志行时间戳（后者在多比赛连扫时会粘滞）
    payload_ts = payload.get("timestamp")
    if payload_ts:
        try:
            timestamp = datetime.fromtimestamp(
                int(payload_ts) / 1000).strftime("%Y/%m/%d %H:%M:%S")
        except (TypeError, ValueError, OSError):
            pass
    room = find_key(event, "gameRoomInfo")
    if not isinstance(room, dict):
        return None
    final = find_key(room, "finalMatchResult")
    if not isinstance(final, dict):
        return None
    config = find_key(room, "gameRoomConfig") or {}
    players = config.get("reservedPlayers") or []
    results = final.get("resultList") or []
    match_scope = [r for r in results if "match" in str(r.get("scope", "")).lower()]
    if not match_scope:
        return None
    winning_team = match_scope[-1].get("winningTeamId")
    game_results = [r for r in results if "game" in str(r.get("scope", "")).lower()]

    def team_of(p):
        return p.get("teamId")

    # 本家识别：优先按本机 screenName 匹配，其次回退 seat 1（实测 seat 1 可能是对手）
    self_player = None
    if local_name:
        self_player = next((p for p in players if p.get("playerName") == local_name), None)
    if self_player is None:
        self_player = next((p for p in players if p.get("systemSeatId") == 1),
                           players[0] if players else {})
    opponents = [p for p in players if p is not self_player]
    own_team = team_of(self_player)
    game_wins = sum(1 for r in game_results if r.get("winningTeamId") == own_team)
    game_losses = sum(1 for r in game_results
                      if r.get("winningTeamId") is not None and r.get("winningTeamId") != own_team)

    def strip_reason(result):
        raw = str(result.get("reason") or "")
        return raw.replace("ResultReason_", "") or None

    return {
        "match_id": final.get("matchId") or config.get("matchId") or "",
        "timestamp": timestamp,
        # eventId 在 reservedPlayers 条目里（实测 2.0 客户端载荷），不在 config 顶层
        "event": self_player.get("eventId") or config.get("eventId") or "",
        "self_name": self_player.get("playerName") or "",
        "deck_name": self_player.get("deckName") or "",
        "opponent_name": (opponents[0].get("playerName") if opponents else "") or "",
        "game_wins": game_wins,
        "game_losses": game_losses,
        "won": winning_team == own_team if winning_team is not None else None,
        "reason": strip_reason(match_scope[-1]),
    }


def load_matches():
    if MATCHES_JSON.is_file():
        with open(MATCHES_JSON, "r", encoding="utf-8") as fh:
            return json.load(fh).get("matches", [])
    return []


def save_matches(matches):
    RECORD_DIR.mkdir(exist_ok=True)
    with open(MATCHES_JSON, "w", encoding="utf-8") as fh:
        json.dump({"matches": matches}, fh, ensure_ascii=False, indent=2)


def scan_logs(paths):
    """扫描日志文件列表，返回新比赛记录列表（与既有记录按 match_id 去重）。"""
    known = {m["match_id"] for m in load_matches()}
    new_records = {}
    for path in paths:
        if not Path(path).is_file():
            raise LogToolError(f"日志不存在: {path}")
        local_name = find_local_name(path)
        for payload, _lineno, ts in iter_json_payloads(path):
            rec = parse_match(payload, ts, local_name=local_name)
            if rec and rec["match_id"] and rec["match_id"] not in known:
                new_records[rec["match_id"]] = rec  # 同 matchId 多次出现只留最终态
    return list(new_records.values())


def cmd_scan(args):
    paths = [args.log]
    if args.prev:
        paths.append(str(Path(args.log).with_name("Player-prev.log")))
    try:
        new = scan_logs(paths)
    except LogToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    if not new:
        print("未发现新比赛（若近期打过对局，请确认 MTGA 已开启 Detailed Logs）", file=sys.stderr)
        return 0
    if args.deck:  # 载荷通常不含牌表名，允许手动给本次新记录打标
        for m in new:
            if not m["deck_name"]:
                m["deck_name"] = args.deck
    matches = load_matches() + new
    matches.sort(key=lambda m: m["timestamp"])
    save_matches(matches)
    print("| 时间 | 事件 | 牌表 | 局比分 | 对手 | 胜负 | 结束方式 |")
    print("|---|---|---|---|---|---|---|")
    for m in new:
        verdict = "胜" if m["won"] else ("负" if m["won"] is False else "未知")
        print(f"| {m['timestamp']} | {m['event']} | {m['deck_name']} "
              f"| {m['game_wins']}:{m['game_losses']} | {m['opponent_name']} | {verdict} "
              f"| {m.get('reason') or ''} |")
    print(f"\n新增 {len(new)} 场，累计 {len(matches)} 场 → {MATCHES_JSON}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- 聚合报告
def cmd_report(args):
    matches = load_matches()
    if args.deck:
        matches = [m for m in matches if args.deck.lower() in m["deck_name"].lower()]
    if not matches:
        print("[错误] 无比赛记录，先执行 scan", file=sys.stderr)
        return 4
    groups = {}
    for m in matches:
        groups.setdefault(m["deck_name"] or "(未知牌表)", []).append(m)
    print("| 牌表 | 场数 | 场胜 | 场胜率 | 局胜 | 局负 | 局胜率 |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for deck, rows in sorted(groups.items()):
        n = len(rows)
        mw = sum(1 for r in rows if r["won"])
        gw = sum(r["game_wins"] for r in rows)
        gl = sum(r["game_losses"] for r in rows)
        print(f"| {deck} | {n} | {mw} | {mw / n:.1%} | {gw} | {gl} "
              f"| {gw / (gw + gl):.1%} |" if gw + gl else f"| {deck} | {n} | {mw} | {mw / n:.1%} | 0 | 0 | - |")
    print(f"\n> 数据来源：MTGA 真人对局日志（{MATCHES_JSON}），共 {len(matches)} 场。", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- 提交牌表导出
def resolve_arena_card(arena_id):
    """arena_id → 英文名；失败返回 None（不静默当作不存在）。"""
    try:
        card = scryfall_get(f"/cards/arena/{arena_id}")
        return card.get("name")
    except (MtgToolError, KeyError):
        return None


def cmd_decks(args):
    path = args.log
    if not Path(path).is_file():
        print(f"[错误] 日志不存在: {path}", file=sys.stderr)
        return 2
    decks = {}
    for payload, _lineno, ts in iter_json_payloads(path):
        course = find_key(payload, "courseDeck")
        if not isinstance(course, dict) or not course.get("mainDeck"):
            continue
        name = course.get("name") or "unnamed"
        decks[name] = course
    if not decks:
        print("日志中未找到提交牌表（CourseDeck）", file=sys.stderr)
        return 0
    DECKS_DIR.mkdir(parents=True, exist_ok=True)
    unresolved = 0
    for name, course in decks.items():
        lines, sb_lines = [], []
        for target, entries in (("main", lines), ("sideboard", sb_lines)):
            for entry in course.get("mainDeck" if target == "main" else "sideboard") or []:
                card_name = resolve_arena_card(entry.get("cardId"))
                if card_name is None:
                    unresolved += 1
                    card_name = f"<arena_id {entry.get('cardId')}>"
                # 双面牌只取正面名，与 MTGO/MTGA 导入格式一致
                (lines if target == "main" else sb_lines).append(
                    f"{entry.get('quantity', 1)} {card_name.split(' // ')[0]}")
        out = sorted(lines) + ([""] + ["Sideboard"] + sorted(sb_lines) if sb_lines else [])
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "deck"
        dest = DECKS_DIR / f"{safe}.txt"
        dest.write_text("\n".join(out) + "\n", encoding="utf-8")
        print(str(dest))
    if unresolved:
        print(f"[警告] {unresolved} 个 arena_id 未能解析为牌名，已原样标注", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- GRE 对局重建（共享基建）
GRP_CACHE_JSON = RECORD_DIR / "grp_cache.json"
OPPONENTS_DIR = RECORD_DIR / "opponents"
REPLAYS_DIR = RECORD_DIR / "replays"

# 区域类型 → 中文名（未知类型原样展示）
ZONE_TYPE_NAMES = {
    "ZoneType_Hand": "手牌",
    "ZoneType_Library": "牌库",
    "ZoneType_Battlefield": "战场",
    "ZoneType_Graveyard": "坟墓场",
    "ZoneType_Stack": "堆叠",
    "ZoneType_Exile": "放逐",
    "ZoneType_Revealed": "展示区",
    "ZoneType_Command": "统帅区",
    "ZoneType_Limbo": "灵薄区",
    "ZoneType_Sideboard": "备牌",
}

# ZoneTransfer category → 动作（按真实日志统计校准：实测另有 Resolve/Surveil/Exile/
# Return/SBA_Damage/Discard 等，一律不计入动作、归入"未识别事件"）
CATEGORY_ACTIONS = {
    "PlayLand": "下地",
    "CastSpell": "施放",
    "Put": "放进战场",
    "Draw": "抓牌",
    "DrawCard": "抓牌",
}

# risk 模式标记阈值（硬编码）
RISK_TURN3_LANDS = 3     # 自己第 3 个回合结束时应已下的地数，不足则标记
RISK_MULLIGAN_LIMIT = 2  # 单局调度达到此次数则标记
RISK_STUCK_NONLAND = 4   # 终局手牌中未打出的非地牌达到此数量则标记

_grp_cache = None


def load_grp_cache():
    """grpId → 牌面数据落盘缓存（MatchRecord/grp_cache.json）。
    新格式 {"name","type_line"}；兼容旧格式纯牌名字符串与 None（解析失败）。"""
    global _grp_cache
    if _grp_cache is None:
        if GRP_CACHE_JSON.is_file():
            with open(GRP_CACHE_JSON, "r", encoding="utf-8") as fh:
                _grp_cache = json.load(fh)
        else:
            _grp_cache = {}
    return _grp_cache


def save_grp_cache():
    if _grp_cache is not None:
        RECORD_DIR.mkdir(exist_ok=True)
        with open(GRP_CACHE_JSON, "w", encoding="utf-8") as fh:
            json.dump(_grp_cache, fh, ensure_ascii=False, indent=2, sort_keys=True)


def resolve_grp_meta(grp_id):
    """grpId → {"name":..., "type_line":...}（各自可为 None）。

    缓存三种历史形态兼容：dict（新格式）/ str（旧格式纯牌名，补抓 type_line 升级，
    HTTP 磁盘缓存命中时零网络成本）/ None（历史失败，不重试）。"""
    if grp_id is None:
        return {"name": None, "type_line": None}
    cache = load_grp_cache()
    key = str(grp_id)
    if key in cache:
        entry = cache[key]
        if isinstance(entry, dict):
            return {"name": entry.get("name"), "type_line": entry.get("type_line")}
        if entry is None:
            return {"name": None, "type_line": None}
        meta = {"name": entry, "type_line": None}
        try:
            card = scryfall_get(f"/cards/arena/{grp_id}")
            meta["type_line"] = card.get("type_line")
            cache[key] = meta
            save_grp_cache()
        except (MtgToolError, KeyError):
            pass
        return meta
    meta = {"name": None, "type_line": None}
    try:
        card = scryfall_get(f"/cards/arena/{grp_id}")
        meta = {"name": card.get("name"), "type_line": card.get("type_line")}
    except (MtgToolError, KeyError):
        pass
    cache[key] = meta
    save_grp_cache()
    return meta


def resolve_grp_card(grp_id):
    """grpId → 英文牌名（兼容旧接口）；解析失败返回 None。"""
    return resolve_grp_meta(grp_id)["name"]


def card_label(grp_id):
    """展示用牌名：解析失败统一为 <grpId N>。"""
    name = resolve_grp_card(grp_id)
    return name if name else f"<grpId {grp_id}>"


_CARD_TYPE_NAMES = ("Battle", "Planeswalker", "Creature", "Instant", "Sorcery",
                    "Enchantment", "Artifact", "Land")


def printed_types(type_line):
    """从 Scryfall type_line 提取牌面类型（双面牌跨面去重）。

    牌面类型是印刷属性；对局内 gameObjects 的 cardTypes 会被复制/变形效应
    改写（实测：Spark Double 复制鹏洛客后物件类型变 Planeswalker），不能当印刷类型用。"""
    if not type_line:
        return []
    out = []
    for face in type_line.split(" // "):
        head = face.split("—")[0]
        found = [t for t in _CARD_TYPE_NAMES if t in head]
        label = "/".join(found) if found else "?"
        if label not in out:
            out.append(label)
    return out


def _anno_value(anno, key):
    """取 annotation details 中指定 key 的第一个值（int 或 str），无则 None。"""
    for d in anno.get("details") or []:
        if d.get("key") == key:
            if d.get("valueInt32"):
                return d["valueInt32"][0]
            if d.get("valueString"):
                return d["valueString"][0]
    return None


def _zone_name(zones, zone_id):
    z = zones.get(zone_id)
    if not z:
        return f"区域{zone_id}"
    return ZONE_TYPE_NAMES.get(z.get("type"), z.get("type") or f"区域{zone_id}")


def _iter_game_states(log_path):
    """按日志顺序产出 (消息, gameStateMessage)（含 QueuedGameStateMessage 内嵌的）。"""
    for payload, _lineno, _ts in iter_json_payloads(log_path):
        event = payload.get("greToClientEvent")
        if not isinstance(event, dict):
            continue
        for msg in event.get("greToClientMessages") or []:
            gsm = msg.get("gameStateMessage")
            if isinstance(gsm, dict):
                yield msg, gsm


def build_match_context(log_path, match_id=None):
    """扫描全日志，重建指定比赛的 GRE 上下文；match_id=None 时取最后一个有
    finalMatchResult 的比赛。gameInfo 只在少数消息出现：缺失时按出现顺序归属，
    以最近一次 gameInfo.matchID/gameNumber 为准。"""
    if not Path(log_path).is_file():
        raise LogToolError(f"日志不存在: {log_path}")
    if match_id is None:
        for payload, _lineno, _ts in iter_json_payloads(log_path):
            final = find_key(payload, "finalMatchResult")
            if isinstance(final, dict) and final.get("matchId"):
                match_id = final["matchId"]
        if not match_id:
            raise LogToolError("日志中没有带 finalMatchResult 的比赛记录")
    # 本家座位按场绑定：ConnectResp 每场一条、紧跟该场开局消息之前（systemSeatIds
    # 在消息顶层）。用最近的 ConnectResp 座位做待定值，在该 matchID 首个 gameInfo
    # 出现时绑定；取全日志最后一条会把后续场次的座位错套到前面的比赛上。
    self_seat = None
    pending_seat = None
    for payload, _lineno, _ts in iter_json_payloads(log_path):
        event = payload.get("greToClientEvent")
        if not isinstance(event, dict):
            continue
        for msg in event.get("greToClientMessages") or []:
            if msg.get("type") == "GREMessageType_ConnectResp" and msg.get("systemSeatIds"):
                pending_seat = msg["systemSeatIds"][0]
                continue
            gsm = msg.get("gameStateMessage")
            if not isinstance(gsm, dict):
                continue
            info = gsm.get("gameInfo")
            if self_seat is None and isinstance(info, dict) and info.get("matchID") == match_id:
                self_seat = pending_seat
    cur_match = None
    cur_game = None
    games = {}
    game_order = []
    seats = set()
    zones = {}
    objects = {}
    mulligans = {}
    for msg, gsm in _iter_game_states(log_path):
        info = gsm.get("gameInfo")
        if isinstance(info, dict) and info.get("matchID"):
            cur_match = info["matchID"]
            cur_game = info.get("gameNumber") or 1
        if cur_match != match_id:
            continue
        gn = cur_game or 1
        if gn not in games:
            games[gn] = []
            game_order.append(gn)
            mulligans[gn] = {}
        games[gn].append(gsm)
        for p in gsm.get("players") or []:
            seat = p.get("systemSeatNumber")
            if seat is None:
                continue
            seats.add(seat)
        for z in gsm.get("zones") or []:
            if z.get("zoneId") is not None:
                zones[z["zoneId"]] = {"type": z.get("type"), "ownerSeatId": z.get("ownerSeatId")}
        for o in gsm.get("gameObjects") or []:
            if o.get("instanceId") is not None:
                objects[o["instanceId"]] = o
        for iid in gsm.get("diffDeletedInstanceIds") or []:
            objects.pop(iid, None)
    if not games:
        raise LogToolError(f"日志中未找到比赛 {match_id} 的 GRE 消息")
    # 调度次数按开局手牌数推断：players[].mulliganCount 多数场次缺字段。开局首批
    # 消息里双方手牌区（ZoneType_Hand + ownerSeatId + objectInstanceIds）都在；
    # 伦敦调度后最终手牌 = 7 - 调度次数。取首个 turnNumber>=1 消息（含该消息本身，
    # 实测置底快照与首个 turnInfo 同帧到达）之前的最小非空手牌数，兼容
    # "重抓 7 → 置底后 6"的快照序列；无快照则不记该座位（未知，不静默当 0）。
    for gn, msgs in games.items():
        hand_sizes = {}
        for gsm in msgs:
            for z in gsm.get("zones") or []:
                ids = z.get("objectInstanceIds")
                if (z.get("type") == "ZoneType_Hand" and z.get("ownerSeatId") is not None
                        and isinstance(ids, list) and ids):
                    seat = z["ownerSeatId"]
                    hand_sizes[seat] = min(hand_sizes.get(seat, 8), len(ids))
            ti = gsm.get("turnInfo")
            if isinstance(ti, dict) and (ti.get("turnNumber") or 0) >= 1:
                break
        mulligans[gn] = {seat: max(0, 7 - size) for seat, size in hand_sizes.items()}
    opp_seat = next((s for s in sorted(seats) if s != self_seat), None)
    return {
        "match_id": match_id,
        "self_seat": self_seat,  # ConnectResp 缺失时为 None，由调用方处理
        "opp_seat": opp_seat,
        "games": [{"game_number": gn, "messages": games[gn]} for gn in game_order],
        "zones": zones,      # zoneId → {"type", "ownerSeatId"}
        "objects": objects,  # instanceId → 物件 dict（后到的消息覆盖同 id 旧值）
        "mulligans": mulligans,  # game_number → {seat: 调度次数}
        "resolve": resolve_grp_card,
    }


def _walk_game(messages):
    """逐消息产出 (gsm, 前向填充的 turnInfo, 当前 objects 状态)。
    turnInfo 按 key 前向填充（实测存在只带 decisionPlayer 的增量消息）。"""
    turn = {}
    objects = {}
    for gsm in messages:
        ti = gsm.get("turnInfo")
        if isinstance(ti, dict):
            turn.update(ti)
        for o in gsm.get("gameObjects") or []:
            if o.get("instanceId") is not None:
                objects[o["instanceId"]] = o
        for a in gsm.get("annotations") or []:
            types = a.get("type") or []
            if "AnnotationType_ObjectIdChanged" in types:
                orig, new = _anno_value(a, "orig_id"), _anno_value(a, "new_id")
                if orig in objects and new is not None:
                    objects[new] = objects.pop(orig)
                    objects[new]["instanceId"] = new
            elif "AnnotationType_ZoneTransfer" in types:
                dest = _anno_value(a, "zone_dest")
                for iid in a.get("affectedIds") or []:
                    if iid in objects and dest is not None:
                        objects[iid] = dict(objects[iid], zoneId=dest)
        for iid in gsm.get("diffDeletedInstanceIds") or []:
            objects.pop(iid, None)
        yield gsm, (dict(turn) if turn.get("turnNumber") else None), objects


def _obj_name(objects, instance_id):
    """物件显示名：按 grpId 解析（Adventure 等子物件共享 grpId，不会重复计数，仅展示）。"""
    obj = objects.get(instance_id)
    if not obj:
        return f"<物件 {instance_id}>"
    return card_label(obj.get("grpId"))


def _match_record(match_id):
    for m in load_matches():
        if m.get("match_id") == match_id:
            return m
    return None


def _opponent_label(ctx):
    rec = _match_record(ctx["match_id"])
    if rec and rec.get("opponent_name"):
        return rec["opponent_name"]
    return f"seat{ctx['opp_seat']}"


def _safe_filename(name):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "unknown"


def _require_seats(ctx):
    if ctx["self_seat"] is None or ctx["opp_seat"] is None:
        raise LogToolError("日志缺少 ConnectResp 或 players，无法确定本家/对手座位")


# ---------------------------------------------------------------- opponent：对手已见牌
def cmd_opponent(args):
    try:
        ctx = build_match_context(args.log, args.match_id)
        _require_seats(ctx)
    except LogToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    opp_seat = ctx["opp_seat"]
    # 同名牌多次进场按 instanceId 去重后按 grpId 聚合计数；
    # 只算 GameObjectType_Card（Adventure 子物件与牌共享 grpId，token 不算"牌"）
    seen = {}  # grpId → {"ids": set, "types": [...], "pt": str}
    for game in ctx["games"]:
        for gsm in game["messages"]:
            for o in gsm.get("gameObjects") or []:
                if o.get("ownerSeatId") != opp_seat or o.get("visibility") != "Visibility_Public":
                    continue
                if o.get("type") != "GameObjectType_Card" or not o.get("grpId"):
                    continue
                entry = seen.setdefault(o["grpId"], {"ids": set(), "types": [], "pt": ""})
                entry["ids"].add(o.get("instanceId"))
                if o.get("cardTypes"):
                    entry["types"] = o["cardTypes"]
                power, tough = (o.get("power") or {}).get("value"), (o.get("toughness") or {}).get("value")
                if power is not None and tough is not None:
                    entry["pt"] = f"{power}/{tough}"
    opp_name = _opponent_label(ctx)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    OPPONENTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = OPPONENTS_DIR / f"{ts}_{_safe_filename(opp_name)}.md"
    rec = _match_record(ctx["match_id"]) or {}
    type_totals = Counter()
    rows = []
    for grp, entry in sorted(seen.items(), key=lambda kv: (-len(kv[1]["ids"]), kv[0])):
        ingame = [t.replace("CardType_", "") for t in entry["types"]]
        printed = printed_types(resolve_grp_meta(grp)["type_line"])
        if printed:
            display = "/".join(printed)
            printed_set = {t for label in printed for t in label.split("/")}
            divergent = [t for t in ingame if t not in printed_set and t != "?"]
            if divergent:  # 复制/变形体：保留对局内形态信号但不当印刷类型统计
                display += f"（复制/变形：{'/'.join(divergent)}）"
            types = printed
        else:
            display = "/".join(ingame) or "?"
            types = ingame or ["?"]
        for t in types:
            type_totals[t] += len(entry["ids"])
        rows.append(f"| {len(entry['ids'])} | {card_label(grp)} | {display} | {entry['pt']} |")
    lines = [
        f"# 对手已见牌 - {opp_name}",
        "",
        f"- 比赛：{ctx['match_id']}（事件 {rec.get('event') or '未知'}，{rec.get('timestamp') or '时间未知'}）",
        f"- 座位：我方 seat {ctx['self_seat']} / 对方 seat {opp_seat}",
        "",
        "| 见到数量 | 牌名 | 类型 | P/T |",
        "|---:|---|---|---|",
    ]
    lines += rows or ["| - | （无公开可见的对手牌） | - | - |"]
    lines += ["", "## 按类型总计", ""]
    lines += [f"- {t}：{n}" for t, n in type_totals.most_common()] or ["- 无"]
    lands = type_totals.get("Land", 0)
    creatures = type_totals.get("Creature", 0)
    others = sum(n for t, n in type_totals.items() if t not in ("Land", "Creature"))
    lines += [
        "",
        f"> 原型线索（启发式，仅供参考）：对手已见 {lands} 张地、{creatures} 张生物、"
        f"{others} 张其他牌；标志牌：{rows[0].split('|')[2].strip() if rows else '无'}。",
    ]
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(str(dest))
    print(f"对手 {opp_name} 已见牌 {sum(len(e['ids']) for e in seen.values())} 张"
          f"（{len(seen)} 种）→ {dest}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- replay：逐回合复盘
def cmd_replay(args):
    try:
        ctx = build_match_context(args.log, args.match_id)
        _require_seats(ctx)
    except LogToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    self_seat, opp_seat = ctx["self_seat"], ctx["opp_seat"]
    zones = ctx["zones"]
    opp_name = _opponent_label(ctx)
    rec = _match_record(ctx["match_id"]) or {}
    self_hand_zones = {zid for zid, z in zones.items()
                       if z["type"] == "ZoneType_Hand" and z["ownerSeatId"] == self_seat}
    out = []
    unknown_total = Counter()
    for game in ctx["games"]:
        gn = game["game_number"]
        mull = ctx["mulligans"].get(gn) or {}
        if mull:
            def _mull_seat_text(seat):
                v = mull.get(seat)
                return "未知" if v is None else f"{v} 次"
            mull_text = f"我方 {_mull_seat_text(self_seat)} / 对方 {_mull_seat_text(opp_seat)}"
        else:
            mull_text = "调度数据未解析"
        opening = []
        for gsm in game["messages"]:
            opening = [card_label(o.get("grpId")) for o in gsm.get("gameObjects") or []
                       if o.get("zoneId") in self_hand_zones and o.get("ownerSeatId") == self_seat
                       and o.get("type") == "GameObjectType_Card"]
            if opening:
                break
        out += [
            f"## 第 {gn} 局",
            "",
            f"- 对手：{opp_name}（事件 {rec.get('event') or '未知'}）",
            f"- 本家 seat：{self_seat}；调度：{mull_text}",
            f"- 我方起手 {len(opening)} 张：{'、'.join(opening) if opening else '（未解析）'}",
            "",
        ]
        turns = {}
        turn_order = []
        last_life = {}  # players 是增量消息（常只含单方），生命按 seat 前向填充
        for gsm, ti, objects in _walk_game(game["messages"]):
            if not ti:
                continue
            key = (ti["turnNumber"], ti.get("activePlayer"))
            if key not in turns:
                turns[key] = {"events": [], "life": None}
                turn_order.append(key)
            slot = turns[key]
            for p in gsm.get("players") or []:
                if p.get("systemSeatNumber") is not None and p.get("lifeTotal") is not None:
                    last_life[p["systemSeatNumber"]] = p["lifeTotal"]
            if self_seat in last_life or opp_seat in last_life:
                slot["life"] = (last_life.get(self_seat), last_life.get(opp_seat))
            for a in gsm.get("annotations") or []:
                types = a.get("type") or []
                active = ti.get("activePlayer")

                def _actor_of(obj_id):
                    obj = objects.get(obj_id) or {}
                    return obj.get("controllerSeatId") or obj.get("ownerSeatId") or active

                def _resp_prefix(actor):
                    # 回合内事件按施放者归属：非当前回合方的瞬时/闪出响应单独标注
                    if actor == active:
                        return ""
                    return "我方响应：" if actor == self_seat else "对方响应："

                if "AnnotationType_ZoneTransfer" in types:
                    cat = _anno_value(a, "category")
                    action = CATEGORY_ACTIONS.get(cat)
                    if action is None:
                        unknown_total[cat or "?"] += 1
                        continue
                    src = _zone_name(zones, _anno_value(a, "zone_src"))
                    dst = _zone_name(zones, _anno_value(a, "zone_dest"))
                    # Put 只有目的地是战场才是"放进战场"（实测调度放回牌库、Stock Up 置入手牌也用 Put）
                    if cat == "Put" and dst != "战场":
                        action = "移动"
                    for iid in a.get("affectedIds") or []:
                        name = _obj_name(objects, iid)
                        prefix = _resp_prefix(_actor_of(iid))
                        if action == "抓牌" and name.startswith("<"):
                            slot["events"].append(f"{prefix}抓牌")  # 对方抓牌物件不可见，不展示占位符
                        else:
                            slot["events"].append(f"{prefix}{action} {name}（{src}→{dst}）")
                elif "AnnotationType_DamageDealt" in types:
                    damage = _anno_value(a, "damage")
                    source = _obj_name(objects, a.get("affectorId"))
                    prefix = _resp_prefix(_actor_of(a.get("affectorId")))
                    for tid in a.get("affectedIds") or []:
                        if tid == self_seat:
                            target = "我方"
                        elif tid == opp_seat:
                            target = "对方"
                        else:
                            target = _obj_name(objects, tid)
                        slot["events"].append(f"{prefix}伤害 {damage}({source}→{target})")
        for turn_no, active in turn_order:
            slot = turns[(turn_no, active)]
            side = "我方" if active == self_seat else "对方"
            parts = slot["events"] or ["（无记录事件）"]
            if slot["life"] and slot["life"] != (None, None):
                s, o = slot["life"]
                parts.append(f"生命 {'?' if s is None else s}:{'?' if o is None else o}")
            out.append(f"[T{turn_no} {side}] {'；'.join(parts)}")
        out.append("")
    if unknown_total:
        out += ["### 未识别事件（ZoneTransfer category 未入映射表，原样计数）", ""]
        out += [f"- {cat}：{n} 次" for cat, n in unknown_total.most_common()]
    else:
        out += ["### 未识别事件：无"]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    REPLAYS_DIR.mkdir(parents=True, exist_ok=True)
    dest = REPLAYS_DIR / f"{ts}_{_safe_filename(opp_name)}.md"
    header = [f"# 对局复盘 - vs {opp_name}（{ctx['match_id']}）", ""]
    dest.write_text("\n".join(header + out) + "\n", encoding="utf-8")
    print(str(dest))
    print(f"复盘 {len(ctx['games'])} 局 → {dest}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- risk：我方风险点归纳
def _list_match_ids(log_path):
    """日志中出现的全部 matchId（gameInfo 顺序优先，finalMatchResult 补充）。"""
    ids = []
    for _msg, gsm in _iter_game_states(log_path):
        info = gsm.get("gameInfo")
        if isinstance(info, dict) and info.get("matchID") and info["matchID"] not in ids:
            ids.append(info["matchID"])
    for payload, _lineno, _ts in iter_json_payloads(log_path):
        final = find_key(payload, "finalMatchResult")
        if isinstance(final, dict) and final.get("matchId") and final["matchId"] not in ids:
            ids.append(final["matchId"])
    return ids


def _game_self_facts(ctx, game):
    """单局本家事实：调度、前 6 个自己回合下地、终局卡手非地牌、总回合数、生命最低值。"""
    self_seat = ctx["self_seat"]
    zones = ctx["zones"]
    gn = game["game_number"]
    mull = (ctx["mulligans"].get(gn) or {}).get(self_seat)  # 无开局手牌快照时为 None（未知）
    self_turns = []       # activePlayer==本家 的 turnNumber，按出现顺序
    land_turns = set()    # 本家下过地的 turnNumber
    total_turns = 0
    min_life = None
    objects = {}
    for gsm, ti, objects in _walk_game(game["messages"]):
        if ti:
            total_turns = max(total_turns, ti["turnNumber"])
            if ti.get("activePlayer") == self_seat and ti["turnNumber"] not in self_turns:
                self_turns.append(ti["turnNumber"])
        for p in gsm.get("players") or []:
            if p.get("systemSeatNumber") == self_seat and p.get("lifeTotal") is not None:
                min_life = p["lifeTotal"] if min_life is None else min(min_life, p["lifeTotal"])
        for a in gsm.get("annotations") or []:
            if "AnnotationType_ZoneTransfer" not in (a.get("type") or []) or not ti:
                continue
            if _anno_value(a, "category") != "PlayLand":
                continue
            # 归属本家：被移动物件属于本家，或目的区域属于本家
            mine = any((objects.get(iid) or {}).get("ownerSeatId") == self_seat
                       for iid in a.get("affectedIds") or [])
            dest_zone = zones.get(_anno_value(a, "zone_dest")) or {}
            if mine or dest_zone.get("ownerSeatId") == self_seat:
                land_turns.add(ti["turnNumber"])
    hand_zones = {zid for zid, z in zones.items()
                  if z["type"] == "ZoneType_Hand" and z["ownerSeatId"] == self_seat}
    stuck = [o for o in objects.values()
             if o.get("zoneId") in hand_zones and o.get("ownerSeatId") == self_seat
             and o.get("type") == "GameObjectType_Card"
             and "CardType_Land" not in (o.get("cardTypes") or [])]
    first6 = self_turns[:6]
    missed = [f"第{k + 1}回合" for k, tn in enumerate(first6) if tn not in land_turns]
    lands_t3 = sum(1 for tn in self_turns[:3] if tn in land_turns)
    flags = []
    if len(self_turns) >= 3 and lands_t3 < RISK_TURN3_LANDS:
        flags.append(f"T3 未下第三块地（前 3 个自己回合仅下地 {lands_t3} 块，阈值 {RISK_TURN3_LANDS}）")
    if mull is not None and mull >= RISK_MULLIGAN_LIMIT:
        flags.append(f"单局调度≥{RISK_MULLIGAN_LIMIT}（实际 {mull} 次）")
    if len(stuck) >= RISK_STUCK_NONLAND:
        flags.append(f"终局卡手非地牌≥{RISK_STUCK_NONLAND}（实际 {len(stuck)} 张）")
    return {
        "mulligans": mull,
        "missed_land_turns": missed,
        "stuck_names": [card_label(o.get("grpId")) for o in stuck],
        "total_turns": total_turns,
        "min_life": min_life,
        "flags": flags,
    }


def cmd_risk(args):
    if not args.all and not args.match_id:
        print("[错误] risk 需要 --match-id 或 --all", file=sys.stderr)
        return 2
    try:
        match_ids = _list_match_ids(args.log) if args.all else [args.match_id]
        if not match_ids:
            raise LogToolError("日志中未找到任何比赛")
        sections = []
        flag_totals = Counter()
        n_games = 0
        for mid in match_ids:
            ctx = build_match_context(args.log, mid)
            _require_seats(ctx)
            opp_name = _opponent_label(ctx)
            sections.append(f"## 比赛 {mid}（对手 {opp_name}）\n")
            for game in ctx["games"]:
                facts = _game_self_facts(ctx, game)
                n_games += 1
                for f in facts["flags"]:
                    flag_totals[f.split("（")[0]] += 1
                sections += [
                    f"### 第 {game['game_number']} 局",
                    "",
                    f"- 调度次数：{facts['mulligans'] if facts['mulligans'] is not None else '未知'}",
                    f"- 前 6 个自己回合缺地：{'、'.join(facts['missed_land_turns']) or '无'}",
                    f"- 终局卡手非地牌 {len(facts['stuck_names'])} 张"
                    f"（{'、'.join(facts['stuck_names']) or '无'}）",
                    f"- 对局总回合数：{facts['total_turns']}；我方生命最低值："
                    f"{facts['min_life'] if facts['min_life'] is not None else '未知'}",
                    f"- 模式标记：{'；'.join(facts['flags']) if facts['flags'] else '无'}",
                    "",
                ]
        if args.all and n_games:
            sections += ["## 发生率汇总", ""]
            sections += [f"- {name}：{n}/{n_games}（{n / n_games:.1%}）"
                         for name, n in flag_totals.most_common()] or ["- 无标记"]
            sections.append("")
        sections.append(f"> 基于 {n_games} 局样本，仅事实归纳，不构成改动建议")
        dest = RECORD_DIR / f"risk_{datetime.now().strftime('%Y%m%d')}.md"
        dest.write_text("\n".join(["# 我方风险点归纳", ""] + sections) + "\n", encoding="utf-8")
    except LogToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    print(str(dest))
    print(f"风险归纳 {len(match_ids)} 场 / {n_games} 局 → {dest}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- main
def build_parser():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("scan", help="扫描日志，新增比赛记录写入 MatchRecord/matches.json")
    ps.add_argument("--log", default=str(DEFAULT_LOG), help="Player.log 路径")
    ps.add_argument("--prev", action="store_true", help="同时扫描 Player-prev.log")
    ps.add_argument("--deck", help="给本次新记录统一打上牌表名（载荷通常不含牌表名）")
    ps.set_defaults(func=cmd_scan)

    pr = sub.add_parser("report", help="按牌表聚合胜率（Markdown）")
    pr.add_argument("--deck", help="只统计牌表名含此词的比赛")
    pr.set_defaults(func=cmd_report)

    pd = sub.add_parser("decks", help="导出日志中的提交牌表到 MatchRecord/decks/")
    pd.add_argument("--log", default=str(DEFAULT_LOG), help="Player.log 路径")
    pd.set_defaults(func=cmd_decks)

    po = sub.add_parser("opponent", help="重建 GRE 状态，汇总对手已见牌（Markdown）")
    po.add_argument("--match-id", help="目标比赛 matchId（默认取最后一场有结果的比赛）")
    po.add_argument("--log", default=str(DEFAULT_LOG), help="Player.log 路径")
    po.set_defaults(func=cmd_opponent)

    pp = sub.add_parser("replay", help="逐回合流程复盘（Markdown）")
    pp.add_argument("--match-id", help="目标比赛 matchId（默认取最后一场有结果的比赛）")
    pp.add_argument("--log", default=str(DEFAULT_LOG), help="Player.log 路径")
    pp.set_defaults(func=cmd_replay)

    pk = sub.add_parser("risk", help="本家风险点归纳：缺地/调度/卡手（Markdown）")
    g = pk.add_mutually_exclusive_group()
    g.add_argument("--match-id", help="只分析该比赛")
    g.add_argument("--all", action="store_true", help="聚合日志中所有比赛")
    pk.add_argument("--log", default=str(DEFAULT_LOG), help="Player.log 路径")
    pk.set_defaults(func=cmd_risk)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
