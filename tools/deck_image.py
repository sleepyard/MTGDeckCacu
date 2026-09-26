#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""牌表图片生成：把 MTGA 导入格式牌表渲染成 Untapped.gg 风格的卡牌网格图。

用法:
  python tools/deck_image.py <牌表.txt> [--out 输出.png] [--title 标题] [--subtitle 副标题]

行为:
  - 主牌按类别分组（生物/鹏洛客/瞬间/法术/结界/神器/地），每组另起一行、
    组内按法术力值升序，每张去重牌一格；格顶标签条（Untapped 样式）左侧 "xN" 数量、
    右侧法术力费用；备牌（若有）列于右侧（>8 种双列）。
  - 顶部标题栏含类型统计与造价指标行（签名/物质点/PP核心/PP全量，deck_cost 口径，
    数据缺失时自动省略）。
  - 卡图取 Scryfall image_uris.normal（双面牌取正面），下载缓存到
    tools/cache/card_images/（gitignored），复用 mtg_tool 的查询缓存与节流。
  - 顶部标题栏含牌数统计（生物/法术/瞬间/结界/神器/鹏洛客/地）。

依赖: Pillow（惰性导入，缺失时退出码 3 并提示 pip install pillow）。
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mtg_tool  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CACHE_DIR = os.path.join(mtg_tool.CACHE_DIR if hasattr(mtg_tool, "CACHE_DIR") else
                         os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache"),
                         "card_images")
UA = "NeoMtgDeckCacu-deck-image/1.0"
TILE_W, TILE_H = 244, 340          # Scryfall normal = 488x680 的半尺寸
COLS = 8
HEADER_H = 122
LABEL_H = 24                       # 每格顶部标签条（Untapped 样式：左 xN、右法术力费）

GROUP_ORDER = {"Creature": 0, "Planeswalker": 1, "Instant": 2, "Sorcery": 3,
               "Enchantment": 4, "Artifact": 5, "Land": 6, "Other": 7}

PIP_COLORS = {"W": (235, 225, 190), "U": (110, 160, 245), "B": (185, 155, 210),
              "R": (240, 120, 90), "G": (120, 200, 130), "C": (190, 190, 190)}


def _load_pil():
    try:
        from PIL import Image, ImageDraw, ImageFont
        return Image, ImageDraw, ImageFont
    except ImportError:
        print("[错误] 需要 Pillow：pip install pillow", file=sys.stderr)
        sys.exit(3)


def _font(ImageFont, size):
    for cand in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\arial.ttf"):
        if os.path.exists(cand):
            try:
                return ImageFont.truetype(cand, size)
            except Exception:
                pass
    return ImageFont.load_default()


def parse_deck(path):
    """返回 (main, side)：[（数量, 牌名）]，识别 Deck/Sideboard/Companion/Commander 段。"""
    main, side, zone = [], [], "main"
    for raw in open(path, encoding="utf-8"):
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if low in ("deck", "main"):
            zone = "main"
            continue
        if low in ("sideboard", "companion"):
            zone = "side"
            continue
        if low == "commander":
            zone = "main"
            continue
        parts = line.split(" ", 1)
        if len(parts) == 2 and parts[0].isdigit():
            (main if zone == "main" else side).append((int(parts[0]), parts[1].strip()))
    return main, side


def card_info(name):
    """Scryfall 查牌：返回 (image_url, type_line, cmc, mana_cost)。"""
    try:
        card = mtg_tool.scryfall_get("/cards/named", {"exact": name})
    except Exception as exc:
        print("[警告] 查询失败 %s: %s" % (name, exc), file=sys.stderr)
        return None, "", 0.0, ""
    tline, cmc = card.get("type_line", ""), card.get("cmc", 0.0)
    mana = card.get("mana_cost", "")
    if "image_uris" in card:
        return card["image_uris"].get("normal"), tline, cmc, mana
    faces = card.get("card_faces") or []
    if faces and not mana:
        mana = faces[0].get("mana_cost", "")
    if faces and "image_uris" in faces[0]:
        return faces[0]["image_uris"].get("normal"), tline, cmc, mana
    return None, tline, cmc, mana


def fetch_image(url, key):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, key + ".png")
    if not os.path.exists(path):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as f:
            f.write(r.read())
        time.sleep(0.1)
    return path


def type_bucket(type_line):
    for t in ("Creature", "Instant", "Sorcery", "Enchantment", "Artifact", "Planeswalker", "Land"):
        if t in type_line:
            return t
    return "Other"


def cost_line(main):
    """造价指标行（deck_cost 口径）；数据缺失时返回空串。"""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "newbie"))
        import deck_cost
        sig, unk, _extra = deck_cost.census([(n, q, "main") for q, n in main])
        if unk:
            return ""
        _ok, _tier, budget_txt = deck_cost.budget_check(sig)
        m = deck_cost.metrics(sig)
        return ("造价 %s ｜ 物质点 %s ｜ PP核心 %.1f 包 ｜ PP全量 %.1f 包"
                % (deck_cost.fmt_sig(sig), budget_txt.split("（")[0].strip(),
                   m["packs_core"], m["packs_all"]))
    except Exception:
        return ""


def render(main, side, title, subtitle, out):
    Image, ImageDraw, ImageFont = _load_pil()
    f_title = _font(ImageFont, 30)
    f_sub = _font(ImageFont, 18)
    f_label = _font(ImageFont, 17)

    entries = []  # (cmc, is_land, count, name, img_path, bucket, mana_cost)
    counts = {}
    fails = []
    for zone_entries in (main,):
        for qty, name in zone_entries:
            url, tline, cmc, mana = card_info(name)
            bucket = type_bucket(tline)
            counts[bucket] = counts.get(bucket, 0) + qty
            img = fetch_image(url, name.replace(" ", "_").replace("/", "_")) if url else None
            if img is None:
                fails.append(name)
            entries.append((cmc, bucket == "Land", qty, name, img, bucket, mana))

    entries.sort(key=lambda e: (GROUP_ORDER.get(e[5], 99), e[0], e[3]))
    total = sum(q for q, _ in main)

    side_entries = []
    for qty, name in side:
        url, _tl, _cmc, mana = card_info(name)
        img = fetch_image(url, name.replace(" ", "_").replace("/", "_")) if url else None
        side_entries.append((qty, name, img, mana))

    positions = []  # 与 entries 对齐的 (col, row)；类别变化时另起一行
    col, row, prev_group = 0, 0, None
    for e in entries:
        g = GROUP_ORDER.get(e[5], 99)
        if prev_group is not None and g != prev_group and col != 0:
            col, row = 0, row + 1
        positions.append((col, row))
        col += 1
        if col == COLS:
            col, row = 0, row + 1
        prev_group = g
    cell_h = LABEL_H + TILE_H
    rows = row + 1
    side_cols = 1 if len(side_entries) <= 8 else 2
    side_w = side_cols * (TILE_W + 10) + 10 if side_entries else 0
    side_rows = (len(side_entries) + side_cols - 1) // side_cols
    h = HEADER_H + max(rows, side_rows) * cell_h + 20
    w = COLS * TILE_W + side_w + 20
    canvas = Image.new("RGB", (w, h), (24, 26, 30))
    draw = ImageDraw.Draw(canvas)

    draw.text((16, 10), title, font=f_title, fill=(240, 240, 240))
    stat = "Main (%d): " % total + "  ".join(
        "%d %s" % (counts[k], k) for k in
        ("Creature", "Instant", "Sorcery", "Enchantment", "Artifact", "Planeswalker", "Land")
        if counts.get(k))
    if side:
        stat += "    Sideboard (%d)" % sum(q for q, _ in side)
    draw.text((16, 52), stat, font=f_sub, fill=(170, 175, 185))
    cost = cost_line(main)
    if cost:
        draw.text((16, 82), cost, font=f_sub, fill=(150, 190, 230))
    if subtitle:
        draw.text((w - draw.textlength(subtitle, font=f_sub) - 16, 14), subtitle,
                  font=f_sub, fill=(170, 175, 185))

    def draw_mana(x_right, y, mana):
        pips = re.findall(r"\{([^}]*)\}", mana or "")
        widths = [draw.textlength(p, font=f_label) + 3 for p in pips]
        x = x_right - sum(widths)
        for p, pw in zip(pips, widths):
            color = PIP_COLORS.get(p.upper(), (190, 190, 190))
            draw.text((x, y), p, font=f_label, fill=color)
            x += pw

    def paste(img_path, x, y, qty, mana):
        draw.rectangle([x, y, x + TILE_W, y + LABEL_H], fill=(16, 18, 22))
        draw.text((x + 6, y + 3), "x%d" % qty, font=f_label, fill=(255, 255, 120))
        draw_mana(x + TILE_W - 6, y + 3, mana)
        y_img = y + LABEL_H
        if img_path:
            tile = Image.open(img_path).resize((TILE_W, TILE_H))
            canvas.paste(tile, (x, y_img))
        else:
            draw.rectangle([x, y_img, x + TILE_W, y_img + TILE_H], outline=(90, 90, 90))

    for (_cmc, _il, qty, _name, img, _b, mana), (c, r) in zip(entries, positions):
        paste(img, c * TILE_W + 10, HEADER_H + r * cell_h, qty, mana)
    for j, (qty, _name, img, mana) in enumerate(side_entries):
        paste(img, COLS * TILE_W + 10 + (j // side_rows) * (TILE_W + 10),
              HEADER_H + (j % side_rows) * cell_h, qty, mana)

    canvas.save(out)
    print("[完成] %s（主 %d / 备 %d，%d 格）" % (out, total, sum(q for q, _ in side), len(entries)))
    if fails:
        print("[警告] 无卡图: %s" % ", ".join(fails), file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="牌表 → Untapped.gg 风格卡牌网格图")
    ap.add_argument("deck")
    ap.add_argument("--out", help="输出 PNG（默认 <牌表>.png）")
    ap.add_argument("--title", default=None)
    ap.add_argument("--subtitle", default="")
    args = ap.parse_args()
    main_entries, side_entries = parse_deck(args.deck)
    if not main_entries:
        print("[错误] 牌表为空或格式不符", file=sys.stderr)
        sys.exit(2)
    title = args.title or os.path.splitext(os.path.basename(args.deck))[0]
    out = args.out or os.path.splitext(args.deck)[0] + ".png"
    render(main_entries, side_entries, title, args.subtitle, out)


if __name__ == "__main__":
    main()
