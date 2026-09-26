#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 MTGA 导入格式牌表渲染成适合中文社区分享的卡牌网格图。

用法::

  python tools/deck_image.py <牌表.txt> [--out 输出.png] [--title 标题]
      [--subtitle 副标题] [--author 作者] [--format 赛制] [--record 战绩]

卡图优先使用 Scryfall 的简中印刷版本，并缓存到 ``tools/cache/card_images``。
版式参考 Untapped.gg：重复牌使用卡图顶部名牌条表达数量，主牌和备牌分区显示，
顶部提供中文标题、颜色身份、类型统计和造价信息。Pillow 采用惰性导入，方便其余
牌表工具在无图像依赖的环境中使用。
"""

import argparse
import math
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mtg_tool  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CACHE_DIR = os.path.join(
    mtg_tool.CACHE_DIR if hasattr(mtg_tool, "CACHE_DIR") else
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache"),
    "card_images",
)
UA = "NeoMtgDeckCacu-deck-image/1.0"
TILE_W, TILE_H = 244, 340
CARD_RATIO = TILE_H / float(TILE_W)
MAX_OUTPUT_W = 1600
MIN_TILE_W = 164
MAX_BARS = 4
BAR_H = 20                         # 兼容旧脚本导入；实际按 tile_h 动态缩放
COL_CELLS = 4
SIDE_COL_CELLS = 8
GAP = 10
MARGIN = 20
SEC_H = 38
FOOTER_H = 28

GROUP_ORDER = {"Creature": 0, "Planeswalker": 1, "Instant": 2, "Sorcery": 3,
               "Enchantment": 4, "Artifact": 5, "Land": 6, "Other": 7}
STAT_LABEL = {"Creature": ("生物", "生物"), "Planeswalker": ("鹏洛客", "鹏洛客"),
              "Instant": ("瞬间", "瞬间"), "Sorcery": ("法术", "法术"),
              "Enchantment": ("结界", "结界"), "Artifact": ("神器", "神器"),
              "Land": ("地", "地"), "Other": ("其他", "其他")}
STAT_LABEL_EN = {"Creature": ("Creature", "Creatures"),
                 "Planeswalker": ("Planeswalker", "Planeswalkers"),
                 "Instant": ("Instant", "Instants"), "Sorcery": ("Sorcery", "Sorceries"),
                 "Enchantment": ("Enchantment", "Enchantments"),
                 "Artifact": ("Artifact", "Artifacts"), "Land": ("Land", "Lands"),
                 "Other": ("Other", "Others")}
PIP_COLORS = {"W": (235, 225, 190), "U": (110, 160, 245), "B": (185, 155, 210),
              "R": (240, 120, 90), "G": (120, 200, 130), "C": (190, 190, 190)}
IDENTITY_ORDER = ("W", "U", "B", "R", "G")
IDENTITY_BG = {"W": (218, 192, 120), "U": (77, 143, 224), "B": (144, 112, 171),
               "R": (224, 89, 62), "G": (70, 164, 103)}
C_TITLE = (248, 249, 250)
C_STAT = (202, 207, 214)
C_COST = (143, 205, 226)
C_SEC = (231, 235, 239)
C_BAR_BG = (16, 18, 22)
C_BAR_TXT = (240, 240, 240)
C_BODY = (22, 24, 28)
C_LINE = (83, 91, 101)
C_ACCENT = (36, 191, 146)


def _load_pil():
    try:
        from PIL import Image, ImageDraw, ImageFont
        return Image, ImageDraw, ImageFont
    except ImportError:
        print("[错误] 需要 Pillow：pip install pillow", file=sys.stderr)
        sys.exit(3)


def _font(ImageFont, size, bold=False):
    candidates = (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\arialbd.ttf") if bold else ()
    candidates += (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\arial.ttf")
    for cand in candidates:
        if os.path.exists(cand):
            try:
                return ImageFont.truetype(cand, size)
            except Exception:
                pass
    return ImageFont.load_default()


def parse_deck(path):
    """返回 (main, side)：[(数量, 牌名)]，识别常见 MTGA 分区标题。"""
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


def _card_image_url(card):
    """单卡对象取正面 normal 图（双面牌取 card_faces[0]）。"""
    if "image_uris" in card:
        return card["image_uris"].get("normal")
    faces = card.get("card_faces") or []
    if faces and "image_uris" in faces[0]:
        return faces[0]["image_uris"].get("normal")
    return None


def _card_info_full(name):
    """英文牌面查询，内部返回颜色身份等完整信息。"""
    try:
        card = mtg_tool.scryfall_get("/cards/named", {"exact": name})
    except Exception as exc:
        print("[警告] 查询失败 %s: %s" % (name, exc), file=sys.stderr)
        return None, "", 0.0, "", ()
    tline, cmc = card.get("type_line", ""), card.get("cmc", 0.0) or 0.0
    mana = card.get("mana_cost", "")
    faces = card.get("card_faces") or []
    if faces and not mana:
        mana = faces[0].get("mana_cost", "")
    return _card_image_url(card), tline, cmc, mana, tuple(card.get("colors") or ())


_CARD_COLOR_CACHE = {}


def card_info(name):
    """兼容旧调用：返回 (image_url, type_line, cmc, mana_cost)。"""
    full = _card_info_full(name)
    _CARD_COLOR_CACHE[name] = full[4]
    return full[:4]


def zhs_card_info(name):
    """返回简中印刷图和印刷名；没有简中版本时返回 (None, None)。"""
    try:
        res = mtg_tool.scryfall_get(
            "/cards/search", {"q": '!"%s" lang:zhs' % name, "unique": "prints"}
        )
    except Exception:
        return None, None
    if not isinstance(res, dict):
        return None, None
    for card in res.get("data", []):
        url = _card_image_url(card)
        if url:
            return url, card.get("printed_name") or card.get("name")
    return None, None


def zhs_image_url(name):
    """兼容旧调用：只返回简中印刷卡图 URL。"""
    return zhs_card_info(name)[0]


def _cache_key(name):
    """把中英文牌名变成跨平台稳定的缓存文件名。"""
    key = re.sub(r"[^\w.-]+", "_", name, flags=re.UNICODE).strip("._")
    return key or "card"


def fetch_image(url, key):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, key + ".png")
    if not os.path.exists(path):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as response, open(path, "wb") as output:
            output.write(response.read())
        time.sleep(0.1)
    return path


def type_bucket(type_line):
    front = (type_line or "").split(" // ")[0]
    for card_type in ("Creature", "Instant", "Sorcery", "Enchantment", "Artifact",
                      "Planeswalker", "Land"):
        if card_type in front:
            return card_type
    return "Other"


def cost_line(main):
    """按 deck_cost.py 口径生成造价行；牌张稀有度未知时整行省略。"""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "newbie"))
        import deck_cost
        sig, unknown, _extra = deck_cost.census([(name, qty, "main") for qty, name in main])
        if unknown:
            return ""
        metrics = deck_cost.metrics(sig)
        gold = sig.get("mythic", 0) * deck_cost.MYTHIC + sig.get("rare", 0) * deck_cost.RARE
        return ("造价 %s ｜ 物质点 %.1f（金位 %.1f/上限 %.1f）｜ PP核心 %.1f 包 ｜ PP全量 %.1f 包"
                % (deck_cost.fmt_sig(sig), metrics["tot_a"], gold, deck_cost.BUDGET_MAX,
                   metrics["packs_core"], metrics["packs_all"]))
    except Exception:
        return ""


def _ellipsize(draw, text, font, max_w):
    if not text or max_w <= 0:
        return ""
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"


def _wrap(draw, text, font, max_w, max_lines):
    """按空格换行；中文标签由调用方插入空格，保证窄图也不会溢出。"""
    words, lines, current = text.split(" "), [], ""
    for word in words:
        trial = (current + " " + word).strip()
        if current and draw.textlength(trial, font=font) > max_w:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _ellipsize(draw, lines[-1], font, max_w)
    return lines


def _identity(colors):
    color_set = set(colors)
    return [color for color in IDENTITY_ORDER if color in color_set]


def render(main, side, title, subtitle, out, author="", format_name="", record="", language="zh"):
    """渲染牌表；旧的五参数调用仍然有效。"""
    Image, ImageDraw, ImageFont = _load_pil()
    english = language.lower() in ("en", "eng", "english")
    stat_labels = STAT_LABEL_EN if english else STAT_LABEL
    section_main = "Main Deck" if english else "主牌"
    section_side = "Sideboard" if english else "备牌"
    card_unit = "cards" if english else "张"
    footer = ("NeoMtgDeckCacu · Card art and printings from Scryfall" if english else
              "NeoMtgDeckCacu · 卡图与印刷信息来自 Scryfall")
    f_title = _font(ImageFont, 31, bold=True)
    f_meta = _font(ImageFont, 15)
    f_stat = _font(ImageFont, 17, bold=True)
    f_sec = _font(ImageFont, 20, bold=True)
    f_footer = _font(ImageFont, 12)
    f_probe = _font(ImageFont, 17)

    fails, zhs_hits = [], set()
    counts, info, identities, entries = {}, {}, set(), []

    def lookup(name):
        en_url, type_line, cmc, mana = card_info(name)
        colors = _CARD_COLOR_CACHE.get(name, ())
        zhs_url, printed_name = zhs_card_info(name)
        image_url = zhs_url or en_url
        key = ("zhs_" if zhs_url else "") + _cache_key(name)
        image_path = None
        if image_url:
            try:
                image_path = fetch_image(image_url, key)
            except Exception as exc:
                print("[警告] 卡图下载失败 %s: %s" % (name, exc), file=sys.stderr)
        if image_path is None:
            fails.append(name)
        if zhs_url:
            zhs_hits.add(name)
        display_name = printed_name if printed_name and not english else name
        return type_line, cmc, mana, image_path, display_name, tuple(colors)

    for quantity, name in main:
        if name not in info:
            info[name] = lookup(name)
        type_line, cmc, _mana, _image, _display, colors = info[name]
        bucket = type_bucket(type_line)
        counts[bucket] = counts.get(bucket, 0) + quantity
        identities.update(colors)
        entries.append((cmc, bucket, quantity, name))
    for _quantity, name in side:
        if name not in info:
            info[name] = lookup(name)
        identities.update(info[name][5])
    entries.sort(key=lambda entry: (GROUP_ORDER.get(entry[1], 99), entry[0], entry[3]))

    def split_cells(items):
        cells = []
        for quantity, name in items:
            while quantity > MAX_BARS:
                cells.append((name, MAX_BARS))
                quantity -= MAX_BARS
            cells.append((name, quantity))
        return cells

    main_cells = split_cells([(quantity, name) for _cmc, _bucket, quantity, name in entries])
    side_cells = split_cells(side)
    main_cols = min(5, max(1, math.ceil(len(main_cells) / 4)))
    side_cols = min(2, max(1, math.ceil(len(side_cells) / 8))) if side_cells else 0
    total_cols = main_cols + side_cols
    gap = max(8, min(12, round(GAP * max(0.8, 6.0 / max(6, total_cols)))))
    tile_w = min(TILE_W, max(MIN_TILE_W,
                             (MAX_OUTPUT_W - 2 * MARGIN - gap * max(0, total_cols - 1)) // total_cols))
    tile_h = max(228, round(tile_w * CARD_RATIO))
    main_w = main_cols * tile_w + (main_cols - 1) * gap
    side_w = side_cols * tile_w + (side_cols - 1) * gap if side_cols else 0
    side_x = MARGIN + main_w + gap if side_cols else 0
    width = side_x + side_w + MARGIN if side_cols else main_w + 2 * MARGIN
    main_rows = math.ceil(len(main_cells) / main_cols)
    side_rows = math.ceil(len(side_cells) / side_cols) if side_cells else 0
    main_h = main_rows * tile_h + max(0, main_rows - 1) * gap
    side_h = side_rows * tile_h + max(0, side_rows - 1) * gap if side_rows else 0
    body_h = max(main_h, side_h)

    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    available = width - 2 * MARGIN
    total = sum(quantity for quantity, _name in main)
    stats_parts = []
    for bucket in ("Planeswalker", "Creature", "Instant", "Sorcery", "Enchantment",
                   "Artifact", "Land", "Other"):
        if counts.get(bucket):
            label = stat_labels[bucket][counts[bucket] != 1]
            stats_parts.append("%d %s" % (counts[bucket], label))
    stats_text = " · ".join(stats_parts)
    stat_lines = _wrap(probe, stats_text, f_stat, available, 2) if stats_text else []
    cost = cost_line(main)
    cost_lines = _wrap(probe, cost, f_probe, available, 3) if cost else []
    title = _ellipsize(probe, title, f_title, available)
    meta_text = " · ".join(part for part in (author, format_name) if part)
    header_h = 14 + 43 + (24 if meta_text else 0) + len(stat_lines) * 25 + len(cost_lines) * 24 + 12
    body_y = header_h + SEC_H
    height = body_y + body_h + FOOTER_H

    canvas = Image.new("RGB", (width, height), C_BODY)
    draw = ImageDraw.Draw(canvas)
    top_color = (52, 55, 63)
    for line_y in range(header_h):
        ratio = line_y / float(max(1, header_h - 1))
        color = tuple(round(top_color[i] * (1 - ratio) + C_BODY[i] * ratio) for i in range(3))
        draw.line((0, line_y, width, line_y), fill=color)
    accent = IDENTITY_BG.get(_identity(identities)[0], C_ACCENT) if identities else C_ACCENT
    draw.rectangle((0, header_h - 3, width, header_h), fill=accent)

    x = MARGIN
    for color in _identity(identities):
        draw.ellipse((x, 23, x + 23, 46), fill=IDENTITY_BG[color], outline=(230, 235, 238))
        draw.text((x + 7, 25), color, font=f_meta, fill=(18, 22, 25))
        x += 29
    badge_text = " · ".join(part for part in (subtitle, record) if part)
    badge = _ellipsize(draw, badge_text, f_meta, min(370, available // 3)) if badge_text else ""
    badge_w = draw.textlength(badge, font=f_meta) + 26 if badge else 0
    title_x = x + 8 if x > MARGIN else MARGIN
    title_max = max(80, width - title_x - MARGIN - badge_w - (16 if badge else 0))
    draw.text((title_x, 17), _ellipsize(draw, title, f_title, title_max), font=f_title, fill=C_TITLE)
    if badge:
        badge_x = width - MARGIN - badge_w
        draw.rounded_rectangle((badge_x, 18, width - MARGIN, 49), radius=9,
                               fill=(26, 29, 34), outline=(69, 75, 84))
        draw.text((badge_x + 13, 25), badge, font=f_meta, fill=C_STAT)

    y = 58
    if meta_text:
        draw.text((MARGIN, y), _ellipsize(draw, meta_text, f_meta, available),
                  font=f_meta, fill=C_STAT)
        y += 24
    for line in stat_lines:
        draw.text((MARGIN, y), line, font=f_stat, fill=C_TITLE)
        y += 25
    for line in cost_lines:
        draw.text((MARGIN, y), line, font=f_probe, fill=C_COST)
        y += 24

    def section_heading(x0, section_w, text):
        text_w = draw.textlength(text, font=f_sec)
        text_x = x0 + (section_w - text_w) / 2
        line_y = header_h + SEC_H // 2 + 1
        draw.line((x0, line_y, max(x0, text_x - 14), line_y), fill=C_LINE, width=1)
        draw.line((text_x + text_w + 14, line_y, x0 + section_w, line_y), fill=C_LINE, width=1)
        draw.text((text_x, header_h + 7), text, font=f_sec, fill=C_SEC)

    section_heading(MARGIN, main_w, "%s · %d %s" % (section_main, total, card_unit))
    if side_cols:
        section_heading(side_x, side_w, "%s · %d %s" %
                        (section_side, sum(quantity for quantity, _name in side), card_unit))

    bar_h = max(16, round(tile_h * 0.059))
    bar_font = _font(ImageFont, max(11, min(15, round(tile_w * 0.061))))
    pip_font = _font(ImageFont, max(10, min(14, round(tile_w * 0.057))), bold=True)

    def mana_width(mana):
        return sum(max(13, draw.textlength(pip, font=pip_font)) + 4
                   for pip in re.findall(r"\{([^}]*)\}", mana or ""))

    def draw_mana(x_right, y0, mana):
        pips = re.findall(r"\{([^}]*)\}", mana or "")
        x0 = x_right - mana_width(mana)
        pip_h = max(13, bar_h - 4)
        for pip in pips:
            pip_w = max(13, draw.textlength(pip, font=pip_font))
            fill = PIP_COLORS.get(pip.upper(), (190, 190, 190))
            draw.rounded_rectangle((x0, y0 + 2, x0 + pip_w, y0 + 2 + pip_h), radius=4, fill=fill)
            draw.text((x0 + (pip_w - draw.textlength(pip, font=pip_font)) / 2, y0 + 2),
                      pip, font=pip_font, fill=(20, 23, 27))
            x0 += pip_w + 4

    def draw_cell(x0, y0, name, bars):
        _type_line, _cmc, mana, image_path, display_name, _colors = info[name]
        if image_path:
            with Image.open(image_path) as source:
                resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS",
                                     getattr(Image, "LANCZOS", 1))
                tile = source.convert("RGB").resize((tile_w, tile_h), resampling)
            canvas.paste(tile, (x0, y0))
        else:
            draw.rectangle((x0, y0, x0 + tile_w, y0 + tile_h), fill=(36, 39, 44), outline=C_LINE)
            draw.text((x0 + 8, y0 + tile_h // 2), display_name, font=bar_font, fill=(155, 160, 166))
        mana_w = mana_width(mana)
        name_w = max(30, tile_w - 14 - (mana_w + 9 if mana_w else 0))
        label = _ellipsize(draw, display_name, bar_font, name_w)
        for index in range(bars):
            bar_y = y0 + index * bar_h
            draw.rectangle((x0, bar_y, x0 + tile_w, bar_y + bar_h), fill=C_BAR_BG)
            draw.line((x0, bar_y + bar_h - 1, x0 + tile_w, bar_y + bar_h - 1), fill=(53, 58, 66))
            font_size = getattr(bar_font, "size", 12)
            draw.text((x0 + 6, bar_y + max(1, (bar_h - font_size) // 2)), label,
                      font=bar_font, fill=C_BAR_TXT)
            draw_mana(x0 + tile_w - 6, bar_y, mana)

    for index, (name, bars) in enumerate(main_cells):
        column, row = divmod(index, main_rows)
        draw_cell(MARGIN + column * (tile_w + gap), body_y + row * (tile_h + gap), name, bars)
    for index, (name, bars) in enumerate(side_cells):
        column, row = divmod(index, side_rows)
        draw_cell(side_x + column * (tile_w + gap), body_y + row * (tile_h + gap), name, bars)

    footer_y = body_y + body_h + 6
    draw.text((MARGIN, footer_y), _ellipsize(draw, footer, f_footer, width - 2 * MARGIN),
              font=f_footer, fill=(123, 129, 138))
    canvas.save(out)
    print("[完成] %s（主 %d / 备 %d，主 %d 格 %d 列%s）" %
          (out, total, sum(quantity for quantity, _name in side), len(main_cells), main_cols,
           "，备 %d 格 %d 列" % (len(side_cells), side_cols) if side_cols else ""))
    print("[卡图] 简中命中 %d/%d 种: %s" %
          (len(zhs_hits), len(info), ", ".join(sorted(zhs_hits)) or "（无）"))
    if fails:
        print("[警告] 无卡图: %s" % ", ".join(sorted(set(fails))), file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="牌表 → 中文社区牌表图片")
    parser.add_argument("deck")
    parser.add_argument("--out", help="输出 PNG（默认 <牌表>.png）")
    parser.add_argument("--title", default=None)
    parser.add_argument("--subtitle", default="", help="标题右侧徽章文字")
    parser.add_argument("--author", default="", help="作者名")
    parser.add_argument("--format", dest="format_name", default="", help="赛制或环境")
    parser.add_argument("--record", default="", help="战绩，例如 7-0")
    parser.add_argument("--lang", choices=("zh", "en"), default="zh", help="标签语言（默认 zh）")
    args = parser.parse_args()
    main_entries, side_entries = parse_deck(args.deck)
    if not main_entries:
        print("[错误] 牌表为空或格式不符", file=sys.stderr)
        sys.exit(2)
    title = args.title or os.path.splitext(os.path.basename(args.deck))[0]
    out = args.out or os.path.splitext(args.deck)[0] + ".png"
    render(main_entries, side_entries, title, args.subtitle, out, args.author,
           args.format_name, args.record, args.lang)


if __name__ == "__main__":
    main()
