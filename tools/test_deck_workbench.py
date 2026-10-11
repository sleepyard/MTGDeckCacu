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
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck_model
import deck_workbench as workbench
import mtg_tool

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

    def post_obj(self, path, obj=None, raw=None):
        headers = {"Content-Type": "application/json; charset=utf-8"}
        status, body = self._request(
            "POST", path,
            body=raw.encode("utf-8") if raw is not None
            else json.dumps(obj or {}).encode("utf-8"),
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
            for path in ("/nope", "/index.html"):
                status, payload = fx.get_json(path)
                self.assertEqual(status, 404, path)
                self.assertEqual(payload["status"], "error")
                self.assertEqual(payload["error"]["type"], "NotFoundError")
                self.assertIn(path, payload["error"]["message"])

    def test_unknown_post_path_404(self):
        with ServerFixture() as fx:
            status, payload = fx.post_obj("/api/deck/frob", {"name": "X"})
            self.assertEqual(status, 404)
            self.assertEqual(payload["error"]["type"], "NotFoundError")

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
            # 最后一次成功写入获胜：终态必须等于最大序号那次导入的结果
            # （请求到达顺序由线程调度决定，不能硬编码某个 BoltN 最后到）
            winner = next(snap for _, snap in results
                          if snap["session"]["import_seq"] == len(decks))
            self.assertEqual(final["sections"], winner["sections"])
            self.assertEqual(len(final["sections"]["main"]), 1)
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


# ---------------------------------------------------------------- Phase 1 fixtures

def pool_card(name, colors, cmc, grade="B", count=1, cost=None, **extra):
    data = {"name": name, "colors": list(colors), "cmc": cmc,
            "cost": cost or ("{" + str(cmc) + "}" if cmc else ""),
            "type_line": "Creature", "grade": grade, "count": count,
            "rarity": "common"}
    data.update(extra)
    return data


POOL_CARDS = [
    pool_card("W Knight", "W", 2, count=9, cost="{1}{W}"),
    pool_card("U Drake", "U", 2, count=9, cost="{1}{U}"),
    pool_card("B Zombie", "B", 2, count=8, cost="{1}{B}"),
    pool_card("Filler Golem", [], 3, grade="C", count=8, cost="{3}"),
]

POOL_TEXT = "".join("{} {}\n".format(card["count"], card["name"])
                    for card in POOL_CARDS)


class FakeTable:
    """对齐 limited_strategy 的 table 协议：lookup(name) → entry/None。"""

    def __init__(self, cards):
        self.cards = {card["name"]: card for card in cards}

    def lookup(self, name):
        return self.cards.get(name)


class FakeResolver:
    """可注入的水合 resolver：已知牌名返回卡片 dict，未知抛 MtgToolError。"""

    def __init__(self, cards):
        self.by_name = {card["name"].lower(): card for card in cards}

    def __call__(self, name):
        card = self.by_name.get(name.lower())
        if card is None:
            raise mtg_tool.HttpError("查不到牌: " + name)
        return card


class PoolEngineTests(unittest.TestCase):
    """牌池解析/水合（Phase 1 引擎）。"""

    def test_parse_pool_entries_merges_sections_and_strips_suffix(self):
        text = ("Deck\n2 Lightning Bolt (CLB) 123\n\n"
                "Sideboard\n1 Giant Growth (ABC) 1\n")
        entries, skipped = workbench.parse_pool_entries(text)
        self.assertEqual(entries, [(2, "Lightning Bolt"), (1, "Giant Growth")])
        self.assertEqual(skipped, [])   # 空行误切已并入，不算坏行

    def test_parse_pool_entries_records_bad_lines(self):
        entries, skipped = workbench.parse_pool_entries("2 Island\n乱七八糟\n")
        self.assertEqual(entries, [(2, "Island")])
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["reason"], deck_model.REASON_BAD_LINE)

    def test_parse_pool_entries_empty_raises(self):
        for text in ("", "# 只有注释\n", "完全不是牌\n"):
            with self.assertRaises(workbench.EmptyImportError):
                workbench.parse_pool_entries(text)

    def test_hydrate_pool_resolves_and_aggregates_unresolved(self):
        entries, _ = workbench.parse_pool_entries(
            "2 W Knight\n1 U Drake\n3 No Such Card\n2 no such card\n")
        cards, unresolved = workbench.hydrate_pool(entries, FakeResolver(POOL_CARDS))
        self.assertEqual([(c["count"], c["name"]) for c in cards],
                         [(2, "W Knight"), (1, "U Drake")])
        self.assertEqual(len(unresolved), 1)          # 同名聚合
        self.assertEqual(unresolved[0]["name"], "No Such Card")
        self.assertEqual(unresolved[0]["qty"], 5)     # 3 + 2 按数量累计

    def test_import_pool_snapshot_counts_and_warnings(self):
        state = workbench.WorkbenchState()
        snap = state.import_pool("2 W Knight\n1 Ghost Card\n坏行\n",
                                 source_name="pool.txt",
                                 fetch_card=FakeResolver(POOL_CARDS))
        self.assertEqual(snap["status"], "ok")
        self.assertEqual(snap["counts"]["names"], 1)
        self.assertEqual(snap["counts"]["cards"], 2)
        self.assertEqual(snap["counts"]["unresolved_names"], 1)
        self.assertEqual(snap["counts"]["unresolved_qty"], 1)
        self.assertEqual(snap["counts"]["skipped_lines"], 1)
        self.assertEqual(len(snap["warnings"]), 2)    # 坏行 + 查不到
        self.assertEqual(snap["source_name"], "pool.txt")

    def test_import_pool_all_unresolved_is_success_but_seed_rejected(self):
        state = workbench.WorkbenchState()
        snap = state.import_pool("3 Ghost One\n2 Ghost Two\n",
                                 fetch_card=FakeResolver([]))
        self.assertEqual(snap["status"], "ok")
        self.assertEqual(snap["counts"]["unresolved_names"], 2)
        self.assertEqual(snap["counts"]["unresolved_qty"], 5)
        with self.assertRaises(workbench.PoolEmptyError):
            state.seed_limited(table=FakeTable([]))

    def test_import_pool_updates_card_db_for_stats(self):
        state = workbench.WorkbenchState()
        state.import_pool("1 W Knight\n", fetch_card=FakeResolver(POOL_CARDS))
        snap = state.deck_add("W Knight", "main", 2)
        stats = snap["stats"]
        self.assertEqual(stats["curve"], {"2": 2})
        self.assertEqual(stats["pips"], {"W": 2.0})
        self.assertEqual(stats["unknown"], [])


class SeedTests(unittest.TestCase):
    """seed_limited：自动/强制色组、deck_size、评分表降级。"""

    def _state_with_pool(self):
        state = workbench.WorkbenchState()
        state.import_pool(POOL_TEXT, fetch_card=FakeResolver(POOL_CARDS))
        return state

    def test_seed_auto_picks_best_dual(self):
        state = self._state_with_pool()
        snap = state.seed_limited(table=FakeTable(POOL_CARDS))
        seed = snap["seed"]
        self.assertEqual(set(seed["colors"]), {"W", "U"})
        self.assertEqual(seed["deck_size"], 41)
        self.assertEqual(snap["counts"]["main"], 41)
        self.assertTrue(seed["valid"])
        self.assertTrue(seed["depth_ok"])
        self.assertLessEqual(len(seed["plans"]), 5)
        for plan in seed["plans"]:
            self.assertIn("colors", plan)
            self.assertIn("score", plan)
        self.assertTrue(seed["cuts"])             # 28 张候选裁掉一部分
        self.assertEqual(snap["session"]["source_name"], "seed")

    def test_seed_forced_colors(self):
        state = self._state_with_pool()
        snap = state.seed_limited(colors=["W", "B"], table=FakeTable(POOL_CARDS))
        self.assertEqual(snap["seed"]["colors"], ["W", "B"])
        self.assertEqual(snap["counts"]["main"], 41)

    def test_seed_deck_size_40(self):
        state = self._state_with_pool()
        snap = state.seed_limited(table=FakeTable(POOL_CARDS), deck_size=40)
        self.assertEqual(snap["seed"]["deck_size"], 40)
        self.assertEqual(snap["counts"]["main"], 40)

    def test_seed_rejects_size_below_40(self):
        state = self._state_with_pool()
        with self.assertRaises(ValueError):
            state.seed_limited(table=FakeTable(POOL_CARDS), deck_size=39)

    def test_seed_without_pool_raises(self):
        with self.assertRaises(workbench.PoolEmptyError):
            workbench.WorkbenchState().seed_limited(table=FakeTable([]))

    def test_seed_missing_table_warning_is_explicit(self):
        state = self._state_with_pool()
        warning = "无评分表 tools/cache/draft_ratings/XXX.json，按结构降级"
        snap = state.seed_limited(table=None, table_warnings=[warning])
        self.assertIn(warning, snap["seed"]["warnings"])
        # 降级路径仍出牌（table=None 是 limited_strategy 的合法路径）
        self.assertEqual(snap["counts"]["main"], 41)

    def test_seed_plans_sorted_by_depth_then_score(self):
        state = self._state_with_pool()
        snap = state.seed_limited(table=FakeTable(POOL_CARDS))
        plans = snap["seed"]["plans"]
        keys = [(plan["depth_ok"], plan["score"]) for plan in plans]
        self.assertEqual(keys, sorted(keys, reverse=True))


class StatsTests(unittest.TestCase):
    """build_stats：空牌表、未水合降级、seed 后反映新牌表。"""

    def test_stats_empty_deck_is_ok_not_error(self):
        stats = workbench.WorkbenchState().stats()
        self.assertEqual(stats["status"], "ok")
        self.assertEqual(stats["main"], 0)
        self.assertEqual(stats["lands"], 0)
        self.assertEqual(stats["curve"], {})
        self.assertFalse(stats["land_check"]["ok"])
        self.assertEqual(stats["warnings"], [])

    def test_stats_unknown_card_reported_not_silently_zero_cmc(self):
        state = workbench.WorkbenchState()
        state.import_text("1 Mysterious Card\n")
        stats = state.stats()
        self.assertEqual(stats["unknown"], ["Mysterious Card"])
        self.assertEqual(stats["curve"], {})
        self.assertEqual(stats["nonlands"], 1)   # 计数仍在，只是不计曲线
        self.assertTrue(stats["warnings"])

    def test_stats_basic_lands_without_hydration(self):
        state = workbench.WorkbenchState()
        state.import_text("9 Plains\n7 Swamp\n1 Doom Blade\n")
        stats = state.stats()
        self.assertEqual(stats["lands"], 16)
        self.assertEqual(stats["mana_sources"], {"B": 7, "W": 9})
        self.assertEqual(stats["unknown"], ["Doom Blade"])

    def test_stats_after_seed_reflects_new_deck(self):
        state = workbench.WorkbenchState()
        state.import_pool(POOL_TEXT, fetch_card=FakeResolver(POOL_CARDS))
        state.seed_limited(table=FakeTable(POOL_CARDS))
        stats = state.stats()
        self.assertEqual(stats["main"], 41)
        self.assertGreaterEqual(stats["lands"], 16)
        self.assertGreater(sum(stats["curve"].values()), 0)
        self.assertIn("p3", stats["land_check"])
        self.assertEqual(stats["unknown"], [])


class DeckEditTests(unittest.TestCase):
    """apply_add/remove/move：同名上限、豁免、守恒。"""

    def test_add_over_four_rejected(self):
        state = workbench.WorkbenchState()
        state.deck_add("Lightning Bolt", "main", 4)
        with self.assertRaises(workbench.DeckEditError) as ctx:
            state.deck_add("Lightning Bolt", "main", 1)
        self.assertIn("4", str(ctx.exception))

    def test_basic_land_exempt_from_copy_limit(self):
        state = workbench.WorkbenchState()
        snap = state.deck_add("Plains", "main", 30)
        self.assertEqual(snap["counts"]["main"], 30)
        snap = state.deck_add("Island", "sideboard", 12)
        self.assertEqual(snap["counts"]["sideboard"], 12)

    def test_any_number_card_exempt(self):
        state = workbench.WorkbenchState()
        snap = state.deck_add("Rat Colony", "main", 12)
        self.assertEqual(snap["counts"]["main"], 12)

    def test_remove_conservation_and_underflow(self):
        state = workbench.WorkbenchState()
        state.deck_add("Lightning Bolt", "main", 4)
        snap = state.deck_remove("Lightning Bolt", "main", 2)
        self.assertEqual(snap["counts"]["main"], 2)
        with self.assertRaises(workbench.DeckEditError):
            state.deck_remove("Lightning Bolt", "main", 3)

    def test_remove_absent_card_rejected(self):
        state = workbench.WorkbenchState()
        with self.assertRaises(workbench.DeckEditError):
            state.deck_remove("Lightning Bolt", "main", 1)

    def test_move_main_sideboard_conservation(self):
        state = workbench.WorkbenchState()
        state.deck_add("Lightning Bolt", "main", 4)
        snap = state.deck_move("Lightning Bolt", "main", "sideboard", 2)
        self.assertEqual(snap["counts"]["main"], 2)
        self.assertEqual(snap["counts"]["sideboard"], 2)
        snap = state.deck_move("Lightning Bolt", "sideboard", "main", 1)
        self.assertEqual(snap["counts"]["main"], 3)
        self.assertEqual(snap["counts"]["sideboard"], 1)

    def test_move_rejects_same_section_and_bad_sections(self):
        state = workbench.WorkbenchState()
        state.deck_add("Lightning Bolt", "main", 1)
        with self.assertRaises(workbench.DeckEditError):
            state.deck_move("Lightning Bolt", "main", "main", 1)
        with self.assertRaises(workbench.DeckEditError):
            state.deck_add("Lightning Bolt", "commander", 1)
        with self.assertRaises(workbench.DeckEditError):
            state.deck_add("Lightning Bolt", "main", 0)

    def test_edit_response_includes_recomputed_stats(self):
        state = workbench.WorkbenchState()
        snap = state.deck_add("Wastes", "main", 10)
        self.assertEqual(snap["stats"]["lands"], 10)
        self.assertEqual(snap["stats"]["main"], 10)

    def test_move_respects_copy_limit_in_destination(self):
        state = workbench.WorkbenchState()
        state.deck_add("Lightning Bolt", "main", 4)
        state.deck_add("Lightning Bolt", "sideboard", 4)
        with self.assertRaises(workbench.DeckEditError):
            state.deck_move("Lightning Bolt", "main", "sideboard", 1)


class Phase1HttpTests(unittest.TestCase):
    """Phase 1 端点的 HTTP 行为（resolver/table 全部注入，无外网）。"""

    def _fixture(self, resolver=None, table=None):
        fx = ServerFixture()
        self._patches = [
            mock.patch.object(workbench, "default_fetch_card",
                              side_effect=resolver or FakeResolver(POOL_CARDS)),
            mock.patch.object(workbench.mtga_draft_tool, "load_card_table",
                              return_value=table),
        ]
        for patcher in self._patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        return fx

    def test_pool_endpoint_full_cycle(self):
        with self._fixture() as fx:
            status, snap = fx.post_json("/api/pool", POOL_TEXT, source="web-pool")
            self.assertEqual(status, 200)
            self.assertEqual(snap["counts"]["cards"], 34)
            self.assertEqual(snap["counts"]["unresolved_names"], 0)
            status, snap2 = fx.get_json("/api/pool")
            self.assertEqual(status, 200)
            self.assertEqual(snap2["entries"], snap["entries"])

    def test_pool_endpoint_unresolved_counted(self):
        with self._fixture(resolver=FakeResolver(POOL_CARDS)) as fx:
            status, snap = fx.post_json("/api/pool",
                                        "2 W Knight\n3 Ghost Card\n坏行\n")
            self.assertEqual(status, 200)
            self.assertEqual(snap["counts"]["names"], 1)
            self.assertEqual(snap["counts"]["unresolved_qty"], 3)
            self.assertEqual(snap["counts"]["skipped_lines"], 1)
            self.assertEqual(len(snap["warnings"]), 2)

    def test_pool_empty_text_400(self):
        with self._fixture() as fx:
            status, payload = fx.post_json("/api/pool", "什么都不是\n")
            self.assertEqual(status, 400)
            self.assertEqual(payload["error"]["type"], "EmptyImportError")

    def test_seed_http_auto_and_stats_reflect_deck(self):
        with self._fixture(table=FakeTable(POOL_CARDS)) as fx:
            fx.post_json("/api/pool", POOL_TEXT)
            status, snap = fx.post_obj("/api/seed", {})
            self.assertEqual(status, 200)
            self.assertEqual(set(snap["seed"]["colors"]), {"W", "U"})
            self.assertEqual(snap["counts"]["main"], 41)
            status, stats = fx.get_json("/api/stats")
            self.assertEqual(status, 200)
            self.assertEqual(stats["main"], 41)
            self.assertGreaterEqual(stats["lands"], 16)
            self.assertIn("ok", stats["land_check"])

    def test_seed_http_missing_table_warning_explicit(self):
        with self._fixture(table=None) as fx:
            fx.post_json("/api/pool", POOL_TEXT)
            status, snap = fx.post_obj("/api/seed", {"set": "FRA"})
            self.assertEqual(status, 200)
            self.assertTrue(any("无评分表" in w for w in snap["seed"]["warnings"]),
                            snap["seed"]["warnings"])
            # 降级仍出牌
            self.assertEqual(snap["counts"]["main"], 41)

    def test_seed_http_no_set_warns_degraded(self):
        with self._fixture(table=None) as fx:
            fx.post_json("/api/pool", POOL_TEXT)
            status, snap = fx.post_obj("/api/seed", {})
            self.assertEqual(status, 200)
            self.assertTrue(any("未提供 set" in w for w in snap["seed"]["warnings"]))

    def test_seed_http_forced_colors_and_size_40(self):
        with self._fixture(table=FakeTable(POOL_CARDS)) as fx:
            fx.post_json("/api/pool", POOL_TEXT)
            status, snap = fx.post_obj(
                "/api/seed", {"colors": ["W", "B"], "deck_size": 40})
            self.assertEqual(status, 200)
            self.assertEqual(snap["seed"]["colors"], ["W", "B"])
            self.assertEqual(snap["counts"]["main"], 40)

    def test_seed_http_bad_request_envelope(self):
        with self._fixture(table=FakeTable(POOL_CARDS)) as fx:
            fx.post_json("/api/pool", POOL_TEXT)
            for body in ({"colors": ["W", "W"]}, {"colors": ["X"]},
                         {"colors": "WU"}, {"colors": ["W", "U", "B"]},
                         {"deck_size": 39}, {"deck_size": 42},
                         {"deck_size": "41"}):
                status, payload = fx.post_obj("/api/seed", body)
                self.assertEqual(status, 400, body)
                self.assertEqual(payload["error"]["type"], "BadRequest", body)

    def test_seed_http_without_pool_400(self):
        with self._fixture() as fx:
            status, payload = fx.post_obj("/api/seed", {})
            self.assertEqual(status, 400)
            self.assertEqual(payload["error"]["type"], "PoolEmptyError")

    def test_deck_add_http_limit_and_basic_exempt(self):
        with self._fixture() as fx:
            status, payload = fx.post_obj(
                "/api/deck/add", {"name": "Lightning Bolt", "section": "main",
                                  "qty": 5})
            self.assertEqual(status, 400)
            self.assertEqual(payload["error"]["type"], "DeckEditError")
            self.assertIn("4", payload["error"]["message"])
            status, snap = fx.post_obj(
                "/api/deck/add", {"name": "Plains", "section": "main", "qty": 30})
            self.assertEqual(status, 200)
            self.assertEqual(snap["counts"]["main"], 30)
            self.assertIn("stats", snap)

    def test_deck_remove_move_http_conservation(self):
        with self._fixture() as fx:
            fx.post_obj("/api/deck/add",
                        {"name": "Lightning Bolt", "section": "main", "qty": 4})
            status, snap = fx.post_obj(
                "/api/deck/move", {"name": "Lightning Bolt", "from": "main",
                                   "to": "sideboard", "qty": 2})
            self.assertEqual(status, 200)
            self.assertEqual(snap["counts"]["main"], 2)
            self.assertEqual(snap["counts"]["sideboard"], 2)
            status, payload = fx.post_obj(
                "/api/deck/move", {"name": "Lightning Bolt", "from": "main",
                                   "to": "sideboard", "qty": 9})
            self.assertEqual(status, 400)

    def test_deck_edit_bad_json_400(self):
        with self._fixture() as fx:
            status, payload = fx.post_obj("/api/deck/add", raw="{不是json")
            self.assertEqual(status, 400)
            self.assertEqual(payload["error"]["type"], "BadRequest")

    def test_snapshot_includes_pool_stats_seed(self):
        with self._fixture(table=FakeTable(POOL_CARDS)) as fx:
            snap = fx.get_json("/api/snapshot")[1]
            for key in ("pool", "stats", "seed"):
                self.assertIn(key, snap)
            self.assertIsNone(snap["seed"])
            fx.post_json("/api/pool", POOL_TEXT)
            fx.post_obj("/api/seed", {})
            snap = fx.get_json("/api/snapshot")[1]
            self.assertIsNotNone(snap["seed"])
            self.assertEqual(snap["stats"]["main"], 41)
            self.assertEqual(snap["pool"]["counts"]["cards"], 34)

    def test_root_page_markers(self):
        with ServerFixture() as fx:
            status, body = fx.get("/")
            self.assertEqual(status, 200)
            text = body.decode("utf-8")
            # 用户语言标题（不再是 Phase N 开发语言）
            self.assertIn("MTG 套牌工作台", text)
            self.assertNotIn("Phase 3", text)
            # 模式分流标签与 Agent 区新文案
            self.assertIn("限制赛", text)
            self.assertIn("构筑", text)
            self.assertIn("Agent 助手", text)
            self.assertIn("直连工具", text)
            self.assertIn("Agent 回写候选", text)
            # 结构化结果渲染器（纯函数式 JS，输入 JSON 返回 HTML）
            self.assertIn("renderAgentPayload", text)
            self.assertIn("renderValue", text)
            self.assertNotIn("<pre", text)   # 禁止整段倾倒原始 JSON
            for marker in ("/api/seed", "/api/pool", "/api/deck/move",
                           "/api/deck/add", "/api/seed-constructed",
                           "/api/roles", "/api/combos", "/api/cost",
                           "/api/audit"):
                self.assertIn(marker, text)


# ---------------------------------------------------------------- Phase 2 fixtures

def cand(name, oracle="", types="Creature — Goblin", colors="R", cmc=2,
         cost=None, power=2, keywords=()):
    """constructed_strategy 候选记录（mtg_tool search --out 同构的最小字段集）。"""
    if cost is None:
        cost = ("{" + str(cmc) + "}" if cmc else "")
    return {"name": name, "colors": list(colors),
            "color_identity": list(colors), "cmc": cmc, "mana_cost": cost,
            "type_line": types, "oracle_text": oracle,
            "keywords": list(keywords),
            "power": (str(power) if power is not None else None),
            "rarity": "common", "games": ["arena", "paper", "mtgo"],
            "legalities": {"pioneer": "legal", "standard": "legal"}}


CONSTRUCTED_CANDIDATES = [
    cand("Goblin One"), cand("Goblin Two"), cand("Goblin Three"),
    cand("Diviner One", oracle="Draw a card.", types="Creature — Human Wizard",
         cmc=3),
    cand("Diviner Two", oracle="Draw a card.", types="Creature — Human Wizard",
         cmc=3),
    cand("Dragon One", types="Creature — Dragon", cmc=5, power=4),
    cand("Dragon Two", types="Creature — Dragon", cmc=5, power=4),
    cand("Doomblade One", oracle="Destroy target creature.", types="Instant",
         cost="{1}{R}", power=None),
    cand("Doomblade Two", oracle="Destroy target creature.", types="Instant",
         cost="{1}{R}", power=None),
    cand("Doomblade Three", oracle="Destroy target creature.",
         types="Instant", cost="{1}{R}", power=None),
    cand("Life One", types="Creature — Angel", keywords=("lifelink",)),
    cand("Life Two", types="Creature — Angel", keywords=("lifelink",)),
    cand("Smash One", oracle="Destroy target artifact.", types="Instant",
         cmc=1, cost="{R}", power=None),
    cand("Red Hills", oracle="{T}: Add {R}.", types="Land", cmc=0, cost="",
         power=None),
    cand("Red Cliff", oracle="{T}: Add {R}.", types="Land", cmc=0, cost="",
         power=None),
]


def combo_item(cid, names=("Piece A", "Piece B")):
    return {"id": cid,
            "source_url": "https://commanderspellbook.com/combo/" + cid,
            "popularity": 100,
            "components": [{"name": name, "quantity": 1} for name in names],
            "results": ["infinite mana"], "description": "test combo",
            "legality": {"status": "legal"},
            "combined": {"missing_cards": [], "unverified_templates": []}}


def combo_result(**over):
    base = {key: [] for key in workbench.mtg_combo_tool.OUTPUT_BUCKETS}
    base.update({"variant_count": 0, "analyzed_variant_count": 0,
                 "unexamined_variant_count": 0, "stale": False,
                 "truncated": False, "warnings": []})
    base.update(over)
    return base


COST_STDOUT = """
==========================================================================
deck.txt
  造价签名  4m1r8u5c
  物质点预算  ✅ 低造价档 ｜ 0秘稀×24.59 + 1稀有×5.10 = 5.10 点（低档≤20.4 / 上限≤40.8）
==========================================================================
  稀有度     张数        点/张(物质)       点/张(可定向)      小计(可定向)
----------------------------------------------------------------------
【需要开多少包（四条线不可互换 ⇒ 取 max）】
   PP核心 (max[稀有, 秘稀])          =    1.0 包
   PP全量 (含普通/非普通)            =    5.0 包
   ★ 不可兑换惩罚系数 = 1.25×
  非基本地 5 张 ｜ 生物 20 张 ｜ 主牌合计 38 张
  ⚠ 未识别: Foo, Bar

"""

ROT_STDOUT = """# 轮替存活审计：deck.txt
# 轮替日 2027-02-02 ｜ 退出：WOE LCI MKM OTJ(+BIG) BLB DSK

== 主牌
  ✅存活    4 Lightning Bolt                       存活印刷=M11               轮替印刷=—
  ❌将退    3 Old Card                             存活印刷=—                 轮替印刷=ABC
== 备牌
  ✅存活    2 Rest in Peace                        存活印刷=ABC               轮替印刷=—

主牌：57/60 张轮替后存活（将退 3 张）
备牌：2/2 张轮替后存活（将退 0 张）
"""

ROT_STDOUT_ALL_PASS = """# 轮替存活审计：deck.txt
# 轮替日 2027-02-02 ｜ 退出：WOE LCI MKM OTJ(+BIG) BLB DSK

== 主牌
  ✅存活    4 Lightning Bolt                       存活印刷=M11               轮替印刷=—
== 备牌
  ✅存活    2 Rest in Peace                        存活印刷=ABC               轮替印刷=—

主牌：4/4 张轮替后存活（将退 0 张）
备牌：2/2 张轮替后存活（将退 0 张）
"""

VALIDATE_PASS = ("[info] 逐牌核对:\n\nPASS — 全部门禁通过\n")
VALIDATE_FAIL = ("  [违规] 主牌 40 张 < 60\n  [违规] 'X' 共 5 张 > 4（非基本地）\n"
                 "FAIL — 2 项违规\n")


def cp(returncode, stdout="", stderr=""):
    """伪造的 subprocess.CompletedProcess（字节流，对齐 _run_tool 捕获）。"""
    return mock.Mock(returncode=returncode,
                     stdout=stdout.encode("utf-8"),
                     stderr=stderr.encode("utf-8"))


class ToolDispatcher:
    """按调用顺序返回预置结果（或抛异常），并记录 argv 供断言。"""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        item = self.results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


ROLE_CARDS = [
    {"name": "Doom Blade", "type_line": "Instant",
     "oracle_text": "Destroy target creature.", "keywords": [], "cmc": 2,
     "power": None, "mana_cost": "{1}{B}", "colors": ["B"],
     "legalities": {"pioneer": "legal"}, "games": ["arena"]},
    {"name": "Diviner", "type_line": "Creature — Human Wizard",
     "oracle_text": "When Diviner enters the battlefield, you draw a card.",
     "keywords": [], "cmc": 3, "power": 2, "mana_cost": "{2}{U}",
     "colors": ["U"], "legalities": {"pioneer": "legal"},
     "games": ["arena"]},
    {"name": "Grizzly Bears", "type_line": "Creature — Bear",
     "oracle_text": "", "keywords": [], "cmc": 2, "power": 2,
     "mana_cost": "{1}{G}", "colors": ["G"],
     "legalities": {"pioneer": "legal"}, "games": ["arena"]},
]


class ConstructedSeedTests(unittest.TestCase):
    """seed-constructed：成功路径、输入错误 400、checks 槽位。"""

    def test_body_parse_defaults(self):
        candidates, names, fmt, bo3, strategy, platform = \
            workbench.parse_constructed_body(
                {"candidates": CONSTRUCTED_CANDIDATES, "seeds": ["Goblin One"]})
        self.assertEqual(names, ["Goblin One"])
        self.assertEqual(fmt, "pioneer")
        self.assertEqual(strategy, "mid")
        self.assertEqual(platform, "arena")
        self.assertFalse(bo3)

    def test_body_parse_rejects_empty_candidates(self):
        for bad in ({}, {"candidates": [], "seeds": ["X"]},
                    {"candidates": "x", "seeds": ["X"]}):
            with self.assertRaises(ValueError):
                workbench.parse_constructed_body(bad)

    def test_body_parse_rejects_empty_or_bad_seeds(self):
        for bad in ({"candidates": [{}], "seeds": []},
                    {"candidates": [{}], "seeds": "Goblin One"},
                    {"candidates": [{}], "seeds": ["  "]}):
            with self.assertRaises(ValueError):
                workbench.parse_constructed_body(bad)

    def test_http_seed_constructed_success(self):
        with ServerFixture() as fx:
            status, snap = fx.post_obj("/api/seed-constructed", {
                "candidates": CONSTRUCTED_CANDIDATES,
                "seeds": ["Goblin One"], "bo3": True})
            self.assertEqual(status, 200, snap.get("error"))
            built = snap["constructed"]
            self.assertTrue(built["valid"], built["violations"])
            self.assertEqual(built["main"], 60)
            self.assertLessEqual(built["sideboard"], 15)
            self.assertTrue(built["report"])
            self.assertEqual(snap["counts"]["main"], 60)
            self.assertEqual(snap["session"]["source_name"], "seed-constructed")
            main_names = {c["name"]: c["qty"]
                          for c in snap["sections"]["main"]}
            self.assertEqual(main_names.get("Goblin One"), 1)  # 种子按原数保留
            # checks.constructed 槽位已记录
            slot = fx.get_json("/api/snapshot")[1]["checks"]["constructed"]
            self.assertEqual(slot["status"], "ok")
            self.assertEqual(slot["result"]["main"], 60)

    def test_http_seed_constructed_empty_candidates_400(self):
        with ServerFixture() as fx:
            status, payload = fx.post_obj("/api/seed-constructed",
                                          {"candidates": [], "seeds": ["X"]})
            self.assertEqual(status, 400)
            self.assertEqual(payload["error"]["type"], "BadRequest")

    def test_http_seed_constructed_seed_not_in_candidates_400(self):
        with ServerFixture() as fx:
            status, payload = fx.post_obj("/api/seed-constructed", {
                "candidates": CONSTRUCTED_CANDIDATES,
                "seeds": ["Missing Card"]})
            self.assertEqual(status, 400)
            self.assertIn("不在候选池", payload["error"]["message"])

    def test_http_seed_constructed_bad_strategy_400(self):
        with ServerFixture() as fx:
            status, payload = fx.post_obj("/api/seed-constructed", {
                "candidates": CONSTRUCTED_CANDIDATES,
                "seeds": ["Goblin One"], "strategy": "turbo"})
            self.assertEqual(status, 400)
            self.assertIn("strategy", payload["error"]["message"])

    def test_http_seed_constructed_candidate_missing_name_400(self):
        with ServerFixture() as fx:
            status, payload = fx.post_obj("/api/seed-constructed", {
                "candidates": [{"cmc": 1}], "seeds": ["Goblin One"]})
            self.assertEqual(status, 400)
            self.assertIn("name", payload["error"]["message"])

    def test_snapshot_checks_slots_initially_none(self):
        snap = workbench.WorkbenchState().snapshot()
        for key in ("roles", "combos", "cost", "audit", "constructed"):
            self.assertIn(key, snap["checks"])
            self.assertIsNone(snap["checks"][key])


class RolesTests(unittest.TestCase):
    """roles 聚合：分布/主角色、unknown 明示、缺口对照 M 配额。"""

    DECK_TEXT = "4 Doom Blade\n4 Diviner\n4 Grizzly Bears\n"

    def _db(self):
        return {card["name"]: card for card in ROLE_CARDS}

    def test_build_roles_distribution_and_primary(self):
        deck = deck_model.parse_text(self.DECK_TEXT)
        result = workbench.build_roles(deck, self._db(), FakeResolver([]))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["distribution"]["removal"], 4)
        self.assertEqual(result["distribution"]["card_advantage"], 4)
        self.assertEqual(result["distribution"]["threat"], 4)   # Diviner etb
        self.assertEqual(result["distribution"]["aggro"], 4)
        self.assertEqual(result["unknown"], [])
        by_name = {c["name"]: c for c in result["cards"]}
        self.assertEqual(by_name["Doom Blade"]["primary"], "removal")
        self.assertEqual(by_name["Doom Blade"]["module"], "M5")
        self.assertEqual(by_name["Diviner"]["primary"], "card_advantage")
        self.assertEqual(by_name["Grizzly Bears"]["primary"], "aggro")

    def test_build_roles_unknown_explicit_with_reason_and_qty(self):
        deck = deck_model.parse_text("2 Ghost Card\n3 Doom Blade\n")
        result = workbench.build_roles(deck, {}, FakeResolver(ROLE_CARDS))
        self.assertEqual(len(result["unknown"]), 1)
        self.assertEqual(result["unknown"][0]["name"], "Ghost Card")
        self.assertEqual(result["unknown"][0]["qty"], 2)
        self.assertTrue(result["unknown"][0]["reason"])
        # 已知牌照常分类，未水合牌不计入分布
        self.assertEqual(result["distribution"]["removal"], 3)
        self.assertNotIn("Ghost Card",
                         [c["name"] for c in result["cards"]])

    def test_build_roles_gaps_vs_constructed_module_quotas(self):
        deck = deck_model.parse_text(self.DECK_TEXT)
        result = workbench.build_roles(deck, self._db(), FakeResolver([]))
        gaps = {g["module"]: g for g in result["gaps"]}
        # M1 有 4 张（Bears）目标 8 → 缺 4；M3/M8 完全没有
        self.assertEqual(gaps["M1"]["have"], 4)
        self.assertEqual(gaps["M1"]["want"],
                         workbench.CS.MODULE_QUOTAS["M1"][1])
        self.assertEqual(gaps["M1"]["deficit"], 4)
        self.assertIn("M3", gaps)
        self.assertIn("M8", gaps)
        self.assertIn("MODULE_QUOTAS", result["basis"])

    def test_roles_http_endpoint_and_slot(self):
        with ServerFixture() as fx:
            fx.post_json("/api/builds/import", self.DECK_TEXT)
            fetch = mock.patch.object(
                workbench, "default_fetch_card",
                side_effect=FakeResolver(ROLE_CARDS)).start()
            self.addCleanup(fetch.stop)
            status, result = fx.get_json("/api/roles")
            self.assertEqual(status, 200)
            self.assertEqual(result["distribution"]["removal"], 4)
            self.assertEqual(result["unknown"], [])
            self.assertTrue(result["checked_at"])
            slot = fx.get_json("/api/snapshot")[1]["checks"]["roles"]
            self.assertEqual(slot["status"], "ok")
            self.assertEqual(slot["result"]["main"], 12)

    def test_roles_http_uses_card_db_cache_without_fetch(self):
        with ServerFixture() as fx:
            fx.state.import_pool("1 Doom Blade\n", fetch_card=FakeResolver(ROLE_CARDS))
            fx.post_json("/api/builds/import", "1 Doom Blade\n")
            fetch = mock.patch.object(
                workbench, "default_fetch_card",
                side_effect=AssertionError("不应走到网络水合")).start()
            self.addCleanup(fetch.stop)
            status, result = fx.get_json("/api/roles")
            self.assertEqual(status, 200)
            self.assertEqual(result["unknown"], [])
            fetch.assert_not_called()


class CombosTests(unittest.TestCase):
    """combos：零命中 vs 查询失败分离、stale/truncated 透出、参数校验。"""

    def _fixture(self, result=None, error=None):
        fx = ServerFixture()
        fx.post_json("/api/builds/import", SAMPLE_TEXT)
        side = error if error is not None else \
            (lambda *a, **k: result if result is not None
             else combo_result())
        patcher = mock.patch.object(workbench.mtg_combo_tool, "search_deck",
                                    side_effect=side)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fx

    def test_combos_zero_hits_is_success_not_error(self):
        with self._fixture(result=combo_result()) as fx:
            status, payload = fx.get_json("/api/combos")
            self.assertEqual(status, 200)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(sum(payload["group_counts"].values()), 0)
            self.assertFalse(payload["stale"])
            slot = fx.get_json("/api/snapshot")[1]["checks"]["combos"]
            self.assertEqual(slot["status"], "ok")

    def test_combos_hit_buckets_and_counts(self):
        result = combo_result(main_available=[combo_item("c1")],
                              variant_count=1, analyzed_variant_count=1,
                              unexamined_variant_count=0)
        with self._fixture(result=result) as fx:
            status, payload = fx.get_json(
                "/api/combos?format=pioneer&platform=arena")
            self.assertEqual(status, 200)
            self.assertEqual(payload["group_counts"]["main_available"], 1)
            combo = payload["buckets"]["main_available"][0]
            self.assertEqual(combo["id"], "c1")
            self.assertIn("Piece A", combo["cards"])
            self.assertEqual(combo["produces"], ["infinite mana"])

    def test_combos_query_failure_distinct_from_zero_hits(self):
        with self._fixture(error=mtg_tool.HttpError("Spellbook 网络失败")) as fx:
            status, payload = fx.get_json("/api/combos")
            self.assertEqual(status, 500)
            self.assertEqual(payload["status"], "error")
            self.assertIn("网络失败", payload["error"]["message"])
            self.assertEqual(payload["source"], "commander-spellbook")
            slot = fx.get_json("/api/snapshot")[1]["checks"]["combos"]
            self.assertEqual(slot["status"], "error")
            self.assertIn("网络失败", slot["error"]["message"])

    def test_combos_stale_passthrough(self):
        with self._fixture(result=combo_result(
                stale=True,
                warnings=["Spellbook refresh failed; cached results: boom"])) as fx:
            status, payload = fx.get_json("/api/combos")
            self.assertEqual(status, 200)
            self.assertTrue(payload["stale"])
            self.assertTrue(any("cached" in w for w in payload["warnings"]))

    def test_combos_truncated_passthrough(self):
        with self._fixture(result=combo_result(
                variant_count=50, analyzed_variant_count=20,
                unexamined_variant_count=30, truncated=True)) as fx:
            status, payload = fx.get_json("/api/combos?limit=20")
            self.assertEqual(status, 200)
            self.assertTrue(payload["truncated"])
            self.assertEqual(payload["analyzed_variant_count"], 20)

    def test_combos_empty_deck_400(self):
        with ServerFixture() as fx:
            status, payload = fx.get_json("/api/combos")
            self.assertEqual(status, 400)
            self.assertEqual(payload["error"]["type"], "BadRequest")

    def test_combos_bad_params_400(self):
        with self._fixture() as fx:
            for path in ("/api/combos?format=nonsense",
                         "/api/combos?limit=0",
                         "/api/combos?limit=abc"):
                status, payload = fx.get_json(path)
                self.assertEqual(status, 400, path)
                self.assertEqual(payload["error"]["type"], "BadRequest")


class CostTests(unittest.TestCase):
    """cost：子进程口径、快照缺失/失败显式 error、绝不返回零造价。"""

    def _fixture(self, dispatcher):
        fx = ServerFixture()
        fx.post_json("/api/builds/import", SAMPLE_TEXT)
        patcher = mock.patch.object(workbench, "_run_tool",
                                    side_effect=dispatcher)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fx

    def test_parse_cost_output_unit(self):
        parsed = workbench.parse_cost_output(COST_STDOUT)
        self.assertEqual(parsed["signature"], "4m1r8u5c")
        self.assertTrue(parsed["budget"]["ok"])
        self.assertEqual(parsed["budget"]["tier"], "低造价档")
        self.assertEqual(parsed["packs"]["core"], 1.0)
        self.assertEqual(parsed["packs"]["all"], 5.0)
        self.assertEqual(parsed["packs"]["penalty"], 1.25)
        self.assertEqual(parsed["stats"],
                         {"nonbasic_lands": 5, "creatures": 20,
                          "main_total": 38})
        self.assertEqual(parsed["unrecognized"], ["Foo", "Bar"])

    def test_parse_cost_output_missing_lines_are_none(self):
        parsed = workbench.parse_cost_output("什么都没有")
        self.assertIsNone(parsed["signature"])
        self.assertIsNone(parsed["budget"])
        self.assertEqual(parsed["unrecognized"], [])

    def test_cost_http_success(self):
        dispatcher = ToolDispatcher([cp(0, COST_STDOUT)])
        with self._fixture(dispatcher) as fx:
            status, payload = fx.get_json("/api/cost")
            self.assertEqual(status, 200)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["signature"], "4m1r8u5c")
            self.assertTrue(payload["budget"]["ok"])
            # 子进程 argv = python -X utf8 deck_cost.py sig <tmpfile>
            argv = dispatcher.calls[0]
            self.assertEqual(argv[1], "-X")
            self.assertEqual(argv[2], "utf8")
            self.assertTrue(argv[3].endswith("deck_cost.py"))
            self.assertIn("sig", argv)
            slot = fx.get_json("/api/snapshot")[1]["checks"]["cost"]
            self.assertEqual(slot["status"], "ok")

    def test_cost_snapshot_missing_nonzero_exit_is_error_not_zero(self):
        dispatcher = ToolDispatcher([
            cp(1, "", "Traceback ... FileNotFoundError: rarity_map.json")])
        with self._fixture(dispatcher) as fx:
            status, payload = fx.get_json("/api/cost")
            self.assertEqual(status, 500)
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["error"]["type"], "CostToolError")
            self.assertNotIn("signature", payload)   # 绝无零造价回退
            slot = fx.get_json("/api/snapshot")[1]["checks"]["cost"]
            self.assertEqual(slot["status"], "error")

    def test_cost_subprocess_oserror_is_error(self):
        dispatcher = ToolDispatcher([OSError("python 起不来")])
        with self._fixture(dispatcher) as fx:
            status, payload = fx.get_json("/api/cost")
            self.assertEqual(status, 500)
            self.assertEqual(payload["status"], "error")
            self.assertIn("python 起不来", payload["error"]["message"])

    def test_cost_empty_deck_is_error(self):
        with ServerFixture() as fx:
            status, payload = fx.get_json("/api/cost")
            self.assertEqual(status, 500)
            self.assertEqual(payload["error"]["type"], "EmptyDeckError")


class AuditTests(unittest.TestCase):
    """audit：双门禁交通灯、unknown≠通过、limited/constructed 两口径。"""

    def _fixture(self, results):
        dispatcher = ToolDispatcher(results)
        fx = ServerFixture()
        fx.post_json("/api/builds/import", SAMPLE_TEXT)
        patcher = mock.patch.object(workbench, "_run_tool",
                                    side_effect=dispatcher)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fx, dispatcher

    def test_audit_both_pass(self):
        fx, dispatcher = self._fixture([cp(0, VALIDATE_PASS),
                                        cp(0, ROT_STDOUT_ALL_PASS)])
        with fx:
            status, payload = fx.post_obj(
                "/api/audit", {"format": "pioneer", "limited": False})
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["validate"]["status"], "pass")
            self.assertEqual(payload["validate"]["violations"], [])
            self.assertEqual(payload["rotation"]["status"], "pass")
            self.assertTrue(payload["rotation"]["ok"])
            self.assertEqual(payload["rotation"]["rotating_cards"], [])
            self.assertEqual(payload["rotation"]["main"],
                             {"survive": 4, "total": 4, "rotating": 0})
            self.assertIn("4/4", payload["rotation"]["detail"])
            self.assertTrue(payload["checked_at"])
            slot = fx.get_json("/api/snapshot")[1]["checks"]["audit"]
            self.assertEqual(slot["status"], "ok")

    def test_audit_rotation_lists_dying_cards(self):
        fx, _ = self._fixture([cp(0, VALIDATE_PASS), cp(0, ROT_STDOUT)])
        with fx:
            status, payload = fx.post_obj(
                "/api/audit", {"format": "pioneer", "limited": False})
            self.assertEqual(status, 200)
            # validate 过、轮替有将退 → 整体 fail（不是 unknown）
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["rotation"]["status"], "fail")
            rotating = payload["rotation"]["rotating_cards"]
            self.assertEqual(rotating[0]["name"], "Old Card")
            self.assertEqual(rotating[0]["qty"], 3)
            self.assertEqual(rotating[0]["section"], "主牌")
            self.assertEqual(payload["rotation"]["main"],
                             {"survive": 57, "total": 60, "rotating": 3})
            self.assertIn("57/60", payload["rotation"]["detail"])

    def test_audit_validate_fail_lists_violations(self):
        fx, _ = self._fixture([cp(4, VALIDATE_FAIL), cp(0, ROT_STDOUT)])
        with fx:
            status, payload = fx.post_obj(
                "/api/audit", {"format": "pioneer", "limited": False})
            self.assertEqual(status, 200)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["validate"]["status"], "fail")
            self.assertEqual(payload["validate"]["violations"],
                             ["主牌 40 张 < 60", "'X' 共 5 张 > 4（非基本地）"])

    def test_audit_validate_unknown_is_not_pass(self):
        # 退出码 2（牌表解析失败等）→ unknown；整体 ok=None 而不是 True
        fx, _ = self._fixture([cp(2, "", "[错误] 牌表解析失败: boom"),
                               cp(0, ROT_STDOUT_ALL_PASS)])
        with fx:
            status, payload = fx.post_obj(
                "/api/audit", {"format": "pioneer", "limited": False})
            self.assertEqual(status, 200)
            self.assertIsNone(payload["ok"])
            self.assertEqual(payload["validate"]["status"], "unknown")
            self.assertTrue(payload["validate"]["error"])

    def test_audit_rotation_subprocess_failure_is_unknown(self):
        fx, _ = self._fixture([cp(0, VALIDATE_PASS), cp(9, "", "boom")])
        with fx:
            status, payload = fx.post_obj(
                "/api/audit", {"format": "pioneer", "limited": False})
            self.assertEqual(status, 200)
            self.assertIsNone(payload["ok"])
            self.assertEqual(payload["rotation"]["status"], "unknown")
            self.assertTrue(payload["rotation"]["error"])

    def test_audit_rotation_network_fail_stderr_is_unknown(self):
        # rot_audit 网络失败仍 exit 0，但 stderr 带 '! FAIL' → 不可信，unknown
        fx, _ = self._fixture([cp(0, VALIDATE_PASS),
                               cp(0, "", "  ! FAIL https://api.scryfall.com/sets boom")])
        with fx:
            status, payload = fx.post_obj(
                "/api/audit", {"format": "pioneer", "limited": False})
            self.assertIsNone(payload["ok"])
            self.assertEqual(payload["rotation"]["status"], "unknown")

    def test_audit_limited_and_constructed_argv(self):
        fx, dispatcher = self._fixture(
            [cp(0, VALIDATE_PASS), cp(0, ROT_STDOUT),
             cp(0, VALIDATE_PASS), cp(0, ROT_STDOUT)])
        with fx:
            status, _ = fx.post_obj(
                "/api/audit", {"format": "pioneer", "limited": True})
            self.assertEqual(status, 200)
            status, _ = fx.post_obj(
                "/api/audit", {"format": "pioneer", "limited": False})
            self.assertEqual(status, 200)
            limited_argv, constructed_argv = dispatcher.calls[0], dispatcher.calls[2]
            self.assertIn("--limited", limited_argv)
            self.assertNotIn("--limited", constructed_argv)
            self.assertIn("validate", limited_argv)
            self.assertTrue(limited_argv[3].endswith("mtg_tool.py"))
            self.assertTrue(dispatcher.calls[1][3].endswith("rot_audit.py"))

    def test_clip_detail_truncates_with_marker(self):
        # 子进程 stderr 整段倾倒（含 URL 噪音）→ 单行收敛 + 截断标注
        long_text = "! FAIL https://api.scryfall.com/sets " + "x" * 600
        clipped = workbench._clip_detail(long_text, 500)
        self.assertTrue(clipped.endswith("…[截断]"))
        self.assertLessEqual(len(clipped), 500 + len("…[截断]"))
        self.assertEqual(workbench._clip_detail("短文本", 500), "短文本")
        fx, _ = self._fixture([cp(0, VALIDATE_PASS),
                               cp(9, "", long_text)])
        with fx:
            status, payload = fx.post_obj(
                "/api/audit", {"format": "pioneer", "limited": False})
            self.assertEqual(status, 200)
            error = payload["rotation"]["error"]
            self.assertIn("…[截断]", error)
            self.assertLessEqual(len(error), 500 + len("…[截断]") + 32)

    def test_audit_missing_format_or_limited_400(self):
        fx, _ = self._fixture([])
        with fx:
            for body in ({}, {"format": "pioneer"},
                         {"limited": False},
                         {"format": "", "limited": False},
                         {"format": "pioneer", "limited": "yes"}):
                status, payload = fx.post_obj("/api/audit", body)
                self.assertEqual(status, 400, body)
                self.assertEqual(payload["error"]["type"], "BadRequest")

    def test_audit_empty_deck_is_error(self):
        with ServerFixture() as fx:
            status, payload = fx.post_obj(
                "/api/audit", {"format": "pioneer", "limited": False})
            self.assertEqual(status, 500)
            self.assertEqual(payload["error"]["type"], "EmptyDeckError")


# ---------------------------------------------------------------- Phase 3 fixtures

class FakeClock:
    """可控单调时钟：测试驱动认领租约 / 结果 TTL 过期。"""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make_bridge(**kwargs):
    return workbench.AgentBridge(**kwargs)


class AgentBridgeUnitTests(unittest.TestCase):
    """AgentBridge 纯语义：认领 / 心跳 / 租约重派 / TTL（假时钟驱动）。"""

    def test_submit_returns_request_id_and_queued_at(self):
        bridge = make_bridge()
        out = bridge.submit("next_move", {"note": "x"}, timeout_sec=300)
        self.assertEqual(out["request_id"], "req-1")
        self.assertTrue(out["queued_at"])
        status = bridge.status()
        self.assertEqual(status["queue_depth"], 1)
        self.assertEqual(status["in_flight"], 0)

    def test_next_wait0_empty_queue_returns_wait(self):
        bridge = make_bridge()
        self.assertEqual(bridge.next_request("agent-a", wait=False),
                         {"status": "wait"})

    def test_next_claims_request_with_kind_and_payload(self):
        bridge = make_bridge()
        bridge.submit("explain", {"card": "Lightning Bolt"})
        out = bridge.next_request("agent-a", wait=False)
        self.assertEqual(out["status"], "ok")
        req = out["request"]
        self.assertEqual(req["kind"], "explain")
        self.assertEqual(req["payload"], {"card": "Lightning Bolt"})
        self.assertEqual(req["request_id"], "req-1")
        self.assertEqual(bridge.status()["in_flight"], 1)

    def test_single_claim_semantics(self):
        bridge = make_bridge()
        bridge.submit("next_move", {})
        first = bridge.next_request("agent-a", wait=False)
        self.assertEqual(first["status"], "ok")
        # 同一请求同一时间只派给一个 agent：第二个 agent 拿不到
        second = bridge.next_request("agent-b", wait=False)
        self.assertEqual(second, {"status": "wait"})

    def test_next_blocks_until_submit(self):
        bridge = make_bridge()

        def later_submit():
            time.sleep(0.2)
            bridge.submit("next_move", {})

        thread = threading.Thread(target=later_submit, daemon=True)
        thread.start()
        out = bridge.next_request("agent-a", wait=True, poll_max=5.0)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["request"]["kind"], "next_move")
        thread.join(timeout=5)

    def test_all_four_kinds_accepted(self):
        for kind in ("next_move", "explain", "novel_synergies", "handoff"):
            kind, payload, timeout = workbench.parse_agent_request_body(
                {"kind": kind, "payload": {}, "timeout_sec": 60})
            self.assertIn(kind, workbench.AGENT_KINDS)
            self.assertEqual(payload, {})
            self.assertEqual(timeout, 60.0)

    def test_unknown_kind_rejected(self):
        for body in ({"kind": "bogus"}, {"kind": None}, {}):
            with self.assertRaises(ValueError):
                workbench.parse_agent_request_body(body)

    def test_payload_must_be_object(self):
        with self.assertRaises(ValueError):
            workbench.parse_agent_request_body(
                {"kind": "explain", "payload": [1, 2]})

    def test_timeout_sec_must_be_positive_number(self):
        for bad in (0, -1, "300", True):
            with self.assertRaises(ValueError):
                workbench.parse_agent_request_body(
                    {"kind": "explain", "timeout_sec": bad})

    def test_complete_unknown_returns_missing(self):
        bridge = make_bridge()
        self.assertEqual(bridge.complete("req-999", "ok", {}, ""), "missing")
        self.assertEqual(bridge.get_result("req-999"), ("missing", None))

    def test_result_roundtrip_ok(self):
        bridge = make_bridge()
        rid = bridge.submit("next_move", {})["request_id"]
        bridge.next_request("agent-a", wait=False)
        self.assertEqual(bridge.complete(rid, "ok", {"advice": "cut a land"},
                                         "done"), "ok")
        outcome, view = bridge.get_result(rid)
        self.assertEqual(outcome, "ok")
        self.assertEqual(view["status"], "ok")
        self.assertEqual(view["result"], {"advice": "cut a land"})
        self.assertEqual(view["message"], "done")
        self.assertEqual(view["agent"], "agent-a")
        self.assertEqual(view["claimed_by"], "agent-a")
        self.assertTrue(view["completed_at"])

    def test_result_pending_view_carries_claimed_by(self):
        bridge = make_bridge()
        rid = bridge.submit("explain", {})["request_id"]
        outcome, view = bridge.get_result(rid)
        self.assertEqual(outcome, "pending")
        self.assertIsNone(view["claimed_by"])
        bridge.next_request("agent-a", wait=False)
        outcome, view = bridge.get_result(rid)
        self.assertEqual(outcome, "pending")
        self.assertEqual(view["claimed_by"], "agent-a")

    def test_result_pending_before_complete(self):
        bridge = make_bridge()
        rid = bridge.submit("explain", {})["request_id"]
        outcome, _ = bridge.get_result(rid)
        self.assertEqual(outcome, "pending")
        bridge.next_request("agent-a", wait=False)
        outcome, _ = bridge.get_result(rid)
        self.assertEqual(outcome, "pending")

    def test_error_status_result_roundtrip(self):
        bridge = make_bridge()
        rid = bridge.submit("handoff", {})["request_id"]
        bridge.next_request("agent-a", wait=False)
        self.assertEqual(bridge.complete(rid, "error", {}, "no tool fit"), "ok")
        outcome, view = bridge.get_result(rid)
        self.assertEqual(outcome, "ok")
        self.assertEqual(view["status"], "error")
        self.assertEqual(view["message"], "no tool fit")

    def test_complete_requires_claim(self):
        bridge = make_bridge()
        rid = bridge.submit("next_move", {})["request_id"]
        self.assertEqual(bridge.complete(rid, "ok", {}, ""), "not_claimed")

    def test_double_complete_returns_done(self):
        bridge = make_bridge()
        rid = bridge.submit("next_move", {})["request_id"]
        bridge.next_request("agent-a", wait=False)
        self.assertEqual(bridge.complete(rid, "ok", {}, ""), "ok")
        self.assertEqual(bridge.complete(rid, "ok", {}, "again"), "done")

    def test_heartbeat_extends_lease(self):
        clock = FakeClock()
        bridge = make_bridge(clock=clock)
        rid = bridge.submit("next_move", {})["request_id"]
        bridge.next_request("agent-a", wait=False)
        clock.advance(50)                       # 未到 60s 租约
        self.assertEqual(bridge.heartbeat(rid, "agent-a"), "ok")
        clock.advance(50)                       # 共 100s，但心跳续租
        self.assertEqual(bridge.heartbeat(rid, "agent-a"), "ok")
        self.assertEqual(bridge.complete(rid, "ok", {}, ""), "ok")

    def test_heartbeat_wrong_agent_rejected(self):
        clock = FakeClock()
        bridge = make_bridge(clock=clock)
        rid = bridge.submit("next_move", {})["request_id"]
        bridge.next_request("agent-a", wait=False)
        self.assertEqual(bridge.heartbeat(rid, "agent-b"), "not_claimed")

    def test_lease_expiry_redispatches_without_heartbeat(self):
        clock = FakeClock()
        bridge = make_bridge(clock=clock)
        rid = bridge.submit("next_move", {})["request_id"]
        bridge.next_request("agent-a", wait=False)
        clock.advance(workbench.AGENT_CLAIM_LEASE + 1)
        # agent-a 崩溃挂死：租约过期后请求重新入队，agent-b 可认领
        out = bridge.next_request("agent-b", wait=False)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["request"]["request_id"], rid)
        self.assertEqual(bridge.status()["in_flight"], 1)
        self.assertEqual(bridge.status()["queue_depth"], 0)

    def test_result_ttl_expiry_get_gone(self):
        clock = FakeClock()
        bridge = make_bridge(clock=clock)
        rid = bridge.submit("next_move", {})["request_id"]
        bridge.next_request("agent-a", wait=False)
        bridge.complete(rid, "ok", {}, "")
        clock.advance(workbench.AGENT_RESULT_TTL + 1)
        outcome, _ = bridge.get_result(rid)
        self.assertEqual(outcome, "gone")

    def test_complete_after_ttl_returns_gone(self):
        clock = FakeClock()
        bridge = make_bridge(clock=clock)
        rid = bridge.submit("next_move", {})["request_id"]
        bridge.next_request("agent-a", wait=False)
        bridge.complete(rid, "ok", {}, "")
        clock.advance(workbench.AGENT_RESULT_TTL + 1)
        self.assertEqual(bridge.complete(rid, "ok", {}, "late"), "gone")

    def test_ttl_sweep_runs_on_submit_and_next(self):
        clock = FakeClock()
        bridge = make_bridge(clock=clock)
        rid = bridge.submit("next_move", {})["request_id"]
        bridge.next_request("agent-a", wait=False)
        bridge.complete(rid, "ok", {}, "")
        clock.advance(workbench.AGENT_RESULT_TTL + 1)
        bridge.submit("explain", {})          # submit 触发清扫
        self.assertEqual(bridge.status()["results_ready"], 0)
        self.assertEqual(bridge.complete(rid, "ok", {}, "late"), "gone")

    def test_status_diagnostics(self):
        bridge = make_bridge()
        for kind in workbench.AGENT_KINDS:
            bridge.submit(kind, {})
        bridge.next_request("agent-a", wait=False)
        status = bridge.status()
        self.assertEqual(status["queue_depth"], 3)
        self.assertEqual(status["in_flight"], 1)
        self.assertEqual(status["results_ready"], 0)
        self.assertEqual(status["tracked_requests"], 4)
        self.assertEqual(status["kinds"], list(workbench.AGENT_KINDS))

    def test_status_in_flight_requests_detail(self):
        # 旧字段 in_flight 保持计数兼容；新字段带 request_id + claimed_by 明细
        bridge = make_bridge()
        self.assertEqual(bridge.status()["in_flight_requests"], [])
        rid = bridge.submit("next_move", {})["request_id"]
        bridge.next_request("agent-a", wait=False)
        status = bridge.status()
        self.assertEqual(status["in_flight"], 1)
        self.assertEqual(status["in_flight_requests"],
                         [{"request_id": rid, "claimed_by": "agent-a"}])
        bridge.complete(rid, "ok", {}, "")
        self.assertEqual(bridge.status()["in_flight_requests"], [])


class AgentBridgeHttpTests(unittest.TestCase):
    """Agent 桥端点：request / next / result / heartbeat / status。"""

    def test_request_unknown_kind_400(self):
        with ServerFixture() as fx:
            for kind in ("bogus", None):
                status, payload = fx.post_obj(
                    "/api/agent/request", {"kind": kind, "payload": {}})
                self.assertEqual(status, 400, kind)
                self.assertEqual(payload["error"]["type"], "BadRequest")

    def test_request_bad_payload_400(self):
        with ServerFixture() as fx:
            status, payload = fx.post_obj(
                "/api/agent/request",
                {"kind": "explain", "payload": "not-a-dict"})
            self.assertEqual(status, 400)
            status, payload = fx.post_obj("/api/agent/request",
                                          raw='"just a string"')
            self.assertEqual(status, 400)

    def test_request_ok_then_agent_next_claims(self):
        with ServerFixture() as fx:
            status, out = fx.post_obj("/api/agent/request",
                                      {"kind": "next_move",
                                       "payload": {"note": "suggestion?"}})
            self.assertEqual(status, 200)
            rid = out["request_id"]
            self.assertTrue(out["queued_at"])
            status, claimed = fx.get_json("/api/agent/next?agent=kimi")
            self.assertEqual(status, 200)
            self.assertEqual(claimed["status"], "ok")
            self.assertEqual(claimed["request"]["request_id"], rid)
            self.assertEqual(claimed["request"]["payload"], {"note": "suggestion?"})

    def test_next_wait0_returns_wait_immediately(self):
        with ServerFixture() as fx:
            status, payload = fx.get_json("/api/agent/next?agent=kimi&wait=0")
            self.assertEqual(status, 200)
            self.assertEqual(payload, {"status": "wait"})

    def test_result_unknown_id_404(self):
        with ServerFixture() as fx:
            status, payload = fx.post_obj(
                "/api/agent/result",
                {"request_id": "req-999", "status": "ok", "result": {}})
            self.assertEqual(status, 404)
            self.assertEqual(payload["error"]["type"], "NotFoundError")

    def test_result_bad_body_400(self):
        with ServerFixture() as fx:
            for body in ({}, {"request_id": "req-1"},
                         {"request_id": "req-1", "status": "maybe"},
                         {"request_id": "", "status": "ok"},
                         {"request_id": "req-1", "status": "ok", "result": []}):
                status, payload = fx.post_obj("/api/agent/result", body)
                self.assertEqual(status, 400, body)
                self.assertEqual(payload["error"]["type"], "BadRequest")

    def test_result_before_claim_409(self):
        with ServerFixture() as fx:
            _, out = fx.post_obj("/api/agent/request",
                                 {"kind": "next_move", "payload": {}})
            status, payload = fx.post_obj(
                "/api/agent/result",
                {"request_id": out["request_id"], "status": "ok", "result": {}})
            self.assertEqual(status, 409)
            self.assertEqual(payload["error"]["type"], "ResultConflictError")

    def test_full_roundtrip_web_agent_web(self):
        with ServerFixture() as fx:
            _, out = fx.post_obj("/api/agent/request",
                                 {"kind": "novel_synergies",
                                  "payload": {"theme": "graveyard"}})
            rid = out["request_id"]
            status, pending = fx.get_json("/api/agent/result/{}".format(rid))
            self.assertEqual(status, 202)
            self.assertEqual(pending["status"], "pending")
            self.assertEqual(pending["request_id"], rid)
            self.assertIsNone(pending["claimed_by"])   # 未认领
            status, claimed = fx.get_json("/api/agent/next?agent=kimi&wait=0")
            self.assertEqual(claimed["status"], "ok")
            status, pending = fx.get_json("/api/agent/result/{}".format(rid))
            self.assertEqual(status, 202)
            self.assertEqual(pending["claimed_by"], "kimi")   # 认领人透出
            status, done = fx.post_obj(
                "/api/agent/result",
                {"request_id": rid, "status": "ok",
                 "result": {"synergies": ["A + B"]},
                 "message": "两个协同均经 /api/find 核验"})
            self.assertEqual(status, 200)
            status, view = fx.get_json("/api/agent/result/{}".format(rid))
            self.assertEqual(status, 200)
            self.assertEqual(view["status"], "ok")
            self.assertEqual(view["result"], {"synergies": ["A + B"]})
            self.assertEqual(view["agent"], "kimi")
            self.assertEqual(view["claimed_by"], "kimi")
            # 重复提交 → 409
            status, payload = fx.post_obj(
                "/api/agent/result",
                {"request_id": rid, "status": "ok", "result": {}})
            self.assertEqual(status, 409)

    def test_get_result_unknown_404(self):
        with ServerFixture() as fx:
            status, payload = fx.get_json("/api/agent/result/req-42")
            self.assertEqual(status, 404)
            self.assertEqual(payload["error"]["type"], "NotFoundError")

    def test_result_ttl_expired_410(self):
        state = workbench.WorkbenchState()
        clock = FakeClock()
        state.bridge = make_bridge(clock=clock)
        with ServerFixture(state) as fx:
            _, out = fx.post_obj("/api/agent/request",
                                 {"kind": "next_move", "payload": {}})
            rid = out["request_id"]
            fx.get_json("/api/agent/next?agent=kimi&wait=0")
            fx.post_obj("/api/agent/result",
                        {"request_id": rid, "status": "ok", "result": {}})
            clock.advance(workbench.AGENT_RESULT_TTL + 1)
            status, payload = fx.get_json("/api/agent/result/{}".format(rid))
            self.assertEqual(status, 410)
            self.assertEqual(payload["error"]["type"], "ResultExpiredError")
            status, payload = fx.post_obj(
                "/api/agent/result",
                {"request_id": rid, "status": "ok", "result": {}, "message": "late"})
            self.assertEqual(status, 410)

    def test_heartbeat_endpoint_ok_and_conflict(self):
        with ServerFixture() as fx:
            _, out = fx.post_obj("/api/agent/request",
                                 {"kind": "next_move", "payload": {}})
            rid = out["request_id"]
            status, payload = fx.post_obj("/api/agent/heartbeat",
                                          {"request_id": rid, "agent": "kimi"})
            self.assertEqual(status, 409)       # 未认领，不能心跳
            self.assertEqual(payload["error"]["type"], "HeartbeatConflictError")
            fx.get_json("/api/agent/next?agent=kimi&wait=0")
            status, payload = fx.post_obj("/api/agent/heartbeat",
                                          {"request_id": rid, "agent": "kimi"})
            self.assertEqual(status, 200)
            self.assertEqual(payload, {"status": "ok"})
            status, payload = fx.post_obj("/api/agent/heartbeat",
                                          {"request_id": rid, "agent": "other"})
            self.assertEqual(status, 409)
            status, payload = fx.post_obj("/api/agent/heartbeat",
                                          {"request_id": "req-999",
                                           "agent": "kimi"})
            self.assertEqual(status, 404)

    def test_agent_status_endpoint(self):
        with ServerFixture() as fx:
            _, out = fx.post_obj("/api/agent/request",
                                 {"kind": "explain", "payload": {}})
            status, payload = fx.get_json("/api/agent/status")
            self.assertEqual(status, 200)
            self.assertEqual(payload["queue_depth"], 1)
            self.assertEqual(payload["in_flight"], 0)
            self.assertEqual(payload["in_flight_requests"], [])
            self.assertEqual(payload["kinds"], list(workbench.AGENT_KINDS))

    def test_agent_status_in_flight_requests_http(self):
        with ServerFixture() as fx:
            _, out = fx.post_obj("/api/agent/request",
                                 {"kind": "next_move", "payload": {}})
            fx.get_json("/api/agent/next?agent=kimi&wait=0")
            status, payload = fx.get_json("/api/agent/status")
            self.assertEqual(status, 200)
            self.assertEqual(payload["in_flight"], 1)
            self.assertEqual(payload["in_flight_requests"],
                             [{"request_id": out["request_id"],
                               "claimed_by": "kimi"}])

    def test_snapshot_contains_bridges_and_avenues_slots(self):
        with ServerFixture() as fx:
            status, snap = fx.get_json("/api/snapshot")
            self.assertEqual(status, 200)
            self.assertIn("bridges", snap)
            self.assertEqual(snap["bridges"]["queue_depth"], 0)
            self.assertIn("avenues", snap)
            self.assertEqual(snap["avenues"], [])


class FindTests(unittest.TestCase):
    """GET /api/find：包装 mtg_tool.scryfall_search（mock，无网络）。"""

    RAW_CARDS = [{"name": "Bolt A", "cmc": 1, "oracle_id": "o1"},
                 {"name": "Bolt B", "cmc": 1, "oracle_id": "o2"},
                 {"name": "Bolt C", "cmc": 2, "oracle_id": "o3"}]

    def _patch_search(self, return_value=None, side_effect=None):
        return mock.patch.object(
            mtg_tool, "scryfall_search",
            return_value=return_value, side_effect=side_effect)

    def test_find_wraps_scryfall_search(self):
        with self._patch_search((list(self.RAW_CARDS), 3, ["warn-1"])):
            with ServerFixture() as fx:
                status, payload = fx.get_json("/api/find?q=f:pioneer&limit=20")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["total_cards"], 3)
        self.assertEqual(payload["returned"], 3)
        self.assertEqual(payload["warnings"], ["warn-1"])
        self.assertEqual([c["name"] for c in payload["cards"]],
                         ["Bolt A", "Bolt B", "Bolt C"])

    def test_find_limit_caps_results(self):
        with self._patch_search((list(self.RAW_CARDS), 3, [])):
            with ServerFixture() as fx:
                status, payload = fx.get_json("/api/find?q=f:pioneer&limit=2")
        self.assertEqual(status, 200)
        self.assertEqual(payload["returned"], 2)
        self.assertEqual(payload["total_cards"], 3)   # 总数如实，截断明示

    def test_find_syntax_error_400(self):
        with self._patch_search(side_effect=mtg_tool.QuerySyntaxError("bad q")):
            with ServerFixture() as fx:
                status, payload = fx.get_json("/api/find?q=(((")
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["type"], "QuerySyntaxError")

    def test_find_network_error_500(self):
        with self._patch_search(
                side_effect=mtg_tool.NetworkError("timeout")):
            with ServerFixture() as fx:
                status, payload = fx.get_json("/api/find?q=f:pioneer")
        self.assertEqual(status, 500)
        self.assertEqual(payload["status"], "error")
        self.assertIn("find 查询失败", payload["error"]["message"])

    def test_find_empty_hits_ok_empty_list(self):
        with self._patch_search(([], 0, [])):
            with ServerFixture() as fx:
                status, payload = fx.get_json(
                    "/api/find?q=f:pioneer%20o:definitelynotextant&limit=20")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["cards"], [])
        self.assertEqual(payload["returned"], 0)

    def test_find_missing_q_400(self):
        with ServerFixture() as fx:
            for path in ("/api/find", "/api/find?q=%20%20"):
                status, payload = fx.get_json(path)
                self.assertEqual(status, 400, path)
                self.assertEqual(payload["error"]["type"], "BadRequest")

    def test_find_bad_limit_400(self):
        with ServerFixture() as fx:
            for limit in ("0", "-1", "abc", "99999"):
                status, payload = fx.get_json("/api/find?q=x&limit=" + limit)
                self.assertEqual(status, 400, limit)
                self.assertEqual(payload["error"]["type"], "BadRequest")


class AvenueTests(unittest.TestCase):
    """avenues 反向通路：增 / 列 / 删 / focus / unverified 标记。"""

    BODY = {"title": "低费生物曲线", "note": "aggro 方向",
            "candidates": [{"name": "Bolt A", "reason": "1费 3/2"}]}

    def test_add_and_list_persisted(self):
        with ServerFixture() as fx:
            status, avenue = fx.post_obj("/api/avenues", self.BODY)
            self.assertEqual(status, 200)
            self.assertEqual(avenue["title"], "低费生物曲线")
            self.assertEqual(avenue["candidates"],
                             [{"name": "Bolt A", "reason": "1费 3/2"}])
            self.assertFalse(avenue["focused"])
            status, listed = fx.get_json("/api/avenues")
            self.assertEqual(status, 200)
            self.assertEqual(len(listed["avenues"]), 1)
            self.assertEqual(listed["avenues"][0]["id"], avenue["id"])

    def test_add_missing_title_400(self):
        with ServerFixture() as fx:
            for body in ({}, {"title": ""}, {"title": "  "},
                         {"title": None}, {"note": "只有备注"}):
                status, payload = fx.post_obj("/api/avenues", body)
                self.assertEqual(status, 400, body)
                self.assertEqual(payload["error"]["type"], "BadRequest")

    def test_add_candidate_name_must_be_nonempty_string(self):
        with ServerFixture() as fx:
            for candidates in ([{"name": ""}], [{"name": "  "}],
                               [{"name": None}], [{"reason": "没名字"}],
                               ["Bolt A"], [{"name": 42}]):
                body = dict(self.BODY, candidates=candidates)
                status, payload = fx.post_obj("/api/avenues", body)
                self.assertEqual(status, 400, candidates)
                self.assertEqual(payload["error"]["type"], "BadRequest")

    def test_add_note_and_reason_type_checked(self):
        with ServerFixture() as fx:
            status, _ = fx.post_obj("/api/avenues", dict(self.BODY, note=123))
            self.assertEqual(status, 400)
            status, _ = fx.post_obj(
                "/api/avenues",
                {"title": "t", "candidates": [{"name": "X", "reason": 1}]})
            self.assertEqual(status, 400)

    def test_unverified_card_names_marker(self):
        with ServerFixture() as fx:
            status, with_cards = fx.post_obj("/api/avenues", self.BODY)
            self.assertTrue(with_cards["unverified_card_names"])
            status, no_cards = fx.post_obj(
                "/api/avenues", {"title": "无候选", "candidates": []})
            self.assertFalse(no_cards["unverified_card_names"])
            status, snap = fx.get_json("/api/snapshot")
            markers = {a["title"]: a["unverified_card_names"]
                       for a in snap["avenues"]}
            self.assertEqual(markers,
                             {"低费生物曲线": True, "无候选": False})

    def test_delete_avenue_and_unknown_404(self):
        with ServerFixture() as fx:
            _, avenue = fx.post_obj("/api/avenues", self.BODY)
            status, _ = fx.get_json("/api/avenues")
            self.assertEqual(len(_["avenues"]), 1)
            status, payload = fx._request(
                "DELETE", "/api/avenues/" + avenue["id"])
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(payload.decode("utf-8"))["status"], "ok")
            status, listed = fx.get_json("/api/avenues")
            self.assertEqual(listed["avenues"], [])
            status, payload = fx._request("DELETE", "/api/avenues/av-999")
            self.assertEqual(status, 404)
            self.assertEqual(payload and json.loads(
                payload.decode("utf-8"))["error"]["type"], "NotFoundError")

    def test_focus_single_highlight(self):
        with ServerFixture() as fx:
            _, first = fx.post_obj("/api/avenues", {"title": "A"})
            _, second = fx.post_obj("/api/avenues", {"title": "B"})
            status, focused = fx.post_obj(
                "/api/avenues/{}/focus".format(first["id"]))
            self.assertEqual(status, 200)
            self.assertTrue(focused["focused"])
            status, snap = fx.get_json("/api/snapshot")
            states = {a["title"]: a["focused"] for a in snap["avenues"]}
            self.assertEqual(states, {"A": True, "B": False})
            # 单焦点语义：点亮 B 后 A 熄灭
            fx.post_obj("/api/avenues/{}/focus".format(second["id"]))
            status, snap = fx.get_json("/api/snapshot")
            states = {a["title"]: a["focused"] for a in snap["avenues"]}
            self.assertEqual(states, {"A": False, "B": True})
            status, payload = fx.post_obj("/api/avenues/av-999/focus")
            self.assertEqual(status, 404)

    def test_avenues_visible_in_snapshot(self):
        with ServerFixture() as fx:
            fx.post_obj("/api/avenues", self.BODY)
            status, snap = fx.get_json("/api/snapshot")
            self.assertEqual(status, 200)
            self.assertEqual(len(snap["avenues"]), 1)
            entry = snap["avenues"][0]
            self.assertEqual(entry["title"], "低费生物曲线")
            self.assertEqual(entry["candidates"][0]["name"], "Bolt A")

    def test_bad_json_body_400(self):
        with ServerFixture() as fx:
            status, payload = fx.post_obj("/api/avenues", raw='"not an object"')
            self.assertEqual(status, 400)


class AdviceTests(unittest.TestCase):
    """POST /api/advice：嵌入式 LLM 轴（全 mock，无网络）。"""

    CFG = {"base_url": "https://example.test", "model": "test-model",
           "api_key": "test-key"}

    def _patch_llm(self, chat_return="建议...", chat_side_effect=None):
        load = mock.patch.object(workbench.AUTO, "load_llm_config",
                                 return_value=dict(self.CFG))
        chat = mock.patch.object(workbench.AUTO, "llm_chat",
                                 return_value=chat_return,
                                 side_effect=chat_side_effect)
        return load, chat

    def test_config_missing_offline_with_machine_fallback(self):
        with mock.patch.object(workbench.AUTO, "load_llm_config",
                               side_effect=workbench.AUTO.AutoToolError(
                                   "LLM 配置不存在")):
            with ServerFixture() as fx:
                status, payload = fx.post_obj("/api/advice", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "offline")
        self.assertIsNone(payload["advice"])
        self.assertIn("LLM 配置不存在", payload["offline_reason"])
        self.assertTrue(payload["machine_fallback"])

    def test_env_key_override_success(self):
        # 真实 load_llm_config：配置文件无 api_key，DEEPSEEK_API_KEY 环境变量覆盖
        import mtga_auto_tool as auto_tool
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "llm_config.json"
            cfg_path.write_text(json.dumps(
                {"base_url": "https://example.test", "model": "env-model"}),
                encoding="utf-8")
            with mock.patch.object(workbench, "LLM_CONFIG_JSON", cfg_path), \
                    mock.patch.dict("os.environ",
                                    {"DEEPSEEK_API_KEY": "env-key"}), \
                    mock.patch.object(workbench.AUTO, "llm_chat",
                                      return_value="env 建议") as chat:
                with ServerFixture() as fx:
                    status, payload = fx.post_obj("/api/advice", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["advice"], "env 建议")
        self.assertEqual(payload["model"], "env-model")
        self.assertEqual(chat.call_count, 1)
        cfg_used = chat.call_args[0][0]
        self.assertEqual(cfg_used["api_key"], "env-key")

    def test_llm_success_advice_unverified(self):
        load, chat = self._patch_llm(chat_return="1. 加地；2. 剪曲线顶")
        with load, chat, ServerFixture() as fx:
            status, payload = fx.post_obj("/api/advice", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["advice"], "1. 加地；2. 剪曲线顶")
        self.assertFalse(payload["verified"])       # 明示未经工具核验
        self.assertEqual(payload["model"], "test-model")
        self.assertIsNone(payload["offline_reason"])
        self.assertTrue(payload["machine_fallback"])

    def test_llm_http_error_offline_with_fallback(self):
        load, chat = self._patch_llm(
            chat_side_effect=workbench.AUTO.AutoToolError("LLM HTTP 500"))
        with load, chat, ServerFixture() as fx:
            status, payload = fx.post_obj("/api/advice", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "offline")
        self.assertIn("LLM HTTP 500", payload["offline_reason"])
        self.assertIsNone(payload["advice"])
        fallback = payload["machine_fallback"]
        self.assertIn("land_check", fallback)
        self.assertIn("curve", fallback)

    def test_llm_timeout_offline(self):
        load, chat = self._patch_llm(chat_side_effect=OSError("timed out"))
        with load, chat, ServerFixture() as fx:
            status, payload = fx.post_obj("/api/advice", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "offline")
        self.assertIn("timed out", payload["offline_reason"])
        self.assertTrue(payload["machine_fallback"])

    def test_no_retry_on_failure(self):
        load, chat = self._patch_llm(
            chat_side_effect=workbench.AUTO.AutoToolError("boom"))
        with load, chat as chat_mock, ServerFixture() as fx:
            fx.post_obj("/api/advice", {})
        self.assertEqual(chat_mock.call_count, 1)   # 不重试

    def test_machine_fallback_contents(self):
        state = workbench.WorkbenchState()
        state.import_text(SAMPLE_TEXT)
        state._record_slot("roles", {
            "status": "ok", "checked_at": "t",
            "result": {"gaps": [{"module": "M1", "have": 0, "want": 8,
                                 "deficit": 8}]}})
        fallback = workbench.build_machine_fallback(state)
        self.assertEqual(fallback["main"], 12)
        self.assertEqual(fallback["lands"], 7)
        self.assertEqual(fallback["nonlands"], 5)
        self.assertEqual(fallback["role_gaps"],
                         [{"module": "M1", "have": 0, "want": 8,
                           "deficit": 8}])
        self.assertIn("land_check", fallback)

    def test_machine_fallback_role_gaps_none_without_slot(self):
        state = workbench.WorkbenchState()
        fallback = workbench.build_machine_fallback(state)
        self.assertIsNone(fallback["role_gaps"])
        self.assertEqual(fallback["main"], 0)

    def test_advice_prompt_uses_deck_and_cached_roles_only(self):
        state = workbench.WorkbenchState()
        state.import_text(SAMPLE_TEXT)
        state._record_slot("roles", {"status": "ok", "checked_at": "t",
                                     "result": {"gaps": []}})
        prompt = workbench.build_advice_prompt(state)
        self.assertIn("Lightning Bolt", prompt)
        self.assertIn("land_check", prompt)
        self.assertIn("角色缺口：无", prompt)
        empty_prompt = workbench.build_advice_prompt(
            workbench.WorkbenchState())
        self.assertIn("当前牌表为空", empty_prompt)
        self.assertNotIn("角色缺口", empty_prompt)   # 无缓存槽位就不编

    def test_page_renders_agent_section(self):
        with ServerFixture() as fx:
            status, body = fx.get("/")
            self.assertEqual(status, 200)
            text = body.decode("utf-8")
            self.assertIn("Agent 助手", text)
            self.assertIn("/api/agent/request", text)
            self.assertIn("/api/avenues", text)
            self.assertIn("/api/advice", text)
            self.assertIn("/api/find", text)


if __name__ == "__main__":
    unittest.main()
