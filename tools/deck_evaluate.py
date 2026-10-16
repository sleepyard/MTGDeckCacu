#!/usr/bin/env python3
"""Offline, reproducible deck consistency evaluation and version comparison.

Uses deck_model and a Scryfall/search JSON snapshot. Measures declared London
mulligans and static land-only payment potential, not combat or win rate.
"""
import argparse
import hashlib
import json
import math
import random
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

import deck_model
import opening_hand
import roles
import runlog

MODEL_VERSION = "land-potential-london-v1"
FORMATS = ("standard", "pioneer", "explorer", "historic", "timeless", "brawl",
           "standard_brawl", "competitive_brawl", "commander", "limited")
BASICS = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R",
          "Forest": "G", "Wastes": "C"}
COLORS = "WUBRGC"


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def front(card):
    faces = card.get("card_faces") or []
    return faces[0] if faces else card


def is_land(card):
    return "Land" in str(front(card).get("type_line") or card.get("type_line") or "").split(" // ")[0]


def card_index(cards):
    if not isinstance(cards, list) or any(not isinstance(c, dict)
            or not isinstance(c.get("name"), str) or not c["name"].strip()
            or not isinstance(c.get("card_faces", []), list)
            or any(not isinstance(face, dict) for face in c.get("card_faces", [])) for c in cards):
        raise ValueError("Card snapshot must be an array of named card objects")
    index = {}
    for card in cards:
        aliases = {card["name"], card["name"].split(" // ")[0]}
        # Only front names are aliases for importing/casting; back-only entries
        # must not silently become independently castable cards.
        for name in aliases:
            key = name.casefold()
            if key in index and index[key] != card:
                raise ValueError("Ambiguous snapshot card: " + name)
            index[key] = card
    return index


def resolve(name, index):
    if name.casefold() in index:
        return index[name.casefold()]
    if name in deck_model.BASIC_LANDS:
        base = name.replace("Snow-Covered ", "", 1)
        return {"name": name, "type_line": "Basic Land - " + base,
                "mana_cost": "", "cmc": 0,
                "oracle_text": "{T}: Add {" + BASICS[base] + "}.",
                "produced_mana": [BASICS[base]]}
    raise ValueError("Missing exact card in snapshot: " + name)


def cost_routes(cost):
    """Return alternative (generic, symbol-options) routes; unsupported is explicit."""
    if not isinstance(cost, str) or not cost:
        raise ValueError("Missing mana cost")
    tokens = re.findall(r"\{([^}]+)\}", cost)
    if not tokens or re.sub(r"\{[^}]+\}", "", cost).strip():
        raise ValueError("Malformed mana cost: " + cost)
    routes = [(0, ())]
    for token in tokens:
        if token.isdigit():
            routes = [(generic + int(token), symbols) for generic, symbols in routes]
        elif token in COLORS:
            routes = [(generic, symbols + (token,)) for generic, symbols in routes]
        elif re.fullmatch(r"[WUBRG]/[WUBRG]", token):
            options = token.replace("/", "")
            routes = [(generic, symbols + (options,)) for generic, symbols in routes]
        elif re.fullmatch(r"2/[WUBRG]", token):
            routes = [(generic + 2, symbols) for generic, symbols in routes] + [
                (generic, symbols + (token[-1],)) for generic, symbols in routes]
        else:
            raise ValueError("Unsupported cost symbol: " + token)
        if len(routes) > 64:
            raise ValueError("Too many alternative mana payments")
    return tuple((generic, tuple(sorted(symbols, key=lambda s: (len(s), s))))
                 for generic, symbols in routes)


def land_source(card, commander_colors):
    """Recognize one-mana land abilities only; entry/life timing is not simulated."""
    if card.get("layout") == "modal_dfc":
        return "", "modal land face choice is not modeled"
    text = str(front(card).get("oracle_text") or card.get("oracle_text") or "").split("\n//\n")[0]
    if card["name"] == "Command Tower" and commander_colors:
        return "".join(c for c in COLORS if c in commander_colors), None
    tap = r"\{T\}(?:, Pay \d+ life)?: Add ([^.]+)\."
    mana_lines = [line for line in text.splitlines() if re.search(tap, line)]
    if any(re.search(r"Spend this mana|Activate (?:this ability )?only|for each|an opponent|chosen color|\bif\b|\bunless\b|instead", line, re.I)
           for line in mana_lines):
        return "", "conditional, restricted or variable mana source"
    bodies = [body for line in mana_lines for body in re.findall(tap, line)]
    options = set()
    for body in bodies:
        if body == "one mana of any color":
            options.update("WUBRG")
            continue
        tokens = re.findall(r"\{([WUBRGC])\}", body)
        if re.sub(r"\{[WUBRGC]\}|\bor\b|[\s,]", "", body):
            return "", "mana ability needs state or an additional payment"
        if len(tokens) > 1 and "or" not in body:
            return "", "multiple mana per tap is not modeled"
        options.update(tokens)
    if not bodies:
        # Basic land type supplies the intrinsic ability even if Oracle omits it.
        types = str(front(card).get("type_line") or card.get("type_line") or "")
        if "Basic Land" in types:
            options.update(color for name, color in BASICS.items() if name in types)
    if not options:
        return "", "no supported one-mana tap ability"
    if not (set(card.get("produced_mana") or []) & set(COLORS)).issubset(options):
        return "", "additional mana choices require an unmodeled payment or condition"
    # Additional-cost abilities are intentionally not matched by the strict form.
    return "".join(c for c in COLORS if c in options), None


@lru_cache(maxsize=50000)
def can_pay(sources, routes, turn):
    """One land supplies one symbol; a dual cannot pay both sides at once."""
    for generic, symbols in routes:
        total = generic + len(symbols)
        if total > turn or len(sources) < total:
            continue
        if _match(sources, symbols):
            return True
    return False


def _match(sources, symbols):
    if not symbols:
        return True
    options = symbols[0]
    tried = set()
    for i, source in enumerate(sources):
        if source in tried or not set(source).intersection(options):
            continue
        tried.add(source)
        if _match(sources[:i] + sources[i + 1:], symbols[1:]):
            return True
    return False


def rate(success, total):
    if not total:
        return {"successes": success, "samples": total, "probability": None, "ci95": None}
    p = success / total
    z = 1.959963984540054
    divisor = 1 + z * z / total
    center = (p + z * z / (2 * total)) / divisor
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / divisor
    return {"successes": success, "samples": total, "probability": p,
            "ci95": [max(0.0, center - radius), min(1.0, center + radius)]}


def evaluate(deck, cards, targets=(), runs=10000, seed=20261016, turns=5,
             on_draw=False, max_mulligans=2, free_mulligans=0, keep_min=2, keep_max=5):
    if not 1 <= runs <= 50000 or not 1 <= turns <= 12:
        raise ValueError("Runs must be 1..50000 and turns 1..12")
    if any(type(qty) is not int or qty < 1 for qty, _, _ in deck.entries()):
        raise ValueError("Deck quantities must be positive integers")
    if not 7 <= sum(c.qty for c in deck.main) <= 250:
        raise ValueError("Evaluation requires a library of 7..250 cards")
    index = card_index(cards)
    resolved = {name: resolve(name, index) for _, name, _ in deck.entries()}
    main = Counter()
    for ref in deck.main:
        main[ref.name] += ref.qty
    commanders = {ref.name for ref in deck.commander}
    commander_colors = {color for name in commanders for color in resolved[name].get("color_identity", [])}
    land_names = {name for name in main if is_land(resolved[name])}
    sources, excluded = {}, []
    for name in sorted(land_names):
        sources[name], reason = land_source(resolved[name], commander_colors)
        if reason:
            excluded.append({"name": name, "count": main[name], "reason": reason})
    modal = [name for name in main if name not in land_names
             and resolved[name].get("layout") == "modal_dfc"
             and any("Land" in f.get("type_line", "") for f in resolved[name].get("card_faces", []))]
    ordered = sorted(main)
    library_template = [name for name in ordered for _ in range(main[name])]
    costs = {}
    curve = Counter()
    role_counts = Counter()
    for name in ordered:
        card = resolved[name]
        cost = str(front(card).get("mana_cost") or card.get("mana_cost") or "").split(" // ")[0]
        costs[name] = cost
        if name not in land_names:
            curve[str(card.get("cmc", 0))] += main[name]
            tags = roles.classify_card(card)
            for role in ("mana_development", "card_advantage", "removal", "protection", "threat"):
                if roles.has_root(tags, role):
                    role_counts[role] += main[name]
    if not targets:
        targets = sorted([n for n in main if n not in land_names],
                         key=lambda n: (-main[n], resolved[n].get("cmc", 0), n))[:5]
        targets = list(targets) + sorted(commanders)
    targets = list(dict.fromkeys(targets))
    if len(targets) > 12:
        raise ValueError("At most 12 target spells per run")
    goals = []
    for name in targets:
        if name not in main and name not in commanders:
            raise ValueError("Target must be in main or commander: " + name)
        if name in land_names:
            raise ValueError("Target must be a spell: " + name)
        card = resolved[name]
        cost = str(front(card).get("mana_cost") or card.get("mana_cost") or "").split(" // ")[0]
        try:
            routes, reason = cost_routes(cost), None
        except ValueError as exc:
            routes, reason = (), str(exc)
        goals.append({"name": name, "mana_cost": cost, "zone": "commander" if name in commanders else "main",
                      "routes": routes, "unsupported": reason})
    rng = random.Random(seed)
    opening_sizes, mull_counts = Counter(), Counter()
    counters = Counter()
    for _ in range(runs):
        library = list(library_template)
        rng.shuffle(library)
        hand, mulls, _bottom = opening_hand.london_opening(
            library, rng, lambda n: n in land_names,
            lambda n: float(resolved[n].get("cmc") or 0), keep_min, keep_max,
            max_mulligans, free_mulligans)
        opening_sizes[len(hand)] += 1
        mull_counts[mulls] += 1
        initial_lands = sum(n in land_names for n in hand)
        counters["keepable"] += keep_min <= initial_lands <= keep_max
        seen = set(hand)
        available = [sources[n] for n in hand if n in land_names and sources[n]]
        lands_seen = initial_lands
        for turn in range(1, turns + 1):
            if (turn > 1 or on_draw) and library:
                name = library.pop()
                seen.add(name)
                if name in land_names:
                    lands_seen += 1
                    if sources[name]:
                        available.append(sources[name])
            counters[(turn, "land_drop")] += lands_seen >= turn
            masks = tuple(sorted(available))
            for goal in goals:
                if not goal["routes"]:
                    continue
                name = goal["name"]
                drawn = goal["zone"] == "commander" or name in seen
                payable = can_pay(masks, goal["routes"], turn)
                counters[(turn, name, "seen")] += drawn
                counters[(turn, name, "mana")] += payable
                counters[(turn, name, "both")] += payable and drawn
    output_goals = []
    for goal in goals:
        output = {k: v for k, v in goal.items() if k != "routes"}
        output["by_turn"] = []
        if not goal["unsupported"]:
            for turn in range(1, turns + 1):
                both = counters[(turn, goal["name"], "both")]
                output["by_turn"].append({"turn": turn,
                    "mana_potential": rate(counters[(turn, goal["name"], "mana")], runs),
                    "seen_and_mana": rate(both, runs),
                    "mana_given_seen": rate(both, counters[(turn, goal["name"], "seen")])})
        output_goals.append(output)
    identity = {}
    for section in ("main", "sideboard", "commander", "companion"):
        quantities = Counter()
        for ref in getattr(deck, section):
            quantities[ref.name] += ref.qty
        identity[section] = sorted(quantities.items())
    partial = bool(excluded or modal or any(g["unsupported"] for g in goals))
    return {"status": "partial" if partial else "complete", "model_version": MODEL_VERSION,
            "scope": "London opening policy and static land-only payment potential; not legality, win rate or turn-by-turn casting",
            "deck_hash": digest(identity), "card_snapshot_hash": digest(cards),
            "settings": {"runs": runs, "seed": seed, "turns": turns, "on_draw": on_draw,
                         "max_mulligans": max_mulligans, "free_mulligans": free_mulligans,
                         "keep_min": keep_min, "keep_max": keep_max,
                         "bottom_policy": "retain up to three lands, then bottom high mana value spells"},
            "counts": {"main": sum(main.values()), "lands": sum(main[n] for n in land_names),
                       "commander": sum(c.qty for c in deck.commander),
                       "sideboard": sum(c.qty for c in deck.sideboard)},
            "curve": dict(sorted(curve.items())), "roles": dict(role_counts),
            "opening": {"keepable": rate(counters["keepable"], runs),
                        "hand_sizes": dict(sorted(opening_sizes.items())),
                        "mulligans": dict(sorted(mull_counts.items()))},
            "land_drop_potential": [{"turn": t, **rate(counters[(t, "land_drop")], runs)} for t in range(1, turns + 1)],
            "goals": output_goals, "excluded_sources": excluded, "unmodeled_modal_lands": modal,
            "limitations": ["Entry tapped, land sequencing/Pathway commitment and life payments are ignored.",
                            "One land drop per turn; no ramp, extra draws, spell effects, opponents or alternative casting costs.",
                            "Only explicitly recognized one-mana land tap abilities contribute; excluded sources remain unknown.",
                            "Ordinary shuffled libraries; Arena BO1 hand smoothing is not reproduced.",
                            "Wilson intervals measure Monte Carlo sampling error only, not model accuracy.",
                            "Main library only; sideboard changes must be supplied as a separate deck."]}


def comparison(before, after):
    """Descriptive deltas only; equal seeds do not make unlike decks paired trials."""
    if (before["settings"] != after["settings"] or before["model_version"] != after["model_version"]
            or before["card_snapshot_hash"] != after["card_snapshot_hash"]):
        raise ValueError("Compare requires the same model, settings and card snapshot")
    old = {g["name"]: g for g in before["goals"]}
    new = {g["name"]: g for g in after["goals"]}
    deltas = []
    for name in sorted(set(old) & set(new)):
        if old[name]["unsupported"] or new[name]["unsupported"]:
            continue
        for a, b in zip(old[name]["by_turn"], new[name]["by_turn"]):
            deltas.append({"name": name, "turn": a["turn"],
                           "mana_potential_delta": b["mana_potential"]["probability"] - a["mana_potential"]["probability"],
                           "seen_and_mana_delta": b["seen_and_mana"]["probability"] - a["seen_and_mana"]["probability"]})
    return {"status": "partial" if "partial" in (before["status"], after["status"]) else "complete",
            "before": before, "after": after, "deltas": deltas,
            "targets_only_before": sorted(set(old) - set(new)),
            "targets_only_after": sorted(set(new) - set(old)),
            "interpretation": "Descriptive differences under the same model/settings; not paired significance tests or a stronger-deck verdict."}


def render(result):
    if "before" in result:
        text = "# Deck comparison\n\n" + result["interpretation"] + "\n\n"
        if result["targets_only_before"] or result["targets_only_after"]:
            text += "Targets present in only one report: " + json.dumps({
                "before": result["targets_only_before"], "after": result["targets_only_after"]}) + "\n\n"
        text += "| Spell | Turn | Mana potential delta | Seen + mana delta |\n|---|---:|---:|---:|\n"
        text += "\n".join("| {name} | {turn} | {mana_potential_delta:+.1%} | {seen_and_mana_delta:+.1%} |".format(**r) for r in result["deltas"])
        return text + "\n\n" + render(result["before"]) + "\n" + render(result["after"])
    lines = ["# Deck consistency evaluation", "", "Status: " + result["status"],
             "Model: " + result["model_version"], "Deck SHA-256: " + result["deck_hash"],
             "", result["scope"], "", "Settings: " + json.dumps(result["settings"], sort_keys=True),
             "", "| Spell | Cost | Turn | Mana potential | Seen + mana |", "|---|---|---:|---:|---:|"]
    for goal in result["goals"]:
        if goal["unsupported"]:
            lines.append("| {} | {} | - | unknown: {} | - |".format(goal["name"], goal["mana_cost"], goal["unsupported"]))
        for row in goal["by_turn"]:
            lines.append("| {} | {} | {} | {:.1%} | {:.1%} |".format(goal["name"], goal["mana_cost"], row["turn"], row["mana_potential"]["probability"], row["seen_and_mana"]["probability"]))
    lines += ["", "Keepable after policy: {:.1%}".format(result["opening"]["keepable"]["probability"]), "", "Limits:", ""]
    lines += ["- " + line for line in result["limitations"]]
    lines += ["- Excluded source: " + item["name"] + ": " + item["reason"] for item in result["excluded_sources"]]
    lines += ["- Unmodeled modal land option: " + name for name in result["unmodeled_modal_lands"]]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("evaluate", "compare"):
        sub = commands.add_parser(name)
        sub.add_argument("deck", type=Path)
        if name == "compare":
            sub.add_argument("after", type=Path)
        sub.add_argument("--cards", required=True, type=Path, help="Offline Scryfall/search JSON array")
        sub.add_argument("--format", required=True, choices=FORMATS)
        sub.add_argument("--target", action="append", default=[], help="Exact deck entry name; repeat, max 12")
        sub.add_argument("--runs", type=int, default=10000)
        sub.add_argument("--seed", type=int, default=20261016)
        sub.add_argument("--turns", type=int, default=5)
        sub.add_argument("--on-draw", action="store_true")
        sub.add_argument("--max-mulligans", type=int, default=2)
        sub.add_argument("--free-mulligans", type=int, default=None)
        sub.add_argument("--keep-min", type=int, default=2)
        sub.add_argument("--keep-max", type=int, default=5)
        sub.add_argument("--out", type=Path, help="Write complete JSON evidence")
        sub.add_argument("--report", type=Path, help="Write Markdown report")
        sub.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        cards = json.loads(args.cards.read_text(encoding="utf-8-sig"))
        free = args.free_mulligans
        if free is None:
            free = 1 if args.format in ("brawl", "standard_brawl", "competitive_brawl", "commander") else 0
        options = dict(targets=args.target, runs=args.runs, seed=args.seed, turns=args.turns,
                       on_draw=args.on_draw, max_mulligans=args.max_mulligans,
                       free_mulligans=free, keep_min=args.keep_min, keep_max=args.keep_max)
        result = evaluate(deck_model.parse_deck(args.deck, strict=True), cards, **options)
        if args.command == "compare":
            result = comparison(result, evaluate(deck_model.parse_deck(args.after, strict=True), cards, **options))
        result["format_context"] = args.format
        report = render(result)
        if args.out:
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.report:
            args.report.write_text(report, encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else report)
        code = 3 if result["status"] == "partial" else 0
        runlog.log_run("deck_evaluate.py", result["status"], args.command + " exit=" + str(code))
        return code
    except (OSError, ValueError, TypeError, KeyError, deck_model.DeckParseError) as exc:
        print("[error] " + str(exc))
        runlog.log_run("deck_evaluate.py", "error", str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(runlog.run_logged("deck_evaluate.py", main))
