"""Spellbook regression tests; every network boundary is mocked."""
import contextlib
import copy
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
import deck_model
import mtg_card_facts as facts
import mtg_combo_tool as combos
import mtg_rules_tool as rules
import mtg_tool

PAGE = json.loads((Path(__file__).parent / "testdata" / "spellbook_combo_sample.json").read_text(encoding="utf-8"))
VARIANT = PAGE["results"]["almostIncluded"][0]
NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)


def card(name, **fields):
    result = {"name": name, "id": "printing-" + name, "oracle_id": "oracle-" + name,
              "object": "card", "type_line": "Creature", "oracle_text": "Synthetic card text.",
              "keywords": [], "games": ["arena", "paper"], "legalities": {"pioneer": "legal"}}
    result.update(fields)
    return result


def evidence(name, **fields):
    return {"card": card(name, **fields), "platform_available": True, "stale": False,
            "warnings": [], "fetched_at": NOW.isoformat(), "source_url": "https://api.scryfall.com/cards/synthetic"}


def deck(text):
    return deck_model.parse_text(text, strict=True)


def response(*variants):
    return {"variants": list(variants), "variant_count": len(variants), "stale": False,
            "warnings": [], "fetched_at": NOW.isoformat(), "source": "commander-spellbook"}


class TestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.cache = Path(temporary.name)
        patcher = mock.patch.object(combos, "CACHE_DIR", self.cache / "combos")
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(facts, "CACHE_DIR", self.cache / "cards")
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(rules, "_now", return_value=NOW)
        self.clock = patcher.start()
        self.addCleanup(patcher.stop)
        for module in (facts, combos):
            patcher = mock.patch.object(module, "_now", side_effect=lambda: self.clock())
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(combos.runlog, "log_run")
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(combos.time, "sleep")
        patcher.start()
        self.addCleanup(patcher.stop)
        previous = combos._last_request_at[0]
        self.addCleanup(combos._last_request_at.__setitem__, 0, previous)

    def analyze(self, text, variant=None, overrides=None, **kwargs):
        data = dict(overrides or {})
        def get(name, *args, **kw):
            return data.get(name, evidence(name))
        with mock.patch.object(facts, "card_facts", side_effect=get):
            return combos.analyze(deck(text), response(variant or copy.deepcopy(VARIANT)), "pioneer", **kwargs)


class TestAvailability(TestCase):
    def test_main_components_are_separate_from_sideboard(self):
        result = self.analyze("Deck\n1 Alpha Engine\n1 Beta Trigger\nSideboard\n1 Extra Card")
        self.assertEqual(len(result["main_available"]), 1)
        self.assertFalse(result["main_available"][0]["rules_verified"])
        self.assertIn("prerequisites", " ".join(result["main_available"][0].keys()))

    def test_sideboard_components_are_only_candidates_without_explicit_swap(self):
        result = self.analyze("Deck\n1 Alpha Engine\n1 Extra Card\nSideboard\n1 Beta Trigger")
        self.assertEqual(result["main_available"], [])
        self.assertEqual(result["postboard_available"], [])
        self.assertEqual(len(result["sideboard_candidates"]), 1)
        self.assertEqual(result["sideboard_candidates"][0]["main"]["missing_cards"], [{"name": "Beta Trigger", "quantity": 1}])

    def test_explicit_postboard_requires_conservation(self):
        source = "Deck\n1 Alpha Engine\n1 Extra Card\nSideboard\n1 Beta Trigger"
        after = deck("Deck\n1 Alpha Engine\n1 Beta Trigger\nSideboard\n1 Extra Card")
        result = self.analyze(source, postboard=after)
        self.assertEqual(len(result["postboard_available"]), 1)
        with self.assertRaises(ValueError):
            self.analyze(source, postboard=deck("Deck\n1 Alpha Engine\n1 Beta Trigger"))

    def test_companion_does_not_count_as_active_component(self):
        result = self.analyze("Deck\n1 Alpha Engine\nCompanion\n1 Beta Trigger")
        self.assertEqual(result["main_available"], [])
        self.assertEqual(len(result["missing_components"]), 1)

    def test_component_quantities_are_not_distinct_name_counts(self):
        variant = copy.deepcopy(VARIANT)
        variant["uses"][0]["quantity"] = 2
        result = self.analyze("Deck\n1 Alpha Engine\n1 Beta Trigger", variant)
        self.assertEqual(result["missing_components"][0]["combined"]["missing_cards"], [{"name": "Alpha Engine", "quantity": 1}])

    def test_duplicate_requirements_sum_quantities(self):
        variant = copy.deepcopy(VARIANT)
        variant["uses"].append(copy.deepcopy(variant["uses"][0]))
        result = self.analyze("Deck\n1 Alpha Engine\n1 Beta Trigger", variant)
        self.assertEqual(result["missing_components"][0]["main"]["missing_cards"][0]["quantity"], 1)

    def test_arena_alias_is_resolved_to_canonical_name(self):
        result = self.analyze("Deck\n1 Arena Alias\n1 Beta Trigger", overrides={"Arena Alias": evidence("Alpha Engine", flavor_name="Arena Alias")})
        self.assertEqual(len(result["main_available"]), 1)

    def test_must_be_commander_cannot_be_satisfied_by_mainboard(self):
        variant = copy.deepcopy(VARIANT)
        variant["uses"][0]["mustBeCommander"] = True
        result = self.analyze("Deck\n1 Alpha Engine\n1 Beta Trigger", variant)
        self.assertEqual(len(result["needs_verification"]), 1)
        result = self.analyze("Commander\n1 Alpha Engine\nDeck\n1 Beta Trigger", variant)
        self.assertEqual(len(result["main_available"]), 1)

    def test_template_quantity_and_overlap_are_checked(self):
        variant = copy.deepcopy(VARIANT)
        variant["requires"] = [{"template": {"name": "Persist creature", "scryfallQuery": "t:creature keyword:persist"}, "quantity": 2}]
        data = {name: evidence(name, keywords=["Persist"]) for name in ("Alpha Engine", "Persist Body")}
        result = self.analyze("Deck\n1 Alpha Engine\n1 Beta Trigger\n1 Persist Body", variant, data)
        self.assertEqual(result["missing_components"][0]["combined"]["unmet_template_quantity"], 1)
        result = self.analyze("Deck\n1 Alpha Engine\n1 Beta Trigger\n2 Persist Body", variant, data)
        self.assertEqual(len(result["main_available"]), 1)

    def test_unsupported_template_query_never_claims_assembled(self):
        variant = copy.deepcopy(VARIANT)
        variant["requires"] = [{"template": {"name": "Complex template", "scryfallQuery": "t:creature OR t:artifact"}, "quantity": 1}]
        result = self.analyze("Deck\n1 Alpha Engine\n1 Beta Trigger", variant)
        self.assertEqual(len(result["needs_verification"]), 1)
        self.assertEqual(result["main_available"], [])

    def test_illegal_or_stale_template_card_does_not_complete_combo(self):
        variant = copy.deepcopy(VARIANT)
        variant["requires"] = [{"template": {"name": "Creature", "scryfallQuery": "t:creature"}, "quantity": 1}]
        for item in (evidence("Template Body", legalities={"pioneer": "banned"}),
                     dict(evidence("Template Body"), stale=True)):
            with self.subTest(item=item):
                result = self.analyze("Deck\n1 Alpha Engine\n1 Beta Trigger\n1 Template Body", variant,
                                      overrides={"Template Body": item})
                self.assertEqual(result["main_available"], [])

    def test_generic_commander_requirement_is_not_mainboard_legend(self):
        variant = copy.deepcopy(VARIANT)
        variant["requires"] = [{"template": {"name": "Commander", "scryfallQuery": "t:creature"},
                                "quantity": 1, "mustBeCommander": True}]
        result = self.analyze("Deck\n1 Alpha Engine\n1 Beta Trigger\n1 Template Body", variant)
        self.assertEqual(len(result["missing_components"]), 1)
        result = self.analyze("Commander\n1 Template Body\nDeck\n1 Alpha Engine\n1 Beta Trigger", variant)
        self.assertEqual(len(result["main_available"]), 1)

    def test_restricted_multi_copy_component_is_excluded(self):
        variant = copy.deepcopy(VARIANT)
        variant["uses"][0]["quantity"] = 2
        result = self.analyze("Deck\n2 Alpha Engine\n1 Beta Trigger", variant,
                              overrides={"Alpha Engine": evidence("Alpha Engine", legalities={"pioneer": "restricted"})})
        self.assertEqual(len(result["excluded"]), 1)

    def test_commander_identity_excludes_outside_color_component(self):
        data = {"Leader": evidence("Leader", color_identity=["R"]),
                "Alpha Engine": evidence("Alpha Engine", color_identity=["B"])}
        with mock.patch.object(facts, "card_facts", side_effect=lambda name, *args, **kw: data.get(name, evidence(name))):
            result = combos.analyze(deck("Commander\n1 Leader\nDeck\n1 Alpha Engine\n1 Beta Trigger"),
                                    response(VARIANT), "commander")
        self.assertEqual(len(result["excluded"]), 1)

    def test_legality_and_platform_failures_are_excluded(self):
        for item in (evidence("Alpha Engine", legalities={"pioneer": "banned"}),
                     dict(evidence("Alpha Engine"), platform_available=False)):
            with self.subTest(item=item):
                result = self.analyze("Deck\n1 Alpha Engine\n1 Beta Trigger", overrides={"Alpha Engine": item})
                self.assertEqual(len(result["excluded"]), 1)

    def test_stale_legality_is_not_a_verified_main_combo(self):
        result = self.analyze("Deck\n1 Alpha Engine\n1 Beta Trigger", overrides={"Alpha Engine": dict(evidence("Alpha Engine"), stale=True)})
        self.assertEqual(len(result["needs_verification"]), 1)
        self.assertTrue(result["stale"])

    def test_example_without_steps_is_pending(self):
        variant = copy.deepcopy(VARIANT)
        variant["description"] = None
        result = self.analyze("Deck\n1 Alpha Engine\n1 Beta Trigger", variant)
        self.assertEqual(len(result["needs_verification"]), 1)

    def test_bad_component_shape_and_quantities_are_errors(self):
        for quantity in (0, -1, True, "1"):
            variant = copy.deepcopy(VARIANT)
            variant["uses"][0]["quantity"] = quantity
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                self.analyze("Deck\n1 Alpha Engine\n1 Beta Trigger", variant)

    def test_offline_uncached_component_degrades_only_that_combo(self):
        second = copy.deepcopy(VARIANT)
        second["id"], second["popularity"] = "second", 20
        second["uses"][0] = dict(second["uses"][0], card={"name": "Gamma Piece"})

        def get(name, *args, **kwargs):
            if name == "Gamma Piece":
                raise mtg_tool.HttpError("No card evidence cache in offline mode: " + name)
            return evidence(name)

        with mock.patch.object(facts, "card_facts", side_effect=get):
            result = combos.analyze(deck("Deck\n1 Alpha Engine\n1 Beta Trigger"),
                                    response(copy.deepcopy(VARIANT), second), "pioneer", offline=True)
        self.assertEqual(len(result["needs_verification"]), 1)
        self.assertEqual(result["needs_verification"][0]["id"], "second")
        self.assertIn("Gamma Piece", result["needs_verification"][0]["evidence_error"])
        self.assertEqual(len(result["main_available"]), 1)
        self.assertTrue(any("downgraded to needs_verification" in warning for warning in result["warnings"]))

    def test_unknown_component_card_degrades_to_needs_verification(self):
        def get(name, *args, **kwargs):
            if name == "Gamma Piece":
                raise mtg_tool.CardNotFound("Card not found: " + name)
            return evidence(name)

        variant = copy.deepcopy(VARIANT)
        variant["uses"][0] = dict(variant["uses"][0], card={"name": "Gamma Piece"})
        with mock.patch.object(facts, "card_facts", side_effect=get):
            result = combos.analyze(deck("Deck\n1 Alpha Engine\n1 Beta Trigger"),
                                    response(variant), "pioneer")
        self.assertEqual(len(result["needs_verification"]), 1)
        self.assertIn("not found", result["needs_verification"][0]["evidence_error"])
        self.assertEqual(result["main_available"], [])

    def test_online_channel_failure_still_aborts_the_query(self):
        def get(name, *args, **kwargs):
            if name == "Gamma Piece":
                raise mtg_tool.HttpError("Scryfall HTTP 503: /cards/named")
            return evidence(name)

        variant = copy.deepcopy(VARIANT)
        variant["uses"][0] = dict(variant["uses"][0], card={"name": "Gamma Piece"})
        with mock.patch.object(facts, "card_facts", side_effect=get):
            with self.assertRaises(mtg_tool.HttpError):
                combos.analyze(deck("Deck\n1 Alpha Engine\n1 Beta Trigger"), response(variant), "pioneer")

    def test_all_variants_degraded_warns_that_evidence_is_unavailable(self):
        def get(name, *args, **kwargs):
            raise mtg_tool.HttpError("No card evidence cache in offline mode: " + name)

        variant = copy.deepcopy(VARIANT)
        variant["uses"][0] = dict(variant["uses"][0], card={"name": "Gamma Piece"})
        deck_evidence = {name: evidence(name) for name in ("Alpha Engine", "Beta Trigger")}
        with mock.patch.object(facts, "card_facts", side_effect=get):
            result = combos.analyze(deck("Deck\n1 Alpha Engine\n1 Beta Trigger"),
                                    response(variant), "pioneer", offline=True,
                                    deck_evidence=deck_evidence)
        self.assertEqual(len(result["needs_verification"]), 1)
        self.assertTrue(any("nothing could be verified" in warning for warning in result["warnings"]))


class TestApiCache(TestCase):
    def fetch(self, page=None, **kwargs):
        with mock.patch.object(mtg_tool, "http_post_json", return_value=(200, PAGE if page is None else page)):
            return combos.fetch_variants("/find-my-combos", {"main": []}, **kwargs)

    def test_successful_cache_and_offline_zero_requests(self):
        self.assertEqual(self.fetch()["variant_count"], 1)
        with mock.patch.object(mtg_tool, "http_post_json") as request:
            result = combos.fetch_variants("/find-my-combos", {"main": []}, offline=True)
        request.assert_not_called()
        self.assertFalse(result["stale"])

    def test_empty_success_is_distinct_from_api_failure(self):
        page = copy.deepcopy(PAGE)
        page["count"] = 0
        page["results"]["almostIncluded"] = []
        self.assertEqual(self.fetch(page)["variants"], [])
        with mock.patch.object(mtg_tool, "http_post_json", side_effect=mtg_tool.NetworkError("down")):
            with self.assertRaises(mtg_tool.NetworkError):
                combos.fetch_variants("/find-my-combos", {"main": ["different"]})

    def test_live_nullable_count_is_explicit_and_all_next_pages_still_fetched(self):
        first, second = copy.deepcopy(PAGE), copy.deepcopy(PAGE)
        first["count"] = second["count"] = None
        first["next"] = combos.API + "/find-my-combos?offset=1000"
        second["results"]["almostIncluded"][0]["id"] = "second"
        with mock.patch.object(mtg_tool, "http_post_json", side_effect=[(200, first), (200, second)]):
            result = combos.fetch_variants("/find-my-combos", {"main": []})
        self.assertEqual(result["variant_count"], 2)
        self.assertIsNone(result["api_count"])
        self.assertTrue(result["pagination_complete"])

    def test_failed_refresh_retains_stale_state_and_recovers(self):
        self.fetch()
        with mock.patch.object(mtg_tool, "http_post_json", side_effect=mtg_tool.NetworkError("down")):
            result = combos.fetch_variants("/find-my-combos", {"main": []}, refresh=True)
        self.assertTrue(result["stale"])
        self.assertIn("down", result["warnings"][0])
        self.assertTrue(combos.fetch_variants("/find-my-combos", {"main": []}, offline=True)["stale"])
        self.assertFalse(self.fetch()["stale"])

    def test_multi_page_post_keeps_body(self):
        first, second = copy.deepcopy(PAGE), copy.deepcopy(PAGE)
        first["count"] = second["count"] = 2
        first["next"] = combos.API + "/find-my-combos?offset=1000"
        second["results"]["almostIncluded"][0]["id"] = "second"
        with mock.patch.object(mtg_tool, "http_post_json", side_effect=[(200, first), (200, second)]) as request:
            result = combos.fetch_variants("/find-my-combos", {"main": []})
        self.assertEqual(result["variant_count"], 2)
        self.assertEqual(request.call_args_list[0].args[1], request.call_args_list[1].args[1])

    def test_incomplete_groups_counts_and_next_urls_are_errors(self):
        broken = []
        page = copy.deepcopy(PAGE)
        del page["results"]["included"]
        broken.append(page)
        page = copy.deepcopy(PAGE)
        page["count"] = 2
        broken.append(page)
        page = copy.deepcopy(PAGE)
        page["next"] = "https://example.com/data"
        broken.append(page)
        for page in broken:
            with self.subTest(page=page), self.assertRaises((ValueError, mtg_tool.MtgToolError)):
                self.fetch(page)
        self.assertFalse((self.cache / "combos").exists())

    def test_queries_and_quantities_have_separate_cache_keys(self):
        self.fetch()
        with self.assertRaises(mtg_tool.HttpError):
            combos.fetch_variants("/find-my-combos", {"main": [{"card": "different", "quantity": 2}]}, offline=True)

    def test_broken_cache_cannot_claim_completed_pagination(self):
        self.fetch()
        path = next((self.cache / "combos").glob("*.json"))
        data = json.loads(path.read_text(encoding="utf-8"))
        data["pagination_complete"] = False
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(mtg_tool.HttpError):
            combos.fetch_variants("/find-my-combos", {"main": []}, offline=True)

    def test_expired_cache_is_marked_stale_offline(self):
        self.fetch()
        self.clock.return_value = NOW + timedelta(days=2)
        self.assertTrue(combos.fetch_variants("/find-my-combos", {"main": []}, offline=True)["stale"])

    def test_selection_prioritizes_included_before_popular_near_misses(self):
        a, b = dict(VARIANT, api_group="included", popularity=1), dict(VARIANT, id="b", api_group="almostIncluded", popularity=100)
        selected = combos._select(response(a, b), 1)
        self.assertEqual(selected["variants"][0]["id"], a["id"])
        self.assertEqual(selected["unexamined_variant_count"], 1)
        self.assertTrue(selected["truncated"])


class TestCardEvidence(TestCase):
    def test_alias_identity_and_platform_printing_fallback(self):
        primary = card("Alpha Engine", flavor_name="Arena Alias", games=["paper"])
        printing = card("Alpha Engine", games=["arena"])
        with mock.patch.object(mtg_tool, "http_get_json", side_effect=[(200, primary), (200, {"object": "list", "data": [printing]})]):
            result = facts.card_facts("Arena Alias", "arena")
        self.assertEqual(result["card"]["name"], "Alpha Engine")
        self.assertTrue(result["platform_available"])

    def test_exact_mismatch_does_not_accept_fuzzy_identity(self):
        with mock.patch.object(mtg_tool, "http_get_json", return_value=(200, card("Other Card"))):
            with self.assertRaises(mtg_tool.CardNotFound):
                facts.card_facts("Alpha Engine")

    def test_failed_refresh_does_not_turn_cached_legality_fresh(self):
        with mock.patch.object(mtg_tool, "http_get_json", return_value=(200, card("Alpha Engine"))):
            facts.card_facts("Alpha Engine")
        with mock.patch.object(mtg_tool, "http_get_json", side_effect=mtg_tool.NetworkError("down")):
            self.assertTrue(facts.card_facts("Alpha Engine", refresh=True)["stale"])
        with mock.patch.object(mtg_tool, "http_get_json") as request:
            result = facts.card_facts("Alpha Engine", offline=True)
        request.assert_not_called()
        self.assertTrue(result["stale"])


class TestSharedPost(TestCase):
    def test_post_is_json_and_uses_shared_transport_headers(self):
        raw = mock.MagicMock()
        raw.__enter__.return_value = raw
        raw.status = 200
        raw.read.return_value = b'{"count":0}'
        with mock.patch.object(mtg_tool, "_throttle"), mock.patch.object(mtg_tool.urllib.request, "urlopen", return_value=raw) as request:
            self.assertEqual(mtg_tool.http_post_json(combos.API + "/find-my-combos", {"main": []}), (200, {"count": 0}))
        sent = request.call_args.args[0]
        self.assertEqual(sent.get_method(), "POST")
        self.assertEqual(json.loads(sent.data), {"main": []})
        self.assertEqual(sent.get_header("Content-type"), "application/json")

    def test_read_only_post_retries_rate_limits_with_same_body(self):
        error = urllib.error.HTTPError(combos.API, 429, "limited", {"Retry-After": "2"}, io.BytesIO(b"limited"))
        self.addCleanup(error.close)
        raw = mock.MagicMock()
        raw.__enter__.return_value = raw
        raw.status = 200
        raw.read.return_value = b'{"count":0}'
        with mock.patch.object(mtg_tool, "_throttle"), mock.patch.object(mtg_tool.time, "sleep") as sleep, mock.patch.object(
                mtg_tool.urllib.request, "urlopen", side_effect=[error, raw]) as request:
            mtg_tool.http_post_json(combos.API + "/find-my-combos", {"main": []})
        sleep.assert_called_once_with(2.0)
        self.assertEqual(request.call_args_list[0].args[0].data, request.call_args_list[1].args[0].data)


class TestCli(TestCase):
    def test_network_failure_replaces_previous_success_output(self):
        source, output = self.cache / "deck.txt", self.cache / "out.json"
        source.write_text("Deck\n1 Alpha Engine", encoding="utf-8")
        output.write_text('{"status":"ok"}', encoding="utf-8")
        stream = io.StringIO()
        with mock.patch.object(combos, "search_deck", side_effect=mtg_tool.NetworkError("down")), contextlib.redirect_stdout(stream):
            code = combos.main(["search", str(source), "--format", "pioneer", "--json", "--out", str(output)])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["status"], "error")
        self.assertNotIn("main_available", json.loads(stream.getvalue()))

    def test_unknown_format_does_not_trigger_network(self):
        with mock.patch.object(combos, "discover") as request, contextlib.redirect_stdout(io.StringIO()):
            code = combos.main(["discover", "--card", "Alpha Engine", "--format", "unknown", "--json"])
        request.assert_not_called()
        self.assertEqual(code, 2)

    def test_text_output_reports_truncation_only_when_truncated(self):
        source = self.cache / "deck.txt"
        source.write_text("Deck\n1 Alpha Engine", encoding="utf-8")

        def run(truncated):
            payload = {"variant_count": 3, "stale": False, "truncated": truncated,
                       "analyzed_variant_count": 2, "unexamined_variant_count": 1,
                       "group_counts": {key: 0 for key in combos.OUTPUT_BUCKETS}, "warnings": []}
            payload.update({key: [] for key in combos.OUTPUT_BUCKETS})
            stream = io.StringIO()
            with mock.patch.object(combos, "search_deck", return_value=payload), contextlib.redirect_stdout(stream):
                code = combos.main(["search", str(source), "--format", "pioneer"])
            return code, stream.getvalue()

        code, output = run(True)
        self.assertEqual(code, 0)
        self.assertIn("1 unexamined (truncated)", output)
        code, output = run(False)
        self.assertEqual(code, 0)
        self.assertNotIn("truncated", output)


if __name__ == "__main__":
    unittest.main()
