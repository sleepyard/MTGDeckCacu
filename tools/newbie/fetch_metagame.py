#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重抓真实标准环境牌表（mtgch API，后端 MTGTop8）→ metagame_cards.json / metagame_decks.json

用途（对应计划书 §六 强度锚）：
  · metagame_cards.json  每张牌在真实牌表里的入牌表率 / 总张数 / 色组分布  ⇒ 判断「哪些牌是环境主力」
  · metagame_decks.json  逐副精简牌表（牌型名 + 色组 + 主备牌构成）      ⇒ 判断「某色组的真实形态」
  · 详情接口自带 zhs_name(竞技场中文名) 与 current_cny(人民币价)          ⇒ 中文名与造价的旁证
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json, os, subprocess, sys, time
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, '..', 'data'))
os.makedirs(DATA, exist_ok=True)
UA = 'MinisMTG-NewbieSeries/1.0'
BASE = 'https://mtgch.com/api/v1'
N_EVENTS = int(sys.argv[1]) if len(sys.argv) > 1 else 60


def get(url, tries=4):
    for a in range(tries):
        r = subprocess.run(['curl', '-s', '-m', '40', '-L', '-A', UA, url], capture_output=True, text=True)
        try:
            d = json.loads(r.stdout)
        except Exception:
            d = None
        if d is not None:
            return d
        time.sleep(0.8 * (a + 1))
    return None


def main():
    # ---- 1. 赛事列表
    events, page = [], 1
    while len(events) < N_EVENTS * 2 and page <= 10:
        d = get('%s/decks/events/?format=standard&page=%d' % (BASE, page))
        if not d or not d.get('events'):
            break
        events += d['events']
        page += 1
        time.sleep(0.3)
    events.sort(key=lambda e: e.get('date') or '', reverse=True)
    sel = events[:N_EVENTS]
    print('赛事: %d 场（%s ~ %s）' % (len(sel), sel[-1]['date'], sel[0]['date']))

    # ---- 2. 各场牌表列表
    def fetch_event(ev):
        d = get('%s/decks/event/%s/decks/' % (BASE, ev['id']))
        if not d or not d.get('decks'):
            return []
        return [(ev, x) for x in d['decks']]

    pairs = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(fetch_event, sel):
            pairs += r
    print('牌表数:', len(pairs))

    # ---- 3. 逐副详情
    def fetch_deck(pair):
        ev, meta = pair
        d = get('%s/deck/deck/%s/' % (BASE, meta['id']))
        if not d or 'cards' not in d:
            return None
        c = d['cards']
        jm = d.get('deck_meta', meta)
        def pick(lst):
            out = []
            for x in lst or []:
                nm = x.get('name')
                if nm:
                    out.append({'n': nm, 'q': x.get('quantity', 1), 'zhs': x.get('zhs_name') or '',
                                'r': x.get('rarity'), 'cmc': x.get('cmc'), 'set': x.get('set'),
                                'cn': x.get('collector_number'), 'tl': x.get('type_line', ''),
                                'cny': x.get('current_cny')})
            return out
        return {'id': str(meta['id']), 'arch': meta.get('name') or jm.get('name'),
                'colors': meta.get('colors') or jm.get('colors') or [],
                'date': ev.get('date'), 'event': ev.get('name'), 'place': meta.get('place'),
                'main': pick(c.get('mainboard')), 'side': pick(c.get('sideboard'))}

    decks = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        for i, r in enumerate(ex.map(fetch_deck, pairs)):
            if r:
                decks.append(r)
            if (i + 1) % 100 == 0:
                print('  ...已抓 %d/%d' % (i + 1, len(pairs)), flush=True)
    print('成功牌表:', len(decks))

    # ---- 4. 聚合
    by_card = defaultdict(lambda: {'mb': 0, 'sb': 0, 'decks': 0, 'zhs': None, 'r': None, 'cmc': None,
                                   'sets': Counter(), 'arch': Counter(), 'ci': Counter()})
    arch_counter = Counter()
    ci_counter = Counter()
    mt_total = 0
    for dk in decks:
        arch_counter[dk['arch']] += 1
        ci_counter[tuple(sorted(dk['colors']))] += 1
        seen = set()
        for x in dk['main']:
            e = by_card[x['n']]
            e['mb'] += x['q']; mt_total += x['q']
            e['zhs'] = e['zhs'] or x['zhs']; e['r'] = x['r'] or e['r']; e['cmc'] = x['cmc']
            e['sets'][x['set']] += 1; e['arch'][dk['arch']] += 1
            e['ci'][','.join(sorted(dk['colors'] or []))] += 1
            seen.add(x['n'])
        for x in dk['side']:
            by_card[x['n']]['sb'] += x['q']
        for n in seen:
            by_card[n]['decks'] += 1

    n_decks = len(decks)
    out = []
    for n, e in by_card.items():
        out.append({'name': n, 'zhs': e['zhs'], 'rarity': e['r'], 'cmc': e['cmc'],
                    'mb_total': e['mb'], 'sb_total': e['sb'], 'decks': e['decks'],
                    'deck_pct': round(100.0 * e['decks'] / n_decks, 2),
                    'avg_per_deck': round(e['mb'] / n_decks, 3),
                    'top_sets': [s for s, _ in e['sets'].most_common(4)],
                    'top_arch': [a for a, _ in e['arch'].most_common(3)],
                    'top_ci': [c for c, _ in e['ci'].most_common(4)]})
    out.sort(key=lambda x: -x['mb_total'])
    json.dump({'meta': {'decks': n_decks, 'mainboard_cards': mt_total,
                        'events': len(sel), 'range': [sel[-1]['date'], sel[0]['date']]},
               'cards': out}, open(os.path.join(DATA, 'metagame_cards.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    json.dump(decks, open(os.path.join(DATA, 'metagame_decks.json'), 'w', encoding='utf-8'), ensure_ascii=False)

    print('\n牌型分布 Top 20:')
    for a, c in arch_counter.most_common(20):
        print('  %-28s %d' % (a, c))
    print('\n色组分布 Top 16:')
    for a, c in ci_counter.most_common(16):
        print('  %-14s %d' % ('/'.join(a) or '-', c))
    print('\n主牌入牌率 Top 25:')
    for x in out[:25]:
        print('  %-38s %-9s %4d张 %5.1f%%  %s' % (x['name'][:38], x['rarity'], x['mb_total'],
                                                   x['deck_pct'], x['zhs']))


if __name__ == '__main__':
    main()
