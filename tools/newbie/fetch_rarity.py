#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全池数据表（纯 MTGA 口径）：FRA 发售后标准牌池（19 系列 + FRA）→ rarity_map.json

★ 造价模型 = **MTGA 野卡（wildcard）用量**，与实际价格无关。因此本表的关键字段是：
    arena      : 该牌名是否有 Arena 印刷（无 ⇒ 本项目根本用不了，硬性排除）
    rarity     : **Arena 印刷**的稀有度（rare/mythic 才消耗稀有/神话野卡）
    arena_rarity_conflict : 同一牌名在 Arena 各印刷间稀有度是否冲突（需人工复核）
    basic      : 是否基本地（**基本地在 MTGA 免费，不消耗野卡**）
    alive      : 轮替（2027-02-02）后是否仍有合法的「非数字标准扩展」印刷

关键设计：
  · 查询式 (f:standard or e:fra)：FRA 未发售，Scryfall 统一标 not_legal，必须显式放行。
  · 用 unique:prints：① 轮替存活要看「有没有一张印刷属于存活系列」；② 稀有度在各印刷间可能不同
    （实测 240 个牌名如此，如 Abrade 有 common/uncommon/rare），必须按 **Arena 印刷**取值。
  · 存活判据 = set_type ∈ {core, expansion} 且 digital=false 且 released_at >= FDN(2024-11-15)
    —— 与 skills/tools/rot_audit.py 同源。
  · 原始印刷数据缓存到 std_prints.json，改聚合逻辑无需重抓网络。
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json, os, subprocess, sys, time
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, '..', 'data'))
os.makedirs(DATA, exist_ok=True)
UA = 'MinisMTG-NewbieSeries/1.0'
CUTOFF = '2024-11-15'          # FDN 基石构筑发售日 = 轮替后最旧系列
ALIVE_TYPES = {'core', 'expansion'}
QUERY = '(f:standard or e:fra)'

# ── 标准合法系列白名单（本项目 = 纯 MTGA，故含 Arena 数字标准系列 OM1）──
PREMIER = {'woe', 'lci', 'mkm', 'otj', 'big', 'blb', 'dsk', 'fdn', 'dft', 'tdm', 'fin', 'eoe',
           'spm', 'tla', 'ecl', 'tmt', 'sos', 'msh', 'hob', 'fra',      # 19 系列（BIG 随 OTJ）
           'om1'}                                                       # Arena 数字限定标准系列
# 随标准系列同日发售的 bonus sheet（官方「特别登场 SPG」明确不进标准 ⇒ 排除）
BONUS = {'wot', 'eos', 'fca', 'mar', 'omb', 'otp', 'pza', 'soa'}
STANDARD_SETS = PREMIER | BONUS
RANK = {'common': 0, 'uncommon': 1, 'rare': 2, 'mythic': 3, 'special': 4, 'bonus': 4}


def curl_json(url, tries=5):
    for a in range(tries):
        r = subprocess.run(['curl', '-s', '-m', '45', '-A', UA, url], capture_output=True, text=True)
        try:
            d = json.loads(r.stdout)
        except Exception:
            d = None
        if d and (d.get('data') is not None or d.get('object') == 'error'):
            return d
        time.sleep(1.5 * (a + 1))
    return None


def slim(c):
    faces = None
    if c.get('card_faces'):
        faces = [{'name': f.get('name'), 'mana_cost': f.get('mana_cost', ''),
                  'type_line': f.get('type_line', ''), 'oracle_text': f.get('oracle_text', '')} for f in c['card_faces']]
    return {
        'name': c['name'], 'rarity': c['rarity'], 'set': c['set'], 'set_type': c.get('set_type'),
        'released_at': c.get('released_at'), 'digital': c.get('digital', False),
        'collector_number': c.get('collector_number'),
        'mana_cost': c.get('mana_cost', ''), 'cmc': c.get('cmc'),
        'type_line': c.get('type_line', ''), 'ci': c.get('color_identity', []),
        'oracle': c.get('oracle_text', ''), 'faces': faces,
        'games': c.get('games', []), 'arena_id': c.get('arena_id'),
        'layout': c.get('layout'), 'keywords': c.get('keywords', []),
    }


def fetch_prints():
    prints, url, page = [], 'https://api.scryfall.com/cards/search?q=' + quote(QUERY) + '&unique=prints', 0
    while url:
        page += 1
        d = curl_json(url)
        if not d or d.get('object') == 'error':
            print('!! page %d failed: %s' % (page, str(d)[:200])); break
        prints += [slim(c) for c in d['data']]
        if page % 10 == 0 or page == 1:
            print('  page %d: 累计 %d 张印刷' % (page, len(prints)), flush=True)
        url = d.get('next_page') if d.get('has_more') else None
        time.sleep(0.12)
    print('总印刷数 =', len(prints))
    return prints


def aggregate(prints):
    m = {}
    for p in prints:
        n = p['name']
        e = m.setdefault(n, {'rarity': p['rarity'], 'arena_rarity': None, 'cmc': p['cmc'],
                             'mana_cost': p['mana_cost'], 'type_line': p['type_line'],
                             'ci': p['ci'], 'oracle': p['oracle'], 'faces': p['faces'],
                             'prints': [], 'arena': False, 'alive': False, 'basic': False,
                             'layout': p['layout'], 'keywords': p['keywords'],
                             'arena_prints': [], 'rarity_prints': {}})
        e['rarity_prints'][p['rarity']] = e['rarity_prints'].get(p['rarity'], 0) + 1
        is_arena = 'arena' in (p['games'] or [])
        e['prints'].append({'set': p['set'], 'set_type': p['set_type'], 'released_at': p['released_at'],
                            'cn': p['collector_number'], 'rarity': p['rarity'],
                            'digital': p['digital'], 'arena': is_arena})
        if 'Basic Land' in (p['type_line'] or ''):
            e['basic'] = True
        if is_arena:
            e['arena'] = True
            e['arena_prints'].append({'set': p['set'], 'cn': p['collector_number'],
                                      'rarity': p['rarity'], 'released_at': p['released_at'],
                                      'digital': p['digital']})
        if (p['set_type'] in ALIVE_TYPES) and (not p['digital']) and (p['released_at'] or '') >= CUTOFF:
            e['alive'] = True

    for e in m.values():
        # ★ 只保留「标准合法系列 + Arena 可用」的印刷
        ok = [x for x in e['arena_prints'] if x['set'] in STANDARD_SETS]
        e['arena'] = bool(ok)
        if ok:
            # MTGA 里同名牌有多个印刷时，玩家按**最便宜**的那版付野卡
            best = sorted(ok, key=lambda x: (RANK.get(x['rarity'], 9), x['released_at'] or ''))[0]
            newest = sorted(ok, key=lambda x: (x['released_at'] or ''))[-1]
            e['arena_rarity'] = best['rarity']
            e['arena_print'] = '%s#%s' % (best['set'].upper(), best['cn'])
            e['arena_print_newest'] = '%s#%s(%s)' % (newest['set'].upper(), newest['cn'], newest['rarity'])
            e['arena_rarity_conflict'] = len({x['rarity'] for x in ok}) > 1
            e['via_bonus'] = not any(x['set'] in PREMIER for x in ok)
            e['rarity'] = best['rarity']
            e['std_sets'] = sorted({x['set'] for x in ok})
        else:
            e['arena_rarity'] = e['arena_print'] = e['arena_print_newest'] = None
            e['arena_rarity_conflict'] = False
            e['via_bonus'] = False
            e['std_sets'] = []
        e.pop('arena_prints', None)
        e['wildcard'] = (1 if e['rarity'] in ('rare', 'mythic') else 0) if (e['arena'] and not e['basic']) else 0
        e['wildcard_kind'] = ('mythic' if e['rarity'] == 'mythic' else 'rare') if e['wildcard'] else None

    json.dump(m, open(os.path.join(DATA, 'rarity_map.json'), 'w', encoding='utf-8'), ensure_ascii=False)

    gold = {n: e for n, e in m.items() if e['wildcard']}
    alive_gold = {n: e for n, e in gold.items() if e['alive']}
    json.dump(alive_gold, open(os.path.join(DATA, 'alive_gold.json'), 'w', encoding='utf-8'), ensure_ascii=False)

    from collections import Counter
    print('\n不同牌名 =', len(m))
    print('Arena 可用牌名 =', sum(1 for e in m.values() if e['arena']))
    print('其中消耗野卡(rare/mythic 非基本地) =', len(gold))
    print('  稀有 =', sum(1 for e in gold.values() if e['rarity'] == 'rare'),
          '| 神话 =', sum(1 for e in gold.values() if e['rarity'] == 'mythic'))
    print('  轮替存活的金卡 =', len(alive_gold))
    print('基本地牌名 =', sum(1 for e in m.values() if e['basic']))
    print('Arena 内稀有度有冲突的牌名 =', sum(1 for e in m.values() if e.get('arena_rarity_conflict')))
    for n, e in list(m.items()):
        if e.get('arena_rarity_conflict'):
            print('   ⚠ %-36s 纸面%s | Arena %s(%s) | 全部%s' % (n[:36], e['rarity_prints'],
                  e['arena_rarity'], e['arena_print'], e['rarity_prints']))
    noarena = [n for n, e in m.items() if not e['arena']]
    print('\n无 Arena 印刷（本项目不可用）:', len(noarena), '→', noarena[:15])


def main():
    RAW = os.path.join(DATA, 'std_prints.json')
    if os.path.exists(RAW) and '--refresh' not in sys.argv:
        prints = json.load(open(RAW, encoding='utf-8'))
        print('复用原始印刷缓存 std_prints.json:', len(prints), '张')
    else:
        prints = fetch_prints()
        json.dump(prints, open(RAW, 'w', encoding='utf-8'), ensure_ascii=False)
    aggregate(prints)


if __name__ == '__main__':
    main()
