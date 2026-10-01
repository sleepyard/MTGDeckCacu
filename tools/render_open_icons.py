"""用开源 Mana 字体渲染 tools/assets/icons/ 下的法术力/类别图标（替代 MTGA 提取素材）。

图标来源：Andrew Gioia 的 Mana 字体（https://github.com/andrewgioia/mana），
固定版本 v1.17.1，zipball：
    https://api.github.com/repos/andrewgioia/mana/zipball/v1.17.1
字体本身以 SIL OFL 1.1 发布（许可证全文见 tools/assets/icons/LICENSE-OFL.txt，
归属说明见 tools/assets/icons/NOTICE.md）；符号形象版权归 Wizards of the Coast，
按粉丝内容政策非营利使用。

一次性/按需维护脚本，非常驻依赖：需要 `pip install pillow`（惰性导入，
仓库其余功能不依赖本脚本）。字体 zip 下载后缓存在 tools/cache/fonts/（gitignored），
重复运行离线可用；--refresh 强制重新下载：

    python tools/render_open_icons.py
    python tools/render_open_icons.py --refresh --out tools/assets/icons

渲染内容：
- mana/  46 个法术力符号（单色/通用圆底 + 深色符形；混色与 2W 系列按 mana.css 的
         ms-cost 规则渲染为 135° 对角分色圆底 + 上下两个半符形），96x96 RGBA。
         码点不硬编码，运行时从字体仓库 css/mana.css 解析（.ms-*::before/::after）。
- type/  Artifact / Enchantment / Land（ms-artifact/ms-enchantment/ms-land 字形，
         深色剪影、透明底），尺寸沿用已有文件，缺省 96x96。
"""
import argparse
import io
import os
import re
import sys
import urllib.request
import zipfile

MANA_VERSION = "v1.17.1"
MANA_ZIP_URL = "https://api.github.com/repos/andrewgioia/mana/zipball/" + MANA_VERSION
USER_AGENT = "NeoMtgDeckCacu-render-open-icons"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(ROOT, "tools", "assets", "icons")
CACHE_DIR = os.path.join(ROOT, "tools", "cache", "fonts")

# mana.css 的 --ms-mana-* 变量与 .ms-cost 默认底色（v1.17.1 css/mana.css）
MANA_COLORS = {
    "W": (253, 251, 206), "U": (188, 218, 247), "B": (167, 153, 158),
    "R": (241, 155, 121), "G": (159, 203, 166),
}
GENERIC_COLOR = (190, 185, 178)     # .ms-cost background-color: #beb9b2
GLYPH_COLOR = (17, 17, 17)          # .ms-cost color: #111

HYBRID_NAMES = ("WU", "WB", "UB", "UR", "BR", "BG", "RG", "GW", "GU", "RW")
GENERIC_NAMES = ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
                 "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
                 "X", "C", "S", "T", "E")
COLOR_CLASS = {"W": "w", "U": "u", "B": "b", "R": "r", "G": "g",
               "C": "c", "S": "s", "X": "x", "E": "e", "T": "tap"}

TYPE_ICONS = {"Artifact": "artifact", "Enchantment": "enchantment", "Land": "land"}

SUPERSAMPLE = 4


def download_font_zip(cache_dir, refresh=False):
    """下载（或复用缓存的）Mana 字体 zip，返回 (ttf_bytes, css_text)。失败响亮报错。"""
    os.makedirs(cache_dir, exist_ok=True)
    zip_path = os.path.join(cache_dir, "mana-%s.zip" % MANA_VERSION)
    if refresh or not os.path.exists(zip_path):
        req = urllib.request.Request(MANA_ZIP_URL, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
        except Exception as exc:
            sys.exit("[错误] 下载 Mana 字体 %s 失败：%s\n  URL: %s"
                     % (MANA_VERSION, exc, MANA_ZIP_URL))
        with open(zip_path, "wb") as fh:
            fh.write(data)
        print("[下载] %s -> %s（%d 字节）" % (MANA_ZIP_URL, zip_path, len(data)))
    try:
        zf = zipfile.ZipFile(zip_path)
        ttf_name = next(n for n in zf.namelist()
                        if n.endswith("fonts/mana.ttf"))
        css_name = next(n for n in zf.namelist()
                        if n.endswith("css/mana.css"))
        ttf = zf.read(ttf_name)
        css = zf.read(css_name).decode("utf-8")
    except StopIteration:
        sys.exit("[错误] %s 中找不到 fonts/mana.ttf 或 css/mana.css，"
                 "版本 %s 目录结构可能已变" % (zip_path, MANA_VERSION))
    except zipfile.BadZipFile:
        sys.exit("[错误] 缓存字体包损坏：%s（删除后用 --refresh 重下）" % zip_path)
    return ttf, css


def parse_css_codepoints(css_text):
    """解析 mana.css，返回 {类名: {"before": 码点, "after": 码点}}。"""
    codepoints = {}
    for match in re.finditer(r"([^{}]+)\{\s*content:\s*\"\\([0-9a-f]{4})\"",
                             css_text):
        selectors, hex_cp = match.groups()
        cp = chr(int(hex_cp, 16))
        for sel in selectors.split(","):
            m = re.search(r"\.ms-([\w-]+)::(before|after)", sel)
            if m:
                codepoints.setdefault(m.group(1), {})[m.group(2)] = cp
    if not codepoints:
        sys.exit("[错误] 未能从 mana.css 解析出任何 .ms-* 码点，CSS 结构可能已变")
    return codepoints


def _circle_layer(size, colors, split=False):
    """生成圆底图层：colors=(top, bottom)；split 时按 135° 对角分色（左上 top）。"""
    from PIL import Image, ImageDraw, ImageChops
    inset = max(1, int(size * 0.04))
    box = [inset, inset, size - inset - 1, size - inset - 1]
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse(box, fill=255)
    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    base.paste(Image.new("RGBA", (size, size), colors[0] + (255,)), (0, 0), mask)
    if split:
        tri = Image.new("L", (size, size), 0)
        ImageDraw.Draw(tri).polygon(
            [(size, 0), (size, size), (0, size)], fill=255)
        half = ImageChops.multiply(mask, tri)
        base.paste(Image.new("RGBA", (size, size), colors[1] + (255,)), (0, 0), half)
    return base, mask, box


def _draw_glyph(draw, font, cp, cx, cy):
    draw.text((cx, cy), cp, font=font, fill=GLYPH_COLOR + (255,), anchor="mm")


def render_single(font_path, cp, size, bg_color):
    from PIL import Image, ImageDraw, ImageFont
    ss = SUPERSAMPLE
    big = size * ss
    img, _, box = _circle_layer(big, (bg_color, bg_color))
    diameter = box[2] - box[0]
    font = ImageFont.truetype(font_path, int(diameter * 0.72))
    _draw_glyph(ImageDraw.Draw(img), font, cp, big // 2, big // 2)
    return img.resize((size, size), Image.LANCZOS)


def render_split(font_path, cp_before, cp_after, size, color_top, color_bottom):
    from PIL import Image, ImageDraw, ImageFont
    ss = SUPERSAMPLE
    big = size * ss
    img, _, box = _circle_layer(big, (color_top, color_bottom), split=True)
    diameter = box[2] - box[0]
    font = ImageFont.truetype(font_path, int(diameter * 0.40))
    offset = diameter * 0.17
    center = big // 2
    draw = ImageDraw.Draw(img)
    _draw_glyph(draw, font, cp_before, center - offset, center - offset)
    _draw_glyph(draw, font, cp_after, center + offset, center + offset)
    return img.resize((size, size), Image.LANCZOS)


def render_type(font_path, cp, width, height):
    from PIL import Image, ImageDraw, ImageFont
    ss = SUPERSAMPLE
    big_w, big_h = width * ss, height * ss
    img = Image.new("RGBA", (big_w, big_h), (0, 0, 0, 0))
    font = ImageFont.truetype(font_path, int(min(big_w, big_h) * 0.92))
    _draw_glyph(ImageDraw.Draw(img), font, cp, big_w // 2, big_h // 2)
    return img.resize((width, height), Image.LANCZOS)


def render_mana(font_path, codepoints, out_dir, size):
    """渲染 mana/ 下 46 个符号，返回 (已渲染, 跳过及原因)。"""
    rendered, skipped = [], []
    for name in GENERIC_NAMES + tuple(MANA_COLORS):
        cls = COLOR_CLASS.get(name, name)
        cp = codepoints.get(cls, {}).get("before")
        if not cp:
            skipped.append((name, "mana.css 无 .ms-%s::before" % cls))
            continue
        color = MANA_COLORS.get(name, GENERIC_COLOR)
        render_single(font_path, cp, size, color).save(
            os.path.join(out_dir, name + ".png"))
        rendered.append(name)
    for name in HYBRID_NAMES:
        cls = name.lower()
        entry = codepoints.get(cls, {})
        if "before" not in entry or "after" not in entry:
            skipped.append((name, "mana.css 无 .ms-%s 的 before/after 双符形" % cls))
            continue
        render_split(font_path, entry["before"], entry["after"], size,
                     MANA_COLORS[name[0]], MANA_COLORS[name[1]]).save(
            os.path.join(out_dir, name + ".png"))
        rendered.append(name)
    for color in MANA_COLORS:
        name = "2" + color
        cls = "2" + COLOR_CLASS[color]
        entry = codepoints.get(cls, {})
        if "before" not in entry or "after" not in entry:
            skipped.append((name, "mana.css 无 .ms-%s 的 before/after 双符形" % cls))
            continue
        render_split(font_path, entry["before"], entry["after"], size,
                     GENERIC_COLOR, MANA_COLORS[color]).save(
            os.path.join(out_dir, name + ".png"))
        rendered.append(name)
    return rendered, skipped


def render_types(font_path, codepoints, out_dir, default_size):
    """渲染 type/ 图标（若字体含对应字形），返回 (已渲染, 跳过及原因)。"""
    rendered, skipped = [], []
    for name, cls in TYPE_ICONS.items():
        cp = codepoints.get(cls, {}).get("before")
        if not cp:
            skipped.append((name, "mana.css 无 .ms-%s::before" % cls))
            continue
        target = os.path.join(out_dir, name + ".png")
        if os.path.exists(target):
            from PIL import Image
            with Image.open(target) as old:
                width, height = old.size
        else:
            width = height = default_size
        render_type(font_path, cp, width, height).save(target)
        rendered.append(name)
    return rendered, skipped


def main():
    parser = argparse.ArgumentParser(
        description="用开源 Mana 字体（%s, SIL OFL 1.1）渲染 assets 图标" % MANA_VERSION)
    parser.add_argument("--out", default=DEFAULT_OUT,
                        help="图标输出根目录（默认 tools/assets/icons）")
    parser.add_argument("--size", type=int, default=96,
                        help="mana/ 图标边长（默认 96，对齐旧素材）")
    parser.add_argument("--refresh", action="store_true",
                        help="忽略 tools/cache/fonts/ 缓存，重新下载字体")
    args = parser.parse_args()

    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        sys.exit("[错误] 需要 Pillow：pip install pillow（一次性渲染用，非仓库常驻依赖）")

    ttf, css = download_font_zip(CACHE_DIR, refresh=args.refresh)
    font_path = os.path.join(CACHE_DIR, "mana-%s.ttf" % MANA_VERSION)
    if args.refresh or not os.path.exists(font_path):
        with open(font_path, "wb") as fh:
            fh.write(ttf)
    codepoints = parse_css_codepoints(css)

    mana_dir = os.path.join(args.out, "mana")
    type_dir = os.path.join(args.out, "type")
    os.makedirs(mana_dir, exist_ok=True)
    os.makedirs(type_dir, exist_ok=True)

    mana_ok, mana_skip = render_mana(font_path, codepoints, mana_dir, args.size)
    type_ok, type_skip = render_types(font_path, codepoints, type_dir, args.size)

    print("[完成] mana/ 渲染 %d 个：%s" % (len(mana_ok), " ".join(mana_ok)))
    print("[完成] type/ 渲染 %d 个：%s" % (len(type_ok), " ".join(type_ok) or "（无）"))
    for name, why in mana_skip + type_skip:
        print("[跳过] %s：%s" % (name, why))
    if mana_skip or type_skip:
        sys.exit(1)


if __name__ == "__main__":
    main()
