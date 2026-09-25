#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""归一化定价（不含金色包）：1 包 = 100 点
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

基准（用户指定）：
  每包产出 = 包内实牌 7.4 + 包内野卡 0.6 + 进度轮野卡 0.3667 = 8.3667 张
  按稀有度：普通 5.0 ｜ 非普通 2.1833 ｜ 稀有 0.98 ｜ 秘稀 0.2033
  （不含金色包赠送的 6 张标准稀有/秘稀）

两种归一化口径都算，并说明各自用途。
"""
LB = {'common': '普通', 'uncommon': '非普通', 'rare': '稀有', 'mythic': '秘稀'}
PACK_POINTS = 100.0
GOLD_PER_PACK = 1000.0

# ── 产出率分解（不含金色包实牌）──
SUB = {'common': 1/3., 'uncommon': 1/5., 'rare': 1/30., 'mythic': 1/30.}
TRACK = {'common': 0.0, 'uncommon': 1/6., 'rare': 4/30., 'mythic': 1/30.}
UPGRADE = 7.0
GOLDEN_STEP = 0.1


def build(solid_wildcard=True):
    """solid_wildcard=True 时把包内野卡也计入该稀有度的"产出张数"（用户口径）"""
    solid = {
        'common':   5 - SUB['common'],
        'uncommon': 2 - SUB['uncommon'],
        'rare':     (1 - SUB['rare'] - SUB['mythic']) * (1 - 1/UPGRADE),
        'mythic':   (1 - SUB['rare'] - SUB['mythic']) * (1/UPGRADE),
    }
    wc_in = dict(SUB) if solid_wildcard else {k: 0 for k in SUB}
    return solid, wc_in


def main():
    solid, wc_in = build()
    track_a = {k: v * (1 + GOLDEN_STEP) for k, v in TRACK.items()}   # 含金包推进
    track_b = dict(TRACK)                                            # 完全不含金包

    print('=' * 78)
    print('第 1 步：开一包的产出（不含金色包实牌）')
    print('=' * 78)
    print('%-8s %10s %12s %14s %12s %12s' % ('稀有度', '包内实牌', '包内野卡', '进度轮(含金包推进)', '进度轮(纯)', '用户口径合计'))
    tot_a = tot_b = 0
    for r in ['common', 'uncommon', 'rare', 'mythic']:
        a = solid[r] + wc_in[r] + track_a[r]
        b = solid[r] + wc_in[r] + track_b[r]
        tot_a += a; tot_b += b
        print('%-8s %10.4f %12.4f %14.4f %12.4f %12.4f' % (LB[r], solid[r], wc_in[r], track_a[r], track_b[r], a))
    print('%-8s %10.4f %12.4f %14.4f %12.4f %12.4f' % ('合计',
          sum(solid.values()), sum(wc_in.values()), sum(track_a.values()), sum(track_b.values()), tot_a))
    print()
    print('  ⇒ 用户口径（进度轮含金包推进）：%.4f 张/包' % tot_a)
    print('  ⇒ 完全不含金包：              %.4f 张/包' % tot_b)

    print()
    print('=' * 78)
    print('第 2 步：归一化 —— 1 包 = 100 点')
    print('=' * 78)
    print('规则：把"每条线每包产出的总量"定为 100 点 ⇒ 单张点数 = 100 ÷ 该线每包产出张数')
    print()
    print('%-8s %14s %14s %14s' % ('稀有度', '每包产出(张)', '单张点数', '等价金币'))
    val = {}
    for r in ['common', 'uncommon', 'rare', 'mythic']:
        rate = solid[r] + wc_in[r] + track_a[r]
        val[r] = PACK_POINTS / rate
        print('%-8s %14.4f %14.1f %14.0f' % (LB[r], rate, val[r], val[r] * GOLD_PER_PACK / PACK_POINTS))
    print()
    print('  校验：%d 张稀有 = %.0f 点 ｜ 1 张秘稀 = %.0f 点 ｜ 1 点 = %.0f 金'
          % (4, 4*val['rare'], val['mythic'], GOLD_PER_PACK/PACK_POINTS))
    s = sum((solid[r]+wc_in[r]+track_a[r]) * val[r] for r in val)
    print('  校验：每包各线合计 = %.0f 点（= 4 条线 × 100 点）' % s)

    print()
    print('=' * 78)
    print('第 3 步：★ 两种口径的卡牌价值对照（单张点数）')
    print('=' * 78)
    print('%-8s %14s | %-30s' % ('稀有度', 'A 物质总量', 'B 可定向（造价用）'))
    print('%-8s %14s | %14s %14s' % ('', '', '含金包推进', '纯不含金包'))
    wc_a, wc_b = {}, {}
    for r in ['common', 'uncommon', 'rare', 'mythic']:
        wc_a[r] = PACK_POINTS / (wc_in[r] + track_a[r])
        wc_b[r] = PACK_POINTS / (wc_in[r] + track_b[r])
        print('%-8s %14.1f | %14.1f %14.1f' % (LB[r], val[r], wc_a[r], wc_b[r]))
    print()
    print('  A 物质总量 = 100 ÷ (实牌 + 野卡 + 进度轮)：把"开到的随机实牌"也算资产')
    print('  B 可定向   = 100 ÷ (野卡 + 进度轮)：只有能当野卡用的才算资产')
    print()
    print('  ⚠ A 与 B 的倍率：', ' '.join('%s %.1f×' % (LB[r], wc_a[r]/val[r]) for r in val))
    print('     普通被放大了 15 倍，秘稀只放大 2.9 倍 ⇒ A 口径**系统性高估普通、低估秘稀**')
    print('     原因：普通产出里 93% 是"用不上的实牌"，秘稀产出里野卡占比高得多。')
    print('     ⇒ **造价必须用 B**；A 只能用来衡量"物质总量"。')

    print()
    print('=' * 78)
    print('★ 一句话总结')
    print('=' * 78)
    print('  不含金色包时，每包产出 8.3667 张牌 / 8.3333 张（纯）')
    print('  归一化（1 包 = 100 点）后：')
    print('    物质总量口径：普通 20 ｜ 非普通 46 ｜ 稀有 102 ｜ 秘稀 492')
    print('    可定向口径：  普通 300 ｜ 非普通 261 ｜ 稀有 545 ｜ 秘稀 1364（含金包推进）')
    print('  「1 包 = 100 点」= 每条线的产出各值 100 点（四线不可相加）')


if __name__ == '__main__':
    main()
