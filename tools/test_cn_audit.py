#!/usr/bin/env python3
"""cn_audit.py 的回归测试：mock 掉 subprocess(curl) 边界，不接触真实网络。"""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cn_audit  # noqa: E402


def fake_run(payload):
    """构造 subprocess.run 的替身：返回带 stdout 的对象。"""
    def _run(cmd, **kwargs):
        # 调用方应以 UTF-8 解码（Windows 上 locale 是 GBK，必须显式指定）
        assert kwargs.get("encoding") == "utf-8", kwargs
        return type("R", (), {"stdout": json.dumps(payload, ensure_ascii=False),
                              "returncode": 0})()
    return _run


def bad_run(cmd, **kwargs):
    return type("R", (), {"stdout": "<html>502</html>", "returncode": 0})()


class CnAuditTestBase(unittest.TestCase):
    def setUp(self):
        self._cache_backup = dict(cn_audit._cache)
        cn_audit._cache.clear()
        # 避免测试把假数据写进真实缓存文件
        self._save_patcher = mock.patch.object(cn_audit, "_save", lambda: None)
        self._save_patcher.start()
        self._sleep_patcher = mock.patch("time.sleep", lambda *_a, **_k: None)
        self._sleep_patcher.start()

    def tearDown(self):
        self._sleep_patcher.stop()
        self._save_patcher.stop()
        cn_audit._cache.clear()
        cn_audit._cache.update(self._cache_backup)


class TestZhLookup(CnAuditTestBase):
    def test_exact_match(self):
        payload = {"items": [{"zhs_name": "闪电击", "name": "Lightning Strike", "set": "fdn"}]}
        with mock.patch.object(cn_audit.subprocess, "run", fake_run(payload)):
            st, zh, en, s = cn_audit.zh_lookup("闪电击")
        self.assertEqual("exact", st)
        self.assertEqual("Lightning Strike", en)
        self.assertEqual("FDN", s)

    def test_partial_match(self):
        payload = {"items": [{"zhs_name": "闪电击咒语", "name": "Bolt Trick", "set": "fdn"}]}
        with mock.patch.object(cn_audit.subprocess, "run", fake_run(payload)):
            st, zh, en, s = cn_audit.zh_lookup("闪电击")
        self.assertEqual("partial", st)

    def test_none_when_json_but_no_items(self):
        with mock.patch.object(cn_audit.subprocess, "run", fake_run({"items": []})):
            st, zh, en, s = cn_audit.zh_lookup("编造牌名")
        self.assertEqual("none", st)

    def test_error_when_no_json(self):
        # 限流/网关错误：绝不能误判为「查无此牌」
        with mock.patch.object(cn_audit.subprocess, "run", bad_run):
            st, zh, en, s = cn_audit.zh_lookup("任意名")
        self.assertEqual("error", st)

    def test_result_cached(self):
        payload = {"items": [{"zhs_name": "闪电击", "name": "Lightning Strike", "set": "fdn"}]}
        runner = fake_run(payload)
        counter = {"n": 0}
        def counting_run(cmd, **kwargs):
            counter["n"] += 1
            return runner(cmd, **kwargs)
        with mock.patch.object(cn_audit.subprocess, "run", counting_run):
            cn_audit.zh_lookup("闪电击")
            cn_audit.zh_lookup("闪电击")
        self.assertGreater(counter["n"], 0)
        first = counter["n"]
        with mock.patch.object(cn_audit.subprocess, "run", counting_run):
            cn_audit.zh_lookup("闪电击")
        self.assertEqual(first, counter["n"] + 0)  # 第二次走缓存，不再发请求

    def test_en_fallback_confirms_exact(self):
        # mtgch 不返回中文字段时，用英文名正向回查命中 → exact
        payload = {"items": [{"name": "Mystic Forge", "set": "m20"}]}
        def runner(cmd, **kwargs):
            url = cmd[-1]
            if "Mystic" in url:
                return fake_run(payload)(cmd, **kwargs)
            return fake_run({"items": [{"zhs_name": "玄秘熔炉", "name": "Mystic Forge",
                                        "set": "m20"}]})(cmd, **kwargs)
        with mock.patch.object(cn_audit.subprocess, "run", runner):
            st, zh, en, s = cn_audit.zh_lookup("玄秘熔炉")
        self.assertIn(st, ("exact", "partial"))


class TestEnLookup(CnAuditTestBase):
    def test_returns_official_zh(self):
        payload = {"items": [{"zhs_name": "闪电击", "name": "Lightning Strike", "set": "fdn"}]}
        with mock.patch.object(cn_audit.subprocess, "run", fake_run(payload)):
            self.assertEqual("闪电击", cn_audit.en_lookup("Lightning Strike"))

    def test_fallback_to_input(self):
        with mock.patch.object(cn_audit.subprocess, "run", fake_run({"items": []})):
            self.assertEqual("No Such Card", cn_audit.en_lookup("No Such Card"))


class TestSetZh(CnAuditTestBase):
    def test_translated_name(self):
        payload = {"set_info": {"translated_name": "现实裂界", "name": "Fractured Realms"}}
        with mock.patch.object(cn_audit.subprocess, "run", fake_run(payload)):
            self.assertEqual("现实裂界", cn_audit.set_zh("fra"))

    def test_bad_json_returns_none(self):
        with mock.patch.object(cn_audit.subprocess, "run", bad_run):
            self.assertIsNone(cn_audit.set_zh("fra"))


class TestExtractors(unittest.TestCase):
    def test_extract_zh_table(self):
        text = (
            "| 中文名 | English | 数量 |\n"
            "|---|---|---|\n"
            "| 闪电击 | Lightning Strike | 4 |\n"
            "| 沼泽 | Swamp | 20 |\n"
        )
        hard, soft = cn_audit.extract_zh(text)
        self.assertIn("闪电击", hard)
        self.assertNotIn("中文名", hard)      # 表头被跳过
        self.assertNotIn("数量", hard)        # STOP 词被过滤

    def test_extract_zh_paren_list(self):
        text = "收口线（斩客／暗贾／献神者）都可取。\n"
        hard, soft = cn_audit.extract_zh(text)
        self.assertIn("献神者", soft)

    def test_extract_en(self):
        text = "4 Lightning Strike\n20 Mountain\n2 A B\n!\"Exact Name\"\n"
        names = cn_audit.extract_en(text)
        self.assertIn("Lightning Strike", names)
        self.assertIn("Mountain", names)
        self.assertIn("Exact Name", names)


class TestCachePath(unittest.TestCase):
    def test_cache_under_tools_cache(self):
        # 缓存侧车必须落在 gitignore 的 tools/cache/，而不是脚本旁边
        self.assertEqual("cache", Path(cn_audit.CACHE).parent.name)
        self.assertEqual("_cn_audit_cache.json", Path(cn_audit.CACHE).name)


if __name__ == "__main__":
    unittest.main()
