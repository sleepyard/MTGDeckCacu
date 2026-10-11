"""Continuous receiver regressions; models/tools are mocked, no external APIs."""
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck_workbench as wb
import workbench_agent as agent
from test_deck_workbench import FakeClock, ServerFixture


def eventually(predicate, seconds=4):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        threading.Event().wait(.01)
    raise AssertionError("Condition did not arrive")


class FakeBackend:
    """In-process backend implementing the workbench_agent backend contract."""
    name = "fake"
    label = "Fake"

    def __init__(self):
        self.opened = 0
        self.sessions = []
        self.turns = []
        self.interrupted = 0
        self.closed = False
        self.hold = False
        self.release = threading.Event()
        self.fail_resume = False
        self.bad_answer = False
        self.fail_turn = False
        self.ask_approval = False
        self.approval_decision = None
        self.seq = 0
        self.last_turn_id = None
        self.session_id = None

    def open(self):
        self.opened += 1

    def begin_session(self, saved_id=None):
        self.sessions.append(saved_id)
        if saved_id and self.fail_resume:
            raise RuntimeError("Thread unavailable")
        self.session_id = saved_id or "workbench-thread"
        return {"thread_id": self.session_id, "model": "configured-model"}

    def alive(self):
        return not self.closed

    def run_turn(self, prompt, hooks):
        self.turns.append(prompt)
        self.seq += 1
        self.last_turn_id = "turn-{}".format(self.seq)
        if self.fail_turn:
            raise RuntimeError("Provider unavailable")
        if self.ask_approval:
            self.approval_decision = hooks.approval(
                {"kind": "test/action", "reason": "需要批准测试操作",
                 "detail": "python tools/mtg_tool.py search ..."})
        if self.hold:
            while not self.release.is_set():
                hooks.keepalive()
                self.release.wait(.02)
        if self.bad_answer:
            return "Invalid response"
        return json.dumps({"status": "ok", "message": "已读取工具结果",
                           "result": {"evidence": [self.last_turn_id]}})

    def finish(self):
        self.release.set()

    def interrupt(self):
        self.interrupted += 1

    def close(self):
        self.closed = True


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = wb.WorkbenchState()
        self.backend = FakeBackend()
        factory = lambda: self.backend
        factory.name, factory.label = FakeBackend.name, FakeBackend.label
        self.session_path = Path(self.tmp.name) / "session.json"
        self.receiver = agent.AgentReceiver(self.state, backend_factory=factory,
                                            session_path=self.session_path, heartbeat_interval=.02)
        self.state.receiver = self.receiver
        self.addCleanup(self.receiver.close)

    def connect(self):
        self.receiver.connect("http://127.0.0.1:8644")
        eventually(lambda: self.receiver.status()["status"] == "idle")

    def request(self):
        return self.state.bridge.submit("next_move", {"note": "Check current deck"}, timeout_sec=3)["request_id"]

    def result(self, rid):
        eventually(lambda: self.state.bridge.get_result(rid)[0] == "ok")
        return self.state.bridge.get_result(rid)[1]

    def save_session(self, thread_id="workbench-thread", backend="fake"):
        self.session_path.write_text(json.dumps(
            {"cwd": str(agent.ROOT), "backend": backend, "thread_id": thread_id}), encoding="utf-8")

    def test_one_connection_consumes_multiple_frontend_requests_on_same_thread(self):
        self.connect()
        first, second = self.request(), self.request()
        self.assertEqual(self.result(first)["agent"], self.receiver.agent_name)
        self.assertEqual(self.result(second)["status"], "ok")
        self.assertEqual(len(self.backend.sessions), 1)
        self.assertEqual(len(self.backend.turns), 2)
        self.assertEqual({self.backend.session_id}, {"workbench-thread"})
        self.assertEqual(self.state.bridge.status()["queue_depth"], 0)
        self.assertIn("/api/find", self.backend.turns[0])
        self.assertNotIn("claim_token", self.backend.turns[0])

    def test_offline_queue_starts_automatically_after_connect(self):
        rid = self.request()
        self.assertEqual(self.state.bridge.get_result(rid)[0], "pending")
        self.connect()
        self.assertEqual(self.result(rid)["status"], "ok")

    def test_idle_connect_has_no_model_turn_and_duplicate_connect_is_idempotent(self):
        self.connect()
        self.receiver.connect("http://127.0.0.1:8644")
        self.assertEqual(self.backend.turns, [])
        self.assertEqual(self.backend.opened, 1)

    def test_two_receivers_cannot_concurrently_resume_same_saved_thread(self):
        self.connect()
        other_backend = FakeBackend()
        factory = lambda: other_backend
        factory.name, factory.label = FakeBackend.name, FakeBackend.label
        other = agent.AgentReceiver(wb.WorkbenchState(), backend_factory=factory,
                                    session_path=self.session_path)
        self.addCleanup(other.close)
        other.connect("http://127.0.0.1:9000")
        eventually(lambda: other.status()["status"] == "error")
        self.assertIn("另一个接收端", other.status()["message"])
        self.assertEqual(other_backend.opened, 0)

    def test_reconnect_resumes_saved_thread_without_silent_new_thread(self):
        self.save_session()
        self.connect()
        self.assertEqual(self.backend.sessions, ["workbench-thread"])

    def test_saved_session_from_other_backend_starts_fresh(self):
        self.save_session(thread_id="codex-thread", backend="codex")
        self.connect()
        self.assertEqual(self.backend.sessions, [None])
        saved = json.loads(self.session_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["backend"], "fake")
        self.assertEqual(saved["thread_id"], "workbench-thread")

    def test_resume_failure_is_visible_and_leaves_queued_work_unclaimed(self):
        self.backend.fail_resume = True
        self.save_session(thread_id="missing")
        rid = self.request()
        self.receiver.connect("http://127.0.0.1:8644")
        eventually(lambda: self.receiver.status()["status"] == "error")
        self.assertIn("unavailable", self.receiver.status()["message"])
        self.assertIsNone(self.state.bridge.get_result(rid)[1]["claimed_by"])

    def test_corrupt_saved_session_never_silently_starts_another_thread(self):
        self.session_path.write_text("broken json", encoding="utf-8")
        self.receiver.connect("http://127.0.0.1:8644")
        eventually(lambda: self.receiver.status()["status"] == "error")
        self.assertEqual(self.backend.sessions, [])
        self.receiver.close()
        self.session_path.write_text(json.dumps(
            {"cwd": str(agent.ROOT), "backend": "fake", "thread_id": 42}), encoding="utf-8")
        self.receiver.connect("http://127.0.0.1:8644")
        eventually(lambda: self.receiver.status()["status"] == "error")
        self.assertIn("损坏", self.receiver.status()["message"])
        self.assertEqual(self.backend.sessions, [])

    def test_deck_change_while_working_marks_response_stale(self):
        self.backend.hold = True
        self.connect()
        self.state.import_text("41 Plains")
        rid = self.request()
        eventually(lambda: self.backend.seq == 1)
        self.state.import_text("40 Plains")
        self.backend.finish()
        result = self.result(rid)
        self.assertTrue(result["result"]["stale"])
        self.assertEqual(result["result"]["execution"]["thread_id"], "workbench-thread")
        self.assertEqual(result["result"]["execution"]["turn_id"], "turn-1")

    def test_heartbeats_continue_during_tool_work(self):
        self.backend.hold = True
        self.connect()
        with mock.patch.object(self.state.bridge, "heartbeat", wraps=self.state.bridge.heartbeat) as heartbeat:
            rid = self.request()
            eventually(lambda: self.receiver.status()["status"] == "busy")
            eventually(lambda: heartbeat.call_count >= 3)
            self.backend.finish()
            self.assertEqual(self.result(rid)["status"], "ok")

    def test_timeout_interrupts_turn_and_returns_error(self):
        self.backend.hold = True
        self.connect()
        rid = self.state.bridge.submit("next_move", {}, timeout_sec=1)["request_id"]
        result = self.result(rid)
        self.assertEqual(result["status"], "error")
        self.assertIn("超时", result["message"])
        self.assertGreaterEqual(self.backend.interrupted, 1)

    def test_disconnect_during_work_returns_explicit_failure(self):
        self.backend.hold = True
        self.connect()
        rid = self.request()
        eventually(lambda: self.receiver.status()["status"] == "busy")
        self.receiver.disconnect()
        self.assertEqual(self.result(rid)["status"], "error")
        eventually(lambda: self.receiver.status()["status"] == "offline")

    def test_bad_model_json_and_failed_turn_are_errors_not_success(self):
        self.connect()
        self.backend.bad_answer = True
        self.assertEqual(self.result(self.request())["status"], "error")
        self.backend.bad_answer = False
        self.backend.fail_turn = True
        result = self.result(self.request())
        self.assertEqual(result["status"], "error")
        self.assertIn("Provider unavailable", result["message"])

    def test_approval_is_never_accepted_automatically_and_lease_keeps_alive(self):
        self.backend.ask_approval = True
        self.backend.hold = True
        self.connect()
        rid = self.request()
        eventually(lambda: self.receiver.status()["status"] == "approval")
        self.assertIsNone(self.backend.approval_decision)
        with self.assertRaises(ValueError):
            self.receiver.answer_approval("wrong-id", "accept")
        approval = self.receiver.status()["approval"]
        self.assertEqual(approval["detail"], "python tools/mtg_tool.py search ...")
        self.receiver.answer_approval(approval["id"], "decline")
        eventually(lambda: self.backend.approval_decision is not None)
        self.assertEqual(self.backend.approval_decision, "decline")
        self.assertEqual(self.receiver.status()["status"], "busy")
        self.backend.finish()
        self.assertEqual(self.result(rid)["status"], "ok")

    def test_http_connect_frontend_submission_and_disconnect(self):
        with ServerFixture(self.state) as fx:
            connection = fx.get_json("/api/agent/connection")[1]
            self.assertEqual(connection["status"], "offline")
            self.assertEqual(connection["backend"], "fake")
            self.assertTrue(any(b["name"] == "codex" for b in connection["backends"]))
            self.assertEqual(fx.post_obj("/api/agent/connect", {})[0], 200)
            eventually(lambda: self.receiver.status()["status"] == "idle")
            rid = fx.post_obj("/api/agent/request", {"kind": "next_move"})[1]["request_id"]
            self.assertEqual(self.result(rid)["agent"], self.receiver.agent_name)
            snap = fx.get_json("/api/snapshot")[1]
            self.assertEqual(snap["bridges"]["receiver"]["thread_id"], "workbench-thread")
            self.assertEqual(fx.post_obj("/api/agent/disconnect", {})[0], 200)

    def test_connect_rejects_unknown_backend_without_touching_receiver(self):
        with ServerFixture(self.state) as fx:
            status, body = fx.post_obj("/api/agent/connect", {"backend": "nope"})
            self.assertEqual(status, 400)
            self.assertIn("未知 Agent 后端", body["error"]["message"])
            self.assertEqual(fx.get_json("/api/agent/connection")[1]["backend"], "fake")

    def test_cross_origin_page_cannot_connect_or_submit_agent_work(self):
        with ServerFixture(self.state) as fx:
            for path in ("/api/agent/connect", "/api/agent/approval", "/api/agent/request"):
                status, body = fx._request("POST", path, body=b'{}', headers={
                    "Content-Type": "text/plain", "Origin": "https://other.example"})
                self.assertEqual(status, 400)
                self.assertIn("本机工作台", json.loads(body)["error"]["message"])
        self.assertEqual(self.backend.opened, 0)

    def test_claim_token_prevents_old_receiver_receipt_after_lease_requeue(self):
        clock = FakeClock()
        bridge = wb.AgentBridge(clock=clock)
        rid = bridge.submit("next_move", {})["request_id"]
        old = bridge.next_request(self.receiver.agent_name, wait=False)["request"]
        clock.advance(61)
        new = bridge.next_request(self.receiver.agent_name, wait=False)["request"]
        self.assertNotEqual(old["claim_token"], new["claim_token"])
        agent_name = self.receiver.agent_name
        self.assertEqual(bridge.heartbeat(rid, agent_name, old["claim_token"]), "not_claimed")
        self.assertEqual(bridge.complete(rid, "ok", {}, "old", agent_name, old["claim_token"]), "not_claimed")
        self.assertEqual(bridge.complete(rid, "ok", {}, "new", agent_name, new["claim_token"]), "ok")


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_default_receiver_uses_codex_backend(self):
        receiver = agent.create_receiver(wb.WorkbenchState())
        self.addCleanup(receiver.close)
        self.assertEqual(receiver.backend_name, "codex")
        self.assertEqual(receiver.agent_name, "codex-workbench")
        self.assertEqual(receiver.status()["backend_label"], "Codex")

    def test_unknown_backend_name_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "未知 Agent 后端"):
            agent.create_receiver(wb.WorkbenchState(), backend="nope")

    def test_legacy_session_file_without_backend_key_defaults_to_codex(self):
        path = Path(self.tmp.name) / "session.json"
        path.write_text(json.dumps({"cwd": str(agent.ROOT), "thread_id": "legacy-thread"}),
                        encoding="utf-8")
        receiver = agent.create_receiver(wb.WorkbenchState(), session_path=path)
        self.addCleanup(receiver.close)
        self.assertEqual(receiver._saved_thread_id(), "legacy-thread")


if __name__ == "__main__":
    unittest.main()
