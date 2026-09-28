"""从本机 MTGA 客户端 AssetBundle 提取 UI 图标为项目资源（tools/assets/icons/）。

一次性/按需维护脚本，非常驻依赖：需要本机安装 MTGA 客户端 + `pip install UnityPy pillow`
（两者均不入 requirements，仓库其余功能不依赖本脚本）。提取产物已提交入库，
仅在客户端大更新需刷新图标时重跑：

    python tools/extract_mtga_icons.py
    python tools/extract_mtga_icons.py --mtga-dir "D:/.../downloads/AssetBundle" --out tools/assets/icons

提取内容：
- wildcard/  野卡卡背四稀有度（Textures_Bucket_Card.MaterialOverride_* 中的 CDC_Wildcard_*）
- mana/      法术力符号（Bucket_Card.ManaSymbolSpriteSheet_0 的 TMP glyph 表切片，
             合成彩色圆底 + 黑色符形；混色/非瑞克西亚变体跳过）
- type/      卡牌类型图标（客户端仅有 Artifact / Enchantment / Land，其余类型无原生图形）

已知缺口：鹏洛客 / 生物 / 法术 / 瞬间 在 MTGA 客户端无原生图标（类型在客户端内均用文字呈现），
提取脚本找不到对应资源时会如实报告。
"""
import argparse
import os
import sys

try:
    import UnityPy
except ImportError:
    sys.exit("[错误] 需要 UnityPy：pip install UnityPy（一次性提取用，非仓库常驻依赖）")
try:
    from PIL import Image
except ImportError:
    sys.exit("[错误] 需要 Pillow：pip install pillow")

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.14f1"

DEFAULT_MTGA_DIR = os.path.join(
    "D:/SteamLibrary/steamapps/common/MTGA/MTGA_Data/downloads/AssetBundle")
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "tools", "assets", "icons")

WILDCARD_NAMES = ("CDC_Wildcard_Mythic", "CDC_Wildcard_Rare",
                  "CDC_Wildcard_Uncommon", "CDC_Wildcard_Common")

# 法术力圆底色（MTGA 客户端按符号运行时着色，此处为参照实机观感的近似值；
# 黑法术力圆底深灰 + 白符形，其余黑符形）
MANA_CIRCLE = {
    "W": (247, 245, 208), "U": (14, 104, 171), "B": (56, 47, 44),
    "R": (211, 32, 42), "G": (0, 115, 62),
}
MANA_GENERIC = (214, 208, 203)          # 数字 / X / C / T / S 等灰底
GLYPH_DARK = (20, 16, 14)
GLYPH_LIGHT = (240, 238, 234)


def find_bundle(mtga_dir, prefix):
    import glob
    hits = sorted(glob.glob(os.path.join(mtga_dir, prefix + "*.mtga")))
    return hits


def extract_wildcards(mtga_dir, out_dir):
    found = {}
    for path in find_bundle(mtga_dir, "Textures_Bucket_Card.MaterialOverride_"):
        env = UnityPy.load(path)
        for obj in env.objects:
            if obj.type.name != "Texture2D":
                continue
            d = obj.read()
            if d.m_Name in WILDCARD_NAMES and d.m_Name not in found:
                found[d.m_Name] = d.image
        if len(found) == len(WILDCARD_NAMES):
            break
    saved = []
    for name in WILDCARD_NAMES:
        img = found.get(name)
        if img is None:
            print("  [缺] 未找到贴图", name)
            continue
        img = img.convert("RGBA")
        # 贴图右约 32% 为帷幕，仅保留左部卡背
        img = img.crop((0, 0, int(img.width * 0.68), img.height))
        dest = os.path.join(out_dir, "wildcard", name + ".png")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        img.save(dest)
        saved.append(dest)
    return saved


def _glyph_mask(img):
    """SDF/白符形贴图 → 形状掩码（L 模式）。"""
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")
    lo, hi = alpha.getextrema()
    if hi - lo > 30:                    # alpha 通道含距离/形状信息
        return alpha.point(lambda v: 255 if v > 127 else 0)
    lum = rgba.convert("L")             # 退化为亮度阈值（白符形黑底）
    return lum.point(lambda v: 255 if v > 127 else 0)


def extract_mana(mtga_dir, out_dir, size=96):
    sheet_data = find_bundle(mtga_dir, "Bucket_Card.ManaSymbolSpriteSheet_0_")
    sheet_tex = find_bundle(mtga_dir, "Textures_Bucket_Card.ManaSymbolSpriteSheet_0_")
    if not sheet_data or not sheet_tex:
        print("  [缺] ManaSymbolSpriteSheet bundle 未找到")
        return []
    chars = glyphs = None
    for obj in UnityPy.load(sheet_data[0]).objects:
        if obj.type.name == "MonoBehaviour" and obj.read().m_Name == "SpriteSheet_ManaIcons":
            tt = obj.read_typetree()
            chars = tt["m_SpriteCharacterTable"]
            glyphs = tt["m_GlyphTable"]
            break
    tex = None
    for obj in UnityPy.load(sheet_tex[0]).objects:
        if obj.type.name == "Texture2D" and obj.read().m_Name == "SDF_Icons_ManaCost_Symbols":
            tex = obj.read().image
            break
    if chars is None or tex is None:
        print("  [缺] 法术力 glyph 表或贴图未找到")
        return []
    glyph_by_index = {g["m_Index"]: g["m_GlyphRect"] for g in glyphs}
    tex = tex.convert("RGBA")
    saved, skipped = [], []
    for c in chars:
        name = c["m_Name"].lstrip("x")
        if not name or "?" in name or "P" in name:      # 跳过占位/非瑞克西亚变体
            skipped.append(c["m_Name"])
            continue
        rect = glyph_by_index.get(c["m_GlyphIndex"])
        if rect is None:
            continue
        x, y, w, h = (int(rect[k]) for k in ("m_X", "m_Y", "m_Width", "m_Height"))
        if w <= 0 or h <= 0:
            continue
        crop = tex.crop((x, tex.height - y - h, x + w, tex.height - y))
        mask = _glyph_mask(crop)
        circle_color = MANA_CIRCLE.get(name, MANA_GENERIC)
        glyph_color = GLYPH_LIGHT if name == "B" else GLYPH_DARK
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        # 圆底（径向简单近似：纯色圆 + 深一圈描边）
        from PIL import ImageDraw
        draw = ImageDraw.Draw(canvas)
        pad = size // 14
        edge = tuple(max(0, v - 48) for v in circle_color)
        draw.ellipse((pad, pad, size - pad - 1, size - pad - 1),
                     fill=circle_color + (255,), outline=edge + (255,), width=2)
        # 符形缩放到圆内约 58%
        target = int(size * 0.58)
        scale = target / max(w, h)
        gw, gh = max(1, round(w * scale)), max(1, round(h * scale))
        glyph = Image.new("RGBA", (gw, gh), glyph_color + (0,))
        glyph.putalpha(mask.resize((gw, gh), Image.LANCZOS))
        solid = Image.new("RGBA", (gw, gh), glyph_color + (255,))
        solid.putalpha(glyph.getchannel("A"))
        canvas.paste(solid, ((size - gw) // 2, (size - gh) // 2), solid)
        dest = os.path.join(out_dir, "mana", name + ".png")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        canvas.save(dest)
        saved.append(dest)
    if skipped:
        print("  [跳过] 变体：", " ".join(sorted(skipped)))
    return saved


def _save_sprite(env, sprite_name, dest):
    for obj in env.objects:
        if obj.type.name == "Sprite" and obj.read().m_Name == sprite_name:
            img = obj.read().image
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            img.save(dest)
            return True
    return False


def extract_types(mtga_dir, out_dir):
    saved = []
    kw = find_bundle(mtga_dir, "Atlas_KeywordIcons_")
    cond = find_bundle(mtga_dir, "Bucket_Card.Badge.Card_Badge_Condition_0_")
    jobs = []
    if kw:
        env = UnityPy.load(kw[0])
        jobs += [(env, "Icon_Type_Artifact"), (env, "Icon_Type_Enchantment")]
    if cond:
        env = UnityPy.load(cond[0])
        jobs += [(env, "NPE_Icon_Land")]
    for env, name in jobs:
        dest = os.path.join(out_dir, "type", name.replace("Icon_Type_", "").replace("NPE_Icon_", "") + ".png")
        if _save_sprite(env, name, dest):
            saved.append(dest)
        else:
            print("  [缺] sprite 未找到", name)
    return saved


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mtga-dir", default=DEFAULT_MTGA_DIR)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()
    if not os.path.isdir(args.mtga_dir):
        sys.exit("[错误] MTGA AssetBundle 目录不存在：%s（用 --mtga-dir 指定）" % args.mtga_dir)
    print("[wildcards]")
    saved = extract_wildcards(args.mtga_dir, args.out)
    print("  保存 %d 张" % len(saved))
    print("[mana]")
    saved2 = extract_mana(args.mtga_dir, args.out)
    print("  保存 %d 个符号" % len(saved2))
    print("[types]")
    saved3 = extract_types(args.mtga_dir, args.out)
    print("  保存 %d 个图标" % len(saved3))
    print("[注意] 鹏洛客/生物/法术/瞬间 在 MTGA 客户端无原生类型图标，未提取；"
          "如需展示请用文字或后续自行设计。")
    print("[完成] 输出目录：%s" % args.out)


if __name__ == "__main__":
    main()
