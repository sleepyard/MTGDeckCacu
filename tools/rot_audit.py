#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""轮替存活审计 —— 判定一套标准牌表在**下一次轮替**后还剩多少张牌能用。

规则（官方）：「每年一次，在当年第一个 premier 系列的售前赛之后，标准里最旧的六个系列轮替出去。」
  · 当前窗口的下一次轮替日与退出系列：见 strategy_params 的 rot_audit 节
    （默认 2027-02-02，随《诺克提斯：沉沦之境》售前赛）

判定方法（关键，别用「Scryfall f:standard」直接判存亡）：
  Scryfall 的赛制合法性是**按牌（oracle）**算的 —— 同一张牌的所有印刷都会显示 f:standard，
  包括广告卡/促销印。**促销印救不了牌**：轮替后要看的是「有没有一张印刷属于**非轮替的标准扩展**」。
  因此本工具按 set_type ∈ {core, expansion} 且 set 不在轮替名单内 来判定。

用法：
  python3 rot_audit.py deck <牌表文件>          # 逐张审计一份牌表
  python3 rot_audit.py card <英文名> [<英文名>…]  # 审计指定牌
"""
import json, sys, time, urllib.request, urllib.parse

import deck_config
from deck_model import parse_deck as _parse_deck

UA = "mtg-deckbuilder/1.0"

# 参数（Phase 2 数据化）：import 时加载一次，原常量名保留为兼容别名
_PARAMS = deck_config.load_params()["rot_audit"]
ROTATION_DATE = _PARAMS["ROTATION_DATE"]          # 下一次轮替日
ROTATION_SUMMARY = _PARAMS["ROTATION_SUMMARY"]    # 报告头退出系列展示串
ROTATING = set(_PARAMS["ROTATING_SETS"])          # 本次轮替退出的系列代码

SAVING_TYPES = {"core", "expansion"}
# 轮替后最旧的标准系列 = FDN《基石构筑》(2024-11-15)。此日期之后的 core/expansion 非数字系列
# 都在本次轮替后存活（含尚未发售的 FRA，以及未来的新系列）。
CUTOFF = "2024-11-15"
_sets = None


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            if i == tries - 1:
                print("  ! FAIL", url, e, file=sys.stderr)
                return None
            time.sleep(2)


def set_meta():
    global _sets
    if _sets is None:
        out = {}
        url = "https://api.scryfall.com/sets"
        while url:
            j = get(url) or {"data": []}
            for s in j["data"]:
                out[s["code"].lower()] = (s.get("set_type", "?"), s.get("released_at", ""),
                                          s.get("digital", False))
            url = j.get("next_page")
        _sets = out
    return _sets


def printings(name, only_standard=False):
    q = f'!"{name}"' + (" f:standard" if only_standard else "")
    url = "https://api.scryfall.com/cards/search?q=" + urllib.parse.quote(q) + "&unique=prints"
    out, seen = [], set()
    while url:
        j = get(url)
        if not j:
            break
        for c in j.get("data", []):
            k = (c["set"], c.get("collector_number"))
            if k in seen:
                continue
            seen.add(k)
            out.append({"set": c["set"].lower(), "cn": c.get("collector_number"),
                        "released": c.get("released_at"), "name": c["name"]})
        url = j.get("next_page")
        time.sleep(0.05)
    return out


def audit(name):
    sm = set_meta()
    pr = printings(name)
    survivors, rot = [], []
    for p in pr:
        meta = sm.get(p["set"], ("?", "", False))
        stype, rel, digital = meta
        if p["set"] in ROTATING:
            rot.append(p["set"]); continue
        if stype in SAVING_TYPES and not digital and (rel or "") >= CUTOFF:
            survivors.append(p["set"])
    return {"name": name, "prints": pr,
            "survive_sets": sorted(set(survivors)), "rot_sets": sorted(set(rot)),
            "alive": bool(survivors)}


def parse_deck(path):
    """薄委托：deck_model.parse_deck → (主牌, 备牌) 两个 [(qty, name)]。"""
    return _parse_deck(path).main_side_pairs()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if len(sys.argv) < 3:
        print(__doc__); return
    mode = sys.argv[1]
    if mode == "deck":
        main_c, side_c = parse_deck(sys.argv[2])
        print(f"# 轮替存活审计：{sys.argv[2]}")
        print(f"# 轮替日 {ROTATION_DATE} ｜ 退出：{ROTATION_SUMMARY}\n")
        tot = die = tot_s = die_s = 0
        for label, lst in (("主牌", main_c), ("备牌", side_c)):
            print(f"== {label}")
            for n, name in lst:
                a = audit(name)
                mark = "✅存活" if a["alive"] else "❌将退"
                src = ",".join(s.upper() for s in a["survive_sets"]) or "—"
                bad = ",".join(s.upper() for s in a["rot_sets"]) or "—"
                print(f"  {mark}  {n:2d} {name:44s} 存活印刷={src:22s} 轮替印刷={bad}")
                if label == "主牌":
                    tot += n; die += 0 if a["alive"] else n
                else:
                    tot_s += n; die_s += 0 if a["alive"] else n
        print(f"\n主牌：{tot - die}/{tot} 张轮替后存活（将退 {die} 张）")
        print(f"备牌：{tot_s - die_s}/{tot_s} 张轮替后存活（将退 {die_s} 张）")
    else:
        for n in sys.argv[2:]:
            a = audit(n)
            print(f'{"✅" if a["alive"] else "❌"} {n:44s} 存活={",".join(s.upper() for s in a["survive_sets"]) or "—":24s} '
                  f'轮替={",".join(s.upper() for s in a["rot_sets"]) or "—"}')


if __name__ == "__main__":
    main()
