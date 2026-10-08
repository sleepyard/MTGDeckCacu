#!/usr/bin/env python3
"""mcp_server.py 回归测试：协议握手与工具分发，子进程边界全部 mock，无网络/磁盘 I/O。"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mcp_server  # noqa: E402
import runlog  # noqa: E402


def _req(method, req_id=1, params=None):
    req = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        req["params"] = params
    return req


class TestProtocol(unittest.TestCase):

    def test_initialize_echoes_client_version(self):
        resp = mcp_server.handle(_req("initialize", params={
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"}}))
        self.assertEqual(resp["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual(resp["result"]["serverInfo"]["name"], "neomtgdeckcacu")
        self.assertIn("tools", resp["result"]["capabilities"])

    def test_initialize_default_version(self):
        resp = mcp_server.handle(_req("initialize", params={}))
        self.assertEqual(resp["result"]["protocolVersion"],
                         mcp_server.PROTOCOL_VERSION)

    def test_ping(self):
        self.assertEqual(mcp_server.handle(_req("ping"))["result"], {})

    def test_notification_returns_none(self):
        self.assertIsNone(mcp_server.handle(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_unknown_method(self):
        resp = mcp_server.handle(_req("resources/list"))
        self.assertEqual(resp["error"]["code"], -32601)

    def test_tools_list_shape(self):
        resp = mcp_server.handle(_req("tools/list"))
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}
        self.assertEqual(names, {"mtg_search", "mtg_check", "mtg_baseline",
                                 "deck_validate", "deck_cost", "rot_audit"})
        for tool in tools:
            self.assertIn("inputSchema", tool)
            self.assertEqual(tool["inputSchema"]["type"], "object")


class _FakeProc:
    def __init__(self, stdout="ok-output", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class TestToolCall(unittest.TestCase):

    def _call(self, name, arguments, proc=None):
        proc = proc or _FakeProc()
        with mock.patch.object(mcp_server.subprocess, "run",
                               return_value=proc) as run, \
                mock.patch.object(mcp_server.runlog, "log_run") as log:
            resp = mcp_server.handle(_req("tools/call", params={
                "name": name, "arguments": arguments}))
        return resp, run, log

    def test_search_success(self):
        resp, run, log = self._call("mtg_search", {"query": "f:standard o:flash"})
        result = resp["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(result["content"][0]["text"], "ok-output")
        cmd = run.call_args[0][0]
        self.assertIn("mtg_tool.py", cmd[1])
        self.assertEqual(cmd[2:], ["search", "f:standard o:flash",
                                   "--unique", "oracle"])
        # 子进程强制 UTF-8，避免 Windows GBK 控制台乱码
        self.assertEqual(run.call_args[1]["env"]["PYTHONIOENCODING"], "utf-8")
        # 运行自证行：成功出口记一条 ok
        log.assert_called_once_with("mtg_search", "ok", "exit=0 chars=9")

    def test_nonzero_exit_maps_to_is_error(self):
        resp, run, log = self._call("deck_validate",
                                    {"deckfile": "d.txt", "format": "pioneer",
                                     "bo3": True},
                                    proc=_FakeProc(stdout="bad", returncode=2))
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("--bo3", run.call_args[0][0])
        # 运行自证行：非零退出记一条 error（含退出码与输出长度）
        log.assert_called_once_with("deck_validate", "error", "exit=2 chars=3")

    def test_stderr_merged_into_output(self):
        resp, _, log = self._call("mtg_baseline", {"format": "pioneer"},
                                  proc=_FakeProc(stdout="body", stderr="[错误] x"))
        self.assertEqual(resp["result"]["content"][0]["text"],
                         "body\n[错误] x")
        log.assert_called_once_with("mtg_baseline", "ok", "exit=0 chars=11")

    def test_unknown_tool(self):
        resp = mcp_server.handle(_req("tools/call", params={
            "name": "nope", "arguments": {}}))
        self.assertEqual(resp["error"]["code"], -32602)
        self.assertIn("未知工具", resp["error"]["message"])

    def test_missing_required_argument(self):
        resp, run, log = self._call("mtg_check", {"names": []})
        self.assertEqual(resp["error"]["code"], -32602)
        run.assert_not_called()
        log.assert_not_called()        # 参数校验失败不走子进程，也不记自证行

    def test_timeout_maps_to_is_error(self):
        with mock.patch.object(mcp_server.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("c", 1)), \
                mock.patch.object(mcp_server.runlog, "log_run") as log:
            resp = mcp_server.handle(_req("tools/call", params={
                "name": "mtg_search", "arguments": {"query": "q"}}))
        self.assertTrue(resp["result"]["isError"])
        # 180s 超时 → 错误映射的精确文案
        self.assertEqual(resp["result"]["content"][0]["text"],
                         "[错误] 执行超时（>180s）")
        # 运行自证行：超时记一条 timeout
        log.assert_called_once_with("mtg_search", "timeout", "执行超时（>180s）")

    def test_output_truncation(self):
        resp, _, _ = self._call("mtg_search", {"query": "q"},
                                proc=_FakeProc(stdout="x" * 60000))
        text = resp["result"]["content"][0]["text"]
        self.assertLess(len(text), 60000)
        self.assertIn("截断", text)

    def test_output_truncation_exact_contract(self):
        """50K 截断契约的精确行为：text[:50000] + "\\n…(输出过长已截断)"。"""
        resp, _, _ = self._call("mtg_search", {"query": "q"},
                                proc=_FakeProc(stdout="x" * 50001))
        text = resp["result"]["content"][0]["text"]
        self.assertEqual(text, "x" * 50000 + "\n…(输出过长已截断)")

    def test_output_exactly_50k_not_truncated(self):
        resp, _, _ = self._call("mtg_search", {"query": "q"},
                                proc=_FakeProc(stdout="x" * 50000))
        self.assertEqual(resp["result"]["content"][0]["text"], "x" * 50000)


class TestMainLoop(unittest.TestCase):

    def _run_main(self, lines):
        stdin = io.StringIO("".join(json.dumps(l, ensure_ascii=False) + "\n"
                                    for l in lines))
        stdout = io.StringIO()
        with mock.patch.object(sys, "stdin", stdin), \
                mock.patch.object(sys, "stdout", stdout), \
                mock.patch.object(mcp_server.subprocess, "run",
                                  return_value=_FakeProc()), \
                mock.patch.object(mcp_server.runlog, "log_run"):
            mcp_server.main()
        out = stdout.getvalue()
        return [json.loads(l) for l in out.splitlines() if l.strip()]

    def test_session_flow(self):
        responses = self._run_main([
            _req("initialize", req_id=1, params={}),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            _req("tools/list", req_id=2),
            _req("tools/call", req_id=3, params={
                "name": "rot_audit", "arguments": {"mode": "card",
                                                   "target": "Abrade"}}),
        ])
        # 通知不产生响应
        self.assertEqual([r["id"] for r in responses], [1, 2, 3])
        self.assertEqual(responses[2]["result"]["content"][0]["text"],
                         "ok-output")

    def test_malformed_line_gets_parse_error(self):
        stdin = io.StringIO("not-json\n")
        stdout = io.StringIO()
        with mock.patch.object(sys, "stdin", stdin), \
                mock.patch.object(sys, "stdout", stdout):
            mcp_server.main()
        resp = json.loads(stdout.getvalue().strip())
        self.assertEqual(resp["error"]["code"], -32700)
        self.assertIsNone(resp["id"])


# ---------------------------------------------------------------- 注册表契约（Phase 4）
class TestRegistryContract(unittest.TestCase):
    """mcp_tools.json 是接口定义：tools/list 输出必须与之逐键一致。"""

    def _registry_json(self):
        with open(mcp_server.REGISTRY_PATH, encoding="utf-8") as fh:
            return json.load(fh)

    def test_tools_list_matches_registry_json(self):
        resp = mcp_server.handle(_req("tools/list"))
        listed = resp["result"]["tools"]
        entries = self._registry_json()["tools"]
        self.assertEqual(len(listed), len(entries))
        for got, want in zip(listed, entries):
            self.assertEqual(got["name"], want["name"])
            self.assertEqual(got["description"], want["description"])
            self.assertEqual(got["inputSchema"], want["inputSchema"])

    def test_registry_scripts_exist_on_disk(self):
        for entry in self._registry_json()["tools"]:
            path = os.path.join(mcp_server.HERE, entry["script"])
            self.assertTrue(os.path.exists(path), entry["script"])

    def test_registry_loaded_into_tool_index(self):
        self.assertEqual(set(mcp_server._TOOL_INDEX),
                         {e["name"] for e in self._registry_json()["tools"]})


class TestRegistryValidation(unittest.TestCase):
    """注册表校验 fail-fast：缺字段/重名/未知 builder/script 缺失均报错。"""

    def _write(self, obj):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            if isinstance(obj, str):
                fh.write(obj)
            else:
                json.dump(obj, fh, ensure_ascii=False)
        self.addCleanup(os.remove, path)
        return path

    def _entry(self, **over):
        entry = {"name": "mtg_search", "description": "d",
                 "inputSchema": {"type": "object"},
                 "script": "mtg_tool.py", "builder": "mtg_search"}
        entry.update(over)
        return entry

    def test_valid_minimal_registry(self):
        path = self._write({"tools": [self._entry()]})
        tools = mcp_server.load_registry(path)
        self.assertEqual(tools[0]["name"], "mtg_search")
        self.assertIs(tools[0]["argv"], mcp_server._ARGV_BUILDERS["mtg_search"])

    def test_builder_defaults_to_tool_name(self):
        """默认直传规则：省略 builder 字段时取与工具同名的 builder。"""
        entry = self._entry()
        del entry["builder"]
        path = self._write({"tools": [entry]})
        tools = mcp_server.load_registry(path)
        self.assertIs(tools[0]["argv"], mcp_server._ARGV_BUILDERS["mtg_search"])

    def test_duplicate_name_rejected(self):
        path = self._write({"tools": [self._entry(), self._entry()]})
        with self.assertRaisesRegex(RuntimeError, "重名"):
            mcp_server.load_registry(path)

    def test_missing_key_rejected(self):
        entry = self._entry()
        del entry["inputSchema"]
        path = self._write({"tools": [entry]})
        with self.assertRaisesRegex(RuntimeError, "inputSchema"):
            mcp_server.load_registry(path)

    def test_unknown_builder_rejected(self):
        path = self._write({"tools": [self._entry(builder="no_such_builder")]})
        with self.assertRaisesRegex(RuntimeError, "未知 builder"):
            mcp_server.load_registry(path)

    def test_missing_script_rejected(self):
        path = self._write({"tools": [self._entry(script="no_such_script.py")]})
        with self.assertRaisesRegex(RuntimeError, "script"):
            mcp_server.load_registry(path)

    def test_malformed_json_rejected(self):
        path = self._write("{not json")
        with self.assertRaises(RuntimeError):
            mcp_server.load_registry(path)

    def test_missing_file_rejected(self):
        with self.assertRaises(RuntimeError):
            mcp_server.load_registry("no_such_registry.json")

    def test_empty_tools_rejected(self):
        path = self._write({"tools": []})
        with self.assertRaises(RuntimeError):
            mcp_server.load_registry(path)

    def test_selftest_reports_registry_error(self):
        """注册表损坏时 main() 启动即明确报错（含 --selftest 路径）。"""
        stderr = io.StringIO()
        with mock.patch.object(mcp_server, "REGISTRY_ERROR",
                               RuntimeError("boom")), \
                mock.patch.object(sys, "argv", ["mcp_server.py", "--selftest"]), \
                mock.patch.object(sys, "stderr", stderr):
            rc = mcp_server.main()
        self.assertEqual(rc, 1)
        self.assertIn("启动失败", stderr.getvalue())
        self.assertIn("boom", stderr.getvalue())


# ---------------------------------------------------------------- 运行自证行（Phase 4）
class TestRunLog(unittest.TestCase):

    def test_log_run_appends_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "run_log.jsonl")
            runlog.log_run("mtg_search", "ok", "exit=0 chars=9", path=path)
            runlog.log_run("deck_cost", "error", "exit=2 chars=3", path=path)
            lines = Path(path).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        rec = json.loads(lines[0])
        self.assertEqual(set(rec), {"ts", "tool", "status", "summary"})
        self.assertEqual(rec["tool"], "mtg_search")
        self.assertEqual(rec["status"], "ok")
        self.assertEqual(rec["summary"], "exit=0 chars=9")
        # 时间戳为 UTC ISO 格式且可解析
        datetime.fromisoformat(rec["ts"])
        self.assertEqual(json.loads(lines[1])["status"], "error")

    def test_log_run_swallows_write_failure(self):
        """写日志绝不能弄挂主流程：路径不可写时静默跳过。"""
        runlog.log_run("x", "ok", "s", path=os.path.join(
            "no_such_dir", "deep", "run_log.jsonl"))  # 不抛即过

    def test_log_run_default_path_under_tools_data(self):
        self.assertTrue(mcp_server_runlog_path().endswith(
            os.path.join("tools", "data", "run_log.jsonl")))


def mcp_server_runlog_path():
    return os.path.normpath(runlog.LOG_PATH)


if __name__ == "__main__":
    unittest.main()
