# -*- coding: utf-8 -*-
# Simic Flash V1 法术力超几何校验（仅用标准库 math.comb）
# 母体：60 张主牌
# 地牌卡位：24（23 真地 + 1 树渠通路 MDFC；爪尔干扰 x2 记为咒语/紧急地源，不计入）
# 绿源 21：滋生之池4 + 植物圣所4 + 内陆港湾4 + 亚维马雅海岸4 + 树林3 + 历祚母圣树1 + 树渠通路1(MDFC, 进场横置)
# 蓝源 20：滋生之池4 + 植物圣所4 + 内陆港湾4 + 亚维马雅海岸4 + 海岛2 + 霄城大田原1 + 树渠通路1(MDFC)
# 严格未横置口径另算（排除通路，港湾需有树林/海岛类别地在场——滋生之池具基本地类别可解锁）

from math import comb

N = 60

def p_at_least(k, K, n, N=N):
    """超几何：n 张抽样中命中 K 类至少 k 张的概率"""
    return sum(comb(K, i) * comb(N - K, n - i) for i in range(k, min(K, n) + 1)) / comb(N, n)

def p_gguu(n, dual=17, g_only=4, u_only=3, other=36, N=N):
    """T4 前凑齐 GGUU 施放褶领秘教徒：需 >=2 绿源、>=2 蓝源、总地 >=4。
    双色地 17（16 真双色 + 树渠通路），纯绿 4（树林3+母圣树1），纯蓝 3（海岛2+大田原1），其他 36。"""
    total = comb(N, n)
    ok = 0
    for d in range(dual + 1):
        for g in range(g_only + 1):
            for u in range(u_only + 1):
                o = n - d - g - u
                if o < 0 or o > other:
                    continue
                if d + g >= 2 and d + u >= 2 and d + g + u >= 4:
                    ok += comb(dual, d) * comb(g_only, g) * comb(u_only, u) * comb(other, o)
    return ok / total

def fmt(p):
    return f"{p*100:.2f}%"

print("== Simic Flash V1 mana check (deck=60) ==")
print()

# 1. 起手 7 张 >=2 地牌卡位（24 地）
print(f"起手>=2地(24地牌卡位): {fmt(p_at_least(2, 24, 7))}")
print(f"起手>=3地:             {fmt(p_at_least(3, 24, 7))}")
print(f"起手<=1地(建议调度):   {fmt(1 - p_at_least(2, 24, 7))}")
print(f"T3前(看9张, 先手)>=3地: {fmt(p_at_least(3, 24, 9))}")
print()

# 2. T3 前凑齐 GG（夜群袭狼 {2}{G}{G}）：绿源 21（含通路）/ 20（不含）
print(f"T3前GG 先手(看9张, 绿源21含通路): {fmt(p_at_least(2, 21, 9))}")
print(f"T3前GG 后手(看10张):              {fmt(p_at_least(2, 21, 10))}")
print(f"T3前GG 先手(绿源20不含通路):      {fmt(p_at_least(2, 20, 9))}")
print()

# 3. T3 前凑齐 UU（厚颜借物灵 {1}{U}{U}）：蓝源 20（含通路）/ 19（不含）
print(f"T3前UU 先手(看9张, 蓝源20含通路): {fmt(p_at_least(2, 20, 9))}")
print(f"T3前UU 先手(蓝源19不含通路):      {fmt(p_at_least(2, 19, 9))}")
print()

# 4. T4 前凑齐 GGUU（褶领秘教徒 {G}{G}{U}{U}，需总地>=4）
print(f"T4前GGUU 先手(看10张): {fmt(p_gguu(10))}")
print(f"T4前GGUU 后手(看11张): {fmt(p_gguu(11))}")
print()

# 5. 起手有 1 费闪现生物（魂魅船员 x4）
p_sailor = 1 - comb(56, 7) / comb(60, 7)
print(f"起手有魂魅船员(x4): {fmt(p_sailor)}")
# 起手有任一 <=2 费闪现生物（船员4+割喉客4+保卫者4 = 12）
print(f"起手有<=2费闪现生物(12张): {fmt(1 - comb(48, 7) / comb(60, 7))}")
print()

# 6. 留牌阈值辅助：起手 2 地 + 至少 1 绿源 的概率（2地手能否出保卫者/涡旋）
# 简化：起手>=2地 且 >=1绿源（绿源21）
tot = comb(60, 7)
ok = 0
for lands in range(2, 8):
    for g in range(1, min(lands, 21) + 1):
        ng = lands - g
        if ng <= 3 and 7 - lands <= 36:
            ok += comb(21, g) * comb(3, ng) * comb(36, 7 - lands)
# 上式把地拆成绿源/非绿地不对（双色地既是绿也是地），改用直接口径：
# 绿源21中其余39为非绿源(含3纯蓝? 不, 纯蓝地是地)。重做：类别 绿源地21 / 非绿源的地3 / 非地36
ok = 0
for gl in range(0, 22):
    for nl in range(0, 4):
        for x in range(0, 37):
            if gl + nl + x != 7:
                continue
            if gl + nl >= 2 and gl >= 1:
                ok += comb(21, gl) * comb(3, nl) * comb(36, x)
print(f"起手>=2地且>=1绿源: {fmt(ok / tot)}")
