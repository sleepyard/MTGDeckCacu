#!/usr/bin/env python3
"""set_preview_tool.py 离线回归测试（合成 Scryfall 数据驱动，无网络）。

补丁边界：模块级 fetch_set_cards / mtg_tool.scryfall_get /
AUTO.load_llm_config / mtga_draft_tool.build_card_table（绝不打 urlopen）；
SET_REVIEW_ROOT 与 DRAFT_RATINGS_DIR 补丁到 tempfile 目录。"""

import io
import json
import shutil
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mtg_tool  # noqa: E402
import mtga_draft_tool as MDT  # noqa: E402
import set_preview_tool as SPT  # noqa: E402

# 运行自证行边界屏蔽：本文件直接调 cmd_fetch/main，测试期间不写入真实 run_log。
# 用 setUpModule/tearDownModule 限定在本模块测试执行期内（共享 runlog 模块属性，
# import 时全局 start 会污染其他测试模块）。
_PATCHER = None


def setUpModule():
    global _PATCHER
    _PATCHER = mock.patch.object(SPT.runlog, "log_run")
    _PATCHER.start()


def tearDownModule():
    _PATCHER.stop()


def _card(name, num, oid, text="Trample", cost="{2}{G}",
          type_line="Creature — Beast", layout="normal", rarity="common"):
    """Scryfall 形单卡 dict（tools/testdata 风格，字段与快照消费方对齐）。"""
    return {"object": "card", "name": name, "oracle_id": oid, "id": "id-" + oid,
            "collector_number": str(num), "oracle_text": text,
            "mana_cost": cost, "type_line": type_line, "layout": layout,
            "rarity": rarity}


# 批次 1：三张（含一张变更候选 + 一张移除候选）
BATCH1 = [
    _card("Alpha Beast", 1, "o1", text="Trample"),
    _card("Beta Trick", 2, "o2", text="Draw a card.", cost="{U}",
          type_line="Instant"),
    _card("Delta Wall", 4, "o4", text="Defender"),
]
# 批次 2：Alpha 改 oracle_text，Delta 移除，新增 Gamma
BATCH2 = [
    _card("Alpha Beast", 1, "o1", text="Trample, haste"),
    _card("Beta Trick", 2, "o2", text="Draw a card.", cost="{U}",
          type_line="Instant"),
    _card("Gamma Bomb", 3, "o3", text="Deals 5.", cost="{3}{R}{R}",
          type_line="Sorcery", rarity="rare"),
]

SET_META = {"name": "Test Set", "card_count": 200,
            "released_at": "2099-01-01", "set_type": "expansion"}


class PreviewTestCase(unittest.TestCase):
    """公共脚手架：tempfile 补丁 SET_REVIEW_ROOT / DRAFT_RATINGS_DIR。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="set_preview_test_"))
        self._patches = [
            mock.patch.object(SPT, "SET_REVIEW_ROOT", self.tmp / "SetReview"),
            mock.patch.object(MDT, "DRAFT_RATINGS_DIR", self.tmp / "draft_ratings"),
        ]
        for p in self._patches:
            p.start()
        SPT.SET_REVIEW_ROOT.mkdir()
        self.review_dir = SPT.SET_REVIEW_ROOT / "TS1_20260901"

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------------------------------------------------------------- 辅助
    def make_review_dir(self, cards=None, with_overview=True):
        """手工建评审目录（绕过 init 的网络）；可选写入首快照与 state。"""
        (self.review_dir / "data").mkdir(parents=True, exist_ok=True)
        (self.review_dir / "00_RunManifest.md").write_text(
            SPT.manifest_skeleton("TS1", SET_META), encoding="utf-8")
        if with_overview:
            (self.review_dir / "01_SetOverview.md").write_text(
                SPT.overview_skeleton("TS1"), encoding="utf-8")
        (self.review_dir / "06_ChangeLog.md").write_text(
            SPT.changelog_skeleton("TS1"), encoding="utf-8")
        state = {"set": "TS1", "mode": "P", "card_count": 200,
                 "released_at": "2099-01-01", "batches": []}
        if cards is not None:
            snap_name = "scryfall_ts1_preview_20260901_1200.json"
            (self.review_dir / "data" / snap_name).write_text(
                json.dumps(cards, ensure_ascii=False), encoding="utf-8")
            state["batches"] = [{"ts": "2026-09-01T12:00:00+00:00",
                                 "snapshot": snap_name,
                                 "revealed": len(cards),
                                 "rated_scope": len(SPT.cards_for_rating(cards)),
                                 "added": [c["name"] for c in cards],
                                 "changed": [], "removed": []}]
        SPT.save_state(self.review_dir, state)
        return self.review_dir

    def ns(self, **kw):
        base = dict(set="TS1", dir=str(self.review_dir), no_cache=True,
                    community=None, batch=25, llm_config="dummy.json",
                    date="20260901")
        base.update(kw)
        return Namespace(**base)

    def run_fetch(self, cards):
        with mock.patch.object(SPT, "fetch_set_cards",
                               return_value=(cards, [])) as f:
            rc = SPT.cmd_fetch(self.ns())
        return rc, f

    def read_state(self):
        return json.loads((self.review_dir / "data" / "preview_state.json")
                          .read_text(encoding="utf-8"))


class TestFetchDiff(PreviewTestCase):
    def test_batch_classification_and_noop_fetch(self):
        self.make_review_dir()
        rc, _ = self.run_fetch(BATCH1)
        self.assertEqual(rc, 0)
        state = self.read_state()
        self.assertEqual(len(state["batches"]), 1)
        b1 = state["batches"][0]
        self.assertEqual(sorted(b1["added"]),
                         ["Alpha Beast", "Beta Trick", "Delta Wall"])
        self.assertEqual(b1["changed"], [])
        self.assertEqual(b1["removed"], [])
        self.assertEqual(b1["revealed"], 3)
        self.assertTrue((self.review_dir / "data" / b1["snapshot"]).is_file())

        # 无变化的重复 fetch：不追加批次、不写新快照
        snaps_before = list((self.review_dir / "data").glob("*.json"))
        rc, _ = self.run_fetch(BATCH1)
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.read_state()["batches"]), 1)
        self.assertEqual(list((self.review_dir / "data").glob("*.json")),
                         snaps_before)

        # 批次 2：新增 1 / 变更 1 / 移除 1
        rc, _ = self.run_fetch(BATCH2)
        self.assertEqual(rc, 0)
        state = self.read_state()
        self.assertEqual(len(state["batches"]), 2)
        b2 = state["batches"][1]
        self.assertEqual(b2["added"], ["Gamma Bomb"])
        self.assertEqual(b2["changed"], ["Alpha Beast"])
        self.assertEqual(b2["removed"], ["Delta Wall"])
        self.assertEqual(b2["revealed"], 3)

    def test_changed_detection_ignores_non_face_fields(self):
        # rarity / collector_number 变化不算 changed（只看牌面四字段）
        self.make_review_dir()
        self.run_fetch(BATCH1)
        tweaked = [dict(c, rarity="mythic") for c in BATCH1]
        rc, _ = self.run_fetch(tweaked)
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.read_state()["batches"]), 1)

    def test_changelog_appended_per_batch(self):
        self.make_review_dir()
        self.run_fetch(BATCH1)
        self.run_fetch(BATCH2)
        text = (self.review_dir / "06_ChangeLog.md").read_text(encoding="utf-8")
        rows = [ln for ln in text.splitlines()
                if ln.startswith("|") and "set_preview_tool fetch" in ln]
        self.assertEqual(len(rows), 2)
        self.assertIn("新增 3 张", rows[0])
        self.assertIn("新增 1 张", rows[1])
        self.assertIn("变更 1 张", rows[1])
        self.assertIn("移除 1 张", rows[1])
        self.assertIn("Alpha Beast", rows[1])

    def test_fetch_error_exit_codes(self):
        self.make_review_dir()
        # 真实零结果（与网络失败区分）→ 4
        with mock.patch.object(SPT, "fetch_set_cards", return_value=([], [])):
            self.assertEqual(SPT.cmd_fetch(self.ns()), 4)
        # 查询语法/系列未命中 → 2；分页不完整 → 3；网络失败 → 1
        for exc, code in [(mtg_tool.QuerySyntaxError("q"), 2),
                          (mtg_tool.PaginationIncomplete("p"), 3),
                          (mtg_tool.NetworkError("n"), 1)]:
            with mock.patch.object(SPT, "fetch_set_cards", side_effect=exc):
                self.assertEqual(SPT.cmd_fetch(self.ns()), code, exc)
        # 查询警告透传到 stderr，不影响退出码
        err = io.StringIO()
        with mock.patch.object(SPT, "fetch_set_cards",
                               return_value=(BATCH1, ["some warning"])):
            with redirect_stderr(err):
                self.assertEqual(SPT.cmd_fetch(self.ns()), 0)
        self.assertIn("some warning", err.getvalue())


class TestRatedScope(PreviewTestCase):
    MIXED = BATCH2 + [
        _card("Forest", 250, "o10", text="", cost="",
              type_line="Basic Land — Forest"),                    # 按名字排除
        _card("Generic Nonbasic", 189, "o11", text="Tap: add {C}.",
              type_line="Land"),                                   # >=189 地启发式
        _card("Goblin Token", 5, "o12", text="", cost="",
              type_line="Token Creature — Goblin", layout="token"),  # token 版式
    ]

    def test_exclusion_predicate(self):
        excl = {c["name"] for c in self.MIXED if SPT.is_excluded_from_rating(c)}
        self.assertEqual(excl, {"Forest", "Generic Nonbasic", "Goblin Token"})

    def test_rated_scope_counts_inventory_but_not_todo(self):
        self.make_review_dir()
        rc, _ = self.run_fetch(self.MIXED)
        self.assertEqual(rc, 0)
        batch = self.read_state()["batches"][0]
        self.assertEqual(batch["revealed"], 6)      # 库存计数含基本地/衍生物
        self.assertEqual(batch["rated_scope"], 3)   # 待评级张数不含
        cards = SPT.cards_for_rating(SPT.load_snapshot(
            self.review_dir / "data" / batch["snapshot"]))
        self.assertEqual(sorted(c["name"] for c in cards),
                         ["Alpha Beast", "Beta Trick", "Gamma Bomb"])


class TestRate(PreviewTestCase):
    def _seed_snapshot(self):
        # state 里登记 Alpha Beast 牌面变更 + 既有评分表
        self.make_review_dir()
        self.run_fetch(BATCH1)
        self.run_fetch(BATCH2)
        table = {"Alpha Beast": {"grade": "S", "note": "旧评"},
                 "Beta Trick": {"grade": "B", "note": "不动"},
                 "Ghost Card": {"grade": "C", "note": "不在快照"}}
        SPT.write_rating_table("TS1", table)

    def _fake_build(self, captured, new_grades=None):
        """模拟 build_card_table：把传入 cards 合入既有表并落盘（幂等）。"""
        def fake(set_code, cards, community, context, llm_cfg,
                 batch_size=25, refresh=False, progress=print):
            captured["cards"] = cards
            captured["context"] = context
            captured["existing_at_call"] = SPT.read_rating_table(set_code)
            table = dict(captured["existing_at_call"])
            for c in cards:
                grade = (new_grades or {}).get(c["name"], "B")
                table[c["name"]] = {"grade": grade,
                                    "note": "占位" if not grade else "ok",
                                    "rarity": c["rarity"]}
            SPT.write_rating_table(set_code, table)
            return table
        return fake

    def _llm_ok(self):
        return mock.patch.object(SPT.AUTO, "load_llm_config",
                                 return_value={"api_key": "x", "base_url": "u",
                                               "model": "m"})

    def test_changed_entry_deleted_before_build_and_stamped(self):
        self._seed_snapshot()
        captured = {}
        with self._llm_ok(), \
                mock.patch.object(SPT.mtga_draft_tool, "build_card_table",
                                  side_effect=self._fake_build(captured)) as b:
            rc, placeholders = SPT.do_rate(self.ns())
        self.assertEqual(rc, 0)
        self.assertEqual(placeholders, [])
        # build 被调时，changed 的 Alpha Beast 已从表中删除，未变更的保留
        at_call = captured["existing_at_call"]
        self.assertNotIn("Alpha Beast", at_call)
        self.assertEqual(at_call["Beta Trick"]["grade"], "B")
        self.assertIn("Ghost Card", at_call)
        # 待评清单排除基本地/衍生物（本快照无），context 取自 01_SetOverview.md
        self.assertEqual(sorted(c["name"] for c in captured["cards"]),
                         ["Alpha Beast", "Beta Trick", "Gamma Bomb"])
        self.assertIn("预览进度", captured["context"])
        # 全表条目加盖预览期戳
        final = SPT.read_rating_table("TS1")
        for entry in final.values():
            self.assertEqual(entry["confidence"], "C0")
            self.assertEqual(entry["source"], "preview")
        self.assertEqual(final["Alpha Beast"]["grade"], "B")  # 已重评

    def test_double_faced_changed_entry_deleted_by_front_face(self):
        self.make_review_dir()
        dfc = dict(BATCH1[0], name="Split Card // Back")
        self.run_fetch([dfc])
        changed = [dict(dfc, oracle_text="new text")]
        self.run_fetch(changed)
        SPT.write_rating_table("TS1", {"Split Card // Back": {"grade": "A"},
                                       "Split Card": {"grade": "C"}})
        captured = {}
        with self._llm_ok(), \
                mock.patch.object(SPT.mtga_draft_tool, "build_card_table",
                                  side_effect=self._fake_build(captured)):
            SPT.do_rate(self.ns())
        # 全名与正面名键都被视为 changed 而删除
        self.assertEqual(captured["existing_at_call"], {})

    def test_placeholder_entries_surfaced_as_todo(self):
        self._seed_snapshot()
        captured = {}
        out = io.StringIO()
        with self._llm_ok(), \
                mock.patch.object(SPT.mtga_draft_tool, "build_card_table",
                                  side_effect=self._fake_build(
                                      captured, {"Gamma Bomb": ""})):
            with redirect_stdout(out):
                rc, placeholders = SPT.do_rate(self.ns())
        self.assertEqual(rc, 3)                       # 部分完成退出码
        self.assertEqual(placeholders, ["Gamma Bomb"])
        self.assertIn("待补清单", out.getvalue())
        self.assertEqual(SPT.read_rating_table("TS1")["Gamma Bomb"]["grade"], "")

    def test_placeholder_dropped_and_retried(self):
        # 占位条目（grade ""）须在 build_card_table 调用前删除，否则被幂等
        # 合并永久跳过；本批无 changed 牌，只有占位一类删除
        self.make_review_dir()
        self.run_fetch(BATCH2)
        SPT.write_rating_table("TS1", {
            "Alpha Beast": {"grade": "S", "note": "已评"},
            "Beta Trick": {"grade": "", "note": "LLM 漏评，待补"}})
        captured = {}

        def fake_build(set_code, cards, community, context, llm_cfg,
                       batch_size=25, refresh=False, progress=print):
            captured["existing_at_call"] = SPT.read_rating_table(set_code)
            table = dict(captured["existing_at_call"])
            for c in cards:  # 幂等合并：只补缺失条目，不动已评
                table.setdefault(c["name"], {"grade": "B", "note": "补评",
                                             "rarity": c["rarity"]})
            SPT.write_rating_table(set_code, table)
            return table

        out = io.StringIO()
        with self._llm_ok(), \
                mock.patch.object(SPT.mtga_draft_tool, "build_card_table",
                                  side_effect=fake_build):
            with redirect_stdout(out):
                rc, placeholders = SPT.do_rate(self.ns())
        # (a) build 被调时占位键已删
        self.assertNotIn("Beta Trick", captured["existing_at_call"])
        # (b) 已评条目未动
        self.assertEqual(
            captured["existing_at_call"]["Alpha Beast"]["grade"], "S")
        # (c) 占位补上真实等级后：退出码 0，无待补清单
        self.assertEqual(rc, 0)
        self.assertEqual(placeholders, [])
        self.assertNotIn("待补清单", out.getvalue())
        self.assertIn("1 张占位，重试补评", out.getvalue())
        final = SPT.read_rating_table("TS1")
        self.assertEqual(final["Alpha Beast"]["grade"], "S")
        self.assertEqual(final["Beta Trick"]["grade"], "B")

    def test_released_set_stamped_c1_llm_review(self):
        # 已发售系列（released_at <= 今天）盖 C1/llm_review；setdefault 语义：
        # 既有戳（如早前预览期的 C0/preview）不覆盖
        self.make_review_dir()
        self.run_fetch(BATCH2)
        state = self.read_state()
        state["released_at"] = "2020-01-01"               # 已发售
        SPT.save_state(self.review_dir, state)
        SPT.write_rating_table("TS1", {
            "Ghost Card": {"grade": "C", "note": "不在快照的旧条目",
                           "confidence": "C0", "source": "preview"}})
        captured = {}
        with self._llm_ok(), \
                mock.patch.object(SPT.mtga_draft_tool, "build_card_table",
                                  side_effect=self._fake_build(captured)):
            rc, _ = SPT.do_rate(self.ns())
        self.assertEqual(rc, 0)
        final = SPT.read_rating_table("TS1")
        self.assertEqual(final["Beta Trick"]["confidence"], "C1")
        self.assertEqual(final["Beta Trick"]["source"], "llm_review")
        self.assertEqual(final["Ghost Card"]["confidence"], "C0")  # 旧戳保留
        self.assertEqual(final["Ghost Card"]["source"], "preview")

    def test_rate_without_llm_config_fails_loudly(self):
        self._seed_snapshot()
        err = io.StringIO()
        with mock.patch.object(SPT.AUTO, "load_llm_config",
                               side_effect=SPT.AUTO.AutoToolError(
                                   "LLM 配置不存在: dummy.json")), \
                mock.patch.object(SPT.mtga_draft_tool,
                                  "build_card_table") as b:
            with redirect_stderr(err):
                rc, _ = SPT.do_rate(self.ns())
        self.assertEqual(rc, 5)
        b.assert_not_called()                         # 绝不静默跳过
        self.assertIn("LLM", err.getvalue())
        # 评分表未被触碰
        self.assertEqual(SPT.read_rating_table("TS1")["Alpha Beast"]["grade"], "S")

    def test_rate_without_snapshot_is_usage_error(self):
        self.make_review_dir()                        # 无快照
        with self._llm_ok():
            rc, _ = SPT.do_rate(self.ns())
        self.assertEqual(rc, 2)


class TestReport(PreviewTestCase):
    HUMAN_PROSE = "## 结论摘要\n\n这段人工结论一个字都不能动。\n\n## 系列机制\n\n（待人工填写）"

    def _seed(self):
        self.make_review_dir()
        self.run_fetch(BATCH2)
        SPT.write_rating_table("TS1", {
            "Alpha Beast": {"grade": "B", "note": "合格", "confidence": "C0",
                            "source": "preview"}})

    def test_auto_block_replaced_human_prose_preserved(self):
        self._seed()
        ov = self.review_dir / "01_SetOverview.md"
        stale = ("# TS1 总览\n\n<!-- AUTO:BEGIN preview-progress -->\n"
                 "旧的自动内容\n<!-- AUTO:END preview-progress -->\n\n"
                 + self.HUMAN_PROSE + "\n")
        ov.write_text(stale, encoding="utf-8")
        self.assertEqual(SPT.cmd_report(self.ns()), 0)
        text = ov.read_text(encoding="utf-8")
        self.assertNotIn("旧的自动内容", text)
        self.assertIn("公开进度", text)
        # 标记块之外的内容逐字节保留
        head, rest = text.split("<!-- AUTO:BEGIN preview-progress -->")
        self.assertEqual(head, "# TS1 总览\n\n")
        tail = rest.split("<!-- AUTO:END preview-progress -->", 1)[1]
        self.assertEqual(tail, "\n\n" + self.HUMAN_PROSE + "\n")

    def test_auto_block_appended_when_markers_absent(self):
        self._seed()
        ov = self.review_dir / "01_SetOverview.md"
        ov.write_text("# TS1 总览\n\n" + self.HUMAN_PROSE + "\n", encoding="utf-8")
        self.assertEqual(SPT.cmd_report(self.ns()), 0)
        text = ov.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# TS1 总览\n\n" + self.HUMAN_PROSE))
        self.assertIn("<!-- AUTO:BEGIN preview-progress -->", text)
        self.assertIn("公开进度", text)
        # 幂等：再跑一次结构不变
        self.assertEqual(SPT.cmd_report(self.ns()), 0)
        self.assertEqual(ov.read_text(encoding="utf-8").count(
            "AUTO:BEGIN preview-progress"), 1)

    def test_card_ratings_skeleton(self):
        self._seed()
        self.assertEqual(SPT.cmd_report(self.ns()), 0)
        cr = (self.review_dir / "03_CardRatings.md").read_text(encoding="utf-8")
        self.assertIn("| 1 | Alpha Beast | common | B | C0 | 合格 |", cr)
        self.assertIn("| 3 | Gamma Bomb | rare | 未评级 | C0 |", cr)
        self.assertIn("预览期 C0 临时评级", cr)
        self.assertEqual(cr.count("AUTO:BEGIN card-ratings"), 1)


class TestInitAndDirResolution(PreviewTestCase):
    SEVEN = ["00_RunManifest.md", "01_SetOverview.md", "02_LimitedEnvironment.md",
             "03_CardRatings.md", "04_ConstructedWatchlist.md", "05_TestLog.md",
             "06_ChangeLog.md"]

    def test_init_scaffolds_seven_files_and_state(self):
        with mock.patch.object(SPT.mtg_tool, "scryfall_get",
                               return_value=SET_META) as g:
            rc = SPT.cmd_init(self.ns(dir=None))
        self.assertEqual(rc, 0)
        g.assert_called_once()
        for name in self.SEVEN:
            self.assertTrue((self.review_dir / name).is_file(), name)
        self.assertTrue((self.review_dir / "data").is_dir())
        manifest = (self.review_dir / "00_RunManifest.md").read_text(
            encoding="utf-8")
        self.assertIn("P 预览", manifest)
        self.assertIn("200", manifest)               # card_count
        self.assertIn("2099-01-01", manifest)        # released_at
        state = self.read_state()
        self.assertEqual(state["mode"], "P")
        self.assertEqual(state["card_count"], 200)
        self.assertEqual(state["batches"], [])

    def test_init_refuses_overwrite(self):
        with mock.patch.object(SPT.mtg_tool, "scryfall_get",
                               return_value=SET_META):
            self.assertEqual(SPT.cmd_init(self.ns(dir=None)), 0)
        marker = self.review_dir / "00_RunManifest.md"
        marker.write_text("人工改动", encoding="utf-8")
        with mock.patch.object(SPT.mtg_tool, "scryfall_get") as g:
            self.assertEqual(SPT.cmd_init(self.ns(dir=None)), 2)
        g.assert_not_called()                        # 撞目录即拒，不打网络
        self.assertEqual(marker.read_text(encoding="utf-8"), "人工改动")

    def test_init_scryfall_error_exit_codes(self):
        with mock.patch.object(SPT.mtg_tool, "scryfall_get",
                               side_effect=mtg_tool.QuerySyntaxError("404")):
            self.assertEqual(SPT.cmd_init(self.ns(dir=None)), 2)
        with mock.patch.object(SPT.mtg_tool, "scryfall_get",
                               side_effect=mtg_tool.NetworkError("boom")):
            self.assertEqual(SPT.cmd_init(self.ns(dir=None)), 1)

    def test_missing_dir_is_usage_error(self):
        # --dir 指向不存在目录
        self.assertEqual(SPT.cmd_status(self.ns(dir=str(self.tmp / "nope"))), 2)
        self.assertEqual(SPT.cmd_fetch(self.ns(dir=str(self.tmp / "nope"))), 2)
        with self._llm_ok_patch():
            self.assertEqual(SPT.do_rate(self.ns(dir=str(self.tmp / "nope")))[0], 2)
        self.assertEqual(SPT.cmd_report(self.ns(dir=str(self.tmp / "nope"))), 2)
        # 无 --dir 且 SetReview 下无匹配目录
        self.assertEqual(SPT.cmd_status(self.ns(dir=None)), 2)

    def _llm_ok_patch(self):
        return mock.patch.object(SPT.AUTO, "load_llm_config",
                                 return_value={"api_key": "x"})

    def test_auto_resolution_picks_latest_dir(self):
        old = SPT.SET_REVIEW_ROOT / "TS1_20260101"
        new = SPT.SET_REVIEW_ROOT / "TS1_20260901"
        old.mkdir()
        new.mkdir()
        self.assertEqual(SPT.resolve_review_dir("TS1"), new)
        self.assertEqual(SPT.resolve_review_dir("ts1"), old.parent / "TS1_20260901")
        with self.assertRaises(SPT.PreviewToolError):
            SPT.resolve_review_dir("NOPE")


class TestStatus(PreviewTestCase):
    def test_status_summary(self):
        self.make_review_dir()
        BATCH = TestRatedScope.MIXED
        self.run_fetch(BATCH)
        SPT.write_rating_table("TS1", {
            "Alpha Beast": {"grade": "B", "note": "ok"},
            "Beta Trick": {"grade": "", "note": "LLM 漏评，待补"}})
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(SPT.cmd_status(self.ns()), 0)
        text = out.getvalue()
        self.assertIn("6/200", text)                 # 公开进度含库存
        self.assertIn("待评级张数 3", text)
        self.assertIn("已评 1 / 占位 1 / 未评 1", text)
        self.assertIn("距发售日 2099-01-01", text)
        self.assertIn("门禁 G1", text)

    def test_status_without_manifest_gates_skips(self):
        (self.review_dir / "data").mkdir(parents=True)
        SPT.save_state(self.review_dir,
                       {"set": "TS1", "mode": "P", "batches": []})
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(SPT.cmd_status(self.ns()), 0)
        self.assertIn("跳过", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
