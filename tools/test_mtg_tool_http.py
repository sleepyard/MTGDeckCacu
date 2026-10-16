#!/usr/bin/env python3
"""Regression coverage for the shared mtg_tool HTTP transport layer."""
import io
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mtg_tool

URL = "https://media.wizards.com/2024/downloads/MagicCompRules%2020240202.txt"
TEXT = (Path(__file__).parent / "testdata" / "comprehensive_rules_sample.txt"
        ).read_text(encoding="utf-8")


class TestSharedHttp(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.cache = Path(temporary.name)
        patcher = mock.patch.object(mtg_tool, "CACHE_DIR", str(self.cache))
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(mtg_tool, "_throttle")
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(mtg_tool.time, "sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)
        last = mtg_tool._last_request_at[0]
        self.addCleanup(mtg_tool._last_request_at.__setitem__, 0, last)

    def response(self, body, status=200):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status = status
        response.read.return_value = body.encode("utf-8")
        return response

    def test_text_transport_uses_requested_accept_and_user_agent(self):
        with mock.patch.object(mtg_tool.urllib.request, "urlopen", return_value=self.response(TEXT)) as request:
            self.assertEqual(mtg_tool.http_get_text(URL), (200, TEXT))
        headers = dict(request.call_args.args[0].header_items())
        self.assertEqual(headers["Accept"], "text/plain")
        self.assertEqual(headers["User-agent"], mtg_tool.USER_AGENT)

    def test_json_cache_and_accept_are_preserved(self):
        with mock.patch.object(mtg_tool.urllib.request, "urlopen", return_value=self.response('{"object":"card"}')) as request:
            first = mtg_tool.http_get_json("https://api.scryfall.com/example", "scryfall")
            second = mtg_tool.http_get_json("https://api.scryfall.com/example", "scryfall", offline=True)
        self.assertEqual(first, second)
        request.assert_called_once()
        self.assertEqual(dict(request.call_args.args[0].header_items())["Accept"], "application/json")

    def test_text_transport_honors_retry_after(self):
        error = urllib.error.HTTPError(URL, 429, "limited", {"Retry-After": "2"}, io.BytesIO(b"limited"))
        self.addCleanup(error.close)
        with mock.patch.object(mtg_tool.urllib.request, "urlopen", side_effect=[error, self.response(TEXT)]):
            self.assertEqual(mtg_tool.http_get_text(URL)[0], 200)
        self.sleep.assert_called_once_with(2.0)

    def test_exhausted_server_errors_do_not_populate_json_cache(self):
        errors = [urllib.error.HTTPError(URL, 503, "down", {}, io.BytesIO(b"down")) for _ in range(2)]
        for error in errors:
            self.addCleanup(error.close)
        with mock.patch.object(mtg_tool, "MAX_RETRIES", 1), mock.patch.object(
                mtg_tool.urllib.request, "urlopen", side_effect=errors):
            with self.assertRaises(mtg_tool.HttpError):
                mtg_tool.http_get_json(URL, "scryfall")
        self.assertFalse((self.cache / "scryfall").exists())

    def test_json_404_payload_remains_cacheable(self):
        error = urllib.error.HTTPError(URL, 404, "missing", {}, io.BytesIO(b'{"code":"not_found"}'))
        self.addCleanup(error.close)
        with mock.patch.object(mtg_tool.urllib.request, "urlopen", side_effect=error) as request:
            first = mtg_tool.http_get_json(URL, "scryfall")
            second = mtg_tool.http_get_json(URL, "scryfall", offline=True)
        request.assert_called_once()
        self.assertEqual(first, (404, {"code": "not_found"}))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
