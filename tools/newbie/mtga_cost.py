#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MTGA 套牌造价计算器（纯野卡口径 → 折「造价点数 PP」）

用法:
  python3 mtga_cost.py table                       # 换算率总表
  python3 mtga_cost.py deck <牌表文件> [选项]
  python3 mtga_cost.py cmp  <牌表文件> [<牌表>…]     # 多副对比

选项:
  --open-set <系列代码>   模拟「开该系列的包」自然命中所需稀有/秘稀（蒙特卡洛）
  --sims N               模拟次数（默认 2000）
  --gold-per-day N       F2P 日均金币（默认 1150 休闲 / 用 --hardcore 切 1600）

依据: data/mtga_economy.md（出处：WotC 官方 drop-rates 页）
  · 每包: 5 普通 + 2 非普通 + 1 稀有/秘稀；+1 野卡进度（两条轨道）；+1/10 金色包进度
  · 稀有/秘稀轨道: 每 6 包 1 张 WCR，4 稀有 : 1 秘稀（每 30 包）
  · 包内替换: 普通 1:3、非普通 1:5、稀有 1:30、秘稀 1:30
  · 金色包: 每购 10 包 1 个 → 6 张标准稀有/秘稀（≥1 秘稀），并 +1 进度
  ⇒ 每包期望: 稀有野卡 0.18（≈5.56 包/张）、秘稀野卡 0.07（≈14.29 包/张）
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json, os, random, sys, re
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, '..', 'data'))
M = json.load(open(os.path.join(DATA, 'rarity_map.json'), encoding='utf-8'))

sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..')))
from deck_model import parse_deck as _parse_deck

# ── 产出率（每包期望值）──────────────────────────────
TRACK_PER_PACK = 4.0 / 30          # 稀有轨: 每 30 包 4 张稀有
TRACK_MYTH = 1.0 / 30              # 稀有轨: 每 30 包 1 张秘稀
TRACK_UNC = 1.0 / 6
SUB_RARE, SUB_MYTH, SUB_UNC, SUB_COM = 1/30., 1/30., 1/5., 1/3.
GOLDEN_STEP = 0.1                  # 每包推进 1/10 个金色包
RARE_PER_PACK = TRACK_PER_PACK + SUB_RARE + GOLDEN_STEP * TRACK_PER_PACK
MYTH_PER_PACK = TRACK_MYTH + SUB_MYTH + GOLDEN_STEP * TRACK_MYTH
UNC_PER_PACK = TRACK_UNC + SUB_UNC + GOLDEN_STEP * TRACK_UNC
COM_PER_PACK = SUB_COM

PACK_GOLD, PACK_GEM = 1000, 200
GOLDEN_CARDS = 6.0                 # 每个金色包 6 张标准稀有/秘稀

# 稀有槽升级为秘稀的概率（官方逐系列公布，倒数表示「约 N 包 1 张秘稀」）
RARE_UPGRADE = {
    'woe': 7, 'otj': 7, 'blb': 7, 'dsk': 7, 'fdn': 7, 'dft': 7, 'tdm': 7,
    'eoe': 7, 'tla': 7, 'ecl': 7, 'sos': 7,
    'spm': 8.1, 'tmt': 8.1, 'hob': 8.1,
    'msh': 5.8, 'lci': 6.8, 'mkm': 8.0, 'fin': 8.4,
    'big': 7, 'om1': 7, 'fra': 7,     # FRA 未发售，官方未公布，暂按同期 1:7
}


def rate(x):
    return 1.0 / x if x > 0 else float('inf')


def parse_deck(path):
    """薄委托：deck_model.parse_deck → (主牌, 备牌) 两个 [(qty, name)]。

    ★ Phase 1 起坏行记入 Deck.skipped 而不再兜底成 (1, line) 假牌。"""
    return _parse_deck(path).main_side_pairs()


_PREFIX_IDX = None


def look(name):
    """牌名 → 池内条目（支持双面牌只写正面名）"""
    global _PREFIX_IDX
    e = M.get(name)
    if e is not None:
        return e
    if _PREFIX_IDX is None:
        _PREFIX_IDX = {}
        for k in M:
            if ' // ' in k:
                _PREFIX_IDX[k.split(' // ')[0]] = k
    k = _PREFIX_IDX.get(name)
    return M.get(k) if k else None


def classify(pairs):
    """(张数, 牌名) 列表 → 野卡账单"""
    bill = Counter()
    detail, unknown = [], []
    for n, name in pairs:
        e = look(name)
        if e is None:
            unknown.append(name)
            bill['?'] += n
            detail.append((n, name, '??', True, 0))
            continue
        if e['basic']:
            bill['basic'] += n
            detail.append((n, name, '基本地', False, 0))
            continue
        r = e['rarity']
        bill[r] += n
        detail.append((n, name, r, bool(e['wildcard']), 1 if e['wildcard'] else 0))
    return bill, detail, unknown


def pp_from_bill(bill, wildcard_only=False):
    """返回 (PP核心, PP全量, 各项所需包数)

    PP核心 = max(稀有, 秘稀)  —— 稀有/秘稀野卡是硬约束（开包自然命中率 <6%，只能靠野卡）
    PP全量 = max(所有稀有度)  —— 假设连普通/非普通也全靠野卡（完全从零的账号）
    真实值落在两者之间：完成新手引导的账号，普通/非普通大多已被 15 套起始套牌覆盖。
    """
    if wildcard_only:
        rpc, mpc = 1/6., 1/30.
    else:
        rpc, mpc = RARE_PER_PACK, MYTH_PER_PACK
    need = {}
    need['rare'] = bill['rare'] / rpc
    need['mythic'] = bill['mythic'] / mpc
    need['uncommon'] = bill['uncommon'] / UNC_PER_PACK
    need['common'] = bill['common'] / COM_PER_PACK
    core = max(need['rare'], need['mythic'])
    return core, max(need.values()), need


def report(path, wildcard_only=False, gold_per_day=1150, open_set=None, sims=2000, verbose=True):
    main, side = parse_deck(path)
    mbill, mdet, munk = classify(main)
    sbill, sdet, sunk = classify(side)
    PP, PP_all, need = pp_from_bill(mbill, wildcard_only)
    out = {}
    if verbose:
        print('=' * 66)
        print('牌表: %s' % os.path.basename(path))
        print('  主牌 %d 张 | 备牌 %d 张' % (sum(n for n, _ in main), sum(n for n, _ in side)))
        print('-' * 66)
        print('【主牌野卡账单】按 Arena 印刷稀有度')
        for r, label in [('common', '普通'), ('uncommon', '非普通'),
                         ('rare', '稀有 ★'), ('mythic', '秘稀 ★★'), ('basic', '基本地')]:
            if mbill[r]:
                print('  %-8s %3d 张' % (label, mbill[r]))
        if munk:
            print('  ⚠ 未识别: %s' % ', '.join(munk[:6]))
        print('-' * 66)
        print('【造价点数 PP】[1 PP = 1 包 = 1000 金 = 200 宝石]')
        for k, lb in [('rare', '稀有'), ('mythic', '秘稀'), ('uncommon', '非普通'), ('common', '普通')]:
            print('   %-5s %7.1f PP  ← 该条线单独所需的包数' % (lb, need[k]))
        print('   ── PP核心（稀有/秘稀约束）%7.1f' % PP)
        print('   ── PP全量（含普通/非普通）%7.1f' % PP_all)
        if sbill:
            sp, sp2, _ = pp_from_bill(sbill)
            print('   （备牌另需核心 %.1f / 全量 %.1f PP；本项目 BO1 默认 60 主 0 备，不计入）' % (sp, sp2))
        print('-' * 66)
        gp = PP * GOLDEN_STEP
        print('【折算（按核心）】')
        print('   金币 %8.0f  ｜ 宝石 %7.0f' % (PP * PACK_GOLD, PP * PACK_GEM))
        print('   F2P 天数：休闲 %.1f 天（1150 金/日）｜ 重度 %.1f 天（1600 金/日）'
              % (PP * PACK_GOLD / 1150, PP * PACK_GOLD / 1600))
        print('   顺手拿到：金色包 %.1f 个 ⇒ 额外 %.0f 张标准稀有/秘稀（随机，不可定向）'
              % (gp, gp * GOLDEN_CARDS))
    out['path'] = path
    out['PP'] = PP
    out['need'] = need
    out['mbill'] = dict(mbill)
    out['gold'] = PP * PACK_GOLD
    out['gems'] = PP * PACK_GEM

    if open_set:
        sim = simulate(main, open_set, sims)
        out['sim'] = sim
        if verbose:
            print('-' * 66)
            print('【开 %s 系列包的自然命中模拟】（N=%d，配合野卡补缺）' % (open_set.upper(), sims))
            print('  凑齐全部所需牌 中位数 %d 包 ｜ 平均 %.1f 包 ｜ 90 分位 %d 包'
                  % (sim['p50'], sim['mean'], sim['p90']))
            print('  其中靠开包直接拿到 %.1f 张，靠野卡补 %.1f 张'
                  % (sim['from_packs'], sim['from_wc']))
            print('  ⇒ 折算 %.0f 金 / %.0f 宝石' % (sim['mean'] * PACK_GOLD, sim['mean'] * PACK_GEM))
    if verbose:
        print('=' * 66)
    return out


def set_pools(code):
    rares = [n for n, e in M.items() if e['arena'] and e['rarity'] == 'rare'
             and any(p['set'] == code for p in e['prints'])]
    myths = [n for n, e in M.items() if e['arena'] and e['rarity'] == 'mythic'
             and any(p['set'] == code for p in e['prints'])]
    return rares, myths


def simulate(main, code, sims=2000, rare_upgrade=None):
    """蒙特卡洛：开 code 系列的包 + 野卡补缺，直到凑齐主牌所需稀有/秘稀。

    完成判据（每个包之后检查）：所有「尚未开到的缺口」是否已被手头野卡覆盖。
    """
    if rare_upgrade is None:
        rare_upgrade = RARE_UPGRADE.get(code, 7.0)
    need = defaultdict(int)
    for n, name in main:
        e = look(name)
        if e and e['wildcard']:
            need[(name, e['rarity'])] += n
    if not need:
        return None
    rares, myths = set_pools(code)
    if not rares:
        return None
    need_r = {k[0]: v for k, v in need.items() if k[1] == 'rare'}
    need_m = {k[0]: v for k, v in need.items() if k[1] == 'mythic'}
    res, fps, fws = [], [], []
    for _ in range(sims):
        acq = defaultdict(int)
        wc_r = wc_m = 0
        prog = cyc = 0
        packs = 0
        while packs < 800:
            packs += 1
            prog += 1 + GOLDEN_STEP      # 每包 1 点，金色包额外 0.1 点
            if random.random() < SUB_RARE:
                wc_r += 1
            if random.random() < SUB_MYTH:
                wc_m += 1
            if prog >= 6:
                prog -= 6
                cyc += 1
                if cyc % 5 == 0:
                    wc_m += 1
                else:
                    wc_r += 1
            if random.random() < 1.0 / rare_upgrade:
                if myths:
                    c = random.choice(myths)
                    if acq[c] < 4:
                        acq[c] += 1
            else:
                c = random.choice(rares)
                if acq[c] < 4:
                    acq[c] += 1
            dr = sum(max(0, q - acq[nm]) for nm, q in need_r.items())
            dm = sum(max(0, q - acq[nm]) for nm, q in need_m.items())
            if dr <= wc_r and dm <= wc_m:
                break
        got = sum(min(acq[nm], q) for nm, q in list(need_r.items()) + list(need_m.items()))
        res.append(packs); fps.append(got); fws.append(sum(need.values()) - got)
    res.sort()
    return {'mean': sum(res) / len(res), 'p50': res[len(res) // 2], 'p90': res[int(len(res) * .9)],
            'from_packs': sum(fps) / len(fps), 'from_wc': sum(fws) / len(fws),
            'n': sims, 'set': code, 'upgrade': rare_upgrade}


def table():
    print('MTGA 牌张获取兑换表（纯 MTGA 口径 · 依据 WotC 官方 drop-rates）\n')
    print('每包（1000 金 / 200 宝石）产出期望：')
    print('  稀有野卡  %.4f 张  →  %.2f 包/张' % (RARE_PER_PACK, rate(RARE_PER_PACK)))
    print('  秘稀野卡  %.4f 张  →  %.2f 包/张' % (MYTH_PER_PACK, rate(MYTH_PER_PACK)))
    print('  非普通野卡 %.4f 张  →  %.2f 包/张' % (UNC_PER_PACK, rate(UNC_PER_PACK)))
    print('  普通野卡  %.4f 张  →  %.2f 包/张' % (COM_PER_PACK, rate(COM_PER_PACK)))
    print('  金色包    %.1f 个/10包 ⇒ 额外 %.0f 张标准稀有/秘稀（随机）\n' % (GOLDEN_STEP * 10, GOLDEN_STEP * 10 * GOLDEN_CARDS))
    print('单张造价（PP = 包数）：')
    for label, per in [('普通', rate(COM_PER_PACK)), ('非普通', rate(UNC_PER_PACK)),
                       ('稀有', rate(RARE_PER_PACK)), ('秘稀', rate(MYTH_PER_PACK))]:
        print('  %-5s %6.2f PP   %6.0f 金   %5.0f 宝石' % (label, per, per * PACK_GOLD, per * PACK_GEM))
    print('\n「4 金」典型造价：')
    for r, m in [(4, 0), (3, 1), (2, 2), (0, 4)]:
        p = r * rate(RARE_PER_PACK) + m * rate(MYTH_PER_PACK)
        print('  %d 稀有 + %d 秘稀 = %5.1f PP   %6.0f 金   %5.0f 宝石   休闲 %4.1f 天'
              % (r, m, p, p * PACK_GOLD, p * PACK_GEM, p * PACK_GOLD / 1150))


def main():
    a = sys.argv[1:]
    if not a or a[0] in ('-h', '--help'):
        print(__doc__); return
    if a[0] == 'table':
        table(); return
    wc_only = '--wildcard-only' in a
    gpd = 1150
    if '--hardcore' in a:
        gpd = 1600
    if '--gold-per-day' in a:
        gpd = int(a[a.index('--gold-per-day') + 1])
    os_set, sims = None, 2000
    if '--open-set' in a:
        os_set = a[a.index('--open-set') + 1]
    if '--sims' in a:
        sims = int(a[a.index('--sims') + 1])
    files = [x for x in a[1:] if not x.startswith('--') and x not in (os_set, str(gpd), str(sims))]
    if a[0] == 'deck':
        report(files[0], wc_only, gpd, os_set, sims)
    elif a[0] == 'cmp':
        rows = [report(f, wc_only, gpd, None, sims, verbose=False) for f in files]
        print('%-38s %7s %7s %9s %8s' % ('牌表', '稀有', '秘稀', 'PP', '金'))
        for r in rows:
            print('%-38s %7d %7d %9.1f %8.0f' % (os.path.basename(r['path']), r['mbill'].get('rare', 0),
                                                 r['mbill'].get('mythic', 0), r['PP'], r['gold']))
    else:
        report(a[0], wc_only, gpd, os_set, sims)


if __name__ == '__main__':
    main()
