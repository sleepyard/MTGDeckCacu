#!/usr/bin/env python3
"""轮抓发包复盘：从录样重建每抓包内容 × 评分表，分析信号与 pick 质量。

用法：python tools/draft_pack_review.py [--set HOB] [--out md路径]

实测口径（教训沉淀）：
- 中间态 PickedCards 不可靠（滞后/乱序），"你拿了哪张"用最终 Completed 态
  PickedCards 与当抓包内容做多重集交集反推（按抓序贪心消耗）。
- 轮抓每抓看到的是下一个人的包（连续抓包内容无关），同一包 8 抓后转回：
  机器人吃牌 = 第 N 抓包 − 第 N+8 抓包 − 你的第 N 抓，仅当张数差恰为 8。
仅标准库，网络走磁盘缓存。"""

import argparse
import glob
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck_core as DC  # noqa: E402
import mtga_log_tool as L  # noqa: E402
import mtga_draft_tool as D  # noqa: E402

COLOR_CN = {"W": "白", "U": "蓝", "B": "黑", "R": "红", "G": "绿"}
WHEEL = 8  # 8 人桌：同一包 8 抓后转回


def load_states():
    root = Path(__file__).resolve().parent / "auto" / "draft_samples"
    files = sorted(root.glob("*.jsonl"), key=os.path.getmtime)
    if not files:
        raise SystemExit("[错误] 无录样文件")
    states = []
    for line in open(files[-1], encoding="utf-8"):
        try:
            p = json.loads(line)["payload"]
            inner = p.get("Payload")
            if isinstance(inner, str):
                inner = json.loads(inner)
            if isinstance(inner, dict) and "PackNumber" in inner:
                states.append(inner)
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    seen, out = set(), []
    for s in states:
        key = (s.get("PackNumber"), s.get("PickNumber"),
               tuple(s.get("DraftPack") or ()))
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


class Cache:
    def __init__(self, table):
        self.table = table
        self._meta = {}

    def meta(self, gid):
        if gid not in self._meta:
            c = L.scryfall_get(f"/cards/arena/{gid}")
            if isinstance(c, dict) and "name" in c:
                colors = set(c.get("colors") or [])
                for f in (c.get("card_faces") or []):
                    colors.update(f.get("colors") or [])
                e = self.table.lookup(c["name"]) or {}
                self._meta[gid] = {
                    "name": c["name"], "rarity": c.get("rarity") or "",
                    "colors": sorted(colors), "cmc": c.get("cmc"),
                    "grade": e.get("grade") or "?", "note": e.get("note") or "",
                    "score": e.get("community_score"),
                }
            else:
                self._meta[gid] = {"name": f"<grpId {gid}>", "rarity": "",
                                   "colors": [], "cmc": None, "grade": "?",
                                   "note": "", "score": None}
        return self._meta[gid]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", default="HOB")
    ap.add_argument("--out", help="Markdown 输出路径")
    args = ap.parse_args(argv)

    table = D.load_card_table(args.set)
    if table is None:
        raise SystemExit(f"[错误] 无评分表 cache/draft_ratings/{args.set}.json")
    cache = Cache(table)
    all_states = load_states()
    states = [s for s in all_states if s.get("DraftStatus") == "PickNext"]
    final_pool = Counter()
    for s in all_states:
        if s.get("DraftStatus") == "Completed" or s.get("PickNumber", 0) >= 13:
            pcs = s.get("PickedCards") or []
            if len(pcs) > sum(final_pool.values()):
                final_pool = Counter(pcs)
    if not final_pool:
        raise SystemExit("[错误] 录样中没有最终 PickedCards")

    # 反推每抓拿了哪张（实测口径：中间态 PickedCards 约第 5 抓后滞后乱序，
    # 仅前缀自洽段可信；跨包同名单纯牌会造成多重歧义）：
    # 1) 相邻状态 PickedCards 满足前缀关系时，差集尾牌即本抓；
    # 2) 否则用同包转回（8 抓后）差集 ∩ 最终池；
    # 3) 多候选时排除"在后续包中也出现过"的 grpId（池里那张可能来自后面的包）。
    packs = [s.get("DraftPack") or [] for s in states]
    later_pack_ids = [set() for _ in packs]
    for i in range(len(packs)):
        for j in range(i + 1, len(packs)):
            later_pack_ids[i] |= set(packs[j])
    taken = []
    pool = Counter(final_pool)
    prev_picked = []
    for i, pack in enumerate(packs):
        cur_picked = states[i].get("PickedCards") or []
        pick = None
        if len(cur_picked) > len(prev_picked) and \
                cur_picked[:len(prev_picked)] == prev_picked:
            cand = cur_picked[len(prev_picked)]
            if cand in pack and pool[cand] > 0:
                pick = cand  # 前缀自洽，直接采信
        if pick is None:
            j = i + WHEEL
            has_wheel = (j < len(states)
                         and states[j]["PackNumber"] == states[i]["PackNumber"]
                         and len(pack) - len(packs[j]) == WHEEL)
            base = (Counter(pack) - Counter(packs[j])) if has_wheel else Counter(pack)
            cands = [g for g in base.elements() if pool[g] > 0]
            if len(cands) > 1:
                uniq = [g for g in cands if g not in later_pack_ids[i]]
                if uniq:
                    cands = uniq
            pick = cands[0] if cands else None
        if pick:
            pool[pick] -= 1
        taken.append(pick)
        prev_picked = cur_picked

    lines = [f"# 轮抓发包复盘（{args.set}）", ""]
    cur_pack = 0
    for i, s in enumerate(states):
        pack_no, pick_no = s["PackNumber"] + 1, s["PickNumber"] + 1
        pack = [cache.meta(g) for g in packs[i]]
        if pack_no != cur_pack:
            cur_pack = pack_no
            rares = [c for c in pack if c["rarity"] in ("rare", "mythic")]
            lines += [f"## 第 {pack_no} 包", "",
                      "首抓金卡位: " + (", ".join(
                          f"{c['name']}（{c['grade']}）" for c in rares) or "未见"),
                      ""]
        got = cache.meta(taken[i]) if taken[i] else None
        ranked = sorted(pack, key=lambda c: (-DC.grade_eq(c["grade"]),
                                             -(c["score"] or 0)))
        best = ranked[0] if ranked else None
        got_s = f"{got['name']}（{got['grade']}）" if got else "（未识别）"
        best_s = f"{best['name']}（{best['grade']}）" if best else "-"
        flag = ""
        if got and best and got["name"] != best["name"] and \
                DC.grade_eq(got["grade"]) < DC.grade_eq(best["grade"]):
            flag = " ⚠ 放过了更高分"
        sig = Counter()
        for c in pack:
            if DC.grade_eq(c["grade"]) >= DC.GRADE_EQ["B-"]:
                for col in c["colors"]:
                    sig[col] += 1
        sig_s = " ".join(f"{COLOR_CN[c]}{n}" for c, n in
                         sorted(sig.items(), key=lambda kv: -kv[1])) or "无"
        lines.append(f"- P{pack_no}Pick{pick_no}: 你拿 {got_s} | "
                     f"包内最高 {best_s}{flag}｜剩余 ≥B-: {sig_s}")

    # 机器人吃牌：同一包转回（第 N 抓 vs 第 N+8 抓，张数差恰 8）
    lines += ["", "## 机器人吃牌（同包转回对比，≥B- 部分）", ""]
    for i, s in enumerate(states):
        j = i + WHEEL
        if j >= len(states):
            break
        if states[j]["PackNumber"] != s["PackNumber"]:
            continue
        if len(packs[i]) - len(packs[j]) != WHEEL:
            continue
        gone = Counter(packs[i]) - Counter(packs[j])
        if taken[i]:
            gone.subtract([taken[i]])
        bots = [cache.meta(g) for g in gone.elements()
                if DC.grade_eq(cache.meta(g)["grade"]) >= DC.GRADE_EQ["B-"]]
        if bots:
            lines.append(
                f"- P{s['PackNumber']+1} 第{s['PickNumber']+1}抓的包转回时被拿走: "
                + ", ".join(f"{c['name']}（{c['grade']}，"
                             f"{''.join(c['colors']) or '无色'}）" for c in bots))
    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"[review] 已写入 {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
