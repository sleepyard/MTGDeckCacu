#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新克隆仓库的工作区初始化：目录骨架 + LLM 配置模板 + 可选数据快照重建。

用法：
    python tools/init_workspace.py               # 建目录骨架 + 复制 llm_config 模板
    python tools/init_workspace.py --with-data   # 追加联网重建 tools/data/rarity_map.json

本地产出目录一律 gitignored 不入库（见 .gitignore）；本脚本只补骨架与模板，
已存在的文件绝不覆盖。可选依赖（Pillow / UnityPy / Forge / JDK / MTGA 客户端）
缺失不影响核心 CLI，仅对应增强功能不可用。
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import argparse
import importlib.util
import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 与 .gitignore 保持一致的本地产出目录
DIRS = (
    "tools/cache",
    "tools/data",
    "tools/downloads",
    "MatchRecord",
    "DeckList",
    "SetReview",
    "SimResult",
    "AuditReport",
)

LLM_CONFIG_EXAMPLE = os.path.join(HERE, "llm_config.example.json")
LLM_CONFIG = os.path.join(HERE, "llm_config.json")
FETCH_RARITY = os.path.join(HERE, "newbie", "fetch_rarity.py")


def make_dirs():
    for rel in DIRS:
        path = os.path.join(ROOT, rel)
        os.makedirs(path, exist_ok=True)
        print(f"[dir] {rel}/")


def setup_llm_config():
    if os.path.isfile(LLM_CONFIG):
        print("[cfg] tools/llm_config.json 已存在，跳过")
        return
    shutil.copyfile(LLM_CONFIG_EXAMPLE, LLM_CONFIG)
    print("[cfg] 已复制 tools/llm_config.example.json → tools/llm_config.json"
          "（填入 api_key，或用环境变量 DEEPSEEK_API_KEY 覆盖）")


def rebuild_data():
    if not os.path.isfile(FETCH_RARITY):
        print(f"[data] 未找到 {FETCH_RARITY}，跳过", file=sys.stderr)
        return 1
    print("[data] 联网重建 tools/data/rarity_map.json（首次较慢，有磁盘缓存）...")
    return subprocess.call([sys.executable, FETCH_RARITY], cwd=ROOT)


def check_optional(name, ok, hint):
    mark = "OK" if ok else "--"
    print(f"[{mark}] {name}: {hint}")


def print_checklist():
    print("\n可选依赖检查（缺失仅影响对应增强功能）：")
    check_optional("Pillow",
                   importlib.util.find_spec("PIL") is not None,
                   "deck_image.py 牌表图 / 图标渲染（pip install pillow）")
    check_optional("UnityPy",
                   importlib.util.find_spec("UnityPy") is not None,
                   "extract_mtga_icons.py 本机 MTGA 图标提取（pip install UnityPy）")
    check_optional("Forge", os.path.isdir(os.path.join(HERE, "forge")),
                   "forge_tool.py sim/play（下载说明见 tools/README.md）")
    check_optional("JDK", os.path.isdir(os.path.join(HERE, "jdk")),
                   "Forge 运行时（便携 JDK 放 tools/jdk/）")
    check_optional("Ref/forge", os.path.isdir(os.path.join(ROOT, "Ref", "forge")),
                   "forge_tool.py track / 新系列源码快照（git clone 见 tools/README.md）")
    check_optional("LLM api_key",
                   bool(os.environ.get("DEEPSEEK_API_KEY")),
                   "轮抓/对局 LLM 建议（llm_config.json 或 DEEPSEEK_API_KEY）")
    check_optional("rarity_map",
                   os.path.isfile(os.path.join(HERE, "data", "rarity_map.json")),
                   "tools/newbie/ 造价核算快照（--with-data 联网重建）")


def main():
    parser = argparse.ArgumentParser(description="新克隆仓库的工作区初始化")
    parser.add_argument("--with-data", action="store_true",
                        help="联网重建 tools/data/rarity_map.json 标准牌池快照")
    args = parser.parse_args()

    make_dirs()
    setup_llm_config()
    rc = 0
    if args.with_data:
        rc = rebuild_data()
    print_checklist()
    print("\n初始化完成。回归测试：python -m unittest discover -s tools -p \"test_*.py\"")
    return rc


if __name__ == "__main__":
    sys.exit(main())
