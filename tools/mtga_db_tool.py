#!/usr/bin/env python3
"""MTGA 卡牌数据库反查 CLI：按 grpId 反查英文牌名/系列/编号/稀有度。

直接读取 MTGA 客户端本地 SQLite 卡牌数据库（Raw_CardDatabase_*.mtga），
作为 Scryfall 查不到 arena_id 时的兜底。仅 Python 标准库（3.7+）。

用法：
    python tools/mtga_db_tool.py <CardDatabase.mtga路径> [grpId ...]

    无 grpId：列出数据库全部表名（探查模式）
    有 grpId：每行输出 "{grpId}: {牌名} [{系列} #{编号}] rarity={稀有度}"，
              查不到输出 "{grpId}: NOT FOUND"
"""

import argparse
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path


class MtgaDbToolError(Exception):
    pass


# ---------------------------------------------------------------- 数据库定位
def _steam_install_dirs():
    """Steam 安装目录候选：注册表 SteamPath（Windows）+ 两个默认路径。"""
    dirs = []
    try:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Valve\Steam") as key:
                dirs.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
        except OSError:
            pass
    except ImportError:
        pass
    dirs.append(Path("C:/Program Files (x86)/Steam"))
    dirs.append(Path("C:/Program Files/Steam"))
    return dirs


def _steam_library_roots():
    """Steam 库根目录列表：安装目录自带库 + libraryfolders.vdf 解析出的附加库。"""
    roots = []
    for steam in _steam_install_dirs():
        vdf = steam / "steamapps" / "libraryfolders.vdf"
        if not vdf.is_file():
            continue
        roots.append(steam)
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            roots.append(Path(match.group(1).replace("\\\\", "\\")))
    seen, unique = set(), []
    for root in roots:
        key = str(root).lower()
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def find_database():
    """自动定位最新的 MTGA 客户端卡库（Raw_CardDatabase_*.mtga）。

    优先环境变量 MTGA_CARD_DATABASE（直接指向 .mtga 文件）；否则扫描
    Steam 各库下的 MTGA 安装目录，取修改时间最新的一份。找不到返回 None。"""
    env = os.environ.get("MTGA_CARD_DATABASE")
    if env and Path(env).is_file():
        return Path(env)
    candidates = []
    for root in _steam_library_roots():
        raw = (root / "steamapps" / "common" / "MTGA" / "MTGA_Data"
               / "downloads" / "Raw")
        candidates.extend(raw.glob("Raw_CardDatabase_*.mtga"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


# ---------------------------------------------------------------- 数据库打开
def open_database(db_path):
    """复制 DB 到临时目录（避开运行中游戏的文件锁）后以只读方式打开。

    返回 (conn, tmp_dir)；调用方负责关闭 conn 并清理 tmp_dir。"""
    src = Path(db_path)
    if not src.is_file():
        raise MtgaDbToolError(f"数据库文件不存在: {src}")
    tmp_dir = Path(tempfile.mkdtemp(prefix="mtga_db_tool_"))
    try:
        tmp_db = tmp_dir / src.name
        shutil.copy(str(src), str(tmp_db))
        conn = sqlite3.connect(f"file:{tmp_db.as_posix()}?mode=ro", uri=True)
    except (OSError, sqlite3.Error) as exc:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)
        raise MtgaDbToolError(f"数据库打开失败: {exc}")
    return conn, tmp_dir


# ---------------------------------------------------------------- 表结构嗅探
def list_tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return [r[0] for r in rows]


def table_columns(conn, table):
    return [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]


def _pick(names, exact=None, contains=None):
    """先按 exact（忽略大小写）精确匹配，否则取第一个包含 contains 的名字。"""
    if exact:
        for n in names:
            if n.lower() == exact.lower():
                return n
    if contains:
        lowered = contains.lower()
        for n in names:
            if lowered in n.lower():
                return n
    return None


def sniff_cards_table(conn):
    table = _pick(list_tables(conn), exact="Cards", contains="card")
    if not table:
        raise MtgaDbToolError("表结构嗅探失败：找不到 cards 表")
    return table


def sniff_grp_column(conn, table):
    col = _pick(table_columns(conn, table), exact="grpId", contains="grp")
    if not col:
        raise MtgaDbToolError(f"表结构嗅探失败：{table} 表找不到 grp 列")
    return col


def sniff_localizations_table(conn):
    return _pick(list_tables(conn), exact="Localizations_enUS", contains="localiz")


# ---------------------------------------------------------------- 查询
def _row_get(row, cols, name):
    """按列名（忽略大小写）取值，宽容缺失。"""
    lowered = name.lower()
    for i, c in enumerate(cols):
        if c.lower() == lowered:
            return row[i]
    return None


def lookup_card(conn, table, grp_col, grp_id):
    """按 grpId 查一行，取 TitleId/ExpansionCode/CollectorNumber/Rarity。"""
    cols = table_columns(conn, table)
    row = conn.execute(
        f'SELECT * FROM "{table}" WHERE "{grp_col}" = ?', (grp_id,)).fetchone()
    if not row:
        return None
    return {
        "title_id": _row_get(row, cols, "TitleId"),
        "set_code": _row_get(row, cols, "ExpansionCode"),
        "number": _row_get(row, cols, "CollectorNumber"),
        "rarity": _row_get(row, cols, "Rarity"),
    }


def lookup_card_name(conn, loc_table, title_id):
    """Localizations_enUS 反查英文牌名。

    id 列 = 第一个含 "id" 的列（否则首列）；
    text 列 = 第一个含 "text" 或 "value" 的列（否则末列）。"""
    if not loc_table or title_id is None:
        return None
    cols = table_columns(conn, loc_table)
    if not cols:
        return None
    id_col = _pick(cols, contains="id") or cols[0]
    text_col = _pick(cols, contains="text") or _pick(cols, contains="value") or cols[-1]
    row = conn.execute(
        f'SELECT "{text_col}" FROM "{loc_table}" WHERE "{id_col}" = ?',
        (title_id,)).fetchone()
    return row[0] if row else None


def lookup_names(db_path, grp_ids):
    """批量反查：grpId 可迭代 → {str(grpId): {name, set_code, number, rarity}}。

    只含命中项；db_path 可为 find_database() 的返回路径。"""
    conn, tmp_dir = open_database(db_path)
    try:
        table = sniff_cards_table(conn)
        grp_col = sniff_grp_column(conn, table)
        loc_table = sniff_localizations_table(conn)
        out = {}
        for grp_id in grp_ids:
            card = lookup_card(conn, table, grp_col, int(grp_id))
            if not card:
                continue
            name = lookup_card_name(conn, loc_table, card["title_id"])
            if name:
                out[str(grp_id)] = {
                    "name": name, "set_code": card["set_code"],
                    "number": card["number"], "rarity": card["rarity"]}
        return out
    finally:
        conn.close()
        shutil.rmtree(str(tmp_dir), ignore_errors=True)


# ---------------------------------------------------------------- main
def build_parser():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("db", help="MTGA 卡牌数据库路径（Raw_CardDatabase_*.mtga），"
                              "或 auto 自动定位（环境变量 MTGA_CARD_DATABASE 优先）")
    p.add_argument("grpids", nargs="*", type=int, metavar="grpId",
                   help="要反查的 grpId（省略则列出全部表名）")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    db = args.db
    if db.lower() == "auto":
        found = find_database()
        if found is None:
            print("[错误] 未找到 MTGA 客户端卡库（可设环境变量 "
                  "MTGA_CARD_DATABASE 指定路径）", file=sys.stderr)
            return 2
        db = str(found)
    try:
        conn, tmp_dir = open_database(db)
    except MtgaDbToolError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    try:
        if not args.grpids:
            for name in list_tables(conn):
                print(name)
            return 0
        try:
            table = sniff_cards_table(conn)
            grp_col = sniff_grp_column(conn, table)
        except MtgaDbToolError as exc:
            print(f"[错误] {exc}", file=sys.stderr)
            return 2
        loc_table = sniff_localizations_table(conn)
        for grp_id in args.grpids:
            card = lookup_card(conn, table, grp_col, grp_id)
            if card is None:
                print(f"{grp_id}: NOT FOUND")
                continue
            name = lookup_card_name(conn, loc_table, card["title_id"]) or "?"
            set_code = card["set_code"] or "?"
            number = card["number"] or "?"
            rarity = card["rarity"] or "?"
            print(f"{grp_id}: {name} [{set_code} #{number}] rarity={rarity}")
        return 0
    finally:
        conn.close()
        shutil.rmtree(str(tmp_dir), ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
