"""Codex backend adapter regressions; app-server protocol mocked, no real CLI."""
import json
import queue
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import workbench_agent_codex as codex


class FakeRpcClient:
    def __init__(self):
        self.events = queue.Queue()
        self.closed = threading.Event()
        self.calls = []
        self.replies = []

    def request(self, method, params=None, timeout=30):
        self.calls.append((method, params))
        if method in ("thread/start", "thread/resume"):
            return {"thread": {"id": "workbench-thread"}, "model": "configured-model"}
        if method == "turn/start":
            return {"turn": {"id": "turn-1"}}
        return {}

    def notify(self, method, params=None):
        self.calls.append((method, params))

    def reply(self, key, result=None, error=None):
        self.replies.append((key, result, error))

    def event(self, timeout=1):
        try:
            return self.events.get(timeout=min(timeout, .05))
        except queue.Empty:
            if self.closed.is_set():
                raise RuntimeError("Client disconnected")
            return None

    def close(self):
        self.closed.set()


class FakeHooks:
    def __init__(self):
        self.progress_messages = []
        self.approval_views = []
        self.approval_decision = "accept"
        self.fail_approval = False

    def keepalive(self):
        pass

    def progress(self, message):
        self.progress_messages.append(message)

    def approval(self, view):
        self.approval_views.append(view)
        if self.fail_approval:
            raise RuntimeError("接收端已断开")
        return self.approval_decision


def answer_item(text='{"status":"ok","message":"m","result":{}}'):
    return {"type": "agentMessage", "text": text, "phase": "final_answer"}


class CodexBackendTests(unittest.TestCase):
    def setUp(self):
        self.rpc = FakeRpcClient()
        self.backend = codex.CodexBackend(client_factory=lambda: self.rpc)
        self.hooks = FakeHooks()

    def complete_turn(self, status="completed", error=None, items=None):
        self.rpc.events.put({"method": "turn/completed", "params": {
            "threadId": "workbench-thread",
            "turn": {"id": "turn-1", "status": status, "error": error,
                     "items": items if items is not None else [answer_item()]}}})

    def test_open_handshakes_and_begin_session_starts_or_resumes_thread(self):
        self.backend.open()
        methods = [method for method, _ in self.rpc.calls]
        self.assertEqual(methods, ["initialize", "initialized"])
        self.assertFalse(self.backend.alive() is False)
        info = self.backend.begin_session()
        self.assertEqual(info, {"thread_id": "workbench-thread", "model": "configured-model"})
        self.assertEqual(self.rpc.calls[-1][0], "thread/start")
        self.assertEqual(self.rpc.calls[-1][1]["approvalPolicy"], "on-request")
        info = self.backend.begin_session("saved-thread")
        self.assertEqual(self.rpc.calls[-1][0], "thread/resume")
        self.assertEqual(self.rpc.calls[-1][1]["threadId"], "saved-thread")

    def test_alive_drops_when_client_disconnects(self):
        self.backend.open()
        self.assertTrue(self.backend.alive())
        self.rpc.closed.set()
        self.assertFalse(self.backend.alive())

    def test_run_turn_returns_final_answer_text_and_reports_progress(self):
        self.backend.open()
        self.backend.begin_session()
        self.rpc.events.put({"method": "item/started", "params": {
            "threadId": "workbench-thread", "turnId": "turn-1",
            "item": {"type": "commandExecution"}}})
        self.complete_turn()
        text = self.backend.run_turn("prompt", self.hooks)
        self.assertEqual(json.loads(text)["status"], "ok")
        self.assertEqual(self.backend.last_turn_id, "turn-1")
        self.assertEqual(self.hooks.progress_messages, ["正在执行查证工具"])

    def test_failed_turn_raises_with_provider_message(self):
        self.backend.open()
        self.backend.begin_session()
        self.complete_turn(status="failed", error={"message": "Provider unavailable"})
        with self.assertRaisesRegex(RuntimeError, "Provider unavailable"):
            self.backend.run_turn("prompt", self.hooks)

    def test_events_from_other_threads_or_turns_are_ignored(self):
        self.backend.open()
        self.backend.begin_session()
        self.rpc.events.put({"method": "turn/completed", "params": {
            "threadId": "workbench-thread",
            "turn": {"id": "turn-other", "status": "failed",
                     "error": {"message": "unrelated"}, "items": []}}})
        self.complete_turn()
        self.assertEqual(json.loads(self.backend.run_turn("prompt", self.hooks))["status"], "ok")

    def test_approval_maps_to_generic_view_and_replies_decision(self):
        self.backend.open()
        self.backend.begin_session()
        self.rpc.events.put({"id": 99, "method": "item/commandExecution/requestApproval",
            "params": {"threadId": "workbench-thread", "turnId": "turn-1",
                       "command": "python tools/mtg_tool.py search ...", "reason": "Network"}})
        self.complete_turn()
        self.backend.run_turn("prompt", self.hooks)
        view = self.hooks.approval_views[0]
        self.assertEqual(view["kind"], "item/commandExecution/requestApproval")
        self.assertEqual(view["reason"], "Network")
        self.assertEqual(view["detail"], "python tools/mtg_tool.py search ...")
        self.assertEqual(self.rpc.replies, [(99, {"decision": "accept"}, None)])

    def test_approval_abort_replies_cancel_before_raising(self):
        self.backend.open()
        self.backend.begin_session()
        self.hooks.fail_approval = True
        self.rpc.events.put({"id": 100, "method": "item/fileChange/requestApproval",
            "params": {"threadId": "workbench-thread", "turnId": "turn-1",
                       "changes": {"a.txt": {"type": "update"}}}})
        with self.assertRaisesRegex(RuntimeError, "断开"):
            self.backend.run_turn("prompt", self.hooks)
        self.assertEqual(self.rpc.replies, [(100, {"decision": "cancel"}, None)])

    def test_unknown_server_request_is_refused_and_fails_turn(self):
        self.backend.open()
        self.backend.begin_session()
        self.rpc.events.put({"id": 101, "method": "item/tool/requestUserInput",
            "params": {"threadId": "workbench-thread", "turnId": "turn-1"}})
        with self.assertRaisesRegex(RuntimeError, "不支持"):
            self.backend.run_turn("prompt", self.hooks)
        self.assertEqual(self.rpc.replies[0][2]["code"], -32601)

    def test_interrupt_targets_current_turn(self):
        self.backend.open()
        self.backend.begin_session()
        self.complete_turn()
        self.backend.run_turn("prompt", self.hooks)
        self.backend.interrupt()
        self.assertEqual(self.rpc.calls[-1],
                         ("turn/interrupt", {"threadId": "workbench-thread", "turnId": "turn-1"}))

    def test_no_codex_cli_does_not_mark_connected(self):
        with mock.patch.object(codex.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Codex CLI"):
                codex.codex_command()


class RpcTests(unittest.TestCase):
    def test_stdio_response_routing_notifications_error_and_eof(self):
        fixture = Path(__file__).parent / "testdata" / "codex_app_server_fake.py"
        with mock.patch.object(codex, "codex_command", return_value=[sys.executable, "-u", str(fixture)]):
            client = codex.RpcClient()
        try:
            self.assertEqual(client.request("initialize")["method"], "initialize")
            self.assertTrue(client.request("probe/event")["ok"])
            self.assertEqual(client.event()["method"], "item/started")
            with self.assertRaisesRegex(RuntimeError, "fixture failure"):
                client.request("probe/error")
            with self.assertRaisesRegex(RuntimeError, "断开"):
                client.request("probe/exit")
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
