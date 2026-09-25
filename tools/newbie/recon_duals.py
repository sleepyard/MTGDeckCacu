#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""非金双色地侦查：标准牌池里 rarity<=uncommon 的地，按 产色数 / 是否横置进场 分类。
输出 JSON 缓存 + 摘要。用于判断「4 金全部留给咒语」的双色地可行性。
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json, os, re, subprocess, time, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'data')
os.makedirs(DATA, exist_ok=True)
UA = 'MinisMTG/1.0'


def scry(q, cache_name):
    cp = os.path.join(DATA, cache_name)
    if os.path.exists(cp):
        return json.load(open(cp, encoding='utf-8'))
    out, page = [], 1
    while True:
        url = 'https://api.scryfall.com/cards/search?q=' + q + ('&page=%d' % page if page > 1 else '') + '&unique=cards'
        for attempt in range(5):
            r = subprocess.run(['curl', '-s', '-m', '30', '-A', UA, url], capture_output=True, text=True)
            try:
                d = json.loads(r.stdout)
            except Exception:
                d = None
            if d and d.get('data') is not None:
                break
            time.sleep(2 * (attempt + 1))
        if not d or d.get('data') is None:
            print('FAIL page', page, r.stdout[:200]); break
        out += d['data']
        if not d.get('has_more'):
            break
        page += 1
        time.sleep(0.12)
    json.dump(out, open(cp, 'w', encoding='utf-8'), ensure_ascii=False)
    time.sleep(0.12)
    return out


def colors_added(c):
    txt = c.get('oracle_text') or ''
    if not txt and c.get('card_faces'):
        txt = '\n'.join(f.get('oracle_text', '') for f in c['card_faces'])
    syms = set(re.findall(r'Add \{([WUBRG])\}', txt)) | set(re.findall(r'Add \{([WUBRG])\}', txt))
    # 处理 "Add {W} or {U}" 已被上一条覆盖；处理 "Add one mana of any color"
    anyc = 'any color' in txt or 'any one color' in txt
    return sorted(syms), anyc, txt


def main():
    q = 'f%3Astandard+game%3Aarena+t%3Aland+r%3C%3Duncommon'
    cards = scry(q, 'std_lands_uncommon.json')
    rows = []
    for c in cards:
        syms, anyc, txt = colors_added(c)
        if len(syms) < 2 and not anyc:
            continue
        always_tapped = bool(re.search(r'enters (the battlefield )?tapped(?! unless)', txt)) and 'unless' not in txt.split('tapped')[1][:60] if 'tapped' in txt else False
        rows.append({
            'name': c['name'], 'set': c['set'], 'rarity': c['rarity'],
            'colors': syms, 'any_color': anyc,
            'always_tapped': always_tapped,
            'text': txt.strip()[:220],
        })
    rows.sort(key=lambda r: (r['set'], r['name']))
    json.dump(rows, open(os.path.join(DATA, 'nongold_duals.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('非金（common/uncommon）标准地 =', len(rows))
    from collections import Counter
    print('按系列:', dict(Counter(r['set'] for r in rows)))
    print('按稀有度:', dict(Counter(r['rarity'] for r in rows)))
    print('永久横置进场:', sum(1 for r in rows if r['always_tapped']))
    print()
    for r in rows:
        tag = 'TAP' if r['always_tapped'] else '   '
        print('%-38s %-4s %-4s %s %s' % (r['name'][:38], r['set'], r['rarity'], tag, r['text'].replace('\n', ' | ')[:95]))


if __name__ == '__main__':
    main()
