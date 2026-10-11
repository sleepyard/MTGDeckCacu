#!/usr/bin/env python3
"""mtga_log_tool.resolve_grp_meta 回归测试：客户端卡库兜底路径（网络全 mock）。"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mtga_db_tool as DBT  # noqa: E402
import mtga_log_tool as MLT  # noqa: E402
from mtg_tool import MtgToolError  # noqa: E402


class ResolveGrpMetaFallbackTest(unittest.TestCase):
    def setUp(self):
        self._saved = (MLT._grp_cache, MLT._CLIENT_DB_MEMO,
                       MLT._CLIENT_DB_PROBED, MLT._CLIENT_DB_PATH)
        MLT._grp_cache = {}
        MLT._CLIENT_DB_MEMO = {}
        MLT._CLIENT_DB_PROBED = False
        MLT._CLIENT_DB_PATH = None

    def tearDown(self):
        (MLT._grp_cache, MLT._CLIENT_DB_MEMO,
         MLT._CLIENT_DB_PROBED, MLT._CLIENT_DB_PATH) = self._saved

    def test_scryfall_404_falls_back_to_client_db(self):
        with mock.patch.object(MLT, "scryfall_get",
                               side_effect=MtgToolError("404")), \
                mock.patch.object(MLT, "save_grp_cache"), \
                mock.patch.object(MLT, "_client_db_lookup",
                                  return_value={"name": "Artifist Acumen",
                                                "type_line": "Artifact"}):
            meta = MLT.resolve_grp_meta("106303")
        self.assertEqual(meta["name"], "Artifist Acumen")
        self.assertEqual(MLT._grp_cache["106303"]["name"], "Artifist Acumen")

    def test_cached_none_name_retried_via_fallback(self):
        MLT._grp_cache["106272"] = {"name": None, "type_line": None}
        with mock.patch.object(MLT, "save_grp_cache"), \
                mock.patch.object(MLT, "_client_db_lookup",
                                  return_value={"name": "Undulating Witness",
                                                "type_line": "Creature"}) as fb:
            meta = MLT.resolve_grp_meta("106272")
        self.assertEqual(meta["name"], "Undulating Witness")
        self.assertEqual(MLT._grp_cache["106272"]["name"], "Undulating Witness")
        fb.assert_called_once()

    def test_cached_hit_with_name_skips_fallback(self):
        MLT._grp_cache["1"] = {"name": "Known Card", "type_line": "Land"}
        with mock.patch.object(MLT, "_client_db_lookup") as fb:
            meta = MLT.resolve_grp_meta("1")
        self.assertEqual(meta["name"], "Known Card")
        fb.assert_not_called()

    def test_fallback_unavailable_keeps_none(self):
        with mock.patch.object(MLT, "scryfall_get",
                               side_effect=MtgToolError("404")), \
                mock.patch.object(MLT, "save_grp_cache"), \
                mock.patch.object(MLT, "_client_db_lookup", return_value=None):
            meta = MLT.resolve_grp_meta("999999")
        self.assertIsNone(meta["name"])

    def test_client_db_lookup_uses_mtga_db_tool(self):
        with mock.patch.object(DBT, "find_database",
                               return_value=Path("x.mtga")), \
                mock.patch.object(DBT, "lookup_names",
                                  return_value={"106303": {"name": "Artifist Acumen"}}), \
                mock.patch.object(MLT, "scryfall_get",
                                  return_value={"type_line": "Artifact"}):
            meta = MLT._client_db_lookup("106303")
        self.assertEqual(meta, {"name": "Artifist Acumen",
                                "type_line": "Artifact"})

    def test_client_db_lookup_no_database_returns_none(self):
        with mock.patch.object(DBT, "find_database", return_value=None):
            self.assertIsNone(MLT._client_db_lookup("106303"))
        self.assertTrue(MLT._CLIENT_DB_PROBED)


if __name__ == "__main__":
    unittest.main()
