#!/usr/bin/env python3
"""runlog.py（轮转 + run_logged 包装）与 CLI 接入点的回归测试。

真实磁盘只碰临时目录；接入点用 mock 断言 log_run 调用，
既有 test_mcp_server.py 中的自证行测试保持独立。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck_pooper  # noqa: E402
import deck_version  # noqa: E402
import runlog  # noqa: E402


class TestRotation(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = os.path.join(self._tmp.name, "run_log.jsonl")

    def _fill(self, nbytes):
        with open(self.path, "w", encoding="utf-8") as fh:
            chunk = "x" * 1023 + "\n"
            while fh.tell() < nbytes:
                fh.write(chunk)

    def _rotated(self, name="run_log.1.jsonl"):
        return os.path.join(self._tmp.name, name)

    def test_rotate_over_5mb_keeps_one_generation(self):
        self._fill(runlog.MAX_BYTES + 1)
        runlog.log_run("t", "ok", "s1", path=self.path)
        # 旧内容整体进了 .1
        self.assertGreater(os.path.getsize(self._rotated()), runlog.MAX_BYTES)
        # 新文件只有新行
        lines = Path(self.path).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["summary"], "s1")
        # 再次超限：.1 被覆盖，只留一代（无 .2）
        self._fill(runlog.MAX_BYTES + 1)
        runlog.log_run("t", "ok", "s2", path=self.path)
        self.assertTrue(os.path.exists(self._rotated()))
        self.assertFalse(os.path.exists(self._rotated("run_log.2.jsonl")))
        rec = json.loads(Path(self.path).read_text(encoding="utf-8").strip())
        self.assertEqual(rec["summary"], "s2")

    def test_no_rotation_under_limit(self):
        runlog.log_run("t", "ok", "a", path=self.path)
        runlog.log_run("t", "ok", "b", path=self.path)
        self.assertFalse(os.path.exists(self._rotated()))
        self.assertEqual(
            len(Path(self.path).read_text(encoding="utf-8").splitlines()), 2)


class TestRunLoggedWrapper(unittest.TestCase):

    def test_systemexit_nonzero_logged_and_reraised(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "run_log.jsonl")
            with mock.patch.object(runlog, "LOG_PATH", path):
                def fn():
                    raise SystemExit(2)
                with self.assertRaises(SystemExit):
                    runlog.run_logged("demo.py", fn)
            rec = json.loads(Path(path).read_text(encoding="utf-8").strip())
            self.assertEqual(rec["status"], "error")
            self.assertIn("SystemExit(2)", rec["summary"])

    def test_clean_systemexit_not_logged(self):
        def fn():
            raise SystemExit(0)
        with mock.patch.object(runlog, "log_run") as log:
            with self.assertRaises(SystemExit):
                runlog.run_logged("demo.py", fn)
        log.assert_not_called()

    def test_exception_logged_and_reraised(self):
        def fn():
            raise ValueError("boom")
        with mock.patch.object(runlog, "log_run") as log:
            with self.assertRaises(ValueError):
                runlog.run_logged("demo.py", fn)
        log.assert_called_once()
        self.assertEqual(log.call_args[0][1], "error")
        self.assertIn("ValueError", log.call_args[0][2])

    def test_normal_return_not_logged(self):
        with mock.patch.object(runlog, "log_run") as log:
            self.assertEqual(runlog.run_logged("demo.py", lambda: 0), 0)
        log.assert_not_called()


class TestCliIntegration(unittest.TestCase):

    def test_deck_version_ok_logs_version_and_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            deck_src = root / "src.txt"
            deck_src.write_text("60 Mountain\n", encoding="utf-8")
            with mock.patch.object(deck_version.runlog, "log_run") as log:
                rc = deck_version.main(
                    ["--root", str(root), "--deck-file", str(deck_src),
                     "--dir", "DeckList/Test_X_Y", "--theme", "T"])
        self.assertEqual(rc, 0)
        log.assert_called_once()
        tool, status, summary = log.call_args[0][:3]
        self.assertEqual((tool, status), ("deck_version.py", "ok"))
        self.assertIn("V1", summary)
        self.assertIn("TV1.txt", summary)

    def test_deck_version_gate_failure_logs_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            deck_src = root / "src.txt"
            deck_src.write_text("10 Mountain\n", encoding="utf-8")  # 主牌<60 → 门禁
            with mock.patch.object(deck_version.runlog, "log_run") as log:
                rc = deck_version.main(
                    ["--root", str(root), "--deck-file", str(deck_src),
                     "--dir", "DeckList/Test_X_Y", "--theme", "T"])
        self.assertEqual(rc, 2)
        self.assertEqual(log.call_args[0][1], "error")
        self.assertIn("exit=2", log.call_args[0][2])

    def test_deck_pooper_dispatch_logs_subcommand_and_out(self):
        with mock.patch.object(deck_pooper, "cmd_limited", return_value=0), \
                mock.patch.object(deck_pooper.runlog, "log_run") as log:
            rc = deck_pooper.main(["limited", "--pool", "p.txt", "--set", "HOB",
                                   "--out", "deck.txt"])
        self.assertEqual(rc, 0)
        log.assert_called_once()
        tool, status, summary = log.call_args[0][:3]
        self.assertEqual((tool, status), ("deck_pooper.py", "ok"))
        self.assertIn("limited", summary)
        self.assertIn("exit=0", summary)
        self.assertIn("deck.txt", summary)

    def test_deck_pooper_dispatch_nonzero_logs_error(self):
        with mock.patch.object(deck_pooper, "cmd_constructed", return_value=4), \
                mock.patch.object(deck_pooper.runlog, "log_run") as log:
            rc = deck_pooper.main(["constructed", "--format", "pioneer",
                                   "--seed", "s.txt", "--candidates", "c.json"])
        self.assertEqual(rc, 4)
        self.assertEqual(log.call_args[0][1], "error")
        self.assertIn("constructed", log.call_args[0][2])


if __name__ == "__main__":
    unittest.main()
