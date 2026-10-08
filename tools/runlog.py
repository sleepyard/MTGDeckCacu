#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运行自证行（哦鲸鲸自证纪律的轻量落地）：工具运行留痕。

log_run(tool, status, summary) 向 tools/data/run_log.jsonl 追加一行 JSON
（UTC ISO 时间戳 + tool + status + summary）。铁纪律：全部异常吞掉——
写日志绝不能弄挂主流程；文件不可写时静默跳过。
run_log.jsonl 为本地留痕，已 gitignore（tools/data/* 覆盖）。

当前接入点：mcp_server.run_tool 出口（成功/超时/非零退出各记一条，
覆盖 6 个 MCP 暴露工具）。其他脚本暂不接。
"""
import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "data", "run_log.jsonl")


def log_run(tool, status, summary, path=LOG_PATH):
    """追加一行运行记录；任何失败（含路径不可写）都静默跳过。"""
    try:
        line = json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": str(tool),
            "status": str(status),
            "summary": str(summary),
        }, ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
