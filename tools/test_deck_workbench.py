"""deck_workbench Phase 0 regression tests.

HTTP 全部走真实本地 socket（127.0.0.1 端口 0 的 ThreadingHTTPServer 线程），
不做任何外网请求；测试自包含、可重复运行。
"""
import contextlib
import http.client
import io
import json
import socket
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck_model
import deck_workbench as workbench

SAMPLE_TEXT = """Deck
4 Lightning Bolt
7 Mountain
1 B.F.M. (Big Furry Monster)

Sideboard
3 Deflecting Swat
"""

COMMANDER_TEXT = """Commander
1 Atraxa, Praetors' Voice

Deck
1 Arcane Signet
1 Forest
"""


class EngineTests(unittest.TestCase):
    """引擎纯函数与权威状态（WorkbenchState）。"""

    def test_snapshot_initial_state(self):
        state = workbench.WorkbenchState()
        snap = state.snapshot()
        self.assertEqual(snap["status"], "ok")
        for sec in ("commander", "companion", "main", "sideboard"):
            self.assertEqual(snap["sections"][sec], [])
            self.assertEqual(snap["counts"][sec], 0)
        self.assertEqual(snap["total"], 0)
        self.assertEqual(snap["skipped"], [])
        self.assertEqual(snap["warnings"], [])
        self.assertEqual(snap["session"], {"imported_at": None,
                                           "source_name": None, "import_seq": 0})

    def test_export_initial_state_is_empty(self):
        self.assertEqual(workbench.WorkbenchState().export_text(), "")

    def test_import_success_with_skipped_warnings(self):
        state = workbench.WorkbenchState()
        text = "4 Lightning Bolt\n这不是牌行\n3 Mountain\n"
        snap = state.import_text(text, source_name="pasted.txt")
        self.assertEqual(snap["status"], "ok")
        self.assertEqual(snap["sections"]["main"],
                         [{"qty": 4, "name": "Lightning Bolt"},
                          {"qty": 3, "name": "Mountain"}])
        self.assertEqual(snap["counts"]["main"], 7)
        self.assertEqual(snap["total"], 7)
        self.assertEqual(len(snap["skipped"]), 1)
        self.assertEqual(snap["skipped"][0]["reason"], deck_model.REASON_BAD_LINE)
        self.assertEqual(len(snap["warnings"]), 1)
        self.assertEqual(snap["session"]["source_name"], "pasted.txt")
        self.assertEqual(snap["session"]["import_seq"], 1)
        self.assertTrue(snap["session"]["imported_at"])

    def test_import_replaces_previous_deck(self):
        state = workbench.WorkbenchState()
        state.import_text(SAMPLE_TEXT)
        snap = state.import_text(COMMANDER_TEXT)
        self.assertEqual(snap["session"]["import_seq"], 2)
        self.assertEqual(snap["sections"]["main"],
                         [{"qty": 1, "name": "Arcane Signet"},
                          {"qty": 1, "name": "Forest"}])
        self.assertEqual(snap["sections"]["sideboard"], [])

    def test_import_empty_text_raises(self):
        state = workbench.WorkbenchState()
        for text in ("", "   \n\n", "# 只有注释\n", "完全没有牌的一行\n"):
            with self.assertRaises(workbench.EmptyImportError):
                state.import_text(text)
        self.assertEqual(state.snapshot()["session"]["import_seq"], 0)

    def test_import_only_about_section_raises(self):
        state = workbench.WorkbenchState()
        with self.assertRaises(workbench.EmptyImportError):
            state.import_text("About\n随便写点东西\n")


class RoundTripTests(unittest.TestCase):
    """往返一致性：text → import → export → parse 条目恒等。"""

    CASES = [
        SAMPLE_TEXT,
        COMMANDER_TEXT,
        "1 Island\n\n1 Swamp\n",                       # 无段头，空行切备牌
        "Commander\n1 Kenrith, the Returned King\n"
        "Companion\n1 Jegantha, the Wellspring\n"
        "Deck\n60 Plains\nSideboard\n15 Forest\n",
    ]

    def test_engine_round_trip(self):
        for text in self.CASES:
            deck = deck_model.parse_text(text)
            exported = workbench.serialize_deck(deck)
            self.assertEqual(deck_model.parse_text(exported).entries(), deck.entries())

    def test_skipped_lines_not_part_of_export(self):
        deck = deck_model.parse_text("4 Island\n这不是牌行\n")
        self.assertEqual(len(deck.skipped), 1)
        self.assertEqual(deck_model.parse_text(
            workbench.serialize_deck(deck)).skipped, ())

    def test_export_headers_match_parser(self):
        deck = deck_model.parse_text(SAMPLE_TEXT)
        exported = workbench.serialize_deck(deck)
        self.assertIn("Deck\n", exported)
        self.assertIn("Sideboard\n", exported)
        self.assertNotIn("Commander\n", exported)   # 空分区不输出段头

    def test_mdfc_and_parenthesized_names_survive(self):
        text = "Deck\n1 B.F.M. (Big Furry Monster)\n1 A-Lier, Disciple of the Drowned\n"
        deck = deck_model.parse_text(text)
        reimported = deck_model.parse_text(workbench.serialize_deck(deck))
        self.assertEqual(reimported.entries(), deck.entries())

    def test_http_round_trip(self):
        with ServerFixture() as fx:
            status, snap = fx.post_json("/api/builds/import", SAMPLE_TEXT)
            self.assertEqual(status, 200)
            status, exported = fx.get("/api/export")
            self.assertEqual(status, 200)
            self.assertEqual(exported.decode("utf-8"),
                             workbench.serialize_deck(deck_model.parse_text(SAMPLE_TEXT)))
            status, snap2 = fx.post_json("/api/builds/import", exported.decode("utf-8"))
            self.assertEqual(status, 200)
            for sec in ("commander", "companion", "main", "sideboard"):
                self.assertEqual(snap2["sections"][sec], snap["sections"][sec])
            self.assertEqual(snap2["skipped"], snap["skipped"])
            self.assertEqual(snap2["session"]["import_seq"], 2)


class ServerFixture:
    """127.0.0.1:0 的真实 ThreadingHTTPServer（守护线程）+ 请求助手。"""

    def __init__(self, state=None):
        self.state = state or workbench.WorkbenchState()
        self.server = workbench.ThreadingHTTPServer(
            ("127.0.0.1", 0), workbench.make_handler(self.state))
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        return False

    def _request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            resp = conn.getresponse()
            return resp.status, resp.read()
        finally:
            conn.close()

    def get(self, path):
        return self._request("GET", path)

    def get_json(self, path):
        status, body = self.get(path)
        return status, json.loads(body.decode("utf-8"))

    def post_json(self, path, text, source=None):
        headers = {"Content-Type": "text/plain; charset=utf-8"}
        if source:
            headers["X-Source-Name"] = source
        status, body = self._request("POST", path, body=text.encode("utf-8"),
                                     headers=headers)
        return status, json.loads(body.decode("utf-8"))


class HttpTests(unittest.TestCase):
    def test_root_page(self):
        with ServerFixture() as fx:
            status, body = fx.get("/")
            self.assertEqual(status, 200)
            text = body.decode("utf-8")
            self.assertIn("<html", text)
            self.assertIn("/api/snapshot", text)
            self.assertIn("MTG 套牌工作台", text)

    def test_snapshot_endpoint_initial(self):
        with ServerFixture() as fx:
            status, snap = fx.get_json("/api/snapshot")
            self.assertEqual(status, 200)
            self.assertEqual(snap["total"], 0)
            self.assertEqual(snap["session"]["import_seq"], 0)

    def test_unknown_path_404(self):
        with ServerFixture() as fx:
            for path in ("/nope", "/api/pool", "/index.html"):
                status, payload = fx.get_json(path)
                self.assertEqual(status, 404, path)
                self.assertEqual(payload["status"], "error")
                self.assertEqual(payload["error"]["type"], "NotFoundError")
                self.assertIn(path, payload["error"]["message"])

    def test_import_empty_text_http_400(self):
        with ServerFixture() as fx:
            for text in ("", "乱七八糟的一行\n"):
                status, payload = fx.post_json("/api/builds/import", text)
                self.assertEqual(status, 400, repr(text))
                self.assertEqual(payload["status"], "error")
                self.assertEqual(payload["error"]["type"], "EmptyImportError")
                self.assertTrue(payload["error"]["message"])

    def test_import_bad_body_http_400(self):
        with ServerFixture() as fx:
            status, body = fx._request(
                "POST", "/api/builds/import", body=b"\xff\xfe\x00",
                headers={"Content-Type": "text/plain; charset=utf-8"})
            self.assertEqual(status, 400)
            payload = json.loads(body.decode("utf-8"))
            self.assertEqual(payload["error"]["type"], "BadRequest")

    def test_import_success_response_matches_snapshot_shape(self):
        with ServerFixture() as fx:
            status, snap = fx.post_json("/api/builds/import", SAMPLE_TEXT,
                                        source="web.txt")
            self.assertEqual(status, 200)
            self.assertEqual(snap["session"]["source_name"], "web.txt")
            status, snap2 = fx.get_json("/api/snapshot")
            self.assertEqual(status, 200)
            self.assertEqual(snap2["sections"], snap["sections"])
            self.assertEqual(snap2["counts"], snap["counts"])
            self.assertEqual(snap2["total"], snap["total"])

    def test_export_endpoint(self):
        with ServerFixture() as fx:
            status, body = fx.get("/api/export")
            self.assertEqual(status, 200)
            self.assertEqual(body.decode("utf-8"), "")
            fx.post_json("/api/builds/import", SAMPLE_TEXT)
            status, body = fx.get("/api/export")
            self.assertEqual(status, 200)
            self.assertEqual(deck_model.parse_text(body.decode("utf-8")).entries(),
                             deck_model.parse_text(SAMPLE_TEXT).entries())

    def test_unhandled_exception_500_json_no_traceback(self):
        state = workbench.WorkbenchState()
        with mock.patch.object(workbench.WorkbenchState, "snapshot",
                               side_effect=RuntimeError("boom")):
            with ServerFixture(state) as fx:
                with contextlib.redirect_stderr(io.StringIO()):
                    status, payload = fx.get_json("/api/snapshot")
                self.assertEqual(status, 500)
                self.assertEqual(payload["status"], "error")
                self.assertEqual(payload["error"]["type"], "RuntimeError")
                self.assertNotIn("Traceback", json.dumps(payload))

    def test_concurrent_imports_serialized(self):
        with ServerFixture() as fx:
            decks = {"Deck\n4 Bolt{}\n".format(i): i for i in range(6)}
            results, errors = [], []
            lock = threading.Lock()

            def worker(text):
                try:
                    status, snap = fx.post_json("/api/builds/import", text)
                    with lock:
                        results.append((status, snap))
                except Exception as exc:  # 测试线程内收集，主线程断言
                    with lock:
                        errors.append(exc)

            threads = [threading.Thread(target=worker, args=(text,))
                       for text in decks]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)
            self.assertEqual(errors, [])
            self.assertEqual(len(results), len(decks))
            # 锁串行化：每次成功导入的序号恰好覆盖 1..N，无重复无跳号
            self.assertEqual(sorted(snap["session"]["import_seq"]
                                    for _, snap in results),
                             list(range(1, len(decks) + 1)))
            for status, snap in results:
                self.assertEqual(status, 200)
            final = fx.state.snapshot()
            self.assertEqual(final["session"]["import_seq"], len(decks))
            self.assertEqual(final["sections"]["main"],
                             [{"qty": 4, "name": "Bolt5"}])  # 最后一次成功写入获胜
            # 快照与状态严格一致（skipped/会话同源）
            self.assertEqual(final["skipped"], [])


class ServeCliTests(unittest.TestCase):
    def test_port_in_use_gives_clear_error(self):
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        try:
            busy_port = blocker.getsockname()[1]
            with self.assertRaises(workbench.WorkbenchError) as ctx:
                workbench.serve("127.0.0.1", busy_port)
            self.assertIn(str(busy_port), str(ctx.exception))
        finally:
            blocker.close()

    def test_main_returns_1_on_port_in_use(self):
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        try:
            busy_port = blocker.getsockname()[1]
            with mock.patch.object(workbench.runlog, "log_run"), \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                code = workbench.main(["serve", "--port", str(busy_port)])
            self.assertEqual(code, 1)
            self.assertIn("无法在", err.getvalue())
        finally:
            blocker.close()

    def test_parser_help(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                workbench.main(["--help"])
        self.assertEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
