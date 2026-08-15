# Quintorius Kand V1 法术力蒙特卡洛（60 张牌表，纯颜色可达性，不含横置惩罚）
# 假设：简单调度（起手 2-5 地留下，否则调度到 6 张再判断）；BO1 手牌平滑未建模（实际更好）
import random

deck = (
    ["Sacred Foundry"] * 4 + ["Clifftop Retreat"] * 4 + ["Inspiring Vantage"] * 4
    + ["Battlefield Forge"] * 3 + ["Needleverge Pathway"] * 2
    + ["Hidden Courtyard"] * 2 + ["Hidden Volcano"] * 2 + ["Plains"] * 2 + ["Mountain"] * 1
    + ["spell"] * 36
)
R = {"Sacred Foundry", "Clifftop Retreat", "Inspiring Vantage", "Battlefield Forge",
     "Needleverge Pathway", "Hidden Volcano", "Mountain"}
W = {"Sacred Foundry", "Clifftop Retreat", "Inspiring Vantage", "Battlefield Forge",
     "Needleverge Pathway", "Hidden Courtyard", "Plains"}

N = 200_000
res = {"t2_rw": 0, "t2_land2": 0, "t5_land5_rw": 0, "t3_land3": 0, "mull": 0}
for _ in range(N):
    d = deck[:]
    random.shuffle(d)
    hand = d[:7]
    lands = [c for c in hand if c != "spell"]
    mull = not (2 <= len(lands) <= 5)
    if mull:
        res["mull"] += 1
        d = deck[:]
        random.shuffle(d)
        hand = d[:6]
        lands = [c for c in hand if c != "spell"]
    # T2 看前 8/9 张（后手多一抓，取折中：先手 T2 = 起手+2 抓）
    t2 = hand + d[len(hand):len(hand) + 2]
    l2 = [c for c in t2 if c != "spell"]
    if len(l2) >= 2:
        res["t2_land2"] += 1
        if any(c in R for c in l2) and any(c in W for c in l2):
            res["t2_rw"] += 1
    t3 = hand + d[len(hand):len(hand) + 3]
    if sum(1 for c in t3 if c != "spell") >= 3:
        res["t3_land3"] += 1
    t5 = hand + d[len(hand):len(hand) + 5]
    l5 = [c for c in t5 if c != "spell"]
    if len(l5) >= 5 and any(c in R for c in l5) and any(c in W for c in l5):
        res["t5_land5_rw"] += 1

for k, v in res.items():
    print(f"{k}: {v / N:.2%}")
