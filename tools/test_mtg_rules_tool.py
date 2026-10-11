#!/usr/bin/env python3
"""Offline regression coverage for rules sources, freshness and CLI failures."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mtg_rules_tool as rules
import mtg_tool

FIXTURE = Path(__file__).parent / "testdata" / "comprehensive_rules_sample.txt"
TEXT = FIXTURE.read_text(encoding="utf-8")
NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)
URL = "https://media.wizards.com/2024/downloads/MagicCompRules%2020240202.txt"
HTML = '<a href="{}">Comprehensive Rules</a>'.format(URL)
CARD = {"object": "card", "name": "Test Card", "id": "card-123", "oracle_id": "oracle-123"}
NOTE = {"published_at": "2024-02-02", "source": "wotc", "comment": "Synthetic ruling."}


class CacheTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.cache = Path(temporary.name)
        patcher = mock.patch.object(rules, "_now", return_value=NOW)
        self.clock = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(rules.runlog, "log_run")
        self.log = patcher.start()
        self.addCleanup(patcher.stop)

    def download(self):
        with mock.patch.object(mtg_tool, "http_get_text", side_effect=[(200, HTML), (200, TEXT)]):
            return rules.load_document(self.cache)

    def rulings(self, entries=None):
        page = {"object": "list", "has_more": False,
                "data": [NOTE] if entries is None else entries}
        with mock.patch.object(mtg_tool, "http_get_json", side_effect=[(200, CARD), (200, page)]):
            return rules.lookup_rulings("Test Card", self.cache)

    def cli(self, *argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = rules.main(list(argv) + ["--cache-dir", str(self.cache), "--json"])
        return code, json.loads(stdout.getvalue()), stderr.getvalue()


class TestParser(CacheTestCase):
    def test_body_glossary_and_effective_date(self):
        parsed = rules.parse_rules("\ufeff" + TEXT)
        self.assertEqual(parsed["effective_date"], "2024-02-02")
        self.assertEqual(set(parsed["sections"]), {"1", "6", "7"})
        self.assertEqual(parsed["sections"]["1"]["categories"], ["100"])
        self.assertEqual(parsed["rules"]["100.1a"]["parent"], "100.1")
        self.assertIn("ability", parsed["glossary"])
        self.assertIn("An ability on the stack", parsed["glossary"]["ability"]["text"])
        self.assertNotIn("synthetic fixture contributors.", parsed["glossary"])

    def test_format_quirks_and_wrapped_examples(self):
        parsed = rules.parse_rules(TEXT)
        self.assertEqual(parsed["rules"]["600.2"]["text"], "Missing-period rule text.")
        self.assertEqual(parsed["rules"]["600.3"]["text"], "No-space rule text.")
        self.assertEqual(parsed["rules"]["600.4a"]["text"], "Trailing-period subrule.")
        self.assertEqual(parsed["rules"]["100.1a"]["examples"],
                         ["First example, continued on the following line."])
        self.assertEqual(len(parsed["rules"]["100.2"]["examples"]), 2)

    def test_references_filter_nonexistent_numbers(self):
        parsed = rules.parse_rules(TEXT)
        self.assertEqual(parsed["rules"]["100.1"]["see_rules"], ["600.1"])
        self.assertEqual(parsed["rules"]["100.2"]["see_rules"], [])
        self.assertEqual(parsed["glossary"]["trample"]["see_rules"], ["702.19"])

    def test_malformed_sources_are_rejected(self):
        for text in ("<html>Unavailable</html>", TEXT[:TEXT.index("1. Game Concepts", 100)],
                     TEXT.replace("Glossary", "Missing"),
                     TEXT.replace("These rules are effective as of February 2, 2024.", "No date.")):
            with self.subTest(text=text[:40]), self.assertRaises(rules.RulesDataError):
                rules.parse_rules(text)

    def test_local_file_has_unknown_provenance_and_no_network(self):
        with mock.patch.object(mtg_tool, "http_get_text") as request:
            document = rules.load_document(self.cache, FIXTURE, offline=True)
        request.assert_not_called()
        self.assertEqual(document["source"], "local-cr-file")
        self.assertEqual(document["freshness"], "unknown")
        self.assertIsNone(document["source_url"])
        self.assertIsNone(document["fetched_at"])
        self.assertTrue(document["stale"])

    def test_queries_and_limit_report_full_count(self):
        document = rules.load_document(self.cache, FIXTURE)
        self.assertEqual(rules.query_rules(document, "rule", "100.1a")["matches"][0]["rule_number"], "100.1a")
        term = rules.query_rules(document, "term", "TRAMPLE")
        self.assertEqual(term["matches"][0]["term"], "Trample")
        self.assertEqual(term["referenced_rules"][0]["rule_number"], "702.19")
        result = rules.query_rules(document, "grep", "rule", limit=1)
        self.assertEqual(len(result["matches"]), 1)
        self.assertGreater(result["match_count"], 1)
        self.assertTrue(result["truncated"])
        self.assertEqual(rules.query_rules(document, "rule", "999.99z")["status"], "not_found")

    def test_section_includes_subrules(self):
        document = rules.load_document(self.cache, FIXTURE)
        result = rules.query_rules(document, "rule", "702.19", section=True)
        self.assertEqual([entry["rule_number"] for entry in result["matches"]],
                         ["702.19", "702.19a"])

    def test_invalid_regex_and_limits_are_errors(self):
        document = rules.load_document(self.cache, FIXTURE)
        with self.assertRaises(rules.RulesDataError):
            rules.query_rules(document, "grep", "[")
        with self.assertRaises(rules.RulesDataError):
            rules.query_rules(document, "grep", "rule", limit=0)
        with self.assertRaises(rules.RulesDataError):
            rules.query_rules(document, "term", " ")

    def test_content_changes_invalidate_parsed_cache(self):
        path = self.cache / "local.txt"
        path.write_text(TEXT, encoding="utf-8")
        rules.load_document(self.cache, path)
        path.write_text(TEXT.replace("First subrule.", "Changed subrule."), encoding="utf-8")
        document = rules.load_document(self.cache, path)
        self.assertEqual(document["parsed"]["rules"]["100.1a"]["text"], "Changed subrule.")

    def test_broken_parsed_cache_is_rebuilt(self):
        rules.load_document(self.cache, FIXTURE)
        path = next(self.cache.glob("parsed-*.json"))
        path.write_text("{", encoding="utf-8")
        document = rules.load_document(self.cache, FIXTURE)
        self.assertIn("100.1a", document["parsed"]["rules"])
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["parser_version"], rules.PARSER_VERSION)


class TestDownloads(CacheTestCase):
    def test_discovery_resolves_relative_links_and_picks_latest(self):
        html = ('<a href="/downloads/MagicCompRules%2020240202.txt">old</a>'
                '<a href="https://media.wizards.com/MagicCompRules_20261011.txt?x=1&amp;y=2">new</a>'
                '<a href="https://example.com/MagicCompRules%2020990101.txt">other</a>'
                '<a href="https://media.wizards.com/MagicCompRules%2020269999.txt">invalid</a>')
        self.assertEqual(rules.discover_rules_url(html),
                         "https://media.wizards.com/MagicCompRules_20261011.txt?x=1&y=2")
        self.assertEqual(rules.discover_rules_url('<a href="/MagicCompRules20240202.txt">CR</a>'),
                         "https://magic.wizards.com/MagicCompRules20240202.txt")

    def test_discovery_without_txt_is_error(self):
        with self.assertRaises(rules.RulesDataError):
            rules.discover_rules_url('<a href="rules.pdf">PDF</a>')

    def test_discovery_encodes_literal_spaces_without_double_encoding(self):
        for link in ("MagicCompRules 20260925.txt", "MagicCompRules%2020260925.txt"):
            with self.subTest(link=link):
                self.assertEqual(rules.discover_rules_url('<a href="https://media.wizards.com/2026/downloads/' + link + '">CR</a>'),
                                 "https://media.wizards.com/2026/downloads/MagicCompRules%2020260925.txt")

    def test_first_fetch_writes_verified_cache(self):
        document = self.download()
        self.assertEqual(document["source"], "wotc-comprehensive-rules")
        self.assertEqual(document["source_url"], URL)
        self.assertEqual(document["fetched_at"], NOW.isoformat())
        self.assertFalse(document["stale"])
        self.assertEqual(Path(document["rules_file"]).read_text(encoding="utf-8"), TEXT)

    def test_fresh_cache_does_not_request_network(self):
        self.download()
        with mock.patch.object(mtg_tool, "http_get_text") as request:
            self.assertFalse(rules.load_document(self.cache)["stale"])
        request.assert_not_called()

    def test_downloaded_bom_and_crlf_hash_survive_offline_read(self):
        windows_text = "\ufeff" + TEXT.replace("\n", "\r\n")
        with mock.patch.object(mtg_tool, "http_get_text", side_effect=[(200, HTML), (200, windows_text)]):
            fetched = rules.load_document(self.cache)
        offline = rules.load_document(self.cache, offline=True)
        self.assertEqual(offline["effective_date"], fetched["effective_date"])
        self.assertFalse(offline["stale"])
        self.assertEqual(offline["parsed"], fetched["parsed"])

    def test_expired_offline_cache_preserves_timestamps(self):
        self.download()
        self.clock.return_value = NOW + timedelta(days=2)
        with mock.patch.object(mtg_tool, "http_get_text") as request:
            document = rules.load_document(self.cache, offline=True)
        request.assert_not_called()
        self.assertTrue(document["stale"])
        self.assertEqual(document["freshness"], "stale")
        self.assertEqual(document["fetched_at"], NOW.isoformat())

    def test_expired_cache_refreshes_even_when_url_is_unchanged(self):
        self.download()
        self.clock.return_value = NOW + timedelta(days=2)
        with mock.patch.object(mtg_tool, "http_get_text", side_effect=[(200, HTML), (200, TEXT)]) as request:
            document = rules.load_document(self.cache)
        self.assertEqual(request.call_count, 2)
        self.assertFalse(document["stale"])
        self.assertNotEqual(document["fetched_at"], NOW.isoformat())

    def test_new_version_is_stored_beside_old_version(self):
        old = self.download()
        text = TEXT.replace("February 2, 2024", "October 11, 2026")
        with mock.patch.object(mtg_tool, "http_get_text", side_effect=[(200, HTML), (200, text)]):
            new = rules.load_document(self.cache, refresh=True)
        self.assertEqual(new["effective_date"], "2026-10-11")
        self.assertTrue(Path(old["rules_file"]).exists())
        self.assertNotEqual(old["rules_file"], new["rules_file"])

    def test_failed_refresh_is_explicit_even_for_previously_fresh_cache(self):
        self.download()
        with mock.patch.object(mtg_tool, "http_get_text", side_effect=mtg_tool.NetworkError("offline")):
            document = rules.load_document(self.cache, refresh=True)
        self.assertTrue(document["stale"])
        self.assertIn("refresh failed", document["warnings"][0])
        self.assertEqual(document["fetched_at"], NOW.isoformat())

    def test_failed_initial_fetch_has_no_fake_results(self):
        with mock.patch.object(mtg_tool, "http_get_text", side_effect=mtg_tool.NetworkError("offline")):
            with self.assertRaises(mtg_tool.NetworkError):
                rules.load_document(self.cache)
        self.assertFalse((self.cache / "current.json").exists())

    def test_failed_cr_refresh_stays_stale_until_successful_refresh(self):
        self.download()
        with mock.patch.object(mtg_tool, "http_get_text", side_effect=mtg_tool.NetworkError("down")):
            rules.load_document(self.cache, refresh=True)
        with mock.patch.object(mtg_tool, "http_get_text") as request:
            offline = rules.load_document(self.cache, offline=True)
        request.assert_not_called()
        self.assertTrue(offline["stale"])
        self.assertIn("down", offline["warnings"][0])
        with mock.patch.object(mtg_tool, "http_get_text", side_effect=[(200, HTML), (200, TEXT)]) as request:
            recovered = rules.load_document(self.cache)
        self.assertEqual(request.call_count, 2)
        self.assertFalse(recovered["stale"])
        self.assertEqual(recovered["warnings"], [])

    def test_refresh_cannot_downgrade_version(self):
        text = TEXT.replace("February 2, 2024", "October 11, 2026")
        with mock.patch.object(mtg_tool, "http_get_text", side_effect=[(200, HTML), (200, text)]):
            rules.load_document(self.cache)
        with mock.patch.object(mtg_tool, "http_get_text", side_effect=[(200, HTML), (200, TEXT)]):
            result = rules.load_document(self.cache, refresh=True)
        self.assertEqual(result["effective_date"], "2026-10-11")
        self.assertTrue(result["stale"])
        self.assertIn("older version", result["warnings"][0])

    def test_invalid_update_does_not_overwrite_valid_text_or_manifest(self):
        original = self.download()
        manifest = (self.cache / "current.json").read_bytes()
        with mock.patch.object(mtg_tool, "http_get_text", side_effect=[(200, HTML), (200, "<html>bad</html>")]):
            document = rules.load_document(self.cache, refresh=True)
        self.assertTrue(document["stale"])
        self.assertEqual(Path(original["rules_file"]).read_text(encoding="utf-8"), TEXT)
        cached = json.loads((self.cache / "current.json").read_text(encoding="utf-8"))
        original_manifest = json.loads(manifest)
        self.assertEqual(cached["sha256"], original_manifest["sha256"])
        self.assertEqual(cached["fetched_at"], original_manifest["fetched_at"])
        self.assertIn("refresh_error", cached)

    def test_modified_official_cache_cannot_claim_verified_provenance(self):
        document = self.download()
        Path(document["rules_file"]).write_text(TEXT + "\nchanged", encoding="utf-8")
        with self.assertRaises(rules.RulesDataError):
            rules.load_document(self.cache, offline=True)

    def test_offline_missing_and_incompatible_flags_never_request_network(self):
        with mock.patch.object(mtg_tool, "http_get_text") as request:
            for kwargs in ({"offline": True}, {"offline": True, "refresh": True},
                           {"rules_file": FIXTURE, "refresh": True}):
                with self.subTest(kwargs=kwargs), self.assertRaises(rules.RulesDataError):
                    rules.load_document(self.cache, **kwargs)
        request.assert_not_called()

    def test_http_error_is_not_parsed_as_rules(self):
        with mock.patch.object(mtg_tool, "http_get_text", return_value=(404, "missing")):
            with self.assertRaises(mtg_tool.HttpError):
                rules.load_document(self.cache)


class TestRulings(CacheTestCase):
    def test_notes_include_identity_source_and_freshness(self):
        result = self.rulings()
        self.assertEqual(result["oracle_id"], CARD["oracle_id"])
        self.assertEqual(result["source"], "scryfall-rulings")
        self.assertIsNone(result["effective_date"])
        self.assertEqual(result["rulings"], [NOTE])
        self.assertFalse(result["stale"])

    def test_successful_empty_notes_are_distinct_from_failure(self):
        result = self.rulings([])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["ruling_count"], 0)

    def test_case_insensitive_fresh_and_offline_cache_do_not_request(self):
        self.rulings()
        with mock.patch.object(mtg_tool, "http_get_json") as request:
            self.assertEqual(rules.lookup_rulings("TEST CARD", self.cache)["ruling_count"], 1)
            self.assertFalse(rules.lookup_rulings("Test Card", self.cache, offline=True)["stale"])
        request.assert_not_called()

    def test_expired_rulings_bypass_shared_permanent_http_cache(self):
        self.rulings()
        self.clock.return_value = NOW + timedelta(days=31)
        updated = dict(NOTE, comment="Updated ruling.")
        with mock.patch.object(mtg_tool, "http_get_json", side_effect=[
                (200, CARD), (200, {"object": "list", "has_more": False, "data": [updated]})]) as request:
            result = rules.lookup_rulings("Test Card", self.cache)
        self.assertTrue(all(call.kwargs["use_cache"] is False for call in request.call_args_list))
        self.assertEqual(result["rulings"][0]["comment"], "Updated ruling.")
        self.assertFalse(result["stale"])

    def test_failed_refresh_returns_old_notes_with_warning(self):
        self.rulings()
        with mock.patch.object(mtg_tool, "http_get_json", side_effect=mtg_tool.NetworkError("down")):
            result = rules.lookup_rulings("Test Card", self.cache, refresh=True)
        self.assertEqual(result["rulings"], [NOTE])
        self.assertTrue(result["stale"])
        self.assertIn("refresh failed", result["warnings"][0])

    def test_exact_card_mismatch_is_rejected(self):
        with mock.patch.object(mtg_tool, "http_get_json", return_value=(200, dict(CARD, name="Wrong Card"))):
            with self.assertRaises(mtg_tool.CardNotFound):
                rules.lookup_rulings("Test Card", self.cache)

    def test_failed_rulings_refresh_stays_stale_until_success(self):
        self.rulings()
        with mock.patch.object(mtg_tool, "http_get_json", side_effect=mtg_tool.NetworkError("down")):
            rules.lookup_rulings("Test Card", self.cache, refresh=True)
        with mock.patch.object(mtg_tool, "http_get_json") as request:
            result = rules.lookup_rulings("Test Card", self.cache, offline=True)
        request.assert_not_called()
        self.assertTrue(result["stale"])
        self.assertIn("down", result["warnings"][0])
        recovered = self.rulings()
        self.assertFalse(recovered["stale"])
        self.assertEqual(recovered["warnings"], [])

    def test_pagination_collects_all_notes(self):
        first = {"object": "list", "has_more": True, "data": [NOTE],
                 "next_page": mtg_tool.SCRYFALL_BASE + "/rulings?page=2"}
        second = {"object": "list", "has_more": False, "data": [dict(NOTE, comment="Second.")]}
        with mock.patch.object(mtg_tool, "http_get_json", side_effect=[(200, CARD), (200, first), (200, second)]):
            self.assertEqual(rules.lookup_rulings("Test Card", self.cache)["ruling_count"], 2)

    def test_incomplete_or_malformed_results_are_not_cached_as_empty(self):
        for page in ({"object": "list", "has_more": True, "data": []},
                     {"object": "list", "has_more": False, "data": "bad"},
                     {"object": "list", "has_more": False, "data": [{}]},
                     {"object": "list", "data": []}):
            with self.subTest(page=page):
                with mock.patch.object(mtg_tool, "http_get_json", side_effect=[(200, CARD), (200, page)]):
                    with self.assertRaises((mtg_tool.PaginationIncomplete, rules.RulesDataError)):
                        rules.lookup_rulings("Test Card", self.cache)
                self.assertFalse((self.cache / "rulings").exists())

    def test_offline_missing_cache_is_an_error(self):
        with mock.patch.object(mtg_tool, "http_get_json") as request:
            with self.assertRaises(mtg_tool.HttpError):
                rules.lookup_rulings("Test Card", self.cache, offline=True)
        request.assert_not_called()


class TestCli(CacheTestCase):
    def test_json_out_and_attestation(self):
        output = self.cache / "result.json"
        code, result, _ = self.cli("term", "trample", "--rules-file", str(FIXTURE), "--out", str(output))
        self.assertEqual(code, 0)
        self.assertEqual(result, json.loads(output.read_text(encoding="utf-8")))
        self.assertEqual(result["matches"][0]["term"], "Trample")
        self.log.assert_called_once()

    def test_rule_miss_has_business_exit_code(self):
        code, result, _ = self.cli("rule", "999.99z", "--rules-file", str(FIXTURE))
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["matches"], [])

    def test_bad_regex_has_error_envelope(self):
        code, result, _ = self.cli("grep", "[", "--rules-file", str(FIXTURE))
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "error")
        self.assertNotIn("matches", result)

    def test_network_error_has_error_envelope_and_overwrites_requested_out(self):
        output = self.cache / "result.json"
        output.write_text('{"status":"ok"}', encoding="utf-8")
        with mock.patch.object(mtg_tool, "http_get_text", side_effect=mtg_tool.NetworkError("down")):
            code, result, _ = self.cli("fetch", "--out", str(output))
        self.assertEqual(code, 1)
        self.assertEqual(result["error"]["type"], "NetworkError")
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["status"], "error")

    def test_card_not_found_has_distinct_exit_code(self):
        with mock.patch.object(mtg_tool, "http_get_json", return_value=(404, {"code": "not_found", "details": "missing"})):
            code, result, _ = self.cli("rulings", "Missing Card")
        self.assertEqual(code, 3)
        self.assertIn("error", result)
        self.assertEqual(result["status"], "not_found")

    def test_missing_file_has_data_error_exit_code(self):
        code, result, _ = self.cli("rule", "100", "--rules-file", str(self.cache / "missing.txt"))
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "error")


class TestSharedHttp(CacheTestCase):
    def setUp(self):
        super().setUp()
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
