#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""归一化（二次）：以「1 张普通 = 1 点」为基准的相对造价表。
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

第一次归一化：1 包 = 100 点（每条线各 100 点）
第二次归一化：把 1 张普通定为 1 点 ⇒ 等价于把第一次的结果 ÷ 20（因为普通每包产出 5.0000 张）
              ⇒ 1 包 = 20 点（每条线各 5 点）

★ 不折算金币，纯粹的相对造价单位。
分 A/B 两种口径（A 含随机实牌；B 只含可定向的野卡+进度轮）。
"""
PACK = 100.0                    # 第一次归一化的基准
COMMON_PER_PACK = 5.0           # 普通每包产出张数
SCALE = PACK / COMMON_PER_PACK  # = 20 ⇒ 1 张普通 = 1 点

LB = {'common': '普通', 'uncommon': '非普通', 'rare': '稀有', 'mythic': '秘稀'}
# 每包产出（张），基准 A（不含金色包赠送，含金包对进度轮的推进）
OUT_A = {'common': 5.0000, 'uncommon': 2.1833, 'rare': 0.9800, 'mythic': 0.2033}
# 可定向部分（野卡 + 进度轮）
OUT_B = {'common': 5.0000 - 4.6667, 'uncommon': 2.1833 - 1.8000,
         'rare': 0.9800 - 0.8000, 'mythic': 0.2033 - 0.1333}


def main():
    print('=' * 74)
    print('二次归一化：1 张普通 = 1 点')
    print('=' * 74)
    print('推导：第一次归一化已把「每条线每包产出」定为 100 点；')
    print('      普通每包产出 5.0000 张 ⇒ 1 张普通 = 100 ÷ 5 = 20 点（第一次口径）')
    print('      现把 1 张普通重新定为 1 点 ⇒ 全部数值 ÷ %.0f' % SCALE)
    print('      ⇒ 1 包对**每条线各**贡献 5.0 点（四线并行，合计 20 点但**不可相加**）')
    print()

    A = {r: (PACK / OUT_A[r]) / SCALE for r in OUT_A}
    B = {r: (PACK / OUT_B[r]) / SCALE for r in OUT_B}

    print('-' * 74)
    print('【A 物质总量口径】分母 = 实牌 + 野卡 + 进度轮')
    print('（把"开到的随机实牌"也算进产出）')
    print('-' * 74)
    print('%-8s %14s %14s %16s' % ('稀有度', '每包产出(张)', '点/张', '相对普通'))
    for r in ['common', 'uncommon', 'rare', 'mythic']:
        print('%-8s %14.4f %14.3f %15.2f×' % (LB[r], OUT_A[r], A[r], A[r] / A['common']))
    print('  每包产出点数 = %.1f 点/线（四线各 %.1f，合计 %.0f 点，**不可相加**）'
          % (A['common'] * OUT_A['common'], A['common'] * OUT_A['common'], 4 * A['common'] * OUT_A['common']))

    print()
    print('-' * 74)
    print('【B 可定向口径】分母 = 野卡 + 进度轮  ★造价用这一栏')
    print('（只算能当野卡用的部分；随机实牌不计）')
    print('-' * 74)
    print('%-8s %14s %14s %16s' % ('稀有度', '可定向产出(张)', '点/张', '相对普通'))
    for r in ['common', 'uncommon', 'rare', 'mythic']:
        print('%-8s %14.4f %14.3f %15.2f×' % (LB[r], OUT_B[r], B[r], B[r] / B['common']))
    print('  每包可定向产出 = %.1f 点/线（四线各 %.1f）'
          % (B['common'] * OUT_B['common'], B['common'] * OUT_B['common']))

    print()
    print('=' * 74)
    print('★ 速查（B 可定向口径，1 普通 = 1 点）')
    print('=' * 74)
    for r in ['common', 'uncommon', 'rare', 'mythic']:
        print('  %-8s %6.3f 点/张' % (LB[r], B[r]))
    print()
    print('  含义：1 张普通野卡 = 1 点；1 张稀有野卡 ≈ %.2f 张普通；1 张秘稀野卡 ≈ %.2f 张普通'
          % (B['rare'] / B['common'], B['mythic'] / B['common']))
    print('  ⚠ 1 张非普通野卡 = %.2f 点 —— **比普通还便宜**（非普通野卡产量反而更高）'
          % (B['uncommon'] / B['common']))

    print()
    print('=' * 74)
    print('★ 造价应用（B 口径）')
    print('=' * 74)
    print('%-18s %14s %14s' % ('需要', '点数', '≈ 几张普通'))
    for lb, r, q in [('4 张稀有', 'rare', 4), ('1 张秘稀', 'mythic', 1),
                     ('11.5 张非普通', 'uncommon', 11.5), ('6.6 张普通', 'common', 6.6)]:
        p = q * B[r]
        print('%-18s %14.1f %14.1f' % (lb, p, p / B['common']))

    print()
    print('  「4 金」牌表（4 稀有）= %.1f 点 = %.1f 张普通的等值' % (4*B['rare'], 4*B['rare']/B['common']))
    print()
    print('=' * 74)
    print('⚠ 两种口径不可混用')
    print('=' * 74)
    print('  A 口径会说"1 张稀有 = %.1f 张普通"，B 口径说"%.1f 张"——差 %.1f 倍。'
          % (A['rare']/A['common'], B['rare']/B['common'], (A['rare']/A['common'])/(B['rare']/B['common'])))
    print('  原因：A 里普通产出 93% 是"用不上的随机实牌"，被当成了资产。')
    print('  ⇒ **衡构造价只用 B**；A 只用于衡量"一包的物质总量"。')


if __name__ == '__main__':
    main()
