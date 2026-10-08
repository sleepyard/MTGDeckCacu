#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 MTGA 导入格式牌表渲染成适合中文社区分享的卡牌网格图。

用法::

  python tools/deck_image.py <牌表.txt> [--out 输出.png] [--title 标题]
      [--subtitle 副标题] [--author 作者] [--format 赛制] [--record 战绩]

版式对齐 Untapped.gg 牌表图模板：
  - 每格（stack）= 卡图顶部切片的叠放 + 底部一张完整卡图：副本 1..N-1 各贡献一条
    切片（卡图顶部 12.5% 高度，含牌框边 + 名牌栏 + 一线牌画边缘），切片紧邻叠放、
    底部留 2px 深色缝模拟牌堆阴影；第 N 张为完整卡图。格高 = (N-1)×切片高 + tile_h，
    >4 张仍拆多格（4/4/3）。切片直接用卡图本身（简中图则名牌中文），不再绘文字。
  - 主牌区固定 5 列 stack（不足 5 列按实际），每行 5 格、行数 = ceil(格数/5)，
    行高 = 该行最高格高；类别分组顺序与组内 cmc 升序不变（连续填充不强制换行）。
    备牌区维持右侧独立列、1–2 列均衡分配（每列 ≤8 格），优先不撑高画布（右列 ≤ 主牌区高度，
    并列取少列保牌格尺寸）。总宽 ≤1600，列宽动态缩放。
  - 指挥官/伙伴独立位：Commander / Companion 分区单独解析，渲染在右列顶部带标签
    （指挥官/伙伴）与主题色描边，不计入主牌堆；造价核算含独立位、不含备牌。
  - 主牌/备牌分区标头，顶部中文标题、颜色身份、类型统计、比率行（生物/非生物/地
    占比 + 非地口径有色占比）与造价行（deck_cost 口径：
    MRUC 色块按 MTGA 稀有度配色——秘稀红橙/稀有金/非普通银/普通灰黑——加数量，
    物质点与 PP 明细随后，同带右对齐附指标释义；基本地不计，数据缺失整行省略）。
    牌区中央斜置 DeckPooper 低透明度水印（--no-watermark 关闭），页脚含品牌署名，
    底部留净空带防止高备牌列贴边。

卡图简中优先，三级来源：
  1. MTGCH（主源，覆盖含未发售新牌）：mtgch.com/api/v1/result?q=<牌名>&view=1，
     display_name 精确匹配（双面牌按正面名）取 image_url（webp）与 display_name_zh；
  2. Scryfall zhs（回退 1）：cards/search !"<牌名>" lang:zhs unique=prints；
  3. 英文卡图（回退 2）。
  缓存到 tools/cache/card_images/（按真实扩展名 .webp/.jpg/.png 存，Image.open 自适应；
  命中统计区分来源）。display_name_zh 用于无图占位。查询走 mtg_tool 的磁盘缓存、
  节流与重试。Pillow 惰性导入，缺失时退出码 3。
"""

import argparse
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mtg_tool  # noqa: E402
from deck_model import parse_deck as _parse_deck  # noqa: E402

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
SLICE_RATIO = 0.125                # 叠卡切片 = 卡图顶部 12.5% 高度（实测观感最佳）
MAIN_COLS = 5                      # 主牌区固定 5 列 stack（不足按实际）
COL_CELLS = 4
SIDE_COL_CELLS = 8
CMD_LABEL_H = 26               # 指挥官/伙伴独立位标签行高
SIDE_HEAD_H = 34               # 有独立位时备牌小标头高
GAP = 10
MARGIN = 20
SEC_H = 38
FOOTER_H = 48

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
RARITY_STYLE = {
    # MTGA 稀有度配色方案：秘稀红橙 / 稀有金 / 非普通银 / 普通灰黑
    # （文字方案 M/R/U/C 取自牌底稀有度字母与 MTGA 野卡展示惯例）
    "mythic":   {"letter": "M", "fill": (191, 68, 39),   "edge": (226, 120, 90),
                 "text": (255, 244, 238), "glow": (233, 148, 122)},
    "rare":     {"letter": "R", "fill": (168, 142, 74),  "edge": (212, 186, 116),
                 "text": (28, 22, 10),    "glow": (216, 192, 132)},
    "uncommon": {"letter": "U", "fill": (124, 134, 148), "edge": (168, 178, 192),
                 "text": (18, 22, 26),    "glow": (188, 198, 210)},
    "common":   {"letter": "C", "fill": (66, 66, 70),    "edge": (120, 120, 126),
                 "text": (238, 238, 238), "glow": (198, 198, 202)},
}

# MTGA 客户端提取的野卡卡背贴图（WotC 版权素材，不随仓库分发；
# 本机可用 tools/extract_mtga_icons.py 提取到 tools/assets/icons/wildcard/，
# 该目录已 gitignore）；优先读项目资源目录，其次旧缓存目录，
# 皆缺失时造价行回退到 RARITY_STYLE 手绘色块。
ASSETS_ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "assets", "icons")
WILDCARD_ICON_DIRS = (os.path.join(ASSETS_ICON_DIR, "wildcard"),
                      os.path.join(os.path.dirname(CACHE_DIR), "wildcard_icons"))
WILDCARD_ICON_FILE = {
    "mythic": "CDC_Wildcard_Mythic.png",
    "rare": "CDC_Wildcard_Rare.png",
    "uncommon": "CDC_Wildcard_Uncommon.png",
    "common": "CDC_Wildcard_Common.png",
}
WILDCARD_CROP = 0.68                 # 贴图右侧约 32% 为帷幕，仅取左部卡背
_wildcard_cache = {}


def _wildcard_icon(Image, rarity, height):
    """→ 裁好并缩放到指定高度的野卡卡背 Image；缺失/失败返回 None。"""
    key = (rarity, height)
    if key in _wildcard_cache:
        return _wildcard_cache[key]
    icon = None
    for icon_dir in WILDCARD_ICON_DIRS:
        path = os.path.join(icon_dir, WILDCARD_ICON_FILE.get(rarity, ""))
        if not os.path.exists(path):
            continue
        try:
            src = Image.open(path).convert("RGBA")
            # 原始贴图右约 32% 为帷幕需裁左部；extract_mtga_icons 产物已裁好（宽约高 68%）
            if src.width >= src.height * 0.9:
                src = src.crop((0, 0, int(src.width * WILDCARD_CROP), src.height))
            resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS",
                                 getattr(Image, "LANCZOS", 1))
            icon = src.resize((max(1, round(src.width * height / src.height)), height),
                              resampling)
        except Exception:
            icon = None
        if icon is not None:
            break
    _wildcard_cache[key] = icon
    return icon


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
    """薄委托：deck_model.parse_deck → (main, side, commanders)；commanders 为
    [(数量, 牌名, 类别)]，类别 = commander / companion。

    ★ Phase 1 起自动剥除 `(SET) 123` 后缀（修复：牌名查 Scryfall 更准）。"""
    deck = _parse_deck(path)
    main, side = deck.main_side_pairs()
    return main, side, deck.commanders_with_zone()


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


def mtgch_card_info(name):
    """MTGCH 简中图（主源）：返回 (image_url, display_name_zh)；查不到/失败返回 (None, None)。

    匹配逻辑同 mtg_tool.fetch_chinese_name：display_name 精确匹配优先
    （双面/历险牌允许按正面名匹配），否则取首条。"""
    try:
        status, payload = mtg_tool.http_get_json(
            mtg_tool.MTGCH_BASE + "/api/v1/result", "mtgch",
            {"q": name, "view": 1}, True)
    except Exception:
        return None, None
    if status >= 400 or not isinstance(payload, dict):
        return None, None
    items = payload.get("items") or []
    if not items:
        return None, None
    target = name.strip().lower()
    front = target.split(" // ")[0]
    chosen = None
    for item in items:
        if not isinstance(item, dict):
            continue
        disp = str(item.get("display_name") or "").strip().lower()
        if disp == target or disp == front:
            chosen = item
            break
    if chosen is None:
        chosen = items[0] if isinstance(items[0], dict) else {}
    return chosen.get("image_url") or None, chosen.get("display_name_zh") or None


def _cache_key(name):
    """把中英文牌名变成跨平台稳定的缓存文件名。"""
    key = re.sub(r"[^\w.-]+", "_", name, flags=re.UNICODE).strip("._")
    return key or "card"


def fetch_image(url, key):
    """下载缓存卡图；按 URL 真实扩展名存（.webp/.jpg/.png），Image.open 自适应解码。
    兼容旧缓存：历史上一律存成 <key>.png（内容可能是 JPEG），命中则直接复用。"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        ext = ".png"
    path = os.path.join(CACHE_DIR, key + ext)
    if os.path.exists(path):
        return path
    legacy = os.path.join(CACHE_DIR, key + ".png")
    if os.path.exists(legacy):
        return legacy
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


def cost_info(main):
    """按 deck_cost.py 口径核算造价：返回 (deck_cost 模块, 签名 dict, metrics)；
    牌张稀有度未知或工具不可用返回 None（调用方整行省略）。"""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "newbie"))
        import deck_cost
        sig, unknown, _extra = deck_cost.census([(name, qty, "main") for qty, name in main])
        if unknown:
            return None
        return deck_cost, sig, deck_cost.metrics(sig)
    except Exception:
        return None


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


def _pack_stacks(items, stack_size=MAX_BARS):
    """按牌表顺序把牌张实例连续打包，每堆最多 ``stack_size`` 张。

    Untapped 的堆不是“每种牌一个格子”：一堆的最后一张可以和下一种牌
    连续出现，因此例如 3 张 A 后的 3 张 B 会形成 [A,A,A,B]、[B,B]。
    """
    if stack_size < 1:
        raise ValueError("stack_size must be positive")
    instances = []
    for quantity, name in items:
        instances.extend([name] * max(0, int(quantity)))
    return [instances[offset:offset + stack_size]
            for offset in range(0, len(instances), stack_size)]


def render(main, side, title, subtitle, out, author="", format_name="", record="",
           language="zh", watermark=True, commanders=()):
    """渲染牌表；旧的五参数调用仍然有效。commanders = [(数量, 牌名, 类别)]。"""
    Image, ImageDraw, ImageFont = _load_pil()
    english = language.lower() in ("en", "eng", "english")
    stat_labels = STAT_LABEL_EN if english else STAT_LABEL
    section_main = "Main Deck" if english else "主牌"
    section_side = "Sideboard" if english else "备牌"
    card_unit = "cards" if english else "张"
    footer = ("DeckPooper · NeoMtgDeckCacu · Card art and printings from Scryfall" if english else
              "DeckPooper · NeoMtgDeckCacu · 卡图与印刷信息来自 Scryfall")
    f_title = _font(ImageFont, 31, bold=True)
    f_meta = _font(ImageFont, 15)
    f_stat = _font(ImageFont, 17, bold=True)
    f_sec = _font(ImageFont, 20, bold=True)
    f_footer = _font(ImageFont, 12)
    f_probe = _font(ImageFont, 17)

    fails = []
    zh_hits = {"mtgch": set(), "scryfall": set()}
    counts, info, identities, entries = {}, {}, set(), []

    def lookup(name):
        """三级卡图源：MTGCH 简中 → Scryfall zhs → 英文；某级下载失败顺延下一级。"""
        en_url, type_line, cmc, mana = card_info(name)
        colors = _CARD_COLOR_CACHE.get(name, ())
        zh_name, source, image_path = None, None, None
        for fetcher, prefix, tag in ((mtgch_card_info, "mtgch_", "mtgch"),
                                     (zhs_card_info, "zhs_", "scryfall")):
            url, zh = fetcher(name)
            if not url:
                continue
            if zh and zh_name is None:
                zh_name = zh
            try:
                image_path = fetch_image(url, prefix + _cache_key(name))
                source = tag
                break
            except Exception as exc:
                print("[警告] 卡图下载失败 %s（%s）: %s" % (name, tag, exc), file=sys.stderr)
        if image_path is None and en_url:
            try:
                image_path = fetch_image(en_url, _cache_key(name))
            except Exception as exc:
                print("[警告] 卡图下载失败 %s（英文）: %s" % (name, exc), file=sys.stderr)
        if image_path is None:
            fails.append(name)
        elif source:
            zh_hits[source].add(name)
        display_name = zh_name if zh_name and not english else name
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
    for _quantity, name, _kind in commanders:
        if name not in info:
            info[name] = lookup(name)
        identities.update(info[name][5])
    entries.sort(key=lambda entry: (GROUP_ORDER.get(entry[1], 99), entry[0], entry[3]))

    main_stacks = _pack_stacks([(quantity, name) for _cmc, _bucket, quantity, name in entries])
    side_stacks = _pack_stacks(side)
    main_cols = min(MAIN_COLS, max(1, len(main_stacks)))

    def compute_layout(ncols):
        """ncols = 右列数（0 = 无右列）。右列内容 = 指挥官/伙伴独立位 + 备牌区。"""
        total_cols = main_cols + ncols
        l_gap = max(8, min(12, round(GAP * max(0.8, 6.0 / max(6, total_cols)))))
        l_tw = min(TILE_W, max(MIN_TILE_W,
                               (MAX_OUTPUT_W - 2 * MARGIN - l_gap * max(0, total_cols - 1)) // total_cols))
        l_th = max(228, round(l_tw * CARD_RATIO))
        l_sh = max(20, round(l_th * SLICE_RATIO))

        def l_cell_h(stack):
            """堆高 = (N-1)×切片高 + 完整卡图高。"""
            return max(1, len(stack) - 1) * l_sh + l_th

        # 主牌区：固定 5 列、行优先填充，行高 = 该行最高格高
        rows = math.ceil(len(main_stacks) / main_cols)
        row_hs = [max(l_cell_h(stack) for stack in
                      main_stacks[r * main_cols:(r + 1) * main_cols])
                  for r in range(rows)]
        m_ys, acc = [], 0
        for row_h in row_hs:
            m_ys.append(acc)
            acc += row_h + l_gap
        m_h = acc - l_gap if row_hs else 0
        # 指挥官/伙伴独立位（右列顶部，带标签）
        cmd_h = (len(commanders) * (CMD_LABEL_H + l_th)
                 + l_gap * max(0, len(commanders) - 1)) if commanders and ncols else 0
        # 备牌区：ncols 列均衡分配（每列 ≤8 格），格高随副本数变化；有独立位时加小标头
        s_h, s_ys, per_col = 0, [], SIDE_COL_CELLS
        if side_stacks and ncols:
            per_col = min(SIDE_COL_CELLS, math.ceil(len(side_stacks) / ncols))
            for col in range(ncols):
                chunk = side_stacks[col * per_col:(col + 1) * per_col]
                if chunk:
                    s_h = max(s_h, sum(l_cell_h(stack) for stack in chunk)
                              + l_gap * max(0, len(chunk) - 1))
            for j, _stack in enumerate(side_stacks):
                col, r = divmod(j, per_col)
                chunk = side_stacks[col * per_col:col * per_col + r]
                s_ys.append(sum(l_cell_h(stack) for stack in chunk) + l_gap * r)
            if cmd_h:
                s_h += SIDE_HEAD_H + l_gap
        r_h = cmd_h + (l_gap + s_h if cmd_h and s_h else s_h)
        return {"ncols": ncols, "gap": l_gap, "tile_w": l_tw, "tile_h": l_th,
                "slice_h": l_sh, "cell_h": l_cell_h, "main_rows": rows,
                "main_ys": m_ys, "main_h": m_h, "side_ys": s_ys, "per_col": per_col,
                "cmd_h": cmd_h, "right_h": r_h}

    if side_stacks or commanders:
        # Untapped 口径：右列优先不撑高画布（≤ 主牌区高度），并列取少列（牌格更大）
        lay = min((compute_layout(c) for c in (1, 2)),
                  key=lambda c: (max(0, c["right_h"] - c["main_h"]), c["ncols"]))
    else:
        lay = compute_layout(0)
    gap, tile_w, tile_h, slice_h = lay["gap"], lay["tile_w"], lay["tile_h"], lay["slice_h"]
    cell_h = lay["cell_h"]
    main_rows, main_ys, main_h = lay["main_rows"], lay["main_ys"], lay["main_h"]
    side_ys, cmd_h = lay["side_ys"], lay["cmd_h"]
    side_cols = lay["ncols"]
    body_h = max(main_h, lay["right_h"])
    main_w = main_cols * tile_w + (main_cols - 1) * gap
    side_w = side_cols * tile_w + (side_cols - 1) * gap if side_cols else 0
    side_x = MARGIN + main_w + gap if side_cols else 0
    width = side_x + side_w + MARGIN if side_cols else main_w + 2 * MARGIN

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
    # 比率指标（主牌口径）：生物/非生物/地占比 + 有色占比（非地口径）
    if total:
        creatures = counts.get("Creature", 0)
        lands = counts.get("Land", 0)
        noncreature = total - creatures - lands
        colored = sum(entry[2] for entry in entries
                      if entry[1] != "Land" and info[entry[3]][5])
        nonland = total - lands

        def _pct(part, whole):
            return "%d%%" % round(part * 100.0 / whole) if whole else "-"

        ratio_text = (("Creatures %s · Non-creature %s · Lands %s · Colored %s" if english
                       else "生物 %s · 非生物 %s · 地 %s · 有色 %s")
                      % (_pct(creatures, total), _pct(noncreature, total),
                         _pct(lands, total), _pct(colored, nonland)))
        stat_lines += _wrap(probe, ratio_text, f_stat, available, 1)
    cost = cost_info(main + [(q, n) for q, n, _kind in commanders])
    cost_detail = ""
    if cost:
        dc, cost_sig, cost_metrics = cost
        gold = cost_sig.get("mythic", 0) * dc.MYTHIC + cost_sig.get("rare", 0) * dc.RARE
        if english:
            cost_detail = ("Material %.1f (low %.1f/cap %.1f) | PP core %.1f packs | "
                           "PP full %.1f packs"
                           % (cost_metrics["tot_a"], gold, dc.BUDGET_MAX,
                              cost_metrics["packs_core"], cost_metrics["packs_all"]))
        else:
            cost_detail = ("物质点 %.1f（金位 %.1f/上限 %.1f）｜ PP核心 %.1f 包 ｜ PP全量 %.1f 包"
                           % (cost_metrics["tot_a"], gold, dc.BUDGET_MAX,
                              cost_metrics["packs_core"], cost_metrics["packs_all"]))
    cost_lines = _wrap(probe, cost_detail, f_probe, available, 2) if cost_detail else []
    cost_h = (30 + len(cost_lines) * 24) if cost else 0
    title = _ellipsize(probe, title, f_title, available)
    meta_text = " · ".join(part for part in (author, format_name) if part)
    header_h = 14 + 43 + (24 if meta_text else 0) + len(stat_lines) * 25 + cost_h + 12
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
    if cost:
        _dc, sig, _metrics = cost
        cost_top = y
        x = MARGIN
        label = "Cost" if english else "造价"
        draw.text((x, y + 2), label, font=f_probe, fill=C_COST)
        x += draw.textlength(label, font=f_probe) + 12
        chip = 24
        for rarity in ("mythic", "rare", "uncommon", "common"):
            count = sig.get(rarity, 0)
            if not count:
                continue
            style = RARITY_STYLE[rarity]
            icon = _wildcard_icon(Image, rarity, chip + 4)
            if icon is not None:
                canvas.paste(icon, (int(round(x)), y - 2), icon)
                x += icon.width + 4
            else:
                draw.rounded_rectangle((x, y, x + chip, y + chip), radius=6,
                                       fill=style["fill"], outline=style["edge"], width=1)
                letter_w = draw.textlength(style["letter"], font=f_stat)
                draw.text((x + (chip - letter_w) / 2, y + 1), style["letter"],
                          font=f_stat, fill=style["text"])
                x += chip + 4
            num = "×%d" % count
            draw.text((x, y + 2), num, font=f_probe, fill=style["glow"])
            x += draw.textlength(num, font=f_probe) + 14
        y += 30
        for line in cost_lines:
            draw.text((MARGIN, y), line, font=f_probe, fill=C_COST)
            y += 24
        # 造价指标释义：与造价行同带、右对齐（窄图自动让位于左侧内容）
        legend = (["Material: normalized total yield (additive)",
                   "PP core: max(rare, mythic) line, in packs",
                   "PP full: max of all four lines, in packs"] if english else
                  ["物质点：全产出归一化总量（可加）",
                   "PP核心：max(稀有/秘稀线) 所需包数",
                   "PP全量：四条线取 max 所需包数"])
        for i, lg in enumerate(legend):
            lw = draw.textlength(lg, font=f_footer)
            draw.text((width - MARGIN - lw, cost_top + 2 + i * 16), lg,
                      font=f_footer, fill=C_STAT)

    def section_heading(x0, section_w, text):
        text_w = draw.textlength(text, font=f_sec)
        text_x = x0 + (section_w - text_w) / 2
        line_y = header_h + SEC_H // 2 + 1
        draw.line((x0, line_y, max(x0, text_x - 14), line_y), fill=C_LINE, width=1)
        draw.line((text_x + text_w + 14, line_y, x0 + section_w, line_y), fill=C_LINE, width=1)
        draw.text((text_x, header_h + 7), text, font=f_sec, fill=C_SEC)

    section_heading(MARGIN, main_w, "%s · %d %s" % (section_main, total, card_unit))
    if side_cols and not commanders:
        section_heading(side_x, side_w, "%s · %d %s" %
                        (section_side, sum(quantity for quantity, _name in side), card_unit))

    resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS",
                         getattr(Image, "LANCZOS", 1))

    def draw_cell(x0, y0, stack):
        """渲染一堆牌：前 N-1 张只露出顶部切片，最后一张完整显示。"""
        for index, name in enumerate(stack):
            _type_line, _cmc, _mana, image_path, display_name, _colors = info[name]
            card_y = y0 + index * slice_h
            if image_path:
                with Image.open(image_path) as source:
                    src = source.convert("RGB")
                    if index < len(stack) - 1:
                        slc = src.crop((0, 0, src.size[0],
                                       max(1, round(src.size[1] * SLICE_RATIO))))
                        slc = slc.resize((tile_w, slice_h), resampling)
                        canvas.paste(slc, (x0, card_y))
                        draw.rectangle((x0, card_y + slice_h - 2, x0 + tile_w, card_y + slice_h),
                                       fill=(10, 11, 14))
                    else:
                        canvas.paste(src.resize((tile_w, tile_h), resampling), (x0, card_y))
            else:
                card_h = slice_h if index < len(stack) - 1 else tile_h
                draw.rectangle((x0, card_y, x0 + tile_w, card_y + card_h), fill=(36, 39, 44),
                               outline=C_LINE)
                draw.text((x0 + 8, card_y + max(4, card_h // 2)), display_name,
                          font=f_stat, fill=(155, 160, 166))

    for index, stack in enumerate(main_stacks):
        row, column = divmod(index, main_cols)
        draw_cell(MARGIN + column * (tile_w + gap), body_y + main_ys[row], stack)

    # 指挥官/伙伴独立位：右列顶部，带标签与主题色描边
    cmd_label = {"commander": ("Commander" if english else "指挥官"),
                 "companion": ("Companion" if english else "伙伴")}
    for i, (_q, name, kind) in enumerate(commanders):
        label_y = body_y + i * (CMD_LABEL_H + tile_h + gap)
        label = cmd_label.get(kind, kind)
        label_w = draw.textlength(label, font=f_stat)
        draw.text((side_x + (side_w - label_w) / 2, label_y), label,
                  font=f_stat, fill=C_SEC)
        draw_cell(side_x, label_y + CMD_LABEL_H, [name])
        draw.rounded_rectangle((side_x - 2, label_y + CMD_LABEL_H - 2,
                                side_x + tile_w + 2, label_y + CMD_LABEL_H + tile_h + 2),
                               radius=8, outline=accent, width=2)
    # 有独立位时备牌用列内小标头
    side_base = body_y
    if side_stacks and commanders:
        head_y = body_y + cmd_h + gap
        side_text = "%s · %d %s" % (section_side,
                                    sum(quantity for quantity, _name in side), card_unit)
        st_w = draw.textlength(side_text, font=f_sec)
        st_x = side_x + (side_w - st_w) / 2
        line_y = head_y + SIDE_HEAD_H // 2
        draw.line((side_x, line_y, max(side_x, st_x - 14), line_y), fill=C_LINE, width=1)
        draw.line((st_x + st_w + 14, line_y, side_x + side_w, line_y), fill=C_LINE, width=1)
        draw.text((st_x, head_y + 4), side_text, font=f_sec, fill=C_SEC)
        side_base = head_y + SIDE_HEAD_H
    for index, stack in enumerate(side_stacks):
        column = index // lay["per_col"]
        draw_cell(side_x + column * (tile_w + gap), side_base + side_ys[index], stack)

    if watermark:
        # DeckPooper 商标水印：低透明度斜置于牌区中央，不遮挡阅读
        wm_font = _font(ImageFont, max(52, width // 14), bold=True)
        wm_text = "DeckPooper"
        tw = draw.textlength(wm_text, font=wm_font)
        wm_img = Image.new("RGBA", (int(tw) + 28, wm_font.size + 24), (0, 0, 0, 0))
        ImageDraw.Draw(wm_img).text((14, 8), wm_text, font=wm_font,
                                    fill=(255, 255, 255, 34))
        bicubic = getattr(getattr(Image, "Resampling", Image), "BICUBIC",
                          getattr(Image, "BICUBIC", 3))
        wm_img = wm_img.rotate(24, expand=True, resample=bicubic)
        wx = (width - wm_img.size[0]) // 2
        wy = body_y + max(0, (body_h - wm_img.size[1]) // 2)
        canvas.paste(wm_img, (wx, wy), wm_img)

    footer_y = body_y + body_h + 16
    draw.text((MARGIN, footer_y), _ellipsize(draw, footer, f_footer, width - 2 * MARGIN),
              font=f_footer, fill=(123, 129, 138))
    canvas.save(out)
    print("[完成] %s（主 %d / 备 %d%s，主 %d 堆 %d 列 %d 行%s）" %
          (out, total, sum(quantity for quantity, _name in side),
           " / 独立位 %d" % len(commanders) if commanders else "",
           len(main_stacks), main_cols,
           main_rows, "，备 %d 堆 %d 列" % (len(side_stacks), side_cols) if side_cols else ""))
    zh_names = sorted(zh_hits["mtgch"] | zh_hits["scryfall"])
    print("[卡图] 简中命中 %d/%d 种（mtgch %d / scryfall %d）: %s" %
          (len(zh_names), len(info), len(zh_hits["mtgch"]), len(zh_hits["scryfall"]),
           ", ".join(zh_names) or "（无）"))
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
    parser.add_argument("--no-watermark", action="store_true",
                        help="不绘制 DeckPooper 商标水印")
    args = parser.parse_args()
    main_entries, side_entries, cmd_entries = parse_deck(args.deck)
    if not main_entries:
        print("[错误] 牌表为空或格式不符", file=sys.stderr)
        sys.exit(2)
    title = args.title or os.path.splitext(os.path.basename(args.deck))[0]
    out = args.out or os.path.splitext(args.deck)[0] + ".png"
    render(main_entries, side_entries, title, args.subtitle, out, args.author,
           args.format_name, args.record, args.lang, watermark=not args.no_watermark,
           commanders=cmd_entries)


if __name__ == "__main__":
    main()
