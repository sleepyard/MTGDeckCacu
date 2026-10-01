#!/usr/bin/env python3
"""mcp_server.py 回归测试：协议握手与工具分发，子进程边界全部 mock，无网络/磁盘 I/O。"""

import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mcp_server  # noqa: E402


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
                               return_value=proc) as run:
            resp = mcp_server.handle(_req("tools/call", params={
                "name": name, "arguments": arguments}))
        return resp, run

    def test_search_success(self):
        resp, run = self._call("mtg_search", {"query": "f:standard o:flash"})
        result = resp["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(result["content"][0]["text"], "ok-output")
        cmd = run.call_args[0][0]
        self.assertIn("mtg_tool.py", cmd[1])
        self.assertEqual(cmd[2:], ["search", "f:standard o:flash",
                                   "--unique", "oracle"])
        # 子进程强制 UTF-8，避免 Windows GBK 控制台乱码
        self.assertEqual(run.call_args[1]["env"]["PYTHONIOENCODING"], "utf-8")

    def test_nonzero_exit_maps_to_is_error(self):
        resp, run = self._call("deck_validate",
                               {"deckfile": "d.txt", "format": "pioneer",
                                "bo3": True},
                               proc=_FakeProc(stdout="bad", returncode=2))
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("--bo3", run.call_args[0][0])

    def test_stderr_merged_into_output(self):
        resp, _ = self._call("mtg_baseline", {"format": "pioneer"},
                             proc=_FakeProc(stdout="body", stderr="[错误] x"))
        self.assertEqual(resp["result"]["content"][0]["text"],
                         "body\n[错误] x")

    def test_unknown_tool(self):
        resp = mcp_server.handle(_req("tools/call", params={
            "name": "nope", "arguments": {}}))
        self.assertEqual(resp["error"]["code"], -32602)

    def test_missing_required_argument(self):
        resp, run = self._call("mtg_check", {"names": []})
        self.assertEqual(resp["error"]["code"], -32602)
        run.assert_not_called()

    def test_timeout_maps_to_is_error(self):
        with mock.patch.object(mcp_server.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("c", 1)):
            resp = mcp_server.handle(_req("tools/call", params={
                "name": "mtg_search", "arguments": {"query": "q"}}))
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("超时", resp["result"]["content"][0]["text"])

    def test_output_truncation(self):
        resp, _ = self._call("mtg_search", {"query": "q"},
                             proc=_FakeProc(stdout="x" * 60000))
        text = resp["result"]["content"][0]["text"]
        self.assertLess(len(text), 60000)
        self.assertIn("截断", text)


class TestMainLoop(unittest.TestCase):

    def _run_main(self, lines):
        stdin = io.StringIO("".join(json.dumps(l, ensure_ascii=False) + "\n"
                                    for l in lines))
        stdout = io.StringIO()
        with mock.patch.object(sys, "stdin", stdin), \
                mock.patch.object(sys, "stdout", stdout), \
                mock.patch.object(mcp_server.subprocess, "run",
                                  return_value=_FakeProc()):
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


if __name__ == "__main__":
    unittest.main()
