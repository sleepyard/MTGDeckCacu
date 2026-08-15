# Quintorius Kand V2 法术力蒙特卡洛（RWU 三色，60 张牌表，纯颜色可达性）
# 假设：简单调度（起手 2-5 地留下）；BO1 手牌平滑未建模（实际更好）；不计横置状态
import random

lands = (
    ["Sacred Foundry"] * 4 + ["Hallowed Fountain"] * 2 + ["Steam Vents"] * 2
    + ["Raugrin Triome"] * 3 + ["Clifftop Retreat"] * 3 + ["Glacial Fortress"] * 2
    + ["Inspiring Vantage"] * 2 + ["Hidden Courtyard"] * 2 + ["Hidden Volcano"] * 1
    + ["Hidden Cataract"] * 1 + ["Plains"] * 1 + ["Mountain"] * 1
)
deck = lands + ["spell"] * 36
R = {"Sacred Foundry", "Steam Vents", "Raugrin Triome", "Clifftop Retreat",
     "Inspiring Vantage", "Hidden Volcano", "Mountain"}
W = {"Sacred Foundry", "Hallowed Fountain", "Raugrin Triome", "Clifftop Retreat",
     "Inspiring Vantage", "Glacial Fortress", "Hidden Courtyard", "Plains"}
U = {"Hallowed Fountain", "Steam Vents", "Raugrin Triome", "Glacial Fortress", "Hidden Cataract"}

N = 200_000
res = {"t2_rw": 0, "t4_u": 0, "t5_land5_rw": 0, "t6_u_and_rw": 0, "mull": 0}
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
    if any(c in R for c in t2) and any(c in W for c in t2):
        res["t2_rw"] += 1
    if any(c in U for c in seen(4)):
        res["t4_u"] += 1
    t5 = seen(5)
    if len(t5) >= 5 and any(c in R for c in t5) and any(c in W for c in t5):
        res["t5_land5_rw"] += 1
    t6 = seen(6)
    if any(c in U for c in t6) and any(c in R for c in t6) and any(c in W for c in t6):
        res["t6_u_and_rw"] += 1

for k, v in res.items():
    print(f"{k}: {v / N:.2%}")
