"""Behavioral coverage for offline consistency evaluation and evidence."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import deck_evaluate as E
import deck_model


SPELLS = [
    {"name": "Green Spell", "mana_cost": "{G}{G}", "cmc": 2,
     "type_line": "Creature", "oracle_text": "Trample"},
    {"name": "Blue Spell", "mana_cost": "{U}", "cmc": 1,
     "type_line": "Instant", "oracle_text": "Draw a card."},
]


class PaymentTests(unittest.TestCase):
    def test_dual_is_one_source_not_two(self):
        cost = E.cost_routes("{G}{U}")
        self.assertFalse(E.can_pay(("GU",), cost, 2))
        self.assertTrue(E.can_pay(("GU", "G"), cost, 2))
        self.assertFalse(E.can_pay(("G", "G"), cost, 2))

    def test_hybrid_colorless_and_generic_use_distinct_sources(self):
        self.assertTrue(E.can_pay(("G", "C"), E.cost_routes("{1}{G/U}"), 2))
        self.assertTrue(E.can_pay(("W",), E.cost_routes("{2/W}"), 1))
        self.assertTrue(E.can_pay(("G", "G"), E.cost_routes("{2/W}"), 2))
        self.assertFalse(E.can_pay(("U",), E.cost_routes("{C}"), 1))
        self.assertFalse(E.can_pay(("G", "G", "G"), E.cost_routes("{2}{G}"), 2))

    def test_unsupported_costs_are_not_zero_cost(self):
        for cost in ("{X}{G}", "{S}", "{U/P}", "", "G"):
            with self.assertRaises(ValueError):
                E.cost_routes(cost)

    def test_conditional_dynamic_and_modal_sources_are_explicit(self):
        examples = [
            {"name": "Restricted", "oracle_text": "{T}: Add {G}. Spend this mana only to cast creature spells."},
            {"name": "Dynamic", "oracle_text": "{T}: Add {G} for each creature you control."},
            {"name": "Multi", "oracle_text": "{T}: Add {G}{G}."},
            {"name": "Pathway", "layout": "modal_dfc", "oracle_text": "{T}: Add {G}."},
        ]
        for card in examples:
            mana, error = E.land_source(card, set())
            self.assertFalse(mana)
            self.assertTrue(error)
        self.assertEqual(E.land_source({"name": "Dual", "oracle_text": "{T}: Add {G} or {U}."}, set()), ("UG", None))

    def test_unrelated_channel_discount_does_not_restrict_mana(self):
        card = {"name": "Channel Land", "oracle_text": "{T}: Add {R}.\nChannel - Discard this card: Do something. This costs less for each legend."}
        self.assertEqual(E.land_source(card, set()), ("R", None))
        rainbow = {"name": "Rainbow", "oracle_text": "{T}: Add one mana of any color."}
        self.assertEqual(E.land_source(rainbow, set()), ("WUBRG", None))

    def test_life_payments_are_ignored_but_other_costs_are_partial(self):
        card = {"name": "Life Land", "produced_mana": ["R", "C"],
                "oracle_text": "{T}: Add {C}.\n{T}, Pay 1 life: Add {R}."}
        self.assertEqual(E.land_source(card, set()), ("RC", None))
        card["oracle_text"] = "{T}: Add {C}.\n{T}, Sacrifice a creature: Add {R}."
        self.assertTrue(E.land_source(card, set())[1])


class EvaluationTests(unittest.TestCase):
    def deck(self):
        return deck_model.parse_text("Deck\n12 Forest\n4 Green Spell\n4 Blue Spell\n", strict=True)

    def test_reproducible_hash_independent_of_deck_line_order(self):
        a = E.evaluate(self.deck(), SPELLS, targets=["Green Spell"], runs=100, seed=7)
        b = E.evaluate(deck_model.parse_text("Deck\n4 Blue Spell\n4 Green Spell\n12 Forest\n"), SPELLS,
                       targets=["Green Spell"], runs=100, seed=7)
        self.assertEqual(a, b)
        self.assertEqual(a["counts"], {"main": 20, "lands": 12, "commander": 0, "sideboard": 0})

    def test_no_blue_sources_means_zero_blue_payment(self):
        result = E.evaluate(self.deck(), SPELLS, targets=["Blue Spell"], runs=100)
        self.assertEqual(result["status"], "complete")
        self.assertTrue(all(row["mana_potential"]["probability"] == 0
                            for row in result["goals"][0]["by_turn"]))

    def test_commander_is_accessible_but_not_shuffled_in(self):
        deck = deck_model.parse_text("Commander\n1 Green Spell\n\nDeck\n20 Forest\n")
        result = E.evaluate(deck, SPELLS, runs=10, max_mulligans=0)
        self.assertEqual(result["counts"]["main"], 20)
        row = result["goals"][0]["by_turn"][1]
        self.assertEqual(row["seen_and_mana"]["probability"], 1)
        self.assertEqual(row["mana_given_seen"]["samples"], 10)

    def test_sideboard_does_not_enter_draws(self):
        deck = deck_model.parse_text("Deck\n20 Forest\n\nSideboard\n4 Blue Spell\n")
        result = E.evaluate(deck, SPELLS, runs=10)
        self.assertEqual(result["counts"]["main"], 20)
        self.assertEqual(result["goals"], [])
        with self.assertRaises(ValueError):
            E.evaluate(deck, SPELLS, targets=["Blue Spell"], runs=10)

    def test_comparison_reports_deltas_and_rejects_unlike_settings(self):
        before = E.evaluate(self.deck(), SPELLS, targets=["Blue Spell"], runs=100)
        deck = deck_model.parse_text("Deck\n8 Forest\n4 Island\n4 Green Spell\n4 Blue Spell\n")
        after = E.evaluate(deck, SPELLS, targets=["Blue Spell"], runs=100)
        result = E.comparison(before, after)
        self.assertNotEqual(before["deck_hash"], after["deck_hash"])
        self.assertGreater(result["deltas"][-1]["mana_potential_delta"], 0)
        after["settings"]["seed"] += 1
        with self.assertRaises(ValueError):
            E.comparison(before, after)

    def test_missing_card_errors_and_unsupported_source_returns_partial(self):
        with self.assertRaises(ValueError):
            E.evaluate(self.deck(), [], runs=10)
        cards = SPELLS + [{"name": "Mystery Land", "type_line": "Land", "oracle_text": ""}]
        deck = deck_model.parse_text("Deck\n19 Mystery Land\n1 Green Spell\n")
        result = E.evaluate(deck, cards, runs=10)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["excluded_sources"][0]["count"], 19)

    def test_cli_writes_evidence_and_rejects_alchemy(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(E.runlog, "log_run"):
            root = Path(tmp)
            deck = root / "deck.txt"
            cards = root / "cards.json"
            output = root / "out.json"
            deck.write_text("Deck\n12 Forest\n4 Green Spell\n4 Blue Spell\n", encoding="utf-8")
            cards.write_text(json.dumps(SPELLS), encoding="utf-8")
            args = ["evaluate", str(deck), "--cards", str(cards), "--format", "standard",
                    "--runs", "50", "--target", "Green Spell", "--out", str(output)]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(E.main(args), 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["settings"]["runs"], 50)
            args[args.index("standard")] = "alchemy"
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                E.main(args)

    def test_cli_partial_is_not_success_exit(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(E.runlog, "log_run"):
            root = Path(tmp)
            deck, snapshot = root / 'deck.txt', root / 'cards.json'
            deck.write_text('Deck\n19 Mystery\n1 Green Spell\n', encoding='utf-8')
            snapshot.write_text(json.dumps(SPELLS + [{'name': 'Mystery', 'type_line': 'Land'}]), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                code = E.main(['evaluate', str(deck), '--cards', str(snapshot),
                               '--format', 'pioneer', '--runs', '10'])
            self.assertEqual(code, 3)


if __name__ == '__main__':
    unittest.main()
