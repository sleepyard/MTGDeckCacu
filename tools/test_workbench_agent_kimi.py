"""Kimi backend adapter regressions; the CLI is a stdio fixture, no real model."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import workbench_agent as agent
import workbench_agent_kimi as kimi

FIXTURE = Path(__file__).parent / "testdata" / "kimi_print_fake.py"


class FakeHooks:
    def __init__(self, raise_after=None):
        self.progress_messages = []
        self.keepalive_calls = 0
        self.raise_after = raise_after

    def keepalive(self):
        self.keepalive_calls += 1
        if self.raise_after is not None and self.keepalive_calls > self.raise_after:
            raise RuntimeError("接收端已断开")

    def progress(self, message):
        self.progress_messages.append(message)

    def approval(self, view):
        raise AssertionError("Kimi print mode never asks for approval")


class KimiBackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "spawn.jsonl"
        self.env = mock.patch.dict(os.environ,
                                   {"KIMI_FAKE_LOG": str(self.log)}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.backend = kimi.KimiBackend(command=[sys.executable, "-u", str(FIXTURE)])
        self.hooks = FakeHooks()

    def make(self, mode="ok"):
        os.environ["KIMI_FAKE_MODE"] = mode
        self.backend.open()
        self.backend.begin_session()

    def spawns(self):
        if not self.log.is_file():
            return []
        return [json.loads(line)
                for line in self.log.read_text(encoding="utf-8").splitlines()]

    def test_registered_in_default_registry(self):
        self.assertIn("kimi", agent.BACKENDS)
        self.assertTrue(any(b["name"] == "kimi" for b in agent.backend_options()))

    def test_no_kimi_cli_raises_install_hint(self):
        with mock.patch.object(kimi.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "未找到 Kimi Code CLI"):
                kimi.kimi_command()

    def test_open_rejects_cli_without_stream_json_input(self):
        os.environ["KIMI_FAKE_HELP"] = "limited"
        with self.assertRaisesRegex(RuntimeError, "不支持 --input-format"):
            self.backend.open()

    def test_happy_turn_returns_final_text_progress_and_stdin_prompt(self):
        self.make()
        text = self.backend.run_turn("任务提示词", self.hooks)
        self.assertEqual(json.loads(text)["message"], "完成")
        self.assertIn("正在调用工具：Shell", self.hooks.progress_messages)
        self.assertIn("正在整理答复", self.hooks.progress_messages)
        spawn = self.spawns()[0]
        self.assertIn("--input-format=stream-json", spawn["argv"])
        self.assertIn("--output-format=stream-json", spawn["argv"])
        self.assertNotIn("--session", spawn["argv"])
        stdin = json.loads(spawn["stdin"])
        self.assertEqual(stdin["role"], "user")
        self.assertIn("任务提示词", stdin["content"])

    def test_session_id_captured_from_meta_line(self):
        self.make(mode="meta")
        self.backend.run_turn("p", self.hooks)
        self.assertEqual(self.backend.session_id, "kimi-fake-session")

    def test_session_id_discovered_from_session_index(self):
        index = Path(self.tmp.name) / "session_index.jsonl"
        backend = kimi.KimiBackend(command=[sys.executable, "-u", str(FIXTURE)],
                                   session_index_path=index)
        backend.open()
        backend.begin_session()
        session_dir = Path(self.tmp.name) / "sessions" / "wd_x" / "new-kimi-session"
        session_dir.mkdir(parents=True)
        index.write_text(json.dumps({"sessionId": "new-kimi-session",
                                     "sessionDir": str(session_dir),
                                     "workDir": str(kimi.ROOT)}) + "\n", encoding="utf-8")
        backend.run_turn("p", self.hooks)
        self.assertEqual(backend.session_id, "new-kimi-session")

    def test_resume_passes_session_and_rejects_unknown_saved_id(self):
        index = Path(self.tmp.name) / "session_index.jsonl"
        index.write_text(json.dumps({"sessionId": "known", "sessionDir": "x",
                                     "workDir": str(kimi.ROOT)}) + "\n", encoding="utf-8")
        backend = kimi.KimiBackend(command=[sys.executable, "-u", str(FIXTURE)],
                                   session_index_path=index)
        backend.open()
        with self.assertRaisesRegex(RuntimeError, "已不存在"):
            backend.begin_session("gone")
        backend.begin_session("known")
        backend.run_turn("p", self.hooks)
        argv = self.spawns()[0]["argv"]
        self.assertEqual(argv[argv.index("--session") + 1], "known")

    def test_exit_75_is_retryable_and_exit_1_is_failure_with_stderr(self):
        self.make(mode="fail75")
        with self.assertRaisesRegex(RuntimeError, "可稍后重试.*rate limited"):
            self.backend.run_turn("p", self.hooks)
        self.make(mode="fail1")
        with self.assertRaisesRegex(RuntimeError, "exit 1.*authentication failed"):
            self.backend.run_turn("p", self.hooks)

    def test_empty_final_answer_is_error(self):
        self.make(mode="empty")
        with self.assertRaisesRegex(RuntimeError, "未给出最终答复"):
            self.backend.run_turn("p", self.hooks)

    def test_keepalive_abort_kills_process(self):
        os.environ["KIMI_FAKE_DELAY"] = "30"
        self.make(mode="slow")
        hooks = FakeHooks(raise_after=1)
        with self.assertRaisesRegex(RuntimeError, "断开"):
            self.backend.run_turn("p", hooks)
        self.assertIsNone(self.backend._process)  # cleared after kill
        self.assertEqual(hooks.progress_messages, [])

    def test_close_is_safe_when_idle(self):
        self.make()
        self.backend.close()
        self.backend.interrupt()


if __name__ == "__main__":
    unittest.main()
