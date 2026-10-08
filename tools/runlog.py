#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运行自证行（哦鲸鲸自证纪律的轻量落地）：工具运行留痕。

log_run(tool, status, summary) 向 tools/data/run_log.jsonl 追加一行 JSON
（UTC ISO 时间戳 + tool + status + summary）。铁纪律：全部异常吞掉——
写日志绝不能弄挂主流程；文件不可写时静默跳过。
run_log.jsonl 为本地留痕，已 gitignore（tools/data/* 覆盖）。

轮转：写入前文件超过 MAX_BYTES（5MB）就把现有文件改名为
run_log.1.jsonl（os.replace 覆盖旧 .1，只保留一代），然后写新文件；
轮转本身失败同样静默。

run_logged(tool, fn) 给 CLI 主出口的最外层包装：fn 抛异常（含
argparse 的 SystemExit(非 0)）时先记一条 status="error" 再原样上抛，
退出码与行为不变；正常返回不记（成功/业务失败的行由 fn 内部出口自记，
以便 summary 带上产物信息）。

当前接入点：mcp_server.run_tool 出口、deck_version / deck_image /
deck_pooper / set_preview_tool 的 CLI 主出口。
"""
import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "data", "run_log.jsonl")
MAX_BYTES = 5 * 1024 * 1024        # 超过即轮转
ROTATED_SUFFIX = ".1.jsonl"        # 只保留一代


def _rotate(path):
    """超限轮转：run_log.jsonl → run_log.1.jsonl（覆盖旧 .1）。失败静默。"""
    try:
        if os.path.getsize(path) > MAX_BYTES:
            base = path[:-len(".jsonl")] if path.endswith(".jsonl") else path
            os.replace(path, base + ROTATED_SUFFIX)
    except OSError:
        pass


def log_run(tool, status, summary, path=None):
    """追加一行运行记录；任何失败（含路径不可写、轮转失败）都静默跳过。

    path 缺省为 LOG_PATH（运行时取值，便于测试注入临时路径）。"""
    try:
        line = json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": str(tool),
            "status": str(status),
            "summary": str(summary),
        }, ensure_ascii=False)
        _rotate(path if path is not None else LOG_PATH)
        with open(path if path is not None else LOG_PATH, "a",
                  encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def run_logged(tool, fn, *args, **kwargs):
    """最外层包装：fn 抛 SystemExit(非 0)/异常时记 error 再原样上抛。"""
    try:
        return fn(*args, **kwargs)
    except SystemExit as exc:
        if exc.code:
            log_run(tool, "error", f"SystemExit({exc.code})")
        raise
    except Exception as exc:
        log_run(tool, "error", f"{type(exc).__name__}: {exc}")
        raise
