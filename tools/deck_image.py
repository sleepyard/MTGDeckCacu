#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""牌表图片生成：把 MTGA 导入格式牌表渲染成 Untapped.gg 风格的卡牌网格图。

用法:
  python tools/deck_image.py <牌表.txt> [--out 输出.png] [--title 标题] [--subtitle 副标题]

版式（对齐 Untapped.gg 牌表图模板）:
  - 每种牌占一格，格顶叠放 N 条名牌条（N=该格张数，每条 ~20px 深色底，左侧白色牌名、
    过长截断加省略号，右侧彩色法术力费字母）；张数 >4 的牌拆成多格（每格 ≤4 条，
    如 11 张树林拆 4/4/3 三格）。
  - 主牌区列优先（column-major）排布，每列最多 4 格，列数 = ceil(格数/4)；
    类别分组顺序保留（生物/鹏洛客/瞬间/法术/结界/神器/地，组内按法术力值升序），
    但组间不强制换列、连续填充；画布宽按实际列数计算。
  - 分节标头：主牌区上方居中 "Main Deck (60)"，备牌区上方 "Sideboard (15)"；
    备牌在右侧独立列（>8 种可双列），备牌格同款名牌条样式。
  - 顶部标题栏不超过 3 行：行 1 左标题、右副标题（右对齐）；行 2 类型统计
    （如 "26 Creatures 10 Instants 1 Sorcery 23 Lands"）；行 3 造价行。
    窄画布时类型统计与造价合并为一行（" ｜ " 分隔），长文本自行换行，绝不超出画布宽度。
  - 造价行（tools/newbie/deck_cost.py 口径，基本地不计入任何数字）：
    签名 + 物质点全量（普通/非普通也计入，即 metrics 的 tot_a）并括注金位预算点
    （秘稀×24.59 + 稀有×5.10，上限 40.8）+ PP核心 + PP全量；形如
    "造价 4r8u25c ｜ 物质点 63.7（金位 20.4/上限 40.8）｜ PP核心 22.2 包 ｜ PP全量 75.0 包"。
    rarity_map 数据缺失时整行省略。
  - 卡图优先简中（zhs）印刷：Scryfall cards/search q=!"<牌名>" lang:zhs unique=prints
    取首个带 image_uris 的结果（双面牌取正面）；查不到或查询失败回退英文卡图。
    中文图缓存键加 zhs_ 前缀分开存（tools/cache/card_images/，gitignored），
    复用 mtg_tool 的查询缓存与节流；无 zhs 图属正常，仅汇总进 fails 警告。

依赖: Pillow（惰性导入，缺失时退出码 3 并提示 pip install pillow）。
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

CACHE_DIR = os.path.join(mtg_tool.CACHE_DIR if hasattr(mtg_tool, "CACHE_DIR") else
                         os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache"),
                         "card_images")
UA = "NeoMtgDeckCacu-deck-image/1.0"
TILE_W, TILE_H = 244, 340          # Scryfall normal = 488x680 的半尺寸
BAR_H = 20                         # 每副本一条名牌条
MAX_BARS = 4                       # 每格最多 4 条，>4 张拆多格
COL_CELLS = 4                      # 主牌区每列最多 4 格
SIDE_COL_CELLS = 8                 # 备牌区每列最多 8 格
GAP = 10
MARGIN = 16
SEC_H = 34                         # 分节标头（Main Deck / Sideboard）高度

GROUP_ORDER = {"Creature": 0, "Planeswalker": 1, "Instant": 2, "Sorcery": 3,
               "Enchantment": 4, "Artifact": 5, "Land": 6, "Other": 7}

STAT_LABEL = {"Creature": ("Creature", "Creatures"),
              "Planeswalker": ("Planeswalker", "Planeswalkers"),
              "Instant": ("Instant", "Instants"),
              "Sorcery": ("Sorcery", "Sorceries"),
              "Enchantment": ("Enchantment", "Enchantments"),
              "Artifact": ("Artifact", "Artifacts"),
              "Land": ("Land", "Lands"),
              "Other": ("Other", "Others")}

PIP_COLORS = {"W": (235, 225, 190), "U": (110, 160, 245), "B": (185, 155, 210),
              "R": (240, 120, 90), "G": (120, 200, 130), "C": (190, 190, 190)}

C_TITLE = (240, 240, 240)
C_STAT = (170, 175, 185)
C_COST = (150, 190, 230)
C_SEC = (220, 224, 232)
C_BAR_BG = (16, 18, 22)
C_BAR_TXT = (240, 240, 240)


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


def _card_image_url(card):
    """单卡对象取正面 normal 图（双面牌取 card_faces[0]）。"""
    if "image_uris" in card:
        return card["image_uris"].get("normal")
    faces = card.get("card_faces") or []
    if faces and "image_uris" in faces[0]:
        return faces[0]["image_uris"].get("normal")
    return None


def card_info(name):
    """Scryfall 查牌（英文）：返回 (image_url, type_line, cmc, mana_cost)。"""
    try:
        card = mtg_tool.scryfall_get("/cards/named", {"exact": name})
    except Exception as exc:
        print("[警告] 查询失败 %s: %s" % (name, exc), file=sys.stderr)
        return None, "", 0.0, ""
    tline, cmc = card.get("type_line", ""), card.get("cmc", 0.0)
    mana = card.get("mana_cost", "")
    faces = card.get("card_faces") or []
    if faces and not mana:
        mana = faces[0].get("mana_cost", "")
    return _card_image_url(card), tline, cmc, mana


def zhs_image_url(name):
    """简中印刷卡图：cards/search q=!\"<牌名>\" lang:zhs unique=prints 取首个带图结果；
    查不到或失败返回 None（属正常，不告警）。"""
    try:
        res = mtg_tool.scryfall_get("/cards/search",
                                    {"q": '!"%s" lang:zhs' % name, "unique": "prints"})
    except Exception:
        return None
    for card in res.get("data", []):
        url = _card_image_url(card)
        if url:
            return url
    return None


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
    front = (type_line or "").split(" // ")[0]
    for t in ("Creature", "Instant", "Sorcery", "Enchantment", "Artifact", "Planeswalker", "Land"):
        if t in front:
            return t
    return "Other"


def cost_line(main):
    """造价指标行（deck_cost 口径，基本地不计；物质点取全量 tot_a 并括注金位预算点）。
    rarity_map 数据缺失或有未识别牌时返回空串（整行省略）。"""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "newbie"))
        import deck_cost
        sig, unk, _extra = deck_cost.census([(n, q, "main") for q, n in main])
        if unk:
            return ""
        m = deck_cost.metrics(sig)
        gold = sig.get("mythic", 0) * deck_cost.MYTHIC + sig.get("rare", 0) * deck_cost.RARE
        return ("造价 %s ｜ 物质点 %.1f（金位 %.1f/上限 %.1f）｜ PP核心 %.1f 包 ｜ PP全量 %.1f 包"
                % (deck_cost.fmt_sig(sig), m["tot_a"], gold, deck_cost.BUDGET_MAX,
                   m["packs_core"], m["packs_all"]))
    except Exception:
        return ""


def _ellipsize(draw, text, font, max_w):
    """截断到 max_w 内，超出加省略号。"""
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"


def _wrap(draw, text, font, max_w, max_lines):
    """按空格贪心换行，最多 max_lines 行，溢出末行加省略号。"""
    words, lines, cur = text.split(" "), [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if cur and draw.textlength(trial, font=font) > max_w:
            lines.append(cur)
            cur = wd
        else:
            cur = trial
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _ellipsize(draw, lines[-1], font, max_w)
    return lines


def render(main, side, title, subtitle, out):
    Image, ImageDraw, ImageFont = _load_pil()
    f_title = _font(ImageFont, 30)
    f_sub = _font(ImageFont, 18)
    f_sec = _font(ImageFont, 21)
    f_bar = _font(ImageFont, 15)

    def lookup(name, fails, zhs_hits):
        """返回 (tline, cmc, mana, img_path)；卡图优先简中，回退英文。"""
        en_url, tline, cmc, mana = card_info(name)
        zhs_url = zhs_image_url(name)
        safe = name.replace(" ", "_").replace("/", "_")
        url, key = (zhs_url, "zhs_" + safe) if zhs_url else (en_url, safe)
        img = None
        if url:
            try:
                img = fetch_image(url, key)
            except Exception as exc:
                print("[警告] 卡图下载失败 %s: %s" % (name, exc), file=sys.stderr)
        if img is None:
            fails.append(name)
        elif zhs_url:
            zhs_hits.add(name)
        return tline, cmc, mana, img

    fails, zhs_hits = [], set()
    counts, info = {}, {}
    entries = []  # (cmc, bucket, count, name)
    for qty, name in main:
        if name not in info:
            info[name] = lookup(name, fails, zhs_hits)
        tline, cmc, _mana, _img = info[name]
        bucket = type_bucket(tline)
        counts[bucket] = counts.get(bucket, 0) + qty
        entries.append((cmc, bucket, qty, name))
    for qty, name in side:
        if name not in info:
            info[name] = lookup(name, fails, zhs_hits)

    entries.sort(key=lambda e: (GROUP_ORDER.get(e[1], 99), e[0], e[3]))

    def split_cells(items):
        """（数量>4 拆格，每格 ≤4 条）→ [(name, bars)]"""
        cells = []
        for qty, name in items:
            q = qty
            while q > MAX_BARS:
                cells.append((name, MAX_BARS))
                q -= MAX_BARS
            cells.append((name, q))
        return cells

    main_cells = split_cells([(q, n) for _c, _b, q, n in entries])
    side_cells = split_cells(side)

    main_cols = max(1, math.ceil(len(main_cells) / COL_CELLS))
    main_w = main_cols * (TILE_W + GAP) - GAP
    side_cols = math.ceil(len(side_cells) / SIDE_COL_CELLS) if side_cells else 0
    side_w = side_cols * (TILE_W + GAP) - GAP if side_cols else 0
    side_x = MARGIN + main_w + GAP if side_cols else 0
    w = (side_x + side_w + MARGIN) if side_cols else (MARGIN + main_w + MARGIN)

    main_rows = min(len(main_cells), COL_CELLS)
    main_h = main_rows * TILE_H + (main_rows - 1) * GAP
    side_rows = min(len(side_cells), SIDE_COL_CELLS) if side_cells else 0
    side_h = side_rows * TILE_H + (side_rows - 1) * GAP if side_rows else 0
    body_h = max(main_h, side_h)

    # ── 顶部标题栏规划（≤3 行，绝不超出画布宽度；用临时画布施测）──
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    avail = w - 2 * MARGIN
    total = sum(q for q, _ in main)
    stats = " ".join("%d %s" % (counts[k], STAT_LABEL[k][counts[k] != 1])
                     for k in STAT_LABEL if counts.get(k))
    cost = cost_line(main)

    title = _ellipsize(probe, title, f_title, avail)
    title_w = probe.textlength(title, font=f_title)
    sub_same = bool(subtitle) and \
        title_w + 24 + probe.textlength(subtitle, font=f_sub) <= avail
    rows = [("title", title, subtitle if sub_same else "")]
    budget = 2 if (sub_same or not subtitle) else 1
    if not sub_same and subtitle:
        rows.append(("sub", subtitle, ""))
    flow = stats + ((" ｜ " + cost) if cost else "")
    if flow:
        for ln in _wrap(probe, flow, f_sub, avail, budget):
            rows.append(("flow", ln, ""))
    line_h = {"title": 40, "sub": 26, "flow": 26}
    header_h = 10 + sum(line_h[k] for k, _t, _s in rows) + 4

    h = header_h + SEC_H + body_h + MARGIN
    canvas = Image.new("RGB", (w, h), (24, 26, 30))
    draw = ImageDraw.Draw(canvas)

    y = 10
    in_cost = False
    for kind, text, sub in rows:
        if kind == "title":
            draw.text((MARGIN, y), text, font=f_title, fill=C_TITLE)
            if sub:
                draw.text((w - MARGIN - draw.textlength(sub, font=f_sub), y + 12),
                          sub, font=f_sub, fill=C_STAT)
        elif kind == "sub":
            draw.text((w - MARGIN - draw.textlength(text, font=f_sub), y),
                      text, font=f_sub, fill=C_STAT)
        else:
            # flow 行：类型统计用 C_STAT、造价段用 C_COST（同行混色，跨行延续）
            x = MARGIN
            if not in_cost and "造价 " in text:
                head, tail = text.split("造价 ", 1)
                draw.text((x, y), head, font=f_sub, fill=C_STAT)
                x += draw.textlength(head, font=f_sub)
                draw.text((x, y), "造价 " + tail, font=f_sub, fill=C_COST)
                in_cost = True
            else:
                color = C_COST if in_cost or text.startswith("造价") else C_STAT
                draw.text((x, y), text, font=f_sub, fill=color)
                if text.startswith("造价"):
                    in_cost = True
        y += line_h[kind]

    # ── 分节标头 ──
    sec_y = header_h
    sec = "Main Deck (%d)" % total
    draw.text((MARGIN + (main_w - draw.textlength(sec, font=f_sec)) / 2, sec_y + 4),
              sec, font=f_sec, fill=C_SEC)
    if side_cols:
        sec = "Sideboard (%d)" % sum(q for q, _ in side)
        draw.text((side_x + (side_w - draw.textlength(sec, font=f_sec)) / 2, sec_y + 4),
                  sec, font=f_sec, fill=C_SEC)

    body_y = header_h + SEC_H

    def mana_width(mana):
        return sum(draw.textlength(p, font=f_bar) + 3
                   for p in re.findall(r"\{([^}]*)\}", mana or ""))

    def draw_mana(x_right, y, mana):
        pips = re.findall(r"\{([^}]*)\}", mana or "")
        x = x_right - mana_width(mana)
        for p in pips:
            draw.text((x, y), p, font=f_bar, fill=PIP_COLORS.get(p.upper(), (190, 190, 190)))
            x += draw.textlength(p, font=f_bar) + 3

    def draw_cell(x, y, name, bars):
        _tline, _cmc, mana, img = info[name]
        if img:
            canvas.paste(Image.open(img).resize((TILE_W, TILE_H)), (x, y))
        else:
            draw.rectangle([x, y, x + TILE_W, y + TILE_H], outline=(90, 90, 90))
            draw.text((x + 8, y + TILE_H // 2), name, font=f_bar, fill=(140, 140, 140))
        mw = mana_width(mana)
        name_w = TILE_W - 12 - (mw + 10 if mw else 0)
        label = _ellipsize(draw, name, f_bar, name_w)
        for i in range(bars):
            by = y + i * BAR_H
            draw.rectangle([x, by, x + TILE_W, by + BAR_H], fill=C_BAR_BG)
            draw.line([x, by + BAR_H - 1, x + TILE_W, by + BAR_H - 1], fill=(46, 50, 58))
            draw.text((x + 6, by + 2), label, font=f_bar, fill=C_BAR_TXT)
            draw_mana(x + TILE_W - 6, by + 2, mana)

    for i, (name, bars) in enumerate(main_cells):
        c, r = divmod(i, COL_CELLS)
        draw_cell(MARGIN + c * (TILE_W + GAP), body_y + r * (TILE_H + GAP), name, bars)
    for j, (name, bars) in enumerate(side_cells):
        c, r = divmod(j, SIDE_COL_CELLS)
        draw_cell(side_x + c * (TILE_W + GAP), body_y + r * (TILE_H + GAP), name, bars)

    canvas.save(out)
    print("[完成] %s（主 %d / 备 %d，主 %d 格 %d 列%s）"
          % (out, total, sum(q for q, _ in side), len(main_cells), main_cols,
             "，备 %d 格 %d 列" % (len(side_cells), side_cols) if side_cols else ""))
    print("[卡图] 简中命中 %d/%d 种: %s"
          % (len(zhs_hits), len(info), ", ".join(sorted(zhs_hits)) or "（无）"))
    if fails:
        print("[警告] 无卡图: %s" % ", ".join(sorted(set(fails))), file=sys.stderr)


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
