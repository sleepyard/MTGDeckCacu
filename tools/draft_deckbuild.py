#!/usr/bin/env python3
"""从轮抓录样的 PickedCards 出 40 张牌表（组牌骨架建议）。

用法：python tools/draft_deckbuild.py [--set HOB] [--colors gu] [--out deck.txt]
牌池来源：tools/auto/draft_samples/ 最新录样的最终 PickedCards。
选牌口径：tools/draft_methodology.md §1/§4（grade_eq 排序 + 曲线目标 + 动态地数
+ pip 法术力配比）。仅标准库；网络走 mtg_tool/mtga_log_tool 磁盘缓存。
"""

import argparse
import glob
import itertools
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck_core as DC  # noqa: E402
import mtga_log_tool as L  # noqa: E402
import mtga_draft_tool as D  # noqa: E402

COLORS = "WUBRG"
COLOR_CN = {"W": "白", "U": "蓝", "B": "黑", "R": "红", "G": "绿"}


def latest_picked():
    """最新录样文件的最终 PickedCards → [grpId str]。"""
    root = Path(__file__).resolve().parent / "auto" / "draft_samples"
    files = sorted(root.glob("*.jsonl"), key=os.path.getmtime)
    if not files:
        raise SystemExit("[错误] 无录样文件（先跑 mtga_auto_tool.py draft --record）")
    picked = None
    for line in open(files[-1], encoding="utf-8"):
        try:
            p = json.loads(line)["payload"]
            inner = p.get("Payload")
            if isinstance(inner, str):
                inner = json.loads(inner)
            if isinstance(inner, dict) and inner.get("PickedCards"):
                picked = inner["PickedCards"]
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    if not picked:
        raise SystemExit("[错误] 录样中没有 PickedCards（轮抓未完成？）")
    return picked


def fetch_card(grp_id):
    """grpId → {name, cmc, colors, cost, type, rarity}（双面/历险取正面+并集颜色）。"""
    c = L.scryfall_get(f"/cards/arena/{grp_id}")
    if not isinstance(c, dict) or "name" not in c:
        return {"name": f"<grpId {grp_id}>", "cmc": None, "colors": [],
                "cost": "", "type": "", "rarity": ""}
    colors = set(c.get("colors") or [])
    cost = c.get("mana_cost") or ""
    faces = c.get("card_faces") or []
    if faces and c.get("layout") not in (None, "normal"):
        for f in faces:
            colors.update(f.get("colors") or [])
        cost = cost or faces[0].get("mana_cost", "")
    return {"name": c["name"], "cmc": c.get("cmc"), "colors": sorted(colors),
            "cost": cost, "type": c.get("type_line") or "",
            "rarity": c.get("rarity") or ""}


def evaluate_combo(pool, combo, table):
    """双色组合得分：颜色 ⊆ combo 的牌按 grade_eq 取 top-23 求和 + 生物/去除加成。"""
    playable = [c for c in pool
                if set(c["colors"]) <= set(combo) and "Land" not in c["type"]]
    ranked = sorted(playable,
                    key=lambda c: DC.grade_eq((table.lookup(c["name"]) or {}).get("grade")),
                    reverse=True)
    top = ranked[:DC.TARGET_NON_LANDS]
    score = sum(DC.grade_eq((table.lookup(c["name"]) or {}).get("grade")) for c in top)
    return score, ranked


def build_deck(pool, table, forced_colors=None):
    """选色 → splash 准入 → 地数反推非地配额（总数恒 40）。返回主牌/配比/报告。"""
    if forced_colors:
        combo = tuple(forced_colors)
        _s, ranked = evaluate_combo(pool, combo, table)
    else:
        best = None
        for combo in itertools.combinations(COLORS, 2):
            score, ranked = evaluate_combo(pool, combo, table)
            if best is None or score > best[0]:
                best = (score, combo, ranked)
        _s, combo, ranked = best

    # splash 先定：组合外、仅 1 个异色、等级 ≥B+，最多 SPLASH_MAX_CARDS 张，
    # 占用非地配额（坑：splash 是替换主牌位不是额外加，否则总数会变 41+）
    splash = []
    in_combo = {c["name"] for c in ranked}
    for c in pool:
        if c["name"] in in_combo:
            continue
        extra = set(c["colors"]) - set(combo)
        if len(extra) != 1:
            continue
        e = table.lookup(c["name"]) or {}
        if DC.grade_eq(e.get("grade")) >= DC.GRADE_EQ["B+"] \
                and len(splash) < DC.SPLASH_MAX_CARDS:
            splash.append(c)
            in_combo.add(c["name"])

    # 初取 23 张估算 avg_cmc → 定地数 → 非地配额 = 40 − 地数（含 splash）
    probe = (ranked[:DC.TARGET_NON_LANDS] + splash)
    avg_cmc = (sum(c["cmc"] or 3 for c in probe) / len(probe)) if probe else 3.0
    lands = DC.land_count(avg_cmc, splash_count=len(splash))
    quota = 40 - lands - len(splash)
    main = ranked[:max(0, quota)]
    cuts = ranked[max(0, quota):]

    splash_colors = sorted({x for c in splash for x in c["colors"]} - set(combo))
    pips = Counter()
    for c in main + splash:
        pips.update(DC.parse_mana_pips(c["cost"]))
    mana = DC.mana_base(dict(pips), lands, splash_colors=splash_colors)

    report = [f"主色: {'+'.join(COLOR_CN[c] for c in combo)}"
              + (f"，splash {'+'.join(COLOR_CN[c] for c in splash_colors)}" if splash else ""),
              f"非地 {len(main) + len(splash)} 张（含 splash {len(splash)} 张），"
              f"平均 CMC {avg_cmc:.2f}，地 {lands} 张 → "
              + " / ".join(f"{COLOR_CN[c]}{n}" for c, n in sorted(mana.items())),
              "淘汰: " + (", ".join(c["name"] for c in cuts) or "无")]
    return main + splash, mana, lands, report, combo


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", default="HOB", help="评分表系列码（默认 HOB）")
    ap.add_argument("--colors", help="强制主色（如 gu），缺省自动选最强双色")
    ap.add_argument("--out", help="输出 MTGA 牌表文件（缺省只打印）")
    args = ap.parse_args(argv)

    table = D.load_card_table(args.set)
    if table is None:
        raise SystemExit(f"[错误] 无评分表 cache/draft_ratings/{args.set}.json")
    picked = latest_picked()
    pool = [fetch_card(g) for g in picked]
    land_pool = [c for c in pool if "Land" in c["type"]]
    pool = [c for c in pool if "Land" not in c["type"]]

    forced = list(args.colors.upper()) if args.colors else None
    main_cards, mana, lands, report, combo = build_deck(pool, table, forced)

    basic = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}
    lines = ["Deck"]
    for c in sorted(main_cards, key=lambda c: (c["cmc"] or 0, c["name"])):
        e = table.lookup(c["name"]) or {}
        lines.append(f"1 {c['name']}")
    for color, n in sorted(mana.items()):
        for _ in range(n):
            lines.append(f"1 {basic[color]}")

    print(f"牌池 {len(picked)} 张（非地 {len(pool)}，地/其他 {len(land_pool)}）")
    for r in report:
        print(r)
    curve = Counter(DC.cmc_slot(c["cmc"]) for c in main_cards)
    label, _ = DC.curve_rating(dict(curve))
    print("曲线:", " ".join(f"{s}费×{curve.get(s, 0)}" for s in sorted(curve)),
          f"→ {label}")
    creatures = sum(1 for c in main_cards if "Creature" in c["type"])
    print(f"生物 {creatures} 张")
    print()
    print("\n".join(lines))
    if args.out:
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n[deck] 已写入 {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
