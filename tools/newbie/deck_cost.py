#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""套牌造价签名与多口径核算（纯 MTGA）

★ 造价签名（cost signature）= 逐稀有度的耗野卡张数，形如：
      4m12r11u13c
   读作：4 张秘稀、12 张稀有、11 张非普通、13 张普通
   · 从稀到常排列（m r u c），数量为 0 的项省略
   · **基本地不计**（免费）；非基本地按自身稀有度计入
   · **★ 签名是可加的**：多副牌的签名逐项相加 = 总账单

用法:
  python3 deck_cost.py sig  <牌表文件…>       # 出签名 + 全部口径
  python3 deck_cost.py sum  <牌表文件…>       # 多副相加，给系列总账单
  python3 deck_cost.py parse 4m12r11u13c     # 直接解析签名

稀有度数据：默认读 tools/data/rarity_map.json（标准牌池快照）；快照外的牌
（如 Explorer 池）自动回退 Scryfall 按名检索，取最新 Arena 印刷的稀有度
（走 mtg_tool 磁盘缓存与节流；回退也查不到才计入"未识别"）。
设 DECK_COST_NO_FALLBACK=1 可关闭回退（纯快照口径）。

口径（点值见 data/mtga_economy.md §四；四档口径取 ④ 1普通=1点）:
  A 物质总量 = 实牌+野卡+进度轮 的产出归一化   → 衡量"物质"
  B 可定向   = 野卡+进度轮 的产出归一化        → ★ 衡量造价
  两者都**可逐线相加**；但"需要开多少包"必须取 max（四条线不可互换）
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, '..', 'data'))
M = json.load(open(os.path.join(DATA, 'rarity_map.json'), encoding='utf-8'))

sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..')))
from deck_model import parse_deck as _parse_deck

# ── 产出模型（不含金色包赠送；进度轮 ×1.1 计入金色包对野卡轨的推进）──
SUB = {'common': 1/3., 'uncommon': 1/5., 'rare': 1/30., 'mythic': 1/30.}
UPGRADE = 7.0
SOLID = {
    'common':   5 - SUB['common'],
    'uncommon': 2 - SUB['uncommon'],
    'rare':     (1 - SUB['rare'] - SUB['mythic']) * (1 - 1/UPGRADE),
    'mythic':   (1 - SUB['rare'] - SUB['mythic']) * (1/UPGRADE),
}
TRACK = {'common': 0.0, 'uncommon': (1/6.)*1.1, 'rare': (4/30.)*1.1, 'mythic': (1/30.)*1.1}
OUT_A = {k: SOLID[k] + SUB[k] + TRACK[k] for k in SUB}          # 物质总量
OUT_B = {k: SUB[k] + TRACK[k] for k in SUB}                     # 可定向

# 归一化标度：把「每条线每包的**可定向**产出」定为 N 点
#   5.0  → 普通 15.00 点（当前 ④ 口径；锚定"物质口径下普通=1点"）
#   OUT_B['common'] = 0.3333 → 严格「1 张普通 = 1 点」（B 口径锚定）
# 三种等价标度（只差一个常数倍，PP 完全不受影响）：
#   'line5'   标度 5.0     → 物质A 普通=1.00（= 用户最初"1普通=1点"的锚点）；可定向B 普通=15.00
#   'pack1'   标度 1.0     → 点数 = 需要几包（最直观）
#   'b_common1' 标度 1/3   → **可定向B 普通=1.00**（"1 普通 = 1 点"落在造价口径上）
_UNITS = {'each1': None,      # ★默认：A 与 B 各自以「1 张普通 = 1 点」归一化
          'line5': 5.0, 'pack1': 1.0, 'b_common1': 1/3.}
UNIT = os.environ.get('UNIT', 'each1')
if UNIT == 'each1':
    SCALE_A = OUT_A['common']      # 5.0000  → 物质A 普通 = 1.00
    SCALE_B = OUT_B['common']      # 0.3333  → 可定向B 普通 = 1.00
else:
    SCALE_A = SCALE_B = _UNITS[UNIT]
PTS_PER_LINE = SCALE_B             # 每包对每条线贡献的点数（以 B 标度计）
VAL_A = {k: SCALE_A / OUT_A[k] for k in SUB}                     # 点/张（物质，A 标度）
VAL_B = {k: SCALE_B / OUT_B[k] for k in SUB}                     # 点/张（可定向，B 标度）
ORDER = ['mythic', 'rare', 'uncommon', 'common']
TAG = {'mythic': 'm', 'rare': 'r', 'uncommon': 'u', 'common': 'c'}
LB = {'mythic': '秘稀', 'rare': '稀有', 'uncommon': '非普通', 'common': '普通'}

_PFX = None


def look(name):
    global _PFX
    e = M.get(name)
    if e is not None:
        return e
    if _PFX is None:
        _PFX = {k.split(' // ')[0]: k for k in M if ' // ' in k}
    k = _PFX.get(name)
    return M.get(k) if k else None


_SCRY_CACHE = {}


_RAR_RANK = {'common': 0, 'uncommon': 1, 'rare': 2, 'mythic': 3}


def scryfall_look(name):
    """快照外牌的 Scryfall 回退：按精确名检索全部印刷，在 Arena 印刷中取
    最低稀有度（MTGA 同名共享收藏、各版本可分别合成，最低版本即真实野卡成本；
    升罕重印不会抬高造价），并取对应 type_line / 基本地判定
    （走 mtg_tool 磁盘缓存与节流）。
    查不到或环境不可用时返回 None（调用方按"未识别"处理）。"""
    if os.environ.get('DECK_COST_NO_FALLBACK'):
        return None
    if name in _SCRY_CACHE:
        return _SCRY_CACHE[name]
    entry = None
    try:
        sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..')))
        import mtg_tool
        cards, _total, _warn = mtg_tool.scryfall_search('!"%s"' % name.replace('"', ''),
                                                        unique='prints')
        arena = [c for c in cards if 'arena' in (c.get('games') or [])]
        if arena:
            c = min(arena, key=lambda x: (_RAR_RANK.get(x.get('rarity'), 0),
                                          x.get('released_at') or ''))
            entry = {'rarity': c.get('rarity', 'common'),
                     'basic': (c.get('type_line') or '').startswith('Basic Land'),
                     'type_line': c.get('type_line') or ''}
    except Exception:
        entry = None
    _SCRY_CACHE[name] = entry
    return entry


def parse_deck(path):
    """薄委托：deck_model.parse_deck → 扁平 [(qty, name, section)]。

    ★ Phase 1 起元素顺序统一为 (qty, name, section)（旧实现是反序的
    (name, qty, section)，消费方 census 已同步适配）。"""
    return _parse_deck(path).entries()


def census(pairs):
    """→ (签名dict, 未识别列表, 统计杂项)"""
    sig = {k: 0 for k in ORDER}
    unk, extra = [], {'land': 0, 'basic': 0, 'creature': 0, 'total': 0}
    for q, nm, side in pairs:
        if side != 'main':
            continue
        e = look(nm)
        if e is None:
            e = scryfall_look(nm)
        if e is None:
            unk.append(nm); continue
        extra['total'] += q
        tl = e['type_line'] or ''
        if e['basic']:
            extra['basic'] += q
            continue                       # 基本地免费
        if 'Land' in tl:
            extra['land'] += q
        if 'Creature' in tl:
            extra['creature'] += q
        sig[e['rarity']] = sig.get(e['rarity'], 0) + q
    return sig, unk, extra


def fmt_sig(sig):
    parts = []
    for r in ORDER:
        v = sig.get(r, 0)
        if v:
            parts.append('%d%s' % (v, TAG[r]))
    return ''.join(parts) or '0'


def parse_sig(s):
    sig = {k: 0 for k in ORDER}
    for n, t in re.findall(r'(\d+)\s*([mrucMRUC])', s):
        for r, tag in TAG.items():
            if tag == t.lower():
                sig[r] += int(n)
    return sig


# ★ 物质点预算（用户 2026-09-24 新规则）
#   低造价档 = 4 张稀有 = 4 × 5.10 = 20.4 点
#   放宽上限 = 8 张稀有 = 8 × 5.10 = 40.8 点（可用于"稀有换秘稀"）
BUDGET_LOW = 4 * 5.10      # 20.4
BUDGET_MAX = 8 * 5.10      # 40.8
MYTHIC = 24.59
RARE = 5.10


def budget_check(sig):
    """按物质点检查预算，返回 (是否合规, 档位, 说明)"""
    pts = sig.get('mythic', 0) * MYTHIC + sig.get('rare', 0) * RARE
    m, r = sig.get('mythic', 0), sig.get('rare', 0)
    if pts <= BUDGET_LOW + 1e-6:
        tier = '低造价档'
        ok = True
    elif pts <= BUDGET_MAX + 1e-6:
        tier = '放宽档（需证明比低档更强）'
        ok = True
    else:
        tier = '✗ 超预算'
        ok = False
    return ok, tier, '%d秘稀×%.2f + %d稀有×%.2f = %.2f 点（低档≤%.1f / 上限≤%.1f）' % (
        m, MYTHIC, r, RARE, pts, BUDGET_LOW, BUDGET_MAX)


def metrics(sig):
    a = {r: sig.get(r, 0) * VAL_A[r] for r in ORDER}     # 物质点数（可加）
    b = {r: sig.get(r, 0) * VAL_B[r] for r in ORDER}     # 可定向点数（可加）
    tot_a, tot_b = sum(a.values()), sum(b.values())
    # 需要开多少包：每条线单独算，取 max
    packs_core = max(b['rare'], b['mythic']) / SCALE_B
    packs_all = max(b.values()) / SCALE_B
    fungible = tot_b / (SCALE_B * 4)          # 若四条线可互换（下界）
    penalty = packs_all / fungible if fungible else 0
    return {'a': a, 'b': b, 'tot_a': tot_a, 'tot_b': tot_b,
            'packs_core': packs_core, 'packs_all': packs_all,
            'packs_fungible': fungible, 'penalty': penalty,
            'sum_packs': tot_b / SCALE_B}


def brief(files):
    print('%-30s %-16s %8s %8s %8s %8s %8s %6s %s'
          % ('牌表', '造价签名', 'PP核心', 'PP全量', '点数B', '物质A', '惩罚×', '生物', '瓶颈'))
    tot = {k: 0 for k in ORDER}
    for f in files:
        sig, unk, ex = census(parse_deck(f))
        m = metrics(sig)
        need = {r: m['b'][r] / SCALE_B for r in ORDER}
        bk = max(need, key=lambda r: need[r])
        print('%-30s %-16s %8.1f %8.1f %8.1f %8.1f %8.2f %6d %s'
              % (os.path.basename(f)[:30], fmt_sig(sig), m['packs_core'], m['packs_all'],
                 m['tot_b'], m['tot_a'], m['penalty'], ex['creature'], LB[bk]))
        for k in ORDER:
            tot[k] += sig.get(k, 0)
    if len(files) > 1:
        m = metrics(tot)
        print('-' * 108)
        print('%-30s %-16s %8.1f %8.1f %8.1f %8.1f %8.2f' % ('【合计 %d 副】' % len(files),
              fmt_sig(tot), m['packs_core'], m['packs_all'], m['tot_b'], m['tot_a'], m['penalty']))


def show(sig, title=''):
    m = metrics(sig)
    print('=' * 74)
    if title:
        print(title)
    print('  造价签名  %s' % fmt_sig(sig))
    ok, tier, desc = budget_check(sig)
    print('  物质点预算  %s ｜ %s' % (('✅ ' + tier) if ok else tier, desc))
    print('=' * 74)
    print('%-8s %6s %14s %16s %16s' % ('稀有度', '张数', '点/张(物质)', '点/张(可定向)', '小计(可定向)'))
    for r in ORDER:
        if sig.get(r, 0) == 0 and r != 'rare':
            continue
        print('%-8s %6d %14.2f %16.2f %16.1f'
              % (LB[r], sig.get(r, 0), VAL_A[r], VAL_B[r], m['b'][r]))
    print('-' * 74)
    print('【点数合计（可逐线相加）】')
    print('   物质总量 A = %8.1f 点' % m['tot_a'])
    print('   可定向   B = %8.1f 点' % m['tot_b'])
    print()
    print('【需要开多少包（四条线不可互换 ⇒ 取 max）】')
    print('   PP核心 (max[稀有, 秘稀])          = %6.1f 包' % m['packs_core'])
    print('   PP全量 (含普通/非普通)            = %6.1f 包' % m['packs_all'])
    print('   （对照：若四条线可自由兑换 = %5.1f 包，实际达不到，仅作下界）' % m['packs_fungible'])
    print('   ★ 不可兑换惩罚系数 = PP全量 ÷ 可兑换下界 = %.2f×' % m['penalty'])
    print('      （= 1.0 表示四条线刚好均衡；越大说明造价越偏斜在某一条线上）')
    print()
    print('【每线占用（%.4f 点/包/线）】' % SCALE_B)
    for r in ORDER:
        need = m['b'][r] / SCALE_B
        print('   %-6s 需 %7.1f 包  %s' % (LB[r], need, '← 瓶颈' if abs(need - m['packs_all']) < 1e-9 else ''))
    return m


def derive():
    print('=' * 78)
    print('点数B（可定向口径）的完整推导链')
    print('=' * 78)
    print('总原则：点数B 只统计「能定向变成你要的那张牌」的产出。')
    print('        随机开到的实牌不计 —— 实测为指定牌表开包，命中率仅 5.6%。')
    print()
    print('-' * 78)
    print('来源 ①  包内野卡替换（官方 drop-rates）')
    print('  原文："One card in each rarity card slot (Common, Uncommon, and')
    print('        Mythic/Rare) may redeem for a Wildcard of the same rarity')
    print('        at the following expected rates"')
    print('-' * 78)
    sub = {'common': 1/3., 'uncommon': 1/5., 'rare': 1/30., 'mythic': 1/30.}
    for r in ORDER:
        print('   %-6s 替换率 1:%-3d → %.5f 张/包' % (LB[r], round(1/sub[r]), sub[r]))
    print()
    print('-' * 78)
    print('来源 ②  野卡进度轮（官方 drop-rates）')
    print('  原文："For each Pack you open, you earn 1 progress in **both** the')
    print('        Uncommon and the Rare/Mythic Wildcard Tracks. A WCR is')
    print('        triggered when you earn 6 progress on a track."')
    print('  稀有/秘稀轨："redeems 4 Rare WCRs in a row before you will redeem')
    print('        your Mythic WCR"  ⇒ 每 30 包 = 4 稀有 + 1 秘稀')
    print('  ⚠ 普通**没有**进度轮（只有两条轨道：非普通、稀有/秘稀）')
    print('-' * 78)
    track = {'common': 0.0, 'uncommon': 1/6., 'rare': 4/30., 'mythic': 1/30.}
    for r in ORDER:
        d = '无轨道' if track[r] == 0 else '每 %.0f 包 1 张 → %.5f 张/包' % (1/track[r], track[r])
        print('   %-6s %s' % (LB[r], d))
    print()
    print('-' * 78)
    print('来源 ③  金色包的进度轮推进（官方："Golden Packs ... will advance')
    print('        the wildcard track"，每购买 10 包得 1 个金色包）')
    print('        每 10 包 +1 进度 = 每包 +0.1 进度 ⇒ 进度轮产出 ×1.1')
    print('        （金色包本身给的 6 张随机标准稀有/秘稀**不计入** B）')
    print('-' * 78)
    for r in ORDER:
        if track[r]:
            print('   %-6s %.5f × 1.1 = %.5f 张/包' % (LB[r], track[r], track[r]*1.1))
    print()
    print('=' * 78)
    print('合计：每包可定向产出 OUT_B')
    print('=' * 78)
    print('%-8s %10s %10s %12s %14s' % ('稀有度', '①替换', '②进度轮×1.1', '合计(张/包)', '每张需包数'))
    for r in ORDER:
        t = track[r]*1.1
        print('%-8s %10.5f %10.5f %12.5f %14.4f' % (LB[r], sub[r], t, OUT_B[r], 1/OUT_B[r]))
    print()
    print('=' * 78)
    print('归一化：把「每条线每包的可定向产出」定为 %.4f 点' % PTS_PER_LINE)
    print('=' * 78)
    print('点/张 = %.4f ÷ 该线每包产出 = %.4f × 该牌所需包数' % (PTS_PER_LINE, PTS_PER_LINE))
    print()
    print('%-8s %14s %14s %16s' % ('稀有度', '每包产出', '点/张', '校验=标度×需包数'))
    for r in ORDER:
        print('%-8s %14.5f %14.3f %16.3f' % (LB[r], OUT_B[r], VAL_B[r], PTS_PER_LINE*(1/OUT_B[r])))
    print()
    print('  ⇒ 每张点数 = %.4f × 该牌"需要几包"  ⇒ 反过来：包数 = 点数 ÷ %.4f' % (PTS_PER_LINE, PTS_PER_LINE))
    print('  ⇒ 1 包对**每条线各**贡献 %.4f 点（四线不可相加）' % PTS_PER_LINE)
    print()
    if abs(PTS_PER_LINE - 5.0) < 1e-9:
        print('  ⚠ 当前标度 = 5.0，所以「1 张普通 = %.2f 点」**不是 1**。' % VAL_B['common'])
        print('     若真要「1 张普通 = 1 点」，用 PTS_PER_LINE=%.4f 运行：' % OUT_B['common'])
        for r in ORDER:
            print('        %-6s %.3f 点/张' % (LB[r], PTS_PER_LINE and OUT_B['common']/OUT_B[r]))
        print('     （两者只差一个常数倍 %.1f×，比值结构完全相同，PP 不受影响）'
              % (5.0/OUT_B['common']))


def relation(files):
    print('=' * 78)
    print('点数B 与 PP 的关系：同源，但一个是「和」、一个是「最大」')
    print('=' * 78)
    print('两者都由同一组产出率决定 ⇒ 只差一个常数与聚合方式：')
    print()
    print('   某线 B 点数      = 该线张数 × B点/张')
    print('   某线所需包数     = 该线 B 点数 × 3            （SCALE_B = 1/3）')
    print('   点数B（可加）     = Σ 各线 B 点数')
    print('   PP（不可加）      = max(各线所需包数)')
    print()
    print('   ⇒  点数B × 3 = **Σ 各线包数**（四线之和）')
    print('   ⇒  PP全量    = **max(各线包数)**')
    print('   ⇒  两者相等 当且仅当只有一条线有需求（现实中不可能）')
    print()
    print('-' * 78)
    print('%-30s %8s %10s %10s %10s %8s' % ('牌表', '点数B', '×3=Σ包数', 'PP全量', '可兑换下界', '惩罚×'))
    for f in files:
        sig, unk, ex = census(parse_deck(f))
        m = metrics(sig)
        print('%-30s %8.1f %10.1f %10.1f %10.1f %8.2f'
              % (os.path.basename(f)[:30], m['tot_b'], m['sum_packs'], m['packs_all'],
                 m['packs_fungible'], m['penalty']))
    print()
    print('  可兑换下界 = 点数B × 3 ÷ 4（假设四线能互换，实际不能）')
    print('  惩罚系数   = PP全量 ÷ 可兑换下界（=1 说明四线均衡；越大越偏斜）')
    print()
    print('-' * 78)
    print('★ 为什么要同时报这两个数')
    print('-' * 78)
    print('   点数B：**可加** ⇒ 能做系列总账单、多副横向比较、金卡摊薄成本')
    print('   PP  ：**取 max** ⇒ 才能回答"这一副实际要攒多久"')
    print('   只报点数B 会低估（RDW：63.8×3=191.5 是四线之和，不是要开的包数 66.7）')
    print('   只报 PP 则失去可加性，15 副总账做不出来')


def units():
    print('=' * 78)
    print('三种等价标度对照（只差常数倍；PP / 包数完全一致）')
    print('=' * 78)
    print('%-12s %10s | %-30s | %s' % ('标度名', '标度值', '可定向 B 点/张', '每包每线'))
    for name, k in [('line5', 5.0), ('pack1', 1.0), ('b_common1', 1/3.)]:
        vals = ' '.join('%.2f' % (k / OUT_B[r]) for r in ['common', 'uncommon', 'rare', 'mythic'])
        print('%-12s %10.4f | %-30s | %.4f 点' % (name, k, vals, k))
    print()
    print('  列序：普通 / 非普通 / 稀有 / 秘稀')
    print()
    print('%-12s %10s | %s' % ('标度名', '标度值', '物质 A 点/张（同样列序）'))
    for name, k in [('line5', 5.0), ('pack1', 1.0), ('b_common1', 1/3.)]:
        vals = ' '.join('%.2f' % (k / OUT_A[r]) for r in ['common', 'uncommon', 'rare', 'mythic'])
        print('%-12s %10.4f | %s' % (name, k, vals))
    print()
    print('  用法：UNIT=b_common1 python3 deck_cost.py brief <牌表…>')
    print('  换算：包数 = 该线点数 ÷ 标度值')


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    if a[0] == 'derive':
        derive(); return
    if a[0] == 'units':
        units(); return
    if a[0] == 'relation':
        relation(a[1:] or ['../../rdw_v4/deck_rdw_v4.txt', '../../angel_std/deck_angel.txt'])
        return
    if a[0] == 'parse':
        show(parse_sig(' '.join(a[1:])), '签名解析：%s' % ' '.join(a[1:]))
        return
    files = a[1:]
    if a[0] == 'brief':
        brief(files); return
    if a[0] == 'sig':
        for f in files:
            sig, unk, ex = census(parse_deck(f))
            show(sig, os.path.basename(f))
            print('  非基本地 %d 张 ｜ 生物 %d 张 ｜ 主牌合计 %d 张' % (ex['land'], ex['creature'], ex['total']))
            if unk:
                print('  ⚠ 未识别: %s' % ', '.join(unk))
            print()
    elif a[0] == 'sum':
        tot = {k: 0 for k in ORDER}
        print('%-34s %-22s %10s %10s' % ('牌表', '签名', 'PP核心', '点数B'))
        for f in files:
            sig, unk, ex = census(parse_deck(f))
            mt = metrics(sig)
            _, tier, _ = budget_check(sig)
            print('%-34s %-20s %10.1f %10.1f  %s' % (os.path.basename(f)[:34], fmt_sig(sig),
                                                 mt['packs_core'], mt['tot_b'], tier))
            for k in ORDER:
                tot[k] += sig.get(k, 0)
        print('-' * 82)
        mt = metrics(tot)
        print('%-34s %-22s %10.1f %10.1f' % ('【合计 %d 副】' % len(files), fmt_sig(tot),
                                             mt['packs_core'], mt['tot_b']))
        print()
        show(tot, '系列总账单（%d 副相加）' % len(files))
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
