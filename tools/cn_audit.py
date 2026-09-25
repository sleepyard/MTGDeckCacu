#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文牌名审计门禁（v1.0）——交付前强制运行。

用途：抓出「英文名正确、中文名却是手写编造」的牌。这是历史上反复出现的事故
      （英文名走 API 抓取所以正确，中文名凭记忆手写所以出错）。

三种模式：
  python3 cn_audit.py check <文件...>      # ★ 主门禁：从交付文件里抽出所有中文牌名候选，逐个反查
  python3 cn_audit.py zh <中文名清单文件>   # 批量反查中文名（一行一个）
  python3 cn_audit.py en <英文名清单文件>   # 批量给出官方中文名（用于生成对照表）
  python3 cn_audit.py set <系列代码>       # 系列官方中文名（避免手写系列译名）

判定：
  ✓        精确命中一张真牌 → 合格
  ??       未精确命中，但模糊匹配到别的牌 → 需人工确认（往往是译名漂移）
  ✗✗       查无此牌 → ★ 编造译名，必须修正
  
  ⚠ 特别注意「碰巧命中别的牌」：如「毒疫」会命中 Virulent Plague（另一张牌）、
    「欧尼希兹」会命中 Ob Nixilis, the Ascended（另一位欧尼希兹）——check 模式会
    与文件里出现的英文牌名做交叉比对，把这类假阳性标为 ⚠。
"""
import subprocess, json, sys, os, re, time, urllib.parse

UA = "mtg-cn-audit/1.0"
MTGCH = "https://mtgch.com/api/v1"
SB = "https://api.scryfall.com"

# 表格表头/指标词等非牌名
STOP = set("""中文名 English 数量 费用 定位 献神 符号 改动 结论 依据 教训 版本 口径 指标 含义 原表 终稿
系列 状态 名称 理由 说明 牌 张 条 项 值 差 环节 判 备注 结果 概率 事件 总计 合计 小计 平均 回合 用地
地源 曲线 类型 有色需求 模块 主牌 备牌 地牌 引擎 终结 互动 惩罚件 放大器 组合件 对 清单 线 一 二 三
对手选 由你决定展示哪两张 由对手决定给你哪一张 事实 后果 谁选 内容 评估 配置 见上 判定 命中 需命中
快攻 铺场 控制 组合技 坟场 对局 死牌风险 备选来源 能否找放血魔 与放血魔 有放血魔 没有放血魔时几乎无用
只打对手 几乎不会是死牌 爆费回合可用法术力 空转回合 期望击杀 窥探深渊施放率 窥探深渊施放时已有惩罚件
抽牌引擎 终结件备份 备牌分工明确 牺牲一半永久物 弃一半手牌 干扰 去除 倍放大 地且无引擎
收集编号 竞技场核对 自研金鱼模拟器 本回合能凑出 直到回合结束 每咒语 张一费互动 张互动 张备牌
张惩罚件 张愿望爪护符 愿爪 斩客 暗贾 献神 沼泽 山脉 闪电 火 电震 脱除 收回 抄写 洗牌
快攻/铺场 效果 本轮终稿 同上 无 有 是 否 结论一 结论二 第一轮 第二轮 第三轮 版本一
主阶段 副阶段 换备 起手 留 调 不留 收口 线一 线二 线三 对局指南 运行清单 局限
牌表 导入 分功能表 门禁 校验 数据 结果 分析 建议 结论 附录 参考 注释 表格 图表
单变量扫描 基准 查询式 组合技口径 金鱼裁决力评估 纯吸取 保守战斗 公平计划 数值 弹药
衡量 判定 依据 教训 未杀 空转 献神 密度 加速 死牌 卡位 冗余 曲线 顶费 中费 低费
原因 原角色 均击杀回合 换入 换出 修正 已修正 错译 错误 正确 旧译 现译 正译
换入对局 日期 未译 来源 构型 禁牌 参照 对象 问题 应对 打法 思路 定位说明
英文名 首版 祭刃类去除按数量出 机制名 异能 关键词 类别 类别线 稀有度 颜色 法术力 官方正确译名 原先写的 正确译名 总费用 每符号费用 永久物 献神贡献 黑符号 你一共付了多少
改动 加 砍 数量调整 版本 字段 数值 组 用途 两张 共同点 加厚组 扫场组 干扰组 坟场组 终结组 杀招组 解威胁组 主牌要求 互动密度 互动数 备牌用途 备牌牌名 可有重复 对单个大威胁 对快攻 有放血魔时一张收口 配置 期望击杀 空转 手牌 代价 内容 改动 砍 加 理由 方案 模式 方向 用法 备选方案 工具箱模式 自选祈愿 局限 提醒 版本记录 实战操作 什么时候祈愿 两条收口线 保留起手 为什么杀招组放 组 对 用途 英武 设谋 连咒 中文卡图 机制名 系列名 系列代码""".split())
# 机制名不是牌名，不参与判定
# 牌型/原型名后缀：这些是 meta 里的套牌名称，不是牌名
ARCH_SUFFIX = ("快攻", "控制", "组合技", "中速", "兽群", "大军", "加速", "打脸", "消耗战",
               "精算", "要点", "类别", "细分", "占比", "原型名", "发售日", "一句话", "主系列",
               "关键张", "初判", "大类", "现有牌型", "色对", "灵技", "坟场", "生命", "直伤",
               "书院", "首领", "刺探", "获得了", "祭", "复活术", "掌控", "变体", "平台",
               "愈华", "结构", "论析", "铸丽", "项目", "展鉴", "棘毫", "族", "部族")
MECH = set("""英武 连咒 设谋 备法 后备 勘察 筹谋 调查 骑士 灵技 威胁 践踏 先攻 死触 系命 飞行 威吓
守护 敏捷 延势 不灭 警戒 灵气 结附 闪回 历险 变造 探索 暴烈 呼应 温存 兴奋 搜集 搜寻 坚忍""".split())

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "_cn_audit_cache.json")
_cache = {}
if os.path.exists(CACHE):
    try:
        _cache = json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        _cache = {}


def _save():
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        json.dump(_cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass


def zh_lookup(name):
    """中文名 → (状态, 真名, 英文名, set)。状态 ∈ exact/partial/none/error

    ⚠ 必须区分 none 与 error：mtgch 限流时返回空，若当成「查无此牌」会大规模误报。
    """
    if name in _cache:
        return tuple(_cache[name])
    res = ("error", "", "", "")
    got_json = False
    for attempt in range(4):
        for ep in (f"{MTGCH}/result?q=" + urllib.parse.quote(f'"{name}"') + "&view=0",
                   f"{MTGCH}/autocomplete/?q=" + urllib.parse.quote(name)):
            r = subprocess.run(["curl", "-sL", "--max-time", "20", "-H", f"User-Agent: {UA}", ep],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            try:
                d = json.loads(r.stdout)
                got_json = True
            except Exception:
                continue
            items = d.get("items") or []
            exact = [it for it in items
                     if (it.get("zhs_name") or it.get("display_name") or "").strip() == name.strip()]
            if exact:
                it = exact[0]
                res = ("exact", it.get("zhs_name") or it.get("display_name"), it.get("name", ""),
                       (it.get("set") or "").upper())
                _cache[name] = list(res); _save(); return res
            if items and res[0] != "partial":
                it = items[0]
                zhfield = it.get("zhs_name") or it.get("display_name") or ""
                en = it.get("name", "")
                # 回退：mtgch 对部分牌不返回中文字段 → 用英文名正向回查确认
                if not zhfield and en:
                    fwd = en_lookup(en)
                    if fwd and fwd.strip() == name.strip():
                        res = ("exact", fwd, en, (it.get("set") or "").upper())
                        _cache[name] = list(res); _save(); return res
                res = ("partial", zhfield, en, (it.get("set") or "").upper())
        if got_json:
            if res[0] == "error":
                res = ("none", "", "", "")   # 确实无匹配
            break
        time.sleep(1.5 * (attempt + 1))
    _cache[name] = list(res); _save()
    return res


def en_lookup(name):
    """英文名 → 官方中文（用 mtgch 的 result/autocomplete）"""
    for ep in (f"{MTGCH}/result?q=" + urllib.parse.quote(f'"{name}"') + "&view=0",
               f"{MTGCH}/autocomplete/?q=" + urllib.parse.quote(name)):
        r = subprocess.run(["curl", "-sL", "--max-time", "20", "-H", f"User-Agent: {UA}", ep],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        try:
            d = json.loads(r.stdout)
        except Exception:
            continue
        for it in (d.get("items") or []):
            if it.get("name", "").split(" // ")[0].lower() == name.lower():
                return it.get("zhs_name") or it.get("display_name") or name
    return name


def extract_zh(text):
    """抽出中文牌名候选。

    返回 (hard, soft)：
      hard —— 牌名表格里的中文串（**硬判定区**）
      soft —— 括号名称清单里的候选

    过滤策略：① 跳过 markdown 表头行（下一行是 |---|---| 的）；② STOP/机制名/牌型后缀/虚词过滤；
      ③ 中英混排格（`**中文名** English`）单独抽取。
    """
    hard, soft = {}, {}
    lines = text.split("\n")
    # 先按「连续 | 行」切出表格块
    blocks, cur = [], []
    for line in lines:
        if line.startswith("|"):
            cur.append(line)
        else:
            if cur:
                blocks.append(cur)
                cur = []
    if cur:
        blocks.append(cur)

    EN_CELL = re.compile(r"[A-Z][A-Za-z0-9,'’\-]*(?:\s+[A-Za-z0-9,'’\-]+)*")
    for block in blocks:
        for idx, line in enumerate(block):
            nxt = block[idx + 1].strip() if idx + 1 < len(block) else ""
            if nxt.startswith("|") and set(nxt.replace("|", "").replace(" ", "")) <= set("-:") and nxt.count("|") >= 2:
                continue                      # 表头行
            cells = [c.strip().strip("*").strip() for c in line.strip().strip("|").split("|")]
            for c in cells:
                c2 = c.replace("*", "").replace("`", "")
                # ★ 中英混排格：「中文名 English」成对出现 ⇒ 中文串就是牌名候选
                for m in re.finditer(r"([\u4e00-\u9fff][\u4e00-\u9fff·／/]{1,13})\s*([A-Z][A-Za-z0-9,'’\-]{2,40})", c2):
                    zh = m.group(1)
                    if re.search(r"[张以适配那是的了与和有时后就都也能这]", zh):
                        continue
                    if zh not in STOP and not zh.endswith(ARCH_SUFFIX) and len(zh) >= 2:
                        hard.setdefault(zh, "cell-pair")
                if re.fullmatch(r"[\u4e00-\u9fff][\u4e00-\u9fff／/·]{1,13}", c):
                    if c in STOP or c in MECH or c.endswith(ARCH_SUFFIX):
                        continue
                    if "//" in c:
                        hard[c.replace("//", " // ")] = "table-dfc"
                    if "/" in c or "／" in c:
                        for part in re.split(r"[／/]+", c):
                            part = part.strip()
                            if len(part) >= 2 and part not in STOP:
                                hard.setdefault(part, "table-split")
                    else:
                        hard[c] = "table"

    # 散文区：只抓「括号里的名称清单」——这类格式几乎必然是牌名列举
    for line in lines:
        if line.startswith("|"):
            continue
        for m in re.finditer(r"[（(]([^（()）]{2,80})[）)]", line):
            inner = m.group(1)
            if not re.search(r"[／/、]", inner):
                continue
            for part in re.split(r"[／/、]", inner):
                part = re.sub(r"[×xX]\s*\d+$", "", part).strip(" 　*~～")
                if re.search(r"[把是在若则就也都会能这那等换成要不没有我你他其并且]", part):
                    continue
                if re.fullmatch(r"[\u4e00-\u9fff][\u4e00-\u9fff·]{1,12}", part) and part not in STOP:
                    soft[part] = "paren-list"
    return hard, soft


def extract_en(text):
    """抽出英文牌名候选：支持「4 Card Name」以及一行两列的牌表（4 A    4 B）。"""
    names = set()
    pat = re.compile(r"\b\d+\s+([A-Z][A-Za-z0-9,'\-]+(?:\s+(?:of|the|to|in|from|and|a|an)?\s*[A-Z][A-Za-z0-9,'\-]*)*)")
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            continue
        for m in pat.finditer(line):
            n = m.group(1).strip().rstrip(",")
            if 2 <= len(n) <= 45:
                names.add(n)
        for m in re.finditer(r'!"([^"]+)"', line):
            names.add(m.group(1))
    return names


def cmd_check(paths, ignore=None):
    ignore = set(ignore or [])
    text = ""
    for p in paths:
        if os.path.isfile(p):
            text += open(p, encoding="utf-8").read() + "\n"
            side = p + ".cnignore"
            if os.path.exists(side):
                ignore |= {l.strip() for l in open(side, encoding="utf-8") if l.strip() and not l.startswith("#")}
    ens = extract_en(text)
    zh_of_en = {}
    for e in sorted(ens):
        zh_of_en[e] = en_lookup(e)
        time.sleep(0.3)
    official = set()
    for e, z in zh_of_en.items():
        for part in re.split(r"\s*//\s*", z):
            if part.strip():
                official.add(part.strip())

    hard, soft = extract_zh(text)
    for k in list(hard):
        if k in ignore:
            del hard[k]
    bad, warn, fake, err = [], [], [], []
    for zh in sorted(hard):
        st, real, en, st_set = zh_lookup(zh)
        if st == "error":
            err.append(zh)
        elif st == "exact":
            if any(o.startswith(zh) or zh.startswith(o) for o in official if o):
                continue                      # 双面牌的某一面 / 简写，合格
            base = en.split(" // ")[0].strip()
            first = re.split(r"[ ,]", base)[0]
            present = base in text or (len(first) >= 4 and first in text)
            if not present and zh not in official:
                warn.append((zh, f"{en} [{st_set}]", "撞名"))
        elif st == "partial":
            if any(o.startswith(zh) or zh.startswith(o) for o in official if o):
                continue
            # 回退：mtgch 对部分牌不返回中文字段 ⇒ 若其英文名就出现在本文件里，视为合格
            if en:
                base = en.split(" // ")[0].strip()
                first = re.split(r"[ ,]", base)[0]
                if base in text or (len(first) >= 4 and first in text):
                    continue
            warn.append((zh, f"{real} = {en} [{st_set}]", "未精确命中"))
        else:
            fake.append(zh)
        time.sleep(0.25)

    # ★ 散文区候选：≥3 字且含「牌名特征词根」的也查一次（只报 ⚠，不判失败）
    PROSE_HINT = ("魔", "妖", "僧", "师", "女", "领", "客", "兽", "龙", "灵", "神", "使",
                  "阁楼", "墓穴", "课室", "厅", "馆", "院", "台", "室", "祭", "刃", "记",
                  "客", "刀", "卫", "督", "主", "后裔", "恶魔", "巨像", "法师")
    for zh in sorted(soft):
        if zh in hard or zh in fake or len(zh) < 3:
            continue
        if not any(h in zh for h in PROSE_HINT):
            continue
        st, real, en, st_set = zh_lookup(zh)
        if st == "none":
            warn.append((zh, "", "散文区未命中"))
        time.sleep(0.25)

    print(f"=== 中文牌名审计 ===")
    print(f"文件里的英文牌名 {len(ens)} 个；中文牌名候选（表格区）{len(hard)} 个\n")
    if fake:
        print(f"✗✗ 查无此牌名（编造译名，必须修正）：{len(fake)} 个")
        for f in fake:
            print("     ", f)
    if warn:
        print(f"\n⚠  需人工确认（未精确命中或可能张冠李戴）：{len(warn)} 个")
        for item in warn:
            if len(item) == 3 and item[2] == "散文区未命中":
                print(f"      {item[0]}  →  括号名称清单里出现的串，查无此牌名（若是牌名请修正）")
            elif len(item) == 3 and item[2] == "未精确命中":
                print(f"      {item[0]}  →  最接近：{item[1]}")
            else:
                zh, en, st = item
                print(f"      {zh}  →  命中的是 {en} [{st}]，但该英文牌名未出现在文件里（疑似撞名）")
    if err:
        print(f"\n⚠  查询失败（限流，需重跑）：{len(err)} 个 — {', '.join(err[:6])}")
    if not fake and not warn and not err:
        print("✅ 全部中文牌名均精确命中真牌")
    print(f"\n（另有 {len(soft)} 个散文候选未纳入判定，属正常噪声）")
    print(f"\n官方中文对照（供核对）：")
    for e in sorted(zh_of_en):
        print(f"    {e:34s} → {zh_of_en[e]}")
    return 1 if fake else 0


def cmd_zh(path):
    names = [l.strip() for l in open(path, encoding="utf-8") if l.strip()]
    bad = []
    for n in names:
        st, zh, en, s = zh_lookup(n)
        if st == "exact":
            print(f"✓ {n:34s} → {en} [{s}]")
        elif st == "partial":
            print(f"?? {n:34s} → 未精确命中，最接近 {zh} = {en} [{s}]")
            bad.append(n)
        else:
            print(f"✗✗ {n:34s} → 查无此牌名")
            bad.append(n)
        time.sleep(0.3)
    print(f"\n=== 可疑 {len(bad)} 条 ===")
    for b in bad:
        print("  ", b)
    return 1 if bad else 0


def cmd_en(path):
    names = [l.strip() for l in open(path, encoding="utf-8") if l.strip()]
    for n in names:
        print(f"{n:34s} → {en_lookup(n)}")
        time.sleep(0.3)
    return 0


def set_zh(code):
    """查询系列的官方中文名（mtgch /api/v1/set/<CODE>/ 的 translated_name）。

    用途：避免手写系列译名（如 FRA → 现实裂界）。历史事故：曾把 FRA 写成「现实外推」。
    """
    r = subprocess.run(["curl", "-sL", "--max-time", "20", "-H", f"User-Agent: {UA}",
                        f"{MTGCH}/set/{code.upper()}/"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    try:
        d = json.loads(r.stdout).get("set_info", {})
    except Exception:
        return None
    return d.get("translated_name") or d.get("name")


def cmd_set(code):
    print(f"{code.upper()} → {set_zh(code)}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "check":
        args2, ign = [], []
        it = iter(args)
        for a in it:
            if a == "--ignore":
                ign = [x.strip() for x in next(it).split(",") if x.strip()]
            else:
                args2.append(a)
        sys.exit(cmd_check(args2, ign))
    elif cmd == "zh":
        sys.exit(cmd_zh(args[0]))
    elif cmd == "en":
        sys.exit(cmd_en(args[0]))
    elif cmd == "set":
        sys.exit(cmd_set(args[0]))
    else:
        print(__doc__)
        sys.exit(2)
