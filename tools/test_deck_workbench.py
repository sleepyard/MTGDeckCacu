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

    def test_root_page_phase1_markers(self):
        with ServerFixture() as fx:
            status, body = fx.get("/")
            self.assertEqual(status, 200)
            text = body.decode("utf-8")
            self.assertIn("Phase 1", text)
            self.assertIn("/api/seed", text)
            self.assertIn("/api/pool", text)
            self.assertIn("/api/deck/move", text)
            self.assertIn("/api/deck/add", text)


if __name__ == "__main__":
    unittest.main()
