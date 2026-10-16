"""Pure London mulligan policy shared by consistency and goldfish models.

Libraries use pop() for the top. Bottom cards are placed at index zero.
The default policy keeps a land count in range, then bottoms excess lands
or expensive spells. This is a declared heuristic, not Arena BO1 smoothing.
"""


def bottom_indices(hand, count, is_land, cost=lambda card: 0, keep_min=2,
                   keep_max=5):
    """Choose exactly count positions without discarding scarce land sources."""
    remaining = list(range(len(hand)))
    removed = []
    for _ in range(count):
        lands = [i for i in remaining if is_land(hand[i])]
        spells = [i for i in remaining if not is_land(hand[i])]
        # At small hand sizes leave room for spells while retaining scarce lands.
        land_target = min(keep_max, max(keep_min, 3), max(0, len(remaining) - 2))
        choices = lands if len(lands) > land_target else spells
        if not choices:
            choices = remaining
        index = max(choices, key=lambda i: (cost(hand[i]), i))
        remaining.remove(index)
        removed.append(index)
    return removed


def london_opening(library, rng, is_land, cost=lambda card: 0,
                   keep_min=2, keep_max=5, max_mulligans=2, free_mulligans=0,
                   choose_bottom=None):
    """Return (hand, mulligan_count, bottomed); mutate an already shuffled library.

    Every retry draws the starting hand size. Keep/bottom decisions are a
    land-count policy, independently replaceable through choose_bottom.
    """
    if (not 0 <= keep_min <= keep_max <= 7 or max_mulligans < 0
            or not 0 <= free_mulligans <= max_mulligans):
        raise ValueError("Invalid opening-hand policy")
    starting = min(7, len(library))
    if max(0, max_mulligans - free_mulligans) > starting:
        raise ValueError("Mulligans exceed starting hand size")
    hand = []
    for number in range(max_mulligans + 1):
        if hand:
            library.extend(hand)
            rng.shuffle(library)
        hand = [library.pop() for _ in range(starting)]
        count = max(0, number - free_mulligans)
        chooser = choose_bottom or bottom_indices
        indices = list(chooser(hand, count, is_land, cost, keep_min, keep_max))
        if (len(indices) != count or len(set(indices)) != count
                or any(type(i) is not int or not 0 <= i < len(hand) for i in indices)):
            raise ValueError("Bottom policy must select distinct hand positions")
        rejected = set(indices)
        kept = [card for i, card in enumerate(hand) if i not in rejected]
        land_count = sum(is_land(card) for card in kept)
        if keep_min <= land_count <= keep_max or number == max_mulligans:
            bottomed = [hand[i] for i in indices]
            library[:0] = bottomed
            return kept, number, bottomed
    raise RuntimeError("Opening-hand policy did not terminate")
