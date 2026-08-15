# Quintorius Kand V4 法术力蒙特卡洛（Jeskai 三色，60 张，纯颜色可达性）
# 地牌与 V3 完全相同；新增校验：T2 {1}{R}（火咬/冲刷）、预示分期（T2 {2} 放逐 + 后续 {1}{W}{W}）
# 假设：简单调度（起手 2-5 地留下）；BO1 手牌平滑未建模；不计横置状态
import random

lands = (
    ["Raugrin Triome"] * 4 + ["Hallowed Fountain"] * 4 + ["Steam Vents"] * 4
    + ["Sacred Foundry"] * 4 + ["Spirebluff Canal"] * 2 + ["Glacial Fortress"] * 2
    + ["Hidden Cataract"] * 1 + ["Hidden Courtyard"] * 1 + ["Hidden Volcano"] * 1
    + ["Island"] * 1
)
deck = lands + ["spell"] * 36
R = {"Raugrin Triome", "Steam Vents", "Sacred Foundry", "Spirebluff Canal", "Hidden Volcano"}
W = {"Raugrin Triome", "Hallowed Fountain", "Sacred Foundry", "Hidden Courtyard"}
U = {"Raugrin Triome", "Hallowed Fountain", "Steam Vents", "Spirebluff Canal",
     "Glacial Fortress", "Hidden Cataract", "Island"}

N = 200_000
res = {"t2_1r_charring": 0, "t2_rr_bedeck": 0, "t2_foretell_exile": 0,
       "t4_foretell_cast_ww": 0, "t4_uu_impersonator": 0,
       "t5_land5_rw_kand": 0, "t6_urw": 0, "mull": 0}
for _ in range(N):
    d = deck[:]
    random.shuffle(d)
    hand = d[:7]
    n_lands = sum(1 for c in hand if c != "spell")
    if not (2 <= n_lands <= 5):
        res["mull"] += 1
        d = deck[:]
        random.shuffle(d)
        hand = d[:6]
    def seen(k):
        return [c for c in hand + d[len(hand):len(hand) + k] if c != "spell"]
    t2 = seen(2)
    n_r = sum(1 for c in t2 if c in R)
    n_w = sum(1 for c in t2 if c in W)
    if len(t2) >= 2 and n_r >= 1:
        res["t2_1r_charring"] += 1
    if n_r >= 2:
        res["t2_rr_bedeck"] += 1
    if len(t2) >= 2:
        res["t2_foretell_exile"] += 1
    t4 = seen(4)
    # 预示分期：T2 已付 {2} 放逐，T3/T4 付 {1}{W}{W} 施放（需 3 地且含 2 白源）
    if len(t4) >= 3 and sum(1 for c in t4 if c in W) >= 2:
        res["t4_foretell_cast_ww"] += 1
    if sum(1 for c in t4 if c in U) >= 2:
        res["t4_uu_impersonator"] += 1
    t5 = seen(5)
    if len(t5) >= 5 and any(c in R for c in t5) and any(c in W for c in t5):
        res["t5_land5_rw_kand"] += 1
    t6 = seen(6)
    if any(c in U for c in t6) and any(c in R for c in t6) and any(c in W for c in t6):
        res["t6_urw"] += 1

for k, v in res.items():
    print(f"{k}: {v / N:.2%}")
