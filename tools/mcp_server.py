#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NeoMtgDeckCacu MCP server（stdio，零依赖，仅 Python 标准库）。

把仓库的只读 CLI 能力以 MCP（Model Context Protocol）工具形式暴露给
CherryStudio / WorkBuddy / DeepSeek Harness 等聊天型 Agent 客户端——这些客户端
没有"clone 仓库跑脚本"的概念，MCP 是它们的统一接入方式。有 Shell 能力的编程
Agent（Kimi Code / Claude Code / Codex）请直接用 CLI + skills/，无需经此。

协议：stdio 传输，换行分隔的 JSON-RPC 2.0；实现 initialize / ping /
tools/list / tools/call 最小集。工具执行 = 子进程调用对应 CLI 脚本
（列表参数无 shell 拼接，UTF-8 输出），stdout/stderr 合并为文本结果，
非零退出码映射为 isError。

本 server 面向本机可信使用：deck_validate / deck_cost 接收本地文件路径。

客户端配置示例（CherryStudio / WorkBuddy 的 MCP JSON 同构）：
    {
      "mcpServers": {
        "neomtgdeckcacu": {
          "command": "python",
          "args": ["<仓库绝对路径>/tools/mcp_server.py"]
        }
      }
    }
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")

import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "neomtgdeckcacu"
SERVER_VERSION = "1.0.0"
CALL_TIMEOUT = 180
MAX_OUTPUT_CHARS = 50000


def _fmt(value, default):
    return str(value or default).strip()


# name → (description, inputSchema, argv 构造函数)
def _mtg_check_argv(a):
    names = a.get("names") or []
    if not isinstance(names, list) or not names:
        raise ValueError("names 必须为非空牌名数组")
    argv = ["check"] + [str(n) for n in names]
    argv += ["--format", _fmt(a.get("format"), "standard")]
    argv += ["--platform", _fmt(a.get("platform"), "arena")]
    return argv


def _validate_argv(a):
    deckfile = a.get("deckfile")
    if not deckfile:
        raise ValueError("deckfile 必填（牌表文件路径）")
    argv = ["validate", str(deckfile), "--format", _fmt(a.get("format"), "standard")]
    if a.get("bo3"):
        argv.append("--bo3")
    if a.get("colors"):
        argv += ["--colors", str(a["colors"])]
    return argv


def _baseline_argv(a):
    argv = ["baseline", "--format", _fmt(a.get("format"), "standard")]
    if a.get("date"):
        argv += ["--date", str(a["date"])]
    return argv


TOOLS = (
    {
        "name": "mtg_search",
        "description": "Scryfall 查询枚举候选牌（全分页 + oracle 去重，返回 JSON 数组）。"
                       "查询语法示例：f:standard game:arena ci<=ug o:flash t:creature",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Scryfall 查询式"},
            },
            "required": ["query"],
        },
        "argv": lambda a: ["search", str(a.get("query") or ""), "--unique", "oracle"],
        "script": "mtg_tool.py",
    },
    {
        "name": "mtg_check",
        "description": "逐牌三重核对：赛制合法 + Arena 平台可用 + mtgch 中文名（Markdown 表格）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "names": {"type": "array", "items": {"type": "string"},
                          "description": "英文牌名数组"},
                "format": {"type": "string", "description": "赛制，默认 standard；"
                           "explorer 按先驱别名推导"},
                "platform": {"type": "string", "description": "平台，默认 arena"},
            },
            "required": ["names"],
        },
        "argv": _mtg_check_argv,
        "script": "mtg_tool.py",
    },
    {
        "name": "mtg_baseline",
        "description": "赛制环境基线：已发售系列 + 未发售系列标注 + 禁牌表（Markdown，"
                       "可直接粘进报告）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "format": {"type": "string", "description": "赛制，默认 standard"},
                "date": {"type": "string", "description": "截止日期 YYYY-MM-DD，可选"},
            },
        },
        "argv": _baseline_argv,
        "script": "mtg_tool.py",
    },
    {
        "name": "deck_validate",
        "description": "牌表机器门禁：主牌≥60、备牌≤15、同名≤4（基本地与任意张数牌豁免）、"
                       "逐牌赛制+平台核查。失败非零退出，不写出。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deckfile": {"type": "string", "description": "牌表文件路径（MTGA 导入格式）"},
                "format": {"type": "string", "description": "赛制，默认 standard"},
                "bo3": {"type": "boolean", "description": "BO3 口径（含备牌检查）"},
                "colors": {"type": "string", "description": "颜色身份过滤，如 ug，可选"},
            },
            "required": ["deckfile"],
        },
        "argv": _validate_argv,
        "script": "mtg_tool.py",
    },
    {
        "name": "deck_cost",
        "description": "MTGA 造价核算：造价签名 + 物质点 + PP 包数（野卡用量口径，"
                       "与实际价格无关；需 tools/data/rarity_map.json，缺失先跑 "
                       "init_workspace.py --with-data）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deckfile": {"type": "string", "description": "牌表文件路径"},
            },
            "required": ["deckfile"],
        },
        "argv": lambda a: ["sig", str(a.get("deckfile") or "")],
        "script": os.path.join("newbie", "deck_cost.py"),
    },
    {
        "name": "rot_audit",
        "description": "标准轮替存活审计：判定牌表/单卡在下一次轮替后是否仍可用"
                       "（set_type + 非数字 + 发售日判据，免疫促销重印）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["deck", "card"]},
                "target": {"type": "string",
                           "description": "deck=牌表文件路径；card=英文牌名"},
            },
            "required": ["mode", "target"],
        },
        "argv": lambda a: [str(a.get("mode") or ""), str(a.get("target") or "")],
        "script": "rot_audit.py",
    },
)

_TOOL_INDEX = {t["name"]: t for t in TOOLS}


def run_tool(tool, arguments):
    """子进程执行 CLI，返回 (text, is_error)。"""
    argv = tool["argv"](arguments)
    if not all(argv):
        raise ValueError("必填参数缺失或为空")
    cmd = [sys.executable, os.path.join(HERE, tool["script"])] + argv
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          timeout=CALL_TIMEOUT, env=env)
    text = proc.stdout
    if proc.stderr:
        text += ("\n" if text else "") + proc.stderr
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + "\n…(输出过长已截断)"
    return text or "(无输出)", proc.returncode != 0


def make_error(code, message):
    return {"code": code, "message": message}


def handle(request):
    """处理单个 JSON-RPC 请求，返回响应 dict；通知返回 None。"""
    method = request.get("method")
    req_id = request.get("id")
    if method is None:
        return {"jsonrpc": "2.0", "id": req_id,
                "error": make_error(-32600, "Invalid Request")}
    if method.startswith("notifications/"):
        return None
    if req_id is None:
        return None  # 无 id 的未知通知，静默忽略

    if method == "initialize":
        client_ver = (request.get("params") or {}).get("protocolVersion")
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": client_ver or PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "tools": [{"name": t["name"], "description": t["description"],
                       "inputSchema": t["inputSchema"]} for t in TOOLS],
        }}
    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        tool = _TOOL_INDEX.get(name)
        if tool is None:
            return {"jsonrpc": "2.0", "id": req_id,
                    "error": make_error(-32602, f"未知工具: {name}")}
        try:
            text, is_error = run_tool(tool, params.get("arguments") or {})
        except ValueError as exc:
            return {"jsonrpc": "2.0", "id": req_id,
                    "error": make_error(-32602, str(exc))}
        except subprocess.TimeoutExpired:
            text, is_error = f"[错误] 执行超时（>{CALL_TIMEOUT}s）", True
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "content": [{"type": "text", "text": text}],
            "isError": is_error,
        }}
    return {"jsonrpc": "2.0", "id": req_id,
            "error": make_error(-32601, f"Method not found: {method}")}


def main():
    if "--selftest" in sys.argv:
        print(f"{SERVER_NAME} v{SERVER_VERSION}，工具 {len(TOOLS)} 个：")
        for t in TOOLS:
            print(f"  - {t['name']}: {t['description'][:40]}…")
        return 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            response = {"jsonrpc": "2.0", "id": None,
                        "error": make_error(-32700, "Parse error")}
        else:
            response = handle(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
