#!/usr/bin/env python3
"""tools/mtga_auto_tool.py 的离线回归测试（纯标准库，无需 MTGA/网络）。

覆盖：增量日志读取（含截断）、增量 JSON 提取（分块喂入与整体解析等价）、
实时状态跟踪、调度建议数学口径、watch/run 命令状态机（回收与报告全部 mock）。
运行：python tools/test_mtga_auto.py
"""

import argparse
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mtga_log_tool as MLT  # noqa: E402
import mtga_auto_tool as MAT  # noqa: E402

TESTDATA = Path(__file__).resolve().parent / "testdata"
SAMPLE2 = TESTDATA / "mtga_log_sample2.txt"


def sample2_payloads():
    return [obj for obj, _ln, _ts in MLT.iter_json_payloads(str(SAMPLE2))]


class TestLogTailer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mtga_auto_test_")
        self.log = Path(self.tmp) / "Player.log"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_incremental_read(self):
        self.log.write_text("line1\n", encoding="utf-8")
        tailer = MAT.LogTailer(self.log, from_start=True)
        text, truncated = tailer.read_new()
        self.assertEqual(text, "line1\n")
        self.assertFalse(truncated)
        self.assertEqual(tailer.read_new(), ("", False))  # 无新增
        with open(self.log, "a", encoding="utf-8") as fh:
            fh.write("line2\n")
        text, _ = tailer.read_new()
        self.assertEqual(text, "line2\n")

    def test_default_seeks_to_end(self):
        self.log.write_text("old\n", encoding="utf-8")
        tailer = MAT.LogTailer(self.log)  # 默认从当前位置
        self.assertEqual(tailer.read_new(), ("", False))

    def test_truncation_resets(self):
        self.log.write_text("x" * 100, encoding="utf-8")
        tailer = MAT.LogTailer(self.log, from_start=True)
        tailer.read_new()
        self.log.write_text("new\n", encoding="utf-8")  # 截断重建
        text, truncated = tailer.read_new()
        self.assertTrue(truncated)
        self.assertEqual(text, "new\n")


class TestPayloadFeeder(unittest.TestCase):
    def test_chunked_feed_equals_whole_parse(self):
        text = SAMPLE2.read_text(encoding="utf-8")
        expected = sample2_payloads()
        feeder = MAT.PayloadFeeder()
        got = []
        # 以 997 字节（奇数块）切分，确保切在多行 JSON 中间
        for i in range(0, len(text), 997):
            got.extend(feeder.feed(text[i:i + 997]))
        got.extend(feeder.flush())
        self.assertEqual(got, expected)

    def test_partial_line_held_until_complete(self):
        feeder = MAT.PayloadFeeder()
        self.assertEqual(feeder.feed('{"a": 1'), [])
        self.assertEqual(feeder.feed('}\n'), [{"a": 1}])

    def test_garbage_line_dropped_not_stuck(self):
        feeder = MAT.PayloadFeeder(max_lines=3)
        out = feeder.feed('{broken\n"still\n"going\n"more\n{"ok": 1}\n')
        self.assertEqual(out, [{"ok": 1}])


class TestLiveGameTracker(unittest.TestCase):
    def test_sample2_state(self):
        tracker = MAT.LiveGameTracker()
        for p in sample2_payloads():
            tracker.feed(p)
        self.assertEqual(tracker.self_seat, 2)  # ConnectResp systemSeatIds [2]
        self.assertEqual(tracker.match_id, "match-fixture-gre-002")
        self.assertTrue(tracker.game_over)
        self.assertEqual(tracker.life.get(1), 16)
        self.assertEqual(tracker.life.get(2), 20)
        # 本家手牌区 35（ownerSeatId 2），起手 7 张，271/274 先后进场
        self.assertEqual(len(tracker.hand_cards()), 5)
        self.assertEqual(tracker.land_played_turn, 2)   # T2 下 Forest
        self.assertIn("T2", tracker.brief_line())

    def test_hand_land_count(self):
        tracker = MAT.LiveGameTracker()
        tracker.self_seat = 1
        tracker.feed({"greToClientEvent": {"greToClientMessages": [
            {"type": "GREMessageType_GameStateMessage", "gameStateMessage": {
                "zones": [{"zoneId": 31, "type": "ZoneType_Hand",
                           "ownerSeatId": 1, "objectInstanceIds": [1, 2, 3]}],
                "gameObjects": [
                    {"instanceId": 1, "grpId": 1, "type": "GameObjectType_Card",
                     "zoneId": 31, "ownerSeatId": 1,
                     "cardTypes": ["CardType_Land"]},
                    {"instanceId": 2, "grpId": 2, "type": "GameObjectType_Card",
                     "zoneId": 31, "ownerSeatId": 1,
                     "cardTypes": ["CardType_Creature"]},
                    {"instanceId": 3, "grpId": 3, "type": "GameObjectType_Card",
                     "zoneId": 31, "ownerSeatId": 1,
                     "cardTypes": ["CardType_Land"]},
                ]}}]}})
        self.assertEqual(tracker.hand_land_count(), 2)

    def _gsm(self, **kw):
        return {"greToClientEvent": {"greToClientMessages": [
            {"type": "GREMessageType_GameStateMessage", "gameStateMessage": kw}]}}

    def test_round_isolation_on_game_number_change(self):
        """Bo3 换局（同 matchID，gameNumber 递增）：zones/objects/life/turn 必须
        清空，match_id/self_seat 保留——否则 zoneId 跨局复用造成跨局污染。"""
        tracker = MAT.LiveGameTracker()
        tracker.self_seat = 1
        tracker.feed(self._gsm(gameInfo={"matchID": "m1", "gameNumber": 1},
                               turnInfo={"turnNumber": 9, "phase": "Phase_Main1"},
                               players=[{"systemSeatNumber": 1, "lifeTotal": 14}],
                               zones=[{"zoneId": 31, "type": "ZoneType_Hand",
                                       "ownerSeatId": 1}],
                               gameObjects=[{"instanceId": 1, "grpId": 1,
                                             "type": "GameObjectType_Card",
                                             "zoneId": 31, "ownerSeatId": 1}]))
        self.assertEqual(len(tracker.objects), 1)
        self.assertEqual(tracker.life.get(1), 14)
        tracker.feed(self._gsm(gameInfo={"matchID": "m1", "gameNumber": 2}))
        self.assertEqual(tracker.match_id, "m1")
        self.assertEqual(tracker.game_number, 2)
        self.assertEqual(tracker.self_seat, 1)
        self.assertEqual(tracker.objects, {})
        self.assertEqual(tracker.zones, {})
        self.assertEqual(tracker.life, {})
        self.assertEqual(tracker.turn, {})
        self.assertIsNone(tracker.game_state_id)

    def test_main_phase_step_cleared_unconditional(self):
        """turnInfo diff 同帧携带 phase=Main1 + 过期 step 时也必须清掉。"""
        tracker = MAT.LiveGameTracker()
        tracker.feed(self._gsm(turnInfo={"turnNumber": 3,
                                         "phase": "Phase_Beginning",
                                         "step": "Step_Draw"}))
        self.assertEqual(tracker.turn.get("step"), "Step_Draw")
        tracker.feed(self._gsm(turnInfo={"phase": "Phase_Main1"}))
        self.assertNotIn("step", tracker.turn)
        # 同帧带旧 step 的退化情况
        tracker.feed(self._gsm(turnInfo={"phase": "Phase_Beginning",
                                         "step": "Step_Draw"}))
        tracker.feed(self._gsm(turnInfo={"phase": "Phase_Main1",
                                         "step": "Step_Draw"}))
        self.assertNotIn("step", tracker.turn)

    def test_deck_message_captured_per_match(self):
        """ConnectResp.connectResp.deckMessage 是本局牌表事实源：每场捕获；
        matchID 变化的重置不得抹掉它（实测消息序：ConnectResp → 新 matchID 的
        首条 gameInfo，若重置清牌表则每场都丢）；无 deckMessage 的重连保留旧值。"""
        tracker = MAT.LiveGameTracker()
        dm = {"deckCards": [1, 1, 2], "sideboardCards": [3]}
        tracker.feed({"greToClientEvent": {"greToClientMessages": [
            {"type": "GREMessageType_ConnectResp", "systemSeatIds": [2],
             "connectResp": {"deckMessage": dm}}]}})
        self.assertEqual(tracker.self_seat, 2)
        self.assertEqual(tracker.deck_message, dm)
        # 新 matchID 的 gameInfo（= 上一场的 reset 路径）不得清掉牌表
        tracker.feed(self._gsm(gameInfo={"matchID": "m1", "gameNumber": 1}))
        self.assertEqual(tracker.deck_message, dm)
        # 无 deckMessage 的重连：保留已有牌表
        tracker.feed({"greToClientEvent": {"greToClientMessages": [
            {"type": "GREMessageType_ConnectResp", "systemSeatIds": [1],
             "connectResp": {}}]}})
        self.assertEqual(tracker.deck_message, dm)

    def test_deck_message_stats(self):
        def fake_scryfall(path, params=None):
            if path.endswith("/1"):
                return {"name": "Forest", "type_line": "Basic Land — Forest"}
            return {"name": "Llanowar Elves", "type_line": "Creature — Elf Druid"}

        dm = {"deckCards": [1] * 20 + [2] * 4, "sideboardCards": [2, 2]}
        with mock.patch.object(MAT, "scryfall_get", side_effect=fake_scryfall):
            stats = MAT.deck_message_stats(dm)
        self.assertEqual(stats["lands"], 20)
        self.assertEqual(stats["total"], 24)
        self.assertIn("20 Forest", stats["text"])
        self.assertIn("Sideboard", stats["text"])
        self.assertIn("2 Llanowar Elves", stats["text"])


class TestMulliganAdvice(unittest.TestCase):
    def test_keep_and_mull(self):
        text, keep = MAT.mulligan_advice(7, 3, 24, 60)
        self.assertTrue(keep)
        self.assertIn("留", text)
        text, keep = MAT.mulligan_advice(7, 1, 24, 60)
        self.assertFalse(keep)
        self.assertIn("调度", text)

    def test_threshold_override(self):
        _text, keep = MAT.mulligan_advice(7, 0, 24, 60, land_min=0, land_max=7)
        self.assertTrue(keep)


class TestIterEvents(unittest.TestCase):
    def test_sample2_events(self):
        events = MAT.iter_events(sample2_payloads())
        kinds = [k for k, _ in events]
        self.assertIn("match_start", kinds)
        self.assertIn("match_end", kinds)
        end_ids = [mid for k, mid in events if k == "match_end"]
        self.assertIn("match-fixture-gre-002", end_ids)


class _CmdSmokeBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mtga_auto_test_")
        self.log = Path(self.tmp) / "Player.log"
        shutil.copy(SAMPLE2, self.log)
        self.sessions = Path(self.tmp) / "sessions"
        self._patchers = [
            mock.patch.object(MAT, "SESSIONS_ROOT", self.sessions),
            mock.patch.object(MAT, "collect_match"),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _args(self, **kw):
        base = dict(log=str(self.log), poll=0, from_start=True, max_polls=5,
                    deck=None, llm=False, llm_quiet=4.0, dashboard=None)
        base.update(kw)
        return argparse.Namespace(**base)


class TestDraftRecord(_CmdSmokeBase):
    def test_payload_draft_keys(self):
        self.assertEqual(MAT.payload_draft_keys({"a": 1}), [])
        # 只匹配键不匹配值：事件名里的 QuickDraft_xxx 是值噪声，不命中
        self.assertEqual(MAT.payload_draft_keys({"name": "QuickDraft_OM1"}), [])
        hits = MAT.payload_draft_keys(
            {"outer": {"draftNotify": {"packCards": ["1"]}, "PickNumber": 3}})
        self.assertEqual(hits, ["PickNumber", "draftNotify", "packCards"])

    def test_payload_draft_keys_stringified_json(self):
        # 实测 BotDraftDraftStatus：轮抓状态以字符串化 JSON 塞在 Payload 字段里
        inner = json.dumps({"DraftStatus": "PickNext", "PackNumber": 0,
                            "DraftPack": ["103410"]})
        hits = MAT.payload_draft_keys({"CurrentModule": "BotDraft", "Payload": inner})
        self.assertEqual(hits, ["DraftPack", "DraftStatus", "PackNumber"])
        # 非 JSON 字符串与坏 JSON 不炸
        self.assertEqual(MAT.payload_draft_keys({"Payload": "not json"}), [])
        self.assertEqual(MAT.payload_draft_keys({"Payload": "{broken"}), [])

    def test_record_writes_sample(self):
        sample_dir = Path(self.tmp) / "draft_samples"
        payload = {"draftStatus": {"packCards": ["1", "2"]}}
        self.log.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        with mock.patch.object(MAT, "DRAFT_SAMPLE_DIR", sample_dir):
            rc = MAT.cmd_draft_record(self._args())
        self.assertEqual(rc, 0)
        files = list(sample_dir.glob("*.jsonl"))
        self.assertEqual(len(files), 1)
        rec = json.loads(files[0].read_text(encoding="utf-8").strip())
        self.assertEqual(rec["payload"], payload)
        self.assertIn("draftStatus", rec["keys"])

    def test_record_ignores_non_draft(self):
        self.log.write_text('{"greToClientEvent": {}}\n', encoding="utf-8")
        sample_dir = Path(self.tmp) / "draft_samples"
        with mock.patch.object(MAT, "DRAFT_SAMPLE_DIR", sample_dir):
            rc = MAT.cmd_draft_record(self._args())
        self.assertEqual(rc, 0)
        self.assertEqual(list(sample_dir.glob("*.jsonl")), [])


class TestCmdWatch(_CmdSmokeBase):
    def test_match_end_triggers_collect_once(self):
        rc = MAT.cmd_watch(self._args())
        self.assertEqual(rc, 0)
        MAT.collect_match.assert_called_once_with(str(self.log),
                                                  "match-fixture-gre-002",
                                                  deck_tag=None)


class TestCmdRun(_CmdSmokeBase):
    def test_run_one_game_then_report(self):
        report_proc = mock.Mock(returncode=0, stdout="| report |\n", stderr="")
        with mock.patch.object(MAT.subprocess, "run", return_value=report_proc):
            rc = MAT.cmd_run(self._args(games=1, timeout=1, deck="TestDeck"))
        self.assertEqual(rc, 0)
        MAT.collect_match.assert_called_once()
        reports = list(self.sessions.glob("*/report.md"))
        self.assertEqual(len(reports), 1)
        self.assertIn("| report |", reports[0].read_text(encoding="utf-8"))

    def test_run_timeout_when_no_match(self):
        self.log.write_text("no events here\n", encoding="utf-8")
        rc = MAT.cmd_run(self._args(games=1, timeout=0, max_polls=None))
        self.assertEqual(rc, 7)
        MAT.collect_match.assert_not_called()


class TestCmdAdvise(_CmdSmokeBase):
    def test_advise_prints_brief(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        args = self._args(lands=24, deck_size=60, deckfile=None,
                          land_min=None, land_max=None)
        with redirect_stdout(buf):
            rc = MAT.cmd_advise(args)
        self.assertEqual(rc, 0)
        self.assertIn("[advise]", buf.getvalue())
        self.assertIn("T2", buf.getvalue())

    def test_advise_without_land_info_enters_standby(self):
        # 无牌表参数且日志无 courseDeck → 待识别模式正常运行，不再报错退出
        args = self._args(lands=None, deck_size=None, deckfile=None,
                          land_min=None, land_max=None)
        self.assertEqual(MAT.cmd_advise(args), 0)


FAKE_ORACLE = {"name": "Fake Card", "mana_cost": "{1}{G}",
               "type_line": "Creature — Test", "oracle_text": "Fake text."}


class TestRenderSnapshot(unittest.TestCase):
    def test_sample2_snapshot(self):
        tracker = MAT.LiveGameTracker()
        for p in sample2_payloads():
            tracker.feed(p)
        with mock.patch.object(MAT, "card_oracle", return_value=FAKE_ORACLE):
            text = MAT.render_snapshot(tracker)
        self.assertIn("我方战场", text)
        self.assertIn("对方战场", text)
        self.assertIn("对方手牌", text)
        self.assertIn("禁止假设", text)  # 对手手牌必须显式标注未知
        self.assertIn("我方坟墓场", text)

    def test_prompt_includes_deck_and_snapshot(self):
        tracker = MAT.LiveGameTracker()
        tracker.self_seat = 1
        with mock.patch.object(MAT, "card_oracle", return_value=FAKE_ORACLE):
            prompt = MAT.build_llm_prompt(tracker, deck_text="4 Fake Card\n20 Forest")
        self.assertIn("4 Fake Card", prompt)
        self.assertIn("当前局面快照", prompt)
        self.assertIn("决策点", prompt)


class TestLlmBackend(unittest.TestCase):
    def test_llm_chat_parses_response(self):
        payload = json.dumps(
            {"choices": [{"message": {"content": " 建议下地 "}}]}).encode("utf-8")
        resp = mock.Mock()
        resp.read.return_value = payload
        ctx = mock.Mock()
        ctx.__enter__ = mock.Mock(return_value=resp)
        ctx.__exit__ = mock.Mock(return_value=False)
        with mock.patch.object(MAT.urllib.request, "urlopen", return_value=ctx):
            out = MAT.llm_chat({"base_url": "https://x", "model": "m",
                                "api_key": "k"}, [{"role": "user", "content": "hi"}])
        self.assertEqual(out, "建议下地")

    def test_llm_chat_bad_response_raises(self):
        resp = mock.Mock()
        resp.read.return_value = b"{}"
        ctx = mock.Mock()
        ctx.__enter__ = mock.Mock(return_value=resp)
        ctx.__exit__ = mock.Mock(return_value=False)
        with mock.patch.object(MAT.urllib.request, "urlopen", return_value=ctx):
            with self.assertRaises(MAT.AutoToolError):
                MAT.llm_chat({"base_url": "https://x", "model": "m",
                              "api_key": "k"}, [])

    def test_load_config_env_override(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as fh:
            json.dump({"api_key": "from-file"}, fh)
            cfg_path = fh.name
        try:
            with mock.patch.object(MAT, "LLM_CONFIG_JSON", Path(cfg_path)), \
                    mock.patch.dict("os.environ", {"DEEPSEEK_API_KEY": "from-env"}):
                cfg = MAT.load_llm_config()
            self.assertEqual(cfg["api_key"], "from-env")
            self.assertEqual(cfg["base_url"], "https://api.deepseek.com")
            self.assertEqual(cfg["model"], "deepseek-chat")
        finally:
            Path(cfg_path).unlink(missing_ok=True)

    def test_load_config_missing(self):
        with mock.patch.object(MAT, "LLM_CONFIG_JSON",
                               Path("/nonexistent/llm_config.json")):
            with self.assertRaises(MAT.AutoToolError):
                MAT.load_llm_config()

    def test_config_status_masks_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "llm.json"
            path.write_text(json.dumps({"base_url": "https://llm.test/v1",
                                        "model": "draft-model",
                                        "api_key": "secret-key"}), encoding="utf-8")
            status = MAT.llm_config_status(path)
        self.assertTrue(status["has_api_key"])
        self.assertEqual(status["api_key_source"], "file")
        self.assertNotIn("secret-key", json.dumps(status))

    def test_save_config_validates_endpoint_and_preserves_blank_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "llm.json"
            path.write_text(json.dumps({"api_key": "keep-me"}), encoding="utf-8")
            status = MAT.save_llm_config("https://llm.test/v1", "model-v2", path=path)
            self.assertEqual(status["model"], "model-v2")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["api_key"], "keep-me")
            with self.assertRaises(MAT.AutoToolError):
                MAT.save_llm_config("not-a-url", "model", path=path)


class TestCourseDeck(unittest.TestCase):
    def test_course_deck_stats(self):
        course = {"name": "TestDeck", "mainDeck": [
            {"cardId": 1, "quantity": 4}, {"cardId": 2, "quantity": 20}]}

        def fake_scryfall(path, params=None):
            if path.endswith("/1"):
                return {"name": "Llanowar Elves", "type_line": "Creature — Elf Druid"}
            return {"name": "Forest", "type_line": "Basic Land — Forest"}

        with mock.patch.object(MAT, "scryfall_get", side_effect=fake_scryfall):
            stats = MAT.course_deck_stats(course)
        self.assertEqual(stats["lands"], 20)
        self.assertEqual(stats["total"], 24)
        self.assertIn("20 Forest", stats["text"])

    def test_latest_course_deck_from_log(self):
        import tempfile
        payload = {"courseDeck": {"name": "Logged",
                                  "mainDeck": [{"cardId": 2, "quantity": 60}]}}
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False,
                                         encoding="utf-8") as fh:
            fh.write("noise\n" + json.dumps(payload) + "\n")
            log_path = fh.name
        try:
            with mock.patch.object(MAT, "scryfall_get", return_value={
                    "name": "Forest", "type_line": "Basic Land — Forest"}):
                stats = MAT.latest_course_deck(log_path)
            self.assertEqual(stats["name"], "Logged")
            self.assertEqual(stats["lands"], 60)
        finally:
            Path(log_path).unlink(missing_ok=True)


class TestDashboard(unittest.TestCase):
    def test_status_board_snapshot(self):
        board = MAT.StatusBoard()
        board.set(deck="TestDeck", brief="[T1 我方 Main1]")
        board.log("测试事件", "game")
        board.log("LLM 建议", "llm")
        snap = board.snapshot()
        self.assertEqual(snap["fields"]["deck"], "TestDeck")
        self.assertEqual(len(snap["logs"]), 2)
        self.assertEqual(snap["logs"][1]["kind"], "llm")

    def test_dashboard_http_smoke(self):
        import urllib.request as ur
        board = MAT.StatusBoard()
        board.set(deck="SmokeDeck")
        srv, port = MAT.start_dashboard(board, 0)  # 端口 0 = 随机空闲端口
        try:
            html = ur.urlopen(f"http://127.0.0.1:{port}/", timeout=5
                              ).read().decode("utf-8")
            self.assertIn("监控台", html)
            data = json.loads(ur.urlopen(f"http://127.0.0.1:{port}/status.json",
                                         timeout=5).read().decode("utf-8"))
            self.assertEqual(data["fields"]["deck"], "SmokeDeck")
        finally:
            srv.shutdown()

    def test_draft_panel_state_and_config_api_are_local_and_masked(self):
        import urllib.request as ur
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "llm.json"
            panel = MAT.DraftPickPanel(set_code="HOB", llm=True,
                                       llm_config_path=config_path)
            srv, port = MAT.start_draft_panel(panel, 0)
            try:
                state = json.loads(ur.urlopen(
                    f"http://127.0.0.1:{port}/api/state", timeout=5
                ).read().decode("utf-8"))
                self.assertEqual(state["set_code"], "HOB")
                self.assertNotIn("api_key", state["llm_config"])
                request = ur.Request(
                    f"http://127.0.0.1:{port}/api/config",
                    data=json.dumps({"base_url": "https://llm.test/v1",
                                     "model": "draft-model",
                                     "api_key": "secret-key"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"}, method="POST")
                body = ur.urlopen(request, timeout=5).read().decode("utf-8")
                self.assertNotIn("secret-key", body)
                self.assertTrue(json.loads(body)["ok"])
                page = ur.urlopen(f"http://127.0.0.1:{port}/", timeout=5
                                  ).read().decode("utf-8")
                self.assertIn("LLM 端点配置", page)
                self.assertNotIn("secret-key", page)
            finally:
                srv.shutdown()


class TestHandLabelsCn(unittest.TestCase):
    def test_chinese_label_with_fallback(self):
        objs = [{"grpId": 1}, {"grpId": 2}, {"instanceId": 99}]  # 99 无 grpId 跳过
        with mock.patch.object(MAT.MLT, "resolve_grp_card",
                               side_effect=lambda g: {1: "Forest", 2: "<grpId 2>"}[g]), \
                mock.patch.object(MAT.MLT, "load_grp_cache", return_value={}), \
                mock.patch.object(MAT, "fetch_chinese_name",
                                  return_value=("树林", None)) as m_cn:
            labels = MAT.hand_labels_cn(objs)
        self.assertEqual(labels[0], "树林（Forest）")
        self.assertEqual(labels[1], "<grpId 2>")  # 未解析牌名不查中文
        m_cn.assert_called_once_with("Forest")


class TestSubObjectFilter(unittest.TestCase):
    """历险子物件与未解析 grpId 的渲染口径（对局实测踩坑回归）。"""

    def _tracker_with_adventure(self):
        tracker = MAT.LiveGameTracker()
        tracker.self_seat = 1
        tracker.feed({"greToClientEvent": {"greToClientMessages": [
            {"type": "GREMessageType_GameStateMessage", "gameStateMessage": {
                "zones": [{"zoneId": 28, "type": "ZoneType_Battlefield"},
                          {"zoneId": 31, "type": "ZoneType_Hand", "ownerSeatId": 1}],
                "gameObjects": [
                    # 主牌 Bonecrusher Giant
                    {"instanceId": 10, "grpId": 500, "type": "GameObjectType_Card",
                     "zoneId": 28, "ownerSeatId": 1, "controllerSeatId": 1,
                     "cardTypes": ["CardType_Creature"]},
                    # 历险子物件（影子，必须排除）
                    {"instanceId": 11, "grpId": 70488,
                     "type": "GameObjectType_Adventure", "zoneId": 28,
                     "ownerSeatId": 1, "controllerSeatId": 1, "parentId": 10,
                     "cardTypes": ["CardType_Instant"]},
                    # 手牌里的历险子物件也不计入手牌数
                    {"instanceId": 12, "grpId": 500, "type": "GameObjectType_Card",
                     "zoneId": 31, "ownerSeatId": 1},
                    {"instanceId": 13, "grpId": 70488,
                     "type": "GameObjectType_Adventure", "zoneId": 31,
                     "ownerSeatId": 1, "parentId": 12},
                    # Arena 内部 id 的基本地（Scryfall 查不到，按类别渲染）
                    {"instanceId": 14, "grpId": 100131, "type": "GameObjectType_Card",
                     "zoneId": 28, "ownerSeatId": 2, "controllerSeatId": 2,
                     "superTypes": ["SuperType_Basic"],
                     "cardTypes": ["CardType_Land"], "subtypes": ["SubType_Forest"]},
                ]}}]}})
        return tracker

    def test_subobjects_excluded(self):
        tracker = self._tracker_with_adventure()
        self.assertEqual(len(tracker.hand_cards()), 1)  # 影子物件不计入手牌

        def by_grp(gid):
            if gid == 500:
                return FAKE_ORACLE
            return {"name": f"<grpId {gid}>", "mana_cost": "",
                    "type_line": "", "oracle_text": ""}

        with mock.patch.object(MAT, "card_oracle", side_effect=by_grp):
            text = MAT.render_snapshot(tracker)
        bf_line = next(l for l in text.splitlines() if l.startswith("我方战场"))
        self.assertEqual(bf_line.count("Fake Card"), 1)  # 战场只显示主牌一次
        self.assertNotIn("70488", text)  # 历险影子不出现
        self.assertIn("未解析 Basic Land Forest #100131", text)

    def test_unresolved_basic_land_label(self):
        tracker = self._tracker_with_adventure()

        def unresolved(gid):
            return {"name": f"<grpId {gid}>", "mana_cost": "",
                    "type_line": "", "oracle_text": ""}

        with mock.patch.object(MAT, "card_oracle", side_effect=unresolved):
            text = MAT.render_snapshot(tracker)
        self.assertIn("未解析 Basic Land Forest #100131", text)


class TestActionsAvailable(unittest.TestCase):
    def test_actions_rendered(self):
        tracker = MAT.LiveGameTracker()
        tracker.self_seat = 1
        tracker.feed({"greToClientEvent": {"greToClientMessages": [
            {"type": "GREMessageType_ActionsAvailableReq", "systemSeatIds": [1],
             "actionsAvailableReq": {"actions": [
                 {"actionType": "ActionType_Cast", "grpId": 80296,
                  "manaCost": [{"color": ["ManaColor_Generic"], "count": 2},
                               {"color": ["ManaColor_Green"], "count": 1}]},
                 {"actionType": "ActionType_Play", "grpId": 100},
                 {"actionType": "ActionType_Pass"}]}}]}})
        with mock.patch.object(MAT, "card_oracle", return_value=FAKE_ORACLE):
            line = MAT._fmt_actions(tracker)
        self.assertIn("当前可选动作", line)
        self.assertIn("施放 Fake Card {2}{G}（费用不足）", line)  # 0 地，费用不足
        self.assertIn("下地 Fake Card", line)
        self.assertIn("让过", line)

    def test_affordable_action_not_tagged(self):
        tracker = MAT.LiveGameTracker()
        tracker.self_seat = 1
        tracker.feed({"greToClientEvent": {"greToClientMessages": [
            {"type": "GREMessageType_GameStateMessage", "gameStateMessage": {
                "zones": [{"zoneId": 28, "type": "ZoneType_Battlefield"}],
                "gameObjects": [
                    {"instanceId": 1, "grpId": 9, "type": "GameObjectType_Card",
                     "zoneId": 28, "controllerSeatId": 1,
                     "cardTypes": ["CardType_Land"]},
                    {"instanceId": 2, "grpId": 9, "type": "GameObjectType_Card",
                     "zoneId": 28, "controllerSeatId": 1,
                     "cardTypes": ["CardType_Land"], "tapState": "TapState_Tapped"},
                ]}},
            {"type": "GREMessageType_ActionsAvailableReq", "systemSeatIds": [1],
             "actionsAvailableReq": {"actions": [
                 {"actionType": "ActionType_Cast", "grpId": 80296,
                  "manaCost": [{"color": ["ManaColor_Green"], "count": 1}]}]}}]}})
        with mock.patch.object(MAT, "card_oracle", return_value=FAKE_ORACLE):
            line = MAT._fmt_actions(tracker)
        self.assertIn("施放 Fake Card {G}", line)  # 1 地未横置，1 费可付
        self.assertNotIn("（费用不足）", line)

    def test_stale_step_cleared_on_main_phase(self):
        tracker = MAT.LiveGameTracker()
        tracker.self_seat = 1
        tracker.feed({"greToClientEvent": {"greToClientMessages": [
            {"type": "GREMessageType_GameStateMessage", "gameStateMessage": {
                "turnInfo": {"phase": "Phase_Beginning", "step": "Step_Draw",
                             "turnNumber": 1, "activePlayer": 1}}},
            {"type": "GREMessageType_GameStateMessage", "gameStateMessage": {
                # 切主阶段的增量消息不带 step——前向填充不得留下过期 Draw
                "turnInfo": {"phase": "Phase_Main1", "turnNumber": 1,
                             "activePlayer": 1}}}]}})
        self.assertEqual(tracker.turn.get("phase"), "Phase_Main1")
        self.assertIsNone(tracker.turn.get("step"))  # 过期 Draw 已清除


class TestCmdAdviseMatchEnd(_CmdSmokeBase):
    def test_match_end_triggers_collect_and_verdict(self):
        text = SAMPLE2.read_text(encoding="utf-8")
        reads = [("", False), (text, False)]  # 追平读空，第 1 次轮询喂入整场

        class FakeTailer:
            def __init__(self2, *a, **k):
                pass

            def read_new(self2):
                return reads.pop(0) if reads else ("", False)

        rec = {"match_id": "match-fixture-gre-002", "won": True,
               "game_wins": 2, "game_losses": 0, "opponent_name": "RivalGre"}
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        args = self._args(lands=24, deck_size=60, deckfile=None,
                          land_min=None, land_max=None, max_polls=3)
        with mock.patch.object(MAT, "LogTailer", FakeTailer), \
                mock.patch.object(MAT.MLT, "load_matches", return_value=[rec]), \
                redirect_stdout(buf):
            rc = MAT.cmd_advise(args)
        self.assertEqual(rc, 0)
        MAT.collect_match.assert_called_once()
        out = buf.getvalue()
        self.assertIn("对局结束", out)
        self.assertIn("胜", out)


class TestDraftWatch(unittest.TestCase):
    """draft --watch 实时 pick 排名面板：BotDraftDraftStatus 实测 schema 回归。"""

    @staticmethod
    def _outer(inner):
        """实测形态：外层 JSON 的 Payload 是字符串化 JSON。"""
        return {"CurrentModule": "BotDraft", "Payload": json.dumps(inner)}

    @staticmethod
    def _status(**kw):
        base = {"Result": "Success", "EventName": "QuickDraft_HOB_20260820",
                "DraftStatus": "PickNext", "PackNumber": 0, "PickNumber": 0,
                "NumCardsToPick": 1, "DraftPack": [], "PackStyles": [],
                "PickedCards": [], "PickedStyles": []}
        base.update(kw)
        return base

    def _patch_cards(self, names, cmcs, table_entries, chinese=None):
        """mock 牌名/cmc/中文名/评分表，网络全断。"""
        class FakeTable:
            def lookup(self, name):
                return table_entries.get(name)

        return [mock.patch.object(MAT.MLT, "resolve_grp_meta",
                                  side_effect=lambda g: {"name": names.get(str(g)),
                                                         "type_line": None}),
                mock.patch.object(MAT, "scryfall_get",
                                  side_effect=lambda path, params=None:
                                  {"cmc": cmcs.get(path.rsplit("/", 1)[-1])}),
                mock.patch.object(MAT, "fetch_chinese_name",
                                  side_effect=lambda n: ((chinese or {}).get(n), None)),
                mock.patch.object(MAT, "load_card_table",
                                  return_value=FakeTable())]

    def test_parse_draft_status(self):
        inner = self._status(DraftPack=["103410"])
        self.assertEqual(MAT.parse_draft_status(self._outer(inner)), inner)
        self.assertEqual(MAT.parse_draft_status({"payload": self._outer(inner)}), inner)
        # 非轮抓载荷 / 坏字符串化 JSON / 缺 DraftStatus 一律 None
        self.assertIsNone(MAT.parse_draft_status({"greToClientEvent": {}}))
        self.assertIsNone(MAT.parse_draft_status({"Payload": "not json"}))
        self.assertIsNone(MAT.parse_draft_status({"Payload": "{broken"}))
        self.assertIsNone(MAT.parse_draft_status({"Payload": '{"foo": 1}'}))
        self.assertIsNone(MAT.parse_draft_status({"Payload": ["not str"]}))

    def test_panel_pack_pick_progression(self):
        names = {str(i): f"Card{i}" for i in (1, 2, 3)}
        cmcs = {"1": 2, "2": 3, "3": 4}
        patchers = self._patch_cards(names, cmcs, {})
        for p in patchers:
            p.start()
        try:
            panel = MAT.DraftPickPanel()
            panel.feed(self._status(DraftPack=["1", "2", "3"]))
            self.assertEqual(panel.set_code, "HOB")  # EventName 解析系列码
            panel.feed(self._status(PickNumber=1, DraftPack=["1", "2"],
                                    PickedCards=["3"]))
            self.assertEqual((panel.pack_number, panel.pick_number), (0, 1))
            self.assertEqual(panel.pack, ["1", "2"])
            self.assertEqual(panel.picked, ["3"])  # PickedCards 累计
            panel.feed(self._status(PackNumber=2, PickNumber=4, DraftPack=["1"]))
            self.assertEqual((panel.pack_number, panel.pick_number), (2, 4))
        finally:
            for p in patchers:
                p.stop()

    def test_panel_set_override(self):
        patchers = self._patch_cards({}, {}, {})
        for p in patchers:
            p.start()
        try:
            panel = MAT.DraftPickPanel(set_code="FDN")
            panel.feed(self._status())
            self.assertEqual(panel.set_code, "FDN")  # --set 覆盖 EventName 解析
        finally:
            for p in patchers:
                p.stop()

    @staticmethod
    def _assert_html_balanced(page):
        from html.parser import HTMLParser

        class Checker(HTMLParser):
            VOID = {"meta", "br", "img", "input", "link", "hr"}

            def __init__(self):
                super().__init__()
                self.stack = []
                self.mismatch = []

            def handle_starttag(self, tag, attrs):
                if tag not in self.VOID:
                    self.stack.append(tag)

            def handle_endtag(self, tag):
                if self.stack and self.stack[-1] == tag:
                    self.stack.pop()
                else:
                    self.mismatch.append(tag)

        checker = Checker()
        checker.feed(page)
        self_stack = checker.stack
        assert not checker.mismatch, f"标签不配对: {checker.mismatch}"
        assert not self_stack, f"未闭合标签: {self_stack}"

    def test_panel_ranking_and_render(self):
        names = {"1": "Alpha Card", "2": "Beta Card", "3": None,
                 "4": "Gamma Card", "5": "Picked Card"}
        cmcs = {"1": 2, "2": 3, "4": 5, "5": 2}
        table = {"Alpha Card": {"grade": "S", "community_score": 9.5, "note": "炸弹"},
                 "Beta Card": {"grade": "C", "community_score": 4, "note": "填充"},
                 "Picked Card": {"grade": "B", "community_score": 6, "note": "主力"}}
        patchers = self._patch_cards(names, cmcs, table,
                                     chinese={"Alpha Card": "甲牌"})
        for p in patchers:
            p.start()
        try:
            panel = MAT.DraftPickPanel()
            panel.feed(self._status(DraftPack=["1", "2", "3", "4"],
                                    PickedCards=["5"]))
            # 排名：等级主键 S→F，未评级 "?" 排最后且不丢牌
            self.assertEqual([r["grp_id"] for r in panel.rows],
                             ["1", "2", "3", "4"])
            self.assertEqual(panel.rows[0]["label"], "甲牌（Alpha Card）")
            self.assertEqual(panel.rows[0]["grade"], "S")
            self.assertEqual(panel.rows[2]["label"], "<grpId 3>")  # 解析失败降级
            self.assertEqual(panel.rows[2]["grade"], "")  # 未评级，渲染为 "?"
            self.assertEqual(panel.rows[0]["hint"], "补2费缺口")  # 已抓 1 张 2 费
            page = panel.render_html()
            self.assertIn('refresh" content="3"', page)
            self.assertIn("P1 Pick1", page)
            self.assertIn("补2费缺口", page)
            self.assertIn("&lt;grpId 3&gt;", page)  # 渲染转义
            self.assertIn("已抓 1 张", page)
            self.assertIn("Picked Card", page)
            self.assertIn("2费×1", page)
            self._assert_html_balanced(page)
        finally:
            for p in patchers:
                p.stop()

    def test_panel_non_picknext_status(self):
        patchers = self._patch_cards({}, {}, {})
        for p in patchers:
            p.start()
        try:
            panel = MAT.DraftPickPanel()
            panel.feed(self._status(DraftStatus="Complete"))
            page = panel.render_html()
            self.assertIn("状态：Complete", page)
            self.assertNotIn("<table>", page)  # 非 PickNext 不出当前包表
        finally:
            for p in patchers:
                p.stop()

    def test_panel_llm_advice_reorders_and_records(self):
        names = {"1": "Alpha Card", "2": "Beta Card"}
        cmcs = {"1": 2, "2": 3}
        table = {"Alpha Card": {"grade": "S", "community_score": 9},
                 "Beta Card": {"grade": "B", "community_score": 6}}
        patchers = self._patch_cards(names, cmcs, table)
        for patcher in patchers:
            patcher.start()
        try:
            with mock.patch.object(MAT, "load_llm_config", return_value={"api_key": "k"}), \
                    mock.patch.object(MAT, "llm_chat", return_value=json.dumps([
                        {"name": "Alpha Card", "raw_power": 0.1,
                         "synergy": 0.1, "reason": "保留资源"},
                        {"name": "Beta Card", "raw_power": 0.9,
                         "synergy": 0.9, "reason": "协同更高"},
                    ])), \
                    mock.patch.object(MAT, "record_draft_advice") as record:
                panel = MAT.DraftPickPanel(llm=True)
                panel.feed(self._status(DraftPack=["1", "2"]))
            self.assertEqual(panel.advice_status, "ok")
            self.assertEqual(panel.rows[0]["grp_id"], "2")
            self.assertIn("协同更高", panel.render_html())
            record.assert_called_once()
        finally:
            for patcher in patchers:
                patcher.stop()

    def test_panel_llm_failure_keeps_machine_rows(self):
        names = {"1": "Alpha Card", "2": "Beta Card"}
        cmcs = {"1": 2, "2": 3}
        table = {"Alpha Card": {"grade": "S"}, "Beta Card": {"grade": "B"}}
        patchers = self._patch_cards(names, cmcs, table)
        for patcher in patchers:
            patcher.start()
        try:
            with mock.patch.object(MAT, "load_llm_config",
                                   side_effect=MAT.AutoToolError("no config")), \
                    mock.patch.object(MAT, "record_draft_advice"):
                panel = MAT.DraftPickPanel(llm=True)
                panel.feed(self._status(DraftPack=["1", "2"]))
            self.assertEqual(panel.advice_status, "offline")
            self.assertEqual({row["grp_id"] for row in panel.rows}, {"1", "2"})
            self.assertTrue(all(row["recommendation_score"] is not None
                                for row in panel.rows))
            self.assertIn("LLM", panel.render_html())
        finally:
            for patcher in patchers:
                patcher.stop()

    def test_cmd_draft_watch_smoke(self):
        tmp = tempfile.mkdtemp(prefix="mtga_auto_test_")
        log = Path(tmp) / "Player.log"
        names = {"1": "CardOne", "2": "CardTwo"}
        lines = ["[UnityCrossThreadLogger]==> BotDraftDraftStatus {\"req\": 1}",
                 "<== BotDraftDraftStatus(940404a0-)",
                 json.dumps(self._outer(self._status(DraftPack=["1", "2"]))),
                 "<== BotDraftDraftStatus(940404a1-)",
                 json.dumps(self._outer(self._status(
                     PickNumber=1, DraftPack=["1"], PickedCards=["2"])))]
        try:
            log.write_text("\n".join(lines) + "\n", encoding="utf-8")
            args = argparse.Namespace(log=str(log), poll=0, from_start=True,
                                      max_polls=2, set=None, port=0)
            patchers = self._patch_cards(names, {"1": 2, "2": 3}, {})
            for p in patchers:
                p.start()
            import io
            from contextlib import redirect_stderr
            buf = io.StringIO()
            try:
                with redirect_stderr(buf):
                    rc = MAT.cmd_draft_watch(args)
            finally:
                for p in patchers:
                    p.stop()
            self.assertEqual(rc, 0)
            self.assertIn("[draft] P1Pick2 包内 1 张 | 已抓 1 张", buf.getvalue())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
