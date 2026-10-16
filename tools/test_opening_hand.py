"""Mulligan rules invariants; no HTTP or external card data."""
import random
import unittest
from collections import Counter

from opening_hand import london_opening


class NoShuffle:
    def shuffle(self, cards):
        pass


class OpeningTests(unittest.TestCase):
    def test_retry_sees_seven_and_bottom_is_not_the_next_draw(self):
        seen = []
        def choose(hand, count, *args):
            seen.append((len(hand), count))
            return list(range(count))
        library = list(range(20))
        initial = Counter(library)
        hand, mulls, bottom = london_opening(
            library, NoShuffle(), lambda card: False, max_mulligans=2,
            choose_bottom=choose)
        self.assertEqual(seen, [(7, 0), (7, 1), (7, 2)])
        self.assertEqual((len(hand), mulls, len(bottom)), (5, 2, 2))
        self.assertEqual(library[:2], bottom)
        self.assertNotIn(library[-1], bottom)
        self.assertEqual(Counter(hand + library), initial)

    def test_default_policy_retains_two_lands_and_bottoms_expensive_spell(self):
        library = ['next', 'L', 'L', 'cheap', 'mid', 'expensive', 'other', 'bad']
        def cost(card):
            return {'expensive': 9, 'mid': 3}.get(card, 1)
        # Force exactly one retry, then apply the normal bottom policy.
        calls = []
        def land(card):
            calls.append(card)
            return card == 'L'
        from opening_hand import bottom_indices
        hand = ['L', 'cheap', 'L', 'mid', 'expensive', 'other', 'bad']
        indices = bottom_indices(hand, 1, land, cost)
        self.assertEqual([hand[i] for i in indices], ['expensive'])
        self.assertEqual(sum(card == 'L' for i, card in enumerate(hand) if i not in indices), 2)

    def test_free_mulligan_and_conservation(self):
        library = ['S'] * 30
        hand, mulls, bottom = london_opening(
            library, random.Random(4), lambda c: c == 'L',
            max_mulligans=1, free_mulligans=1)
        self.assertEqual((len(hand), mulls, bottom), (7, 1, []))
        self.assertEqual(len(hand) + len(library), 30)

    def test_invalid_bottom_policy_is_rejected(self):
        with self.assertRaises(ValueError):
            london_opening(['S'] * 20, NoShuffle(), lambda c: False,
                           choose_bottom=lambda *args: [0, 0])


if __name__ == '__main__':
    unittest.main()
