#!/usr/bin/env python3
"""mtga_log_tool.py inventory 子命令的回归测试。"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mtga_log_tool as MLT  # noqa: E402

TESTDATA = Path(__file__).resolve().parent / "testdata"
SAMPLE_LOG = TESTDATA / "mtga_inventory_sample.txt"
SUMMARY_ONLY_LOG = TESTDATA / "mtga_inventory_summary_only.txt"

# 1001/1002 是同一牌的两个不同 grpId（测同名合并）；4001 是双面牌（测取正面名）；
# 3001 只属于 ?=?Loc/ 预组（测排除）
FAKE_CARDS = {
    1001: "Llanowar Elves",
    1002: "Llanowar Elves",
    2001: "Forest",
    3001: "Colossal Dreadmaw",
    4001: "Growing Rites of Itlimoc // Itlimoc, Cradle of the Sun",
}


def fake_resolve(arena_id):
    return FAKE_CARDS.get(arena_id)


class TestInventoryCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.inv_json = Path(self.tmp.name) / "inventory.json"
        patcher = mock.patch.object(MLT, "INVENTORY_JSON", self.inv_json)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, argv, resolver=fake_resolve):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(MLT, "resolve_arena_card", side_effect=resolver), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = MLT.main(argv)
        return code, out.getvalue(), err.getvalue()

    def _load_snapshot(self):
        with open(self.inv_json, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def test_wildcards_and_merged_owned(self):
        code, out, _err = self._run(["inventory", "--log", str(SAMPLE_LOG)])
        self.assertEqual(code, 0)
        data = self._load_snapshot()
        self.assertEqual(data["wildcards"],
                         {"common": 12, "uncommon": 7, "rare": 3, "mythic": 2})
        self.assertEqual(data["economy"]["gold"], 12345)
        self.assertEqual(data["unknown_count"], 0)
        owned = data["owned"]
        # 两个不同 grpId 解析为同名，按牌名合并计数并记录套牌归属
        self.assertEqual(owned["Llanowar Elves"],
                         {"count": 6, "decks": ["Gruul Test Deck"]})
        self.assertEqual(owned["Forest"]["count"], 3)
        # 双面牌取正面名
        self.assertIn("Growing Rites of Itlimoc", owned)
        self.assertNotIn("Growing Rites of Itlimoc // Itlimoc, Cradle of the Sun", owned)
        # ?=?Loc/ 预组被排除
        self.assertNotIn("Colossal Dreadmaw", owned)
        self.assertEqual(data["source"], str(SAMPLE_LOG))
        # stdout Markdown 摘要：通配符表 + 牌种/张数 + 时效提示
        self.assertIn("| 秘稀 (Mythic) | 2 |", out)
        self.assertIn("3 种牌 / 10 张", out)
        self.assertIn("库存下界=已存套牌并集", out)

    def test_unknown_grpids_counted_and_warned(self):
        def resolver(arena_id):
            return None if arena_id == 2001 else fake_resolve(arena_id)

        code, _out, err = self._run(["inventory", "--log", str(SAMPLE_LOG)],
                                    resolver=resolver)
        self.assertEqual(code, 0)
        data = self._load_snapshot()
        self.assertEqual(data["unknown_count"], 1)  # 按未解析 grpId 条目计，与 quantity 无关
        self.assertNotIn("Forest", data["owned"])
        self.assertIn("未能解析", err)

    def test_empty_decks_refuse_overwrite_existing(self):
        good = {"snapshot_time": "earlier", "owned": {"Forest": {"count": 3, "decks": ["A"]}}}
        self.inv_json.write_text(json.dumps(good), encoding="utf-8")
        code, _out, err = self._run(["inventory", "--log", str(SUMMARY_ONLY_LOG)])
        self.assertEqual(code, 3)
        self.assertIn("拒绝覆写", err)
        self.assertEqual(self._load_snapshot(), good)  # 既有快照未被破坏

    def test_empty_decks_first_run_writes(self):
        code, out, _err = self._run(["inventory", "--log", str(SUMMARY_ONLY_LOG)])
        self.assertEqual(code, 0)
        data = self._load_snapshot()
        self.assertEqual(data["owned"], {})
        self.assertEqual(data["wildcards"]["common"], 5)
        self.assertIn("套牌数为 0", out)

    def test_no_starthook_exit_4(self):
        plain_log = Path(self.tmp.name) / "no_starthook.log"
        plain_log.write_text(
            "[UnityCrossThreadLogger]noise line\n"
            '{"someEvent": {"no": "inventory here"}}\n', encoding="utf-8")
        code, _out, err = self._run(["inventory", "--log", str(plain_log)])
        self.assertEqual(code, 4)
        self.assertIn("Detailed Logs", err)

    def test_missing_log_exit_2(self):
        code, _out, err = self._run(["inventory", "--log",
                                     str(Path(self.tmp.name) / "nope.log")])
        self.assertEqual(code, 2)
        self.assertIn("日志不存在", err)


if __name__ == "__main__":
    unittest.main()
