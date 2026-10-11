#!/usr/bin/env python3
"""mtga_db_tool.py 回归测试：sqlite3 合成 fixture DB，无网络无外部依赖。"""

import io
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mtga_db_tool as MDT  # noqa: E402


def _make_fixture_db(path):
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE Cards (grpId INTEGER, TitleId INTEGER, "
                 "ExpansionCode TEXT, CollectorNumber TEXT, Rarity TEXT)")
    conn.execute("CREATE TABLE Localizations_enUS (Id INTEGER, Text TEXT)")
    conn.executemany("INSERT INTO Cards VALUES (?, ?, ?, ?, ?)", [
        (70123, 1001, "TST", "001", "mythic"),
        (70456, 1002, "TST", "002", "common"),
    ])
    conn.executemany("INSERT INTO Localizations_enUS VALUES (?, ?)", [
        (1001, "Test Dragon"),
        (1002, "Test Goblin"),
    ])
    conn.commit()
    conn.close()


class MtgaDbToolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mtga_db_tool_test_"))
        self.db = self.tmp / "Raw_CardDatabase_test.mtga"
        _make_fixture_db(self.db)

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = MDT.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_list_tables(self):
        code, out, _ = self._run([str(self.db)])
        self.assertEqual(code, 0)
        self.assertIn("Cards", out)
        self.assertIn("Localizations_enUS", out)

    def test_lookup_hit(self):
        code, out, _ = self._run([str(self.db), "70123"])
        self.assertEqual(code, 0)
        self.assertIn("70123: Test Dragon [TST #001] rarity=mythic", out)

    def test_lookup_hit_second_row(self):
        code, out, _ = self._run([str(self.db), "70456"])
        self.assertEqual(code, 0)
        self.assertIn("70456: Test Goblin [TST #002] rarity=common", out)

    def test_lookup_not_found(self):
        code, out, _ = self._run([str(self.db), "999999"])
        self.assertEqual(code, 0)
        self.assertIn("999999: NOT FOUND", out)

    def test_missing_db_exit_2(self):
        code, _, err = self._run([str(self.tmp / "nope.mtga")])
        self.assertEqual(code, 2)
        self.assertIn("不存在", err)

    def test_lookup_names_batch(self):
        out = MDT.lookup_names(self.db, [70123, "70456", 999999])
        self.assertEqual(out["70123"]["name"], "Test Dragon")
        self.assertEqual(out["70123"]["set_code"], "TST")
        self.assertEqual(out["70456"]["name"], "Test Goblin")
        self.assertNotIn("999999", out)

    def test_find_database_env_override(self):
        with mock.patch.dict(os.environ,
                             {"MTGA_CARD_DATABASE": str(self.db)}):
            self.assertEqual(MDT.find_database(), self.db)

    def test_find_database_env_missing_file_ignored(self):
        with mock.patch.dict(os.environ,
                             {"MTGA_CARD_DATABASE": str(self.tmp / "nope.mtga")}):
            with mock.patch.object(MDT, "_steam_library_roots", return_value=[]):
                self.assertIsNone(MDT.find_database())

    def test_main_auto_uses_find_database(self):
        with mock.patch.object(MDT, "find_database", return_value=self.db):
            code, out, _ = self._run(["auto", "70123"])
        self.assertEqual(code, 0)
        self.assertIn("70123: Test Dragon", out)

    def test_main_auto_not_found_exit_2(self):
        with mock.patch.object(MDT, "find_database", return_value=None):
            code, _, err = self._run(["auto", "70123"])
        self.assertEqual(code, 2)
        self.assertIn("未找到", err)


if __name__ == "__main__":
    unittest.main()
