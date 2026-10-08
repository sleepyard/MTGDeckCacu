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

工具注册表外置在 mcp_tools.json（接口契约，入库）：启动时 load_registry
加载并 fail-fast 校验（缺字段/重名/未知 builder/script 文件不存在均
启动报错退出，不走兜底）；argv 构造逻辑保留在本文件 _ARGV_BUILDERS，
JSON 以 builder 名引用。run_tool 出口写运行自证行（runlog.log_run →
tools/data/run_log.jsonl，成功/超时/非零退出各一条，写失败静默跳过）。

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

import runlog

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "neomtgdeckcacu"
SERVER_VERSION = "1.1.0"
CALL_TIMEOUT = 180
MAX_OUTPUT_CHARS = 50000
REGISTRY_PATH = os.path.join(HERE, "mcp_tools.json")


def _fmt(value, default):
    return str(value or default).strip()


# name → argv 构造函数（builder 注册表；mcp_tools.json 以名字引用）
def _mtg_search_argv(a):
    return ["search", str(a.get("query") or ""), "--unique", "oracle"]


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


def _deck_cost_argv(a):
    return ["sig", str(a.get("deckfile") or "")]


def _rot_audit_argv(a):
    return [str(a.get("mode") or ""), str(a.get("target") or "")]


_ARGV_BUILDERS = {
    "mtg_search": _mtg_search_argv,
    "mtg_check": _mtg_check_argv,
    "mtg_baseline": _baseline_argv,
    "deck_validate": _validate_argv,
    "deck_cost": _deck_cost_argv,
    "rot_audit": _rot_audit_argv,
}

_REGISTRY_REQUIRED = (("name", str), ("description", str),
                      ("inputSchema", dict), ("script", str))


def load_registry(path=REGISTRY_PATH):
    """加载并校验 mcp_tools.json（接口契约，fail-fast，不走兜底）。

    校验：JSON 可读、tools 非空数组、逐条缺字段/类型错误、重名、
    builder 在 _ARGV_BUILDERS 中存在（省略 builder 字段时默认取与工具
    同名的 builder——约定式引用，同名也不存在即报错）、script 文件真实存在。
    任何违规抛 RuntimeError。
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"MCP 工具注册表加载失败: {path}: {exc}")
    entries = data.get("tools") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise RuntimeError(f"MCP 工具注册表缺非空 tools 数组: {path}")
    tools, seen = [], set()
    for i, entry in enumerate(entries):
        where = f"{path} tools[{i}]"
        if not isinstance(entry, dict):
            raise RuntimeError(f"{where}: 条目必须是对象")
        for key, typ in _REGISTRY_REQUIRED:
            value = entry.get(key)
            if not isinstance(value, typ) or (typ is str and not value):
                raise RuntimeError(f"{where}: 缺字段或类型错误: {key}")
        name = entry["name"]
        if name in seen:
            raise RuntimeError(f"{where}: 工具重名: {name}")
        seen.add(name)
        builder_name = entry.get("builder") or name   # 默认规则：与工具同名
        argv = _ARGV_BUILDERS.get(builder_name)
        if argv is None:
            raise RuntimeError(f"{where}: 未知 builder: {builder_name}")
        if not os.path.exists(os.path.join(HERE, entry["script"])):
            raise RuntimeError(f"{where}: script 文件不存在: {entry['script']}")
        tools.append({"name": name, "description": entry["description"],
                      "inputSchema": entry["inputSchema"],
                      "argv": argv, "script": entry["script"]})
    return tuple(tools)


try:
    TOOLS = load_registry()
    REGISTRY_ERROR = None
except RuntimeError as exc:   # 契约损坏：main() 启动即报错退出，见下
    TOOLS = ()
    REGISTRY_ERROR = exc

_TOOL_INDEX = {t["name"]: t for t in TOOLS}


def run_tool(tool, arguments):
    """子进程执行 CLI，返回 (text, is_error)；出口写运行自证行（runlog）。"""
    argv = tool["argv"](arguments)
    if not all(argv):
        raise ValueError("必填参数缺失或为空")
    cmd = [sys.executable, os.path.join(HERE, tool["script"])] + argv
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=CALL_TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        runlog.log_run(tool["name"], "timeout", f"执行超时（>{CALL_TIMEOUT}s）")
        raise
    text = proc.stdout
    if proc.stderr:
        text += ("\n" if text else "") + proc.stderr
    runlog.log_run(tool["name"], "error" if proc.returncode != 0 else "ok",
                   f"exit={proc.returncode} chars={len(text)}")
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
    if REGISTRY_ERROR is not None:
        print(f"[启动失败] {REGISTRY_ERROR}", file=sys.stderr)
        return 1
    if "--selftest" in sys.argv:
        print(f"{SERVER_NAME} v{SERVER_VERSION}，工具 {len(TOOLS)} 个"
              f"（注册表 {os.path.basename(REGISTRY_PATH)} 校验通过）：")
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
