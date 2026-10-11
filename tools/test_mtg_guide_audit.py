"""Deterministic guide evidence and arithmetic tests, with no external HTTP."""
import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck_model
import mtg_guide_audit as audit
import mtg_rules_tool as rules

ROOT = Path(__file__).parent / "testdata"
CLAIMS = json.loads((ROOT / "guide_claims_sample.json").read_text(encoding="utf-8"))
RULES = rules.parse_rules((ROOT / "comprehensive_rules_sample.txt").read_text(encoding="utf-8"))
DECK = deck_model.parse_text("Deck\n1 Alpha Engine\n2 Beta Trigger\nSideboard\n1 Gamma Land", strict=True)
TEXT = "Main deck: 3 cards\nAfter three cycles: 5 mana\n"


def evidence(name, **fields):
    card = {"name": name, "oracle_id": "oracle-" + name, "type_line": "Creature",
            "oracle_text": "Add mana equal to your Elves."}
    card.update(fields)
    return {"card": card, "stale": False, "source": "scryfall-oracle"}


def document(stale=False):
    return {"parsed": RULES, "stale": stale, "effective_date": "2024-02-02",
            "source_url": "https://magic.wizards.com/en/rules"}


class TestCase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(audit.facts, "card_facts", side_effect=lambda name, **kw: evidence(name))
        self.lookup = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(audit.runlog, "log_run")
        patcher.start()
        self.addCleanup(patcher.stop)


class TestArithmetic(TestCase):
    def test_first_break_even_cycle_can_grow_later(self):
        loop = audit.simulate_loop(CLAIMS["loops"][0])
        self.assertEqual([state["mana"] for state in loop["snapshots"]], [2, 3, 5])
        self.assertTrue(loop["completed"])
        self.assertFalse(loop["infinite_proven"])

    def test_payment_before_gain_cannot_borrow_future_mana(self):
        model = copy.deepcopy(CLAIMS["loops"][0])
        model["initial"]["mana"] = 1
        loop = audit.simulate_loop(model)
        self.assertFalse(loop["completed"])
        self.assertEqual(loop["deficits"], {"mana": 1})
        self.assertEqual(loop["events"], [])

    def test_finite_resource_is_consumed_across_cycles(self):
        model = {"initial": {"mana": 2, "cards": 2}, "iterations": 3,
                 "steps": [{"pay": {"cards": 1}, "gain": {"mana": 1}}]}
        loop = audit.simulate_loop(model)
        self.assertFalse(loop["completed"])
        self.assertEqual(loop["iterations_completed"], 2)
        self.assertEqual(loop["deficits"], {"cards": 1})

    def test_precondition_must_be_met_without_consuming_resource(self):
        model = {"initial": {"creatures": 2}, "steps": [{"require": {"creatures": 3}}]}
        self.assertFalse(audit.simulate_loop(model)["completed"])
        model["steps"][0]["require"]["creatures"] = 2
        self.assertEqual(audit.simulate_loop(model)["final"], {"creatures": 2})

    def test_unsafe_invalid_or_unbounded_expressions_are_rejected(self):
        for expression in ("__import__('os').system('echo unsafe')", "mana.real", "unknown + 1",
                           "2 ** 100", "1 / 2", "1 // 0", "mana - 100", True, 10 ** 13):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                audit.arithmetic(expression, {"mana": 2})

    def test_steps_cannot_introduce_undeclared_resources(self):
        with self.assertRaises(ValueError):
            audit.simulate_loop({"initial": {"mana": 1}, "steps": [{"gain": {"cards": 1}}]})


class TestClaims(TestCase):
    def test_fixture_checks_actual_deck_and_three_iterations(self):
        result = audit.audit(DECK, TEXT, CLAIMS)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["claim_count"], 2)
        self.assertEqual(result["coverage"], "registered-claims-only")
        self.assertTrue(result["semantic_review_required"])
        self.assertEqual(result["deck_counts"]["main"], 3)
        self.assertEqual(result["deck_counts"]["sideboard"], 1)

    def test_cross_section_disagreement_is_found_in_every_occurrence(self):
        result = audit.audit(DECK, TEXT + "Summary: Main deck: 4 cards\n", CLAIMS)
        kinds = {finding["kind"] for finding in result["findings"]}
        self.assertEqual(result["status"], "fail")
        self.assertIn("wrong_number", kinds)
        self.assertIn("inconsistent_repetition", kinds)
        wrong = next(item for item in result["findings"] if item["kind"] == "wrong_number")
        self.assertEqual(wrong["line"], 3)
        self.assertEqual(wrong["expected"], 3)

    def test_unmatched_text_is_not_a_pass(self):
        result = audit.audit(DECK, "No registered statements here.", CLAIMS)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(all(item["kind"] == "missing_text" for item in result["findings"]))

    def test_counts_sum_copies_and_keep_sections_separate(self):
        claims = {"version": 1, "counts": [{"id": "beta", "cards": ["Beta Trigger"],
                   "text_patterns": [r"Beta copies: (?P<value>\d+)"]}]}
        result = audit.audit(DECK, "Beta copies: 2", claims)
        self.assertEqual(result["checks"][0]["expected"], 2)
        self.lookup.assert_not_called()
        claims["counts"][0]["unique"] = True
        self.assertEqual(audit.audit(DECK, "Beta copies: 1", claims)["status"], "pass")

    def test_type_counts_use_front_face_unless_explicitly_any(self):
        deck = deck_model.parse_text("Deck\n1 Modal Card", strict=True)
        item = evidence("Modal Card", type_line="Creature // Land", card_faces=[
            {"type_line": "Creature"}, {"type_line": "Land"}])
        claims = {"version": 1, "counts": [{"id": "lands", "type_pattern": "Land",
                    "text_patterns": [r"Lands: (?P<value>\d+)"]}]}
        result = audit.audit(deck, "Lands: 0", claims, {"Modal Card": item})
        self.assertEqual(result["status"], "pass")
        claims["counts"][0]["face"] = "any"
        self.assertEqual(audit.audit(deck, "Lands: 1", claims, {"Modal Card": item})["status"], "pass")

    def test_stale_card_evidence_marks_result_incomplete(self):
        result = audit.audit(DECK, TEXT, CLAIMS, {"Alpha Engine": dict(evidence("Alpha Engine"), stale=True)})
        self.assertEqual(result["status"], "incomplete")

    def test_variable_cycle_yield_cannot_be_reported_as_constant(self):
        claims = copy.deepcopy(CLAIMS)
        claims["loops"][0]["metric"] = "per_cycle"
        result = audit.audit(DECK, TEXT, claims)
        self.assertIn("variable_cycle_yield", {item["kind"] for item in result["findings"]})

    def test_loop_oracle_quote_and_active_zone_are_checked(self):
        claims = copy.deepcopy(CLAIMS)
        claims["loops"][0]["steps"][0]["card"] = "Gamma Land"
        claims["loops"][0]["steps"][0]["oracle_quote"] = "Made-up ability."
        result = audit.audit(DECK, TEXT, claims)
        kinds = {item["kind"] for item in result["findings"]}
        self.assertIn("inactive_loop_component", kinds)
        self.assertIn("oracle_quote_mismatch", kinds)

    def test_rule_number_quote_and_guide_citation_are_checked(self):
        claims = {"version": 1, "rules": [{"id": "citation", "number": "100.1a", "quote": "First subrule."}]}
        self.assertEqual(audit.audit(DECK, "CR 100.1a: First subrule.", claims, rules_document=document())["status"], "pass")
        result = audit.audit(DECK, "CR 100.1a: Wrong text.", claims, rules_document=document())
        self.assertEqual(result["status"], "fail")
        claims["rules"][0]["quote"] = "Wrong text."
        self.assertIn("rule_quote_mismatch", {item["kind"] for item in audit.audit(DECK, "CR 100.1a: Wrong text.", claims, rules_document=document())["findings"]})

    def test_stale_rule_source_marks_citation_incomplete(self):
        claims = {"version": 1, "rules": [{"id": "citation", "number": "100.1a", "quote": "First subrule."}]}
        result = audit.audit(DECK, "CR 100.1a: First subrule.", claims, rules_document=document(True))
        self.assertEqual(result["status"], "incomplete")

    def test_duplicate_ids_unknown_groups_and_empty_claims_are_errors(self):
        for claims in ({"version": 1}, {"version": 1, "typo": []}, [],
                       {"version": 1, "counts": [CLAIMS["counts"][0], CLAIMS["counts"][0]]}):
            with self.subTest(claims=claims), self.assertRaises(ValueError):
                audit.audit(DECK, TEXT, claims)

    def test_unknown_claim_keys_are_structured_input_errors(self):
        cases = [
            ({"version": 1, "counts": [{"id": "c", "type_patern": "Land",
                                        "text_patterns": [r"Main deck: (?P<value>\d+) cards"]}]},
             "type_patern", "counts claim #1 (id 'c')"),
            ({"version": 1, "loops": [dict(copy.deepcopy(CLAIMS["loops"][0]), metricc="per_cycle")]},
             "metricc", "loops claim #1 (id 'synthetic-loop')"),
            ({"version": 1, "rules": [{"id": "citation", "number": "100.1a", "quote": "First subrule.",
                                       "sections": ["main"]}]},
             "sections", "rules claim #1 (id 'citation')"),
        ]
        for claims, key, label in cases:
            with self.subTest(key=key), self.assertRaises(ValueError) as caught:
                audit.audit(DECK, TEXT, claims)
            self.assertIn(key, str(caught.exception))
            self.assertIn(label, str(caught.exception))
        claims = copy.deepcopy(CLAIMS)
        claims["loops"][0]["steps"][0]["payy"] = {"mana": 1}
        with self.assertRaises(ValueError) as caught:
            audit.audit(DECK, TEXT, claims)
        self.assertIn("payy", str(caught.exception))
        self.assertIn("step 1 of loops claim #1", str(caught.exception))

    def test_invalid_regex_is_a_structured_value_error(self):
        claims = {"version": 1, "counts": [{"id": "typed", "type_pattern": "(unclosed",
                   "text_patterns": [r"Main deck: (?P<value>\d+) cards"]}]}
        with self.assertRaises(ValueError) as caught:
            audit.audit(DECK, TEXT, claims)
        self.assertIn("(unclosed", str(caught.exception))
        self.assertIn("typed", str(caught.exception))
        claims = {"version": 1, "counts": [{"id": "c", "text_patterns": ["(unclosed"]}]}
        with self.assertRaises(ValueError) as caught:
            audit.audit(DECK, TEXT, claims)
        self.assertIn("(unclosed", str(caught.exception))
        self.assertIn("'c'", str(caught.exception))

    def test_rule_citation_drift_across_sections_is_found(self):
        claims = {"version": 1, "rules": [{"id": "citation", "number": "100.1a", "quote": "First subrule."}]}
        text = "Body: CR 100.1a: First subrule.\nQuick ref: 100.1b — First subrule.\n"
        result = audit.audit(DECK, text, claims, rules_document=document())
        finding = next(item for item in result["findings"] if item["kind"] == "inconsistent_repetition")
        self.assertEqual(finding["citations"], ["100.1a", "100.1b"])
        self.assertEqual(finding["claim"], "citation")

    def test_rule_quote_drift_in_summary_is_found(self):
        claims = {"version": 1, "rules": [{"id": "citation", "number": "100.1a", "quote": "First subrule."}]}
        text = "Body: CR 100.1a: First subrule.\nSummary: 100.1a — First subrule, mostly.\n"
        result = audit.audit(DECK, text, claims, rules_document=document())
        finding = next(item for item in result["findings"] if item["kind"] == "inconsistent_repetition")
        self.assertEqual(finding["lines"], [2])

    def test_consistent_rule_repetition_and_cross_references_pass(self):
        claims = {"version": 1, "rules": [{"id": "citation", "number": "100.1a", "quote": "First subrule."}]}
        text = ("Body: CR 100.1a: First subrule.\nSummary: 100.1a — First subrule.\n"
                "Cross-reference: see rules 100.1 and 600.2.\n")
        result = audit.audit(DECK, text, claims, rules_document=document())
        self.assertEqual(result["status"], "pass")

    def test_rule_number_never_matches_a_longer_number(self):
        claims = {"version": 1, "rules": [{"id": "citation", "number": "600.1",
                                           "quote": "Casting a spell is defined here."}]}
        result = audit.audit(DECK, "Timing: see rule 600.10.", claims, rules_document=document())
        kinds = {item["kind"] for item in result["findings"]}
        self.assertIn("rule_citation_missing_from_guide", kinds)
        # A lowercase subrule cite still satisfies the parent number claim.
        ok = audit.audit(DECK, "Body: 600.1a — Casting a spell is defined here.",
                         claims, rules_document=document())
        self.assertEqual(ok["status"], "pass")


class TestCli(TestCase):
    def test_cli_failure_writes_fresh_report_and_passes_offline_flag(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            deck, guide, claims, report = [root / name for name in ("deck.txt", "guide.md", "claims.json", "report.json")]
            deck.write_text("Deck\n1 Alpha Engine\n2 Beta Trigger", encoding="utf-8")
            guide.write_text(TEXT.replace("3 cards", "4 cards"), encoding="utf-8")
            claims.write_text(json.dumps(CLAIMS), encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = audit.main([str(deck), str(guide), "--claims", str(claims), "--offline", "--json", "--out", str(report)])
            self.assertEqual(code, 4)
            result = json.loads(stdout.getvalue())
            self.assertEqual(result, json.loads(report.read_text(encoding="utf-8")))
            self.assertTrue(self.lookup.call_args.kwargs["offline"])

    def test_cli_invalid_regex_exits_2_without_traceback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            deck, guide, claims, report = [root / name for name in ("deck.txt", "guide.md", "claims.json", "report.json")]
            deck.write_text("Deck\n1 Alpha Engine\n2 Beta Trigger", encoding="utf-8")
            guide.write_text(TEXT, encoding="utf-8")
            claims.write_text(json.dumps({"version": 1, "counts": [{"id": "c", "text_patterns": ["(unclosed"]}]}),
                              encoding="utf-8")
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = audit.main([str(deck), str(guide), "--claims", str(claims), "--offline",
                                   "--json", "--out", str(report)])
            self.assertEqual(code, 2)
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["error"]["type"], "ValueError")
            self.assertIn("(unclosed", result["error"]["message"])
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertEqual(json.loads(report.read_text(encoding="utf-8")), result)


if __name__ == "__main__":
    unittest.main()
