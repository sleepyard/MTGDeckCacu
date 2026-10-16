"""Directional synergy hints must connect actions to explicit payoffs."""
import unittest
import constructed_synergy as S


def card(name, types="Creature — Elf", text=""):
    return {"name": name, "type_line": types, "oracle_text": text}


class SynergyTests(unittest.TestCase):
    def test_same_type_alone_has_no_bonus(self):
        self.assertEqual(S.score_candidate(card("A"), [card("B")])["score"], 0)

    def test_tribal_payoff_and_actual_type_work_in_both_directions(self):
        elf, lord = card("Elf Body"), card("Lord", text="Other Elves you control get +1/+1.")
        for item, context in ((elf, [lord]), (lord, [elf])):
            result = S.score_candidate(item, context)
            self.assertGreater(result["score"], 0)
            self.assertEqual(result["evidence"][0]["signal"], "type:elf")
        self.assertEqual(S.score_candidate(card("Human", "Creature — Human"), [lord])["score"], 0)

    def test_resource_to_payoff_not_two_generic_producers(self):
        producer = card("Maker", text="Create two 1/1 creature tokens.")
        reward = card("Anthem", "Enchantment", "Tokens you control get +1/+1.")
        self.assertGreater(S.score_candidate(producer, [reward])["score"], 0)
        self.assertEqual(S.score_candidate(producer, [dict(producer, name="Other Maker")])["score"], 0)

    def test_opponent_mill_does_not_fill_own_graveyard(self):
        reward = card("Recur", "Sorcery", "Return target creature card from your graveyard to your hand.")
        enemy = card("Opponent Mill", "Sorcery", "Target opponent mills three cards.")
        own = card("Self Mill", "Sorcery", "Mill three cards.")
        self.assertEqual(S.score_candidate(enemy, [reward])["score"], 0)
        self.assertGreater(S.score_candidate(own, [reward])["score"], 0)

    def test_mutate_and_cast_payoff(self):
        mutate = card("Mutant", text="Mutate {2}{G}")
        payoff = card("Support", text="Whenever this creature mutates, draw a card.")
        self.assertGreater(S.score_candidate(mutate, [payoff])["score"], 0)
        self.assertEqual(S.score_candidate(mutate, [mutate])["score"], 0)

    def test_spell_payoffs_respect_spell_types(self):
        instant = card("Instant", "Instant")
        sorcery = card("Sorcery", "Sorcery")
        reward = card("Mage", text="Whenever you cast an instant spell, draw a card.")
        self.assertGreater(S.score_candidate(instant, [reward])["score"], 0)
        self.assertEqual(S.score_candidate(sorcery, [reward])["score"], 0)
        reward["oracle_text"] = "Whenever you cast an instant or sorcery spell, draw a card."
        self.assertGreater(S.score_candidate(sorcery, [reward])["score"], 0)
        reward["oracle_text"] = "Whenever you cast a noncreature spell, draw a card."
        self.assertGreater(S.score_candidate(instant, [reward])["score"], 0)
        self.assertEqual(S.score_candidate(card("Body"), [reward])["score"], 0)


if __name__ == "__main__":
    unittest.main()
