"""Frozen workbench evaluations, request gates and HTTP behavior, without HTTP data."""
import threading
import unittest
from unittest import mock

import deck_model
import deck_workbench as wb
import workbench_evaluation as W
from test_constructed_strategy import normal_pool
from test_deck_workbench import ServerFixture
from test_workbench_jobs import wait_job


CARDS = [{"name": "Green Spell", "type_line": "Creature", "mana_cost": "{G}{G}",
          "cmc": 2, "oracle_text": "Trample"}]
DECK = "Deck\n12 Forest\n8 Green Spell\n"


class RequestTests(unittest.TestCase):
    def test_defaults_and_commander_settings_are_explicit(self):
        fmt, options, cards, baseline = W.parse_request({"format": "commander"})
        self.assertEqual(fmt, "commander")
        self.assertTrue(options["on_draw"])
        self.assertEqual(options["free_mulligans"], 1)
        self.assertIsNone(cards)
        self.assertIsNone(baseline)
        self.assertFalse(W.parse_request({})[1]["on_draw"])

    def test_bad_or_unbounded_options_are_rejected(self):
        for body in ({"format": "alchemy"}, {"runs": 5001}, {"runs": True},
                     {"turns": 9}, {"on_draw": "false"}, {"keep_min": 6},
                     {"free_mulligans": 3}, {"targets": "Name"},
                     {"targets": [""]}, {"targets": ["Name"] * 13},
                     {"card": []}, {"cards": {}}, {"baseline_text": "unparsed"}):
            with self.subTest(body=body), self.assertRaises((ValueError, deck_model.DeckParseError)):
                W.parse_request(body)
        for record in ({"name": 2}, {"name": " "}, {"name": "A", "card_faces": ["bad"]}):
            with self.assertRaises(ValueError):
                W.parse_request({"cards": [record]})

    def test_snapshot_is_copied_and_missing_offline_names_are_fatal(self):
        source = [dict(CARDS[0])]
        cards = W.parse_request({"cards": source})[2]
        source[0]["mana_cost"] = "{U}"
        self.assertEqual(cards[0]["mana_cost"], "{G}{G}")
        deck = deck_model.parse_text(DECK)
        with self.assertRaisesRegex(ValueError, "Green Spell"):
            W.prepare_cards([deck], [])
        fetch = mock.Mock(side_effect=AssertionError("Basic lands need no HTTP"))
        self.assertEqual(W.prepare_cards([deck], cards, fetch), cards)
        fetch.assert_not_called()

    def test_fetch_must_be_exact_and_failure_keeps_the_name(self):
        deck = deck_model.parse_text(DECK)
        for answer in (None, dict(CARDS[0], name="Other Spell")):
            with self.assertRaisesRegex(ValueError, "Green Spell"):
                W.prepare_cards([deck], [], lambda name: answer)
        result = W.prepare_cards([deck], [], lambda name: CARDS[0])
        self.assertEqual(result, CARDS)


class EvaluationJobsTests(unittest.TestCase):
    def state(self):
        state = wb.WorkbenchState()
        state.import_text(DECK)
        return state

    def start(self, state, **options):
        body = dict(cards=CARDS, runs=50, targets=["Green Spell"])
        body.update(options)
        job = state.start_evaluation(body)
        return wait_job(state.jobs, job["job_id"])

    def test_offline_evaluation_does_not_modify_or_validate_deck(self):
        state = self.state()
        with mock.patch.object(wb, "default_fetch_card", side_effect=AssertionError("No network")):
            job = self.start(state)
        self.assertEqual(job["status"], "done", job)
        result = job["result"]
        self.assertFalse(result["stale"])
        self.assertEqual(result["counts"]["main"], 20)
        self.assertEqual(state.export_text(), wb.serialize_deck(deck_model.parse_text(DECK)))
        self.assertEqual(state.slot("evaluation")["result"], result)
        self.assertIsNone(state.slot("audit"))

    def test_comparison_uses_one_snapshot_and_preserves_current_deck(self):
        state = self.state()
        before = state.export_text()
        job = self.start(state, baseline_text="Deck\n8 Forest\n12 Green Spell")
        self.assertEqual(job["status"], "done", job)
        result = job["result"]
        self.assertEqual(result["before"]["counts"]["lands"], 8)
        self.assertEqual(result["after"]["counts"]["lands"], 12)
        self.assertEqual(result["before"]["settings"], result["after"]["settings"])
        self.assertEqual(result["before"]["card_snapshot_hash"], result["after"]["card_snapshot_hash"])
        self.assertEqual(len(result["deltas"]), 5)
        self.assertEqual(state.export_text(), before)

    def test_missing_offline_evidence_is_error_and_clears_old_result(self):
        state = self.state()
        self.assertEqual(self.start(state)["status"], "done")
        with mock.patch.object(wb, "default_fetch_card", side_effect=AssertionError("No network")):
            job = self.start(state, cards=[])
        self.assertEqual(job["status"], "error")
        self.assertIn("Green Spell", job["error"]["message"])
        self.assertIsNone(job["result"])
        self.assertIsNone(state.slot("evaluation"))

    def test_unsupported_source_stays_partial(self):
        state = wb.WorkbenchState()
        state.import_text("Deck\n8 Conditional Land\n12 Green Spell")
        land = {"name": "Conditional Land", "type_line": "Land",
                "oracle_text": "{T}: Add {G}. Spend this mana only to cast creature spells."}
        job = self.start(state, cards=CARDS + [land])
        self.assertEqual(job["status"], "done", job)
        self.assertEqual(job["result"]["status"], "partial")
        self.assertEqual(job["result"]["excluded_sources"][0]["name"], "Conditional Land")

    def test_running_input_is_frozen_and_changed_deck_never_caches_result(self):
        state = self.state()
        entered, release = threading.Event(), threading.Event()
        evaluate = wb.deck_evaluate.evaluate

        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise AssertionError("Test did not release worker")
            return evaluate(*args, **kwargs)

        with mock.patch.object(wb.deck_evaluate, "evaluate", side_effect=delayed):
            job = state.start_evaluation(dict(cards=CARDS, runs=50))
            try:
                self.assertTrue(entered.wait(2))
                same = state.start_evaluation(dict(cards=CARDS, runs=50))
                self.assertEqual(same["job_id"], job["job_id"])
                with self.assertRaises(ValueError):
                    state.start_evaluation(dict(cards=CARDS, runs=51))
                state.import_text("Deck\n20 Forest")
            finally:
                release.set()
            done = wait_job(state.jobs, job["job_id"])
        self.assertEqual(done["status"], "done", done)
        self.assertTrue(done["result"]["stale"])
        self.assertEqual(done["result"]["counts"]["lands"], 12)
        self.assertIsNone(state.slot("evaluation"))

    def test_subsequent_import_invalidates_completed_result(self):
        state = self.state()
        self.start(state)
        state.import_text("Deck\n20 Forest")
        self.assertIsNone(state.slot("evaluation"))

    def test_http_start_poll_and_reject_bad_parameters(self):
        with ServerFixture(self.state()) as fx:
            status, job = fx.post_obj("/api/evaluation/start", dict(cards=CARDS, runs=20))
            self.assertEqual(status, 202)
            result = wait_job(fx.state.jobs, job["job_id"])
            self.assertEqual(result["status"], "done", result)
            status, result = fx.get_json("/api/jobs/" + job["job_id"])
            self.assertEqual(status, 200)
            self.assertEqual(result["result"]["counts"]["lands"], 12)
            for body in ({"runs": 5001}, {"format": "alchemy"}):
                self.assertEqual(fx.post_obj("/api/evaluation/start", body)[0], 400)

    def test_http_fixed_seed_quantities_and_sections_survive(self):
        with ServerFixture() as fx:
            status, result = fx.post_obj("/api/seed-constructed", {
                "candidates": normal_pool(), "format": "pioneer", "platform": "arena",
                "seed_text": "Deck\n4 Seed Payoff\nSideboard\n2 Side Hate"})
            self.assertEqual(status, 200, result)
            deck = deck_model.parse_text(fx.state.export_text())
            self.assertEqual(sum(c.qty for c in deck.main if c.name == "Seed Payoff"), 4)
            self.assertEqual([(c.qty, c.name) for c in deck.sideboard], [(2, "Side Hate")])
            self.assertTrue(fx.state.slot("constructed")["result"]["selections"])
            with mock.patch.object(wb, "default_fetch_card", side_effect=AssertionError("Cached candidates")):
                job = fx.state.start_evaluation({"runs": 10})
                self.assertEqual(wait_job(fx.state.jobs, job["job_id"])["status"], "done")


if __name__ == "__main__":
    unittest.main()
