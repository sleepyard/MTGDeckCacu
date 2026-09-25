#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每包产出点数表：以「1 张普通野卡 = 10 点」为基准，把开一包的所有产出折算成点。

★ 关键概念
  · 1 包 = 1000 金 = 200 宝石
  · 野卡侧（可定向，决定造价） vs 实牌侧（随机，不可定向）
  · 四条线（普通/非普通/稀有/秘稀）**并行积累**，所以造价 = max(各线)，不是相加
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json, os

COMMON_POINTS = 10.0        # 基准：1 张普通野卡 = 10 点

# ── 产出率（每包期望张数），推导见 data/mtga_economy.md ──
G = 0.1                     # 每包推进 1/10 个金色包
SUB = {'common': 1/3., 'uncommon': 1/5., 'rare': 1/30., 'mythic': 1/30.}   # 包内替换为野卡
SUPPLY = {
    'common':   SUB['common'],                                  # 仅包内替换
    'uncommon': (1/6.) * (1 + G) + SUB['uncommon'],             # 进度轮 + 替换（+金色包推进）
    'rare':     (4/30.) * (1 + G) + SUB['rare'],
    'mythic':   (1/30.) * (1 + G) + SUB['mythic'],
}
RARE_UPGRADE = 7.0          # 稀有槽升秘稀（标准多数系列 1:7）
GOLD_UPGRADE = 7.1          # 金色包内稀有升秘稀
GOLDEN_CARDS = 6.0          # 每个金色包 6 张标准稀有/秘稀
VAULT_PTS_C, VAULT_PTS_U = 1, 3      # 重复牌转金库：普通 1 点、非普通 3 点
VAULT_FULL = 1000           # 满 1000 → 1 秘稀 + 2 稀有 + 3 非普通野卡

LB = {'common': '普通', 'uncommon': '非普通', 'rare': '稀有', 'mythic': '秘稀'}

# ── 点值：按「获取成本（包数）」反比定价，基准 = 普通野卡 10 点 ──
NEED_PACKS = {r: 1.0 / SUPPLY[r] for r in SUPPLY}
POINT_PER_PACK = COMMON_POINTS / NEED_PACKS['common']          # 10 / 3 = 3.3333
VALUE = {r: NEED_PACKS[r] * POINT_PER_PACK for r in SUPPLY}

# ── 实牌产出 ──
SOLID = {}
SOLID['common'] = 5 - SUB['common']                            # 5 个普通槽，其中 1 张可能变野卡
SOLID['uncommon'] = 2 - SUB['uncommon']                        # 2 个非普通槽
rest = 1.0 - SUB['rare'] - SUB['mythic']                       # 稀有槽 1 张，扣除变野卡的部分
SOLID['rare'] = rest * (1 - 1/RARE_UPGRADE)
SOLID['mythic'] = rest * (1/RARE_UPGRADE)
# 金色包（每 10 包 1 个）
gp = G * GOLDEN_CARDS
gold_m = G * (1 + (GOLDEN_CARDS - 1) / GOLD_UPGRADE)           # 保底 1 张秘稀 + 其余按 1:7.1 升
gold_r = G * (GOLDEN_CARDS - 1) * (1 - 1/GOLD_UPGRADE)
SOLID['rare'] += gold_r
SOLID['mythic'] += gold_m

# ── 金库长期红利（重复牌转野卡）──
VAULT_VALUE = VAULT_PTS_C * 5 + VAULT_PTS_U * 2                # 每包溢出的普通/非普通 ≈ 5C+2U → 11 点
VAULT_REWARD = VALUE['mythic'] + 2 * VALUE['rare'] + 3 * VALUE['uncommon']
VAULT_PER_PACK = VAULT_VALUE / VAULT_FULL * VAULT_REWARD


PACK_POINTS = 100.0         # ★ 归一化基准：1 包 = 100 点


def cards_per_pack():
    print('=' * 74)
    print('开一包到底产出多少「牌」？（1 包 = 1000 金）')
    print('=' * 74)
    inpack_wc = {'common': SUB['common'], 'uncommon': SUB['uncommon'],
                 'rare': SUB['rare'], 'mythic': SUB['mythic']}
    inpack_real = {
        'common': 5 - SUB['common'],
        'uncommon': 2 - SUB['uncommon'],
        'rare': (1 - SUB['rare'] - SUB['mythic']) * (1 - 1/RARE_UPGRADE),
        'mythic': (1 - SUB['rare'] - SUB['mythic']) * (1/RARE_UPGRADE),
    }
    # 进度轮野卡 = 基础（非普通 1/6、稀有 4/30、秘稀 1/30）＋ 金色包推进的 10%
    track = {
        'uncommon': (1/6.) * (1 + G), 'rare': (4/30.) * (1 + G), 'mythic': (1/30.) * (1 + G),
    }
    gold_real = {'rare': G * (GOLDEN_CARDS - (1 + (GOLDEN_CARDS - 1) / GOLD_UPGRADE)),
                 'mythic': G * (1 + (GOLDEN_CARDS - 1) / GOLD_UPGRADE)}
    print('【包内 8 个卡位】5 普通 + 2 非普通 + 1 稀有/秘稀')
    tot_real = sum(inpack_real.values()) + sum(gold_real.values())
    tot_wc = sum(inpack_wc.values()) + sum(track.values())
    print('%-10s %10s %10s %10s %10s' % ('', '包内实牌', '包内野卡', '进度轮野卡', '金色包实牌'))
    for r in ['common', 'uncommon', 'rare', 'mythic']:
        print('%-10s %10.4f %10.4f %10.4f %10.4f'
              % (LB[r], inpack_real[r], inpack_wc[r], track.get(r, 0), gold_real.get(r, 0)))
    print('%-10s %10.4f %10.4f %10.4f %10.4f' % ('合计', sum(inpack_real.values()),
          sum(inpack_wc.values()), sum(track.values()), sum(gold_real.values())))
    print()
    print('  ⇒ **实牌 %.2f 张 + 野卡 %.4f 张 = %.2f 张/包**' % (tot_real, tot_wc, tot_real + tot_wc))
    print('     拆解：实牌 = 包内 %.2f ＋ 金色包折算 %.2f ｜ 野卡 = 包内替换 %.2f ＋ 进度轮 %.4f'
          % (sum(inpack_real.values()), sum(gold_real.values()), sum(inpack_wc.values()), sum(track.values())))
    print('     ⚠ 野卡会**顶替**同稀有度卡位（不进 8 张之外的额外位置），所以是"8 张里有 0.6 张是野卡"')
    print('     ⚠ 进度轮的 %.3f 张野卡是**额外白给**的，不在 8 张之内' % sum(track.values()))
    return tot_real, tot_wc


def normalized():
    print()
    print('=' * 74)
    print('★ 归一化定价：1 包 = %.0f 点' % PACK_POINTS)
    print('=' * 74)
    print('公式：单张点数 = %.0f ÷ 该牌每包产出张数' % PACK_POINTS)
    print()
    print('%-8s %12s %12s %14s %12s' % ('稀有度', '每包产出', '单张点数', '等价金币', '需要几包'))
    val = {}
    for r in ['common', 'uncommon', 'rare', 'mythic']:
        val[r] = PACK_POINTS / SUPPLY[r]
        print('%-8s %12.4f %12.1f %14.0f %12.2f'
              % (LB[r], SUPPLY[r], val[r], val[r] * 10, 1.0 / SUPPLY[r]))
    print()
    print('  校验：1 点 = %.0f 金（因为 1 包 = 1000 金 = 100 点）' % (1000.0 / PACK_POINTS))
    print('  校验：稀有 %d 张 = %.0f 点 = %.1f 包 ✓' % (4, 4*val['rare'], 4*val['rare']/PACK_POINTS))
    print('  校验：1 张秘稀 = %.0f 点 = %.2f 包 ✓' % (val['mythic'], val['mythic']/PACK_POINTS))

    print()
    print('【一包产出折算成点数】')
    print('%-10s %10s %12s %12s | %10s %12s' % ('稀有度', '野卡张数', '野卡点数', '', '实牌张数', '实牌点数'))
    wc_tot = solid_tot = 0
    inpack_real = {'common': 5 - SUB['common'], 'uncommon': 2 - SUB['uncommon'],
                   'rare': (1 - SUB['rare'] - SUB['mythic']) * (1 - 1/RARE_UPGRADE),
                   'mythic': (1 - SUB['rare'] - SUB['mythic']) * (1/RARE_UPGRADE)}
    gold_real = {'rare': G * (GOLDEN_CARDS - (1 + (GOLDEN_CARDS - 1) / GOLD_UPGRADE)),
                 'mythic': G * (1 + (GOLDEN_CARDS - 1) / GOLD_UPGRADE)}
    for r in ['common', 'uncommon', 'rare', 'mythic']:
        w = SUPPLY[r] * val[r]
        s = (inpack_real[r] + gold_real.get(r, 0)) * val[r]
        wc_tot += w; solid_tot += s
        print('%-10s %10.3f %12.0f %12s | %10.3f %12.0f' % (LB[r], SUPPLY[r], w, '', inpack_real[r] + gold_real.get(r, 0), s))
    print('%-10s %10s %12.0f %12s | %10s %12.0f' % ('合计', '', wc_tot, '', '', solid_tot))
    print()
    print('  野卡侧：**%.0f 点/包** —— 四条线各 %.0f 点（**分属四条不可互换的线**）' % (wc_tot, wc_tot/4))
    print('  实牌侧：%.0f 点/包（**面值口径，不可定向**）' % solid_tot)
    print('  ⚠ 实牌面值不可用于造价：实测为指定牌表开包，命中率仅 5.6%')
    print('     ⇒ 实牌「可用价值」≈ %.0f 点/包（而非 %.0f）' % (solid_tot * 0.056, solid_tot))
    print('  金库长期红利：%.1f 点/包' % (VAULT_PER_PACK / POINT_PER_PACK * PACK_POINTS))


def main():
    print('=' * 74)
    print('点数定价表（基准：1 张普通野卡 = 10 点）')
    print('=' * 74)
    print('%-8s %12s %12s %14s' % ('稀有度', '每张需包数', '单张点值', '1 张 = 几包'))
    for r in ['common', 'uncommon', 'rare', 'mythic']:
        print('%-8s %12.2f %12.2f %14s' % (LB[r], NEED_PACKS[r], VALUE[r], '%.2f 包' % NEED_PACKS[r]))
    print()
    print('⇒ 隐含汇率：**1 包 = %.2f 点**（＝10 点 ÷ 3 包）' % POINT_PER_PACK)
    print('⇒ 反查：%d 张普通 = %.0f 点 = %.2f 包 ✓' % (10, 10*VALUE['common'], 10*NEED_PACKS['common']))

    print()
    print('=' * 74)
    print('★ 每开一包（1000 金）的产出明细')
    print('=' * 74)
    print()
    print('【A. 野卡侧】—— 可定向，决定造价')
    print('%-10s %12s %12s %12s' % ('产出项', '每包张数', '单张点值', '每包点数'))
    tw = 0
    for r in ['common', 'uncommon', 'rare', 'mythic']:
        p = SUPPLY[r] * VALUE[r]
        tw += p
        print('%-10s %12.4f %12.2f %12.2f' % (LB[r] + '野卡', SUPPLY[r], VALUE[r], p))
    print('%-10s %12s %12s %12.2f' % ('小计', '', '', tw))

    print()
    print('【B. 实牌侧】—— 随机，不可定向（面值口径）')
    print('%-10s %12s %12s %12s' % ('产出项', '每包张数', '单张点值', '每包点数'))
    ts = 0
    for r in ['common', 'uncommon', 'rare', 'mythic']:
        p = SOLID[r] * VALUE[r]
        ts += p
        print('%-10s %12.4f %12.2f %12.2f' % (LB[r] + '实牌', SOLID[r], VALUE[r], p))
    print('%-10s %12.4f %12s %12.2f' % ('小计', sum(SOLID.values()), '', ts))

    print()
    print('【C. 金库长期红利】（重复牌转野卡，长期稳态）')
    print('   每包溢出约 5 普通 + 2 非普通 = %d 金库点 → 满 1000 点给 1 秘稀 + 2 稀有 + 3 非普通野卡' % VAULT_VALUE)
    print('   = %.2f 点/包' % VAULT_PER_PACK)
    print()
    print('-' * 74)
    print('合计：野卡 %.2f ＋ 实牌 %.2f ＋ 金库 %.2f = **%.2f 点/包**' % (tw, ts, VAULT_PER_PACK, tw+ts+VAULT_PER_PACK))
    print('纯可定向（野卡＋金库）：**%.2f 点/包**' % (tw + VAULT_PER_PACK))

    print()
    print('=' * 74)
    print('★★ 自洽性：四条线每包产出的点数**完全相等**')
    print('=' * 74)
    for r in ['common', 'uncommon', 'rare', 'mythic']:
        print('   %-6s 线：%.4f 张/包 × %.2f 点 = %.4f 点/包' % (LB[r], SUPPLY[r], VALUE[r], SUPPLY[r]*VALUE[r]))
    print()
    print('   ⇒ 这就是「造价 = max(各线) 而不是相加」的数学基础：')
    print('     四条线等价地产出，你只能被其中最慢的那条卡住。')
    print('     每包对每条线的贡献都是 **%.2f 点**。' % (tw/4))

    print()
    print('=' * 74)
    print('★ 用法：一副牌要多少包？（分线计，取 max）')
    print('=' * 74)
    print('  公式：某线所需包数 = 该线张数 × 单张点值 ÷ %.2f' % (tw/4))
    print()
    cases = [('4 张稀有', 'rare', 4), ('1 张秘稀', 'mythic', 1),
             ('11.5 张非普通', 'uncommon', 11.5), ('6.6 张普通', 'common', 6.6)]
    for lb, r, q in cases:
        pp = q * VALUE[r] / (tw/4)
        print('   %-14s → %6.2f 包  （%.0f 点）' % (lb, pp, q*VALUE[r]))

    print()
    print('  「4 金」牌表（4 稀有 + 0 秘稀）：')
    core = 4 * VALUE['rare'] / (tw/4)
    print('    PP核心 = ceil(4 × %.2f 点 ÷ %.2f 点/包) = %.1f 包 = %.0f 点' % (VALUE['rare'], tw/4, core, 4*VALUE['rare']))
    print('    同理：含 1 秘稀 %.1f 包｜含 2 秘稀 %.1f 包' %
          ((3*VALUE['rare']+VALUE['mythic'])/(tw/4), (2*VALUE['rare']+2*VALUE['mythic'])/(tw/4)))

    print()
    print('=' * 74)
    print('⚠ 使用注意')
    print('=' * 74)
    print('1. 实牌侧面值 %.0f 点看着大，但**不可定向**：实测为指定牌表开包，' % ts)
    print('   16 张目标稀有/秘稀自然命中仅 0.9 张（≈ 5.6%%）⇒ 实牌对"定向构筑"的实际价值 ≈ %.1f 点/包。'
          % (ts * 0.056))
    print('2. 点数**不能跨线兑换**：秘稀线的产出不能拿去换稀有野卡。')
    print('   ⇒ 造价必须分线算 max()，点数只用于同线内比较与"物质总量"衡量。')
    print('3. 金库红利是**长期稳态**值；新手前几副（还没堆够重复牌）应按 0 计。')


if __name__ == '__main__':
    cards_per_pack()
    main()
    normalized()
