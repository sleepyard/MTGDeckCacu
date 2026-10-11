#!/usr/bin/env python3
"""Audit registered guide claims: deck counts, resource arithmetic and CR quotes.

This is evidence checking, not a game engine or an automatic prose/rules judge.
The mtg-guide-review skill inventories the guide's claims and checks semantics.
"""
import argparse
import ast
import json
import operator
import re
import sys
from collections import Counter
from pathlib import Path

import deck_model
import mtg_card_facts as facts
import mtg_rules_tool as rules
import mtg_tool
import runlog

OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
             ast.FloorDiv: operator.floordiv}
MAX_VALUE = 10 ** 12


def _integer(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= MAX_VALUE:
        raise ValueError(name + " must be an integer in the allowed range")
    return value


def arithmetic(expression, state):
    if isinstance(expression, int) and not isinstance(expression, bool):
        return _integer(expression, "resource value")
    if not isinstance(expression, str) or len(expression) > 200:
        raise ValueError("Resource expression must be a short integer expression")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Invalid resource expression") from exc

    def visit(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
            value = node.value
        elif type(node).__name__ == "Num" and isinstance(node.n, int) and not isinstance(node.n, bool):
            value = node.n
        elif isinstance(node, ast.Name) and node.id in state:
            value = state[node.id]
        elif isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            value = OPERATORS[type(node.op)](visit(node.left), visit(node.right))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            value = -visit(node.operand)
        else:
            raise ValueError("Unsupported resource expression")
        if abs(value) > MAX_VALUE:
            raise ValueError("Resource expression exceeded its bound")
        return value

    try:
        return _integer(visit(tree.body), "computed resource value")
    except (ZeroDivisionError, RecursionError) as exc:
        raise ValueError("Invalid resource expression") from exc


def simulate_loop(model):
    initial, steps = model.get("initial"), model.get("steps")
    if not isinstance(initial, dict) or not initial or not isinstance(steps, list) or not steps:
        raise ValueError("A loop needs initial resources and explicit steps")
    state = {}
    for name, value in initial.items():
        if not isinstance(name, str) or not name.isidentifier():
            raise ValueError("Resource names must be identifiers")
        state[name] = _integer(value, name)
    iterations = _integer(model.get("iterations", 3), "iterations", 1)
    if iterations > 1000 or len(steps) > 100:
        raise ValueError("Loop simulation is too large")
    snapshots, events = [], []
    for iteration in range(iterations):
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                raise ValueError("Invalid loop step")
            for key in ("pay", "gain", "require"):
                if not isinstance(step.get(key, {}), dict) or any(name not in state for name in step.get(key, {})):
                    raise ValueError("Loop step references an undeclared resource")
            payments = {name: arithmetic(value, state) for name, value in step.get("pay", {}).items()}
            requirements = {name: arithmetic(value, state) for name, value in step.get("require", {}).items()}
            deficits = {name: max(payments.get(name, 0), requirements.get(name, 0)) - state[name]
                        for name in state if max(payments.get(name, 0), requirements.get(name, 0)) > state[name]}
            if deficits:
                return {"completed": False, "initial": initial, "final": state,
                        "iterations_completed": iteration, "snapshots": snapshots, "events": events,
                        "blocked_step": index + 1, "deficits": deficits, "infinite_proven": False}
            for name, amount in payments.items():
                state[name] -= amount
            gains = {name: arithmetic(value, state) for name, value in step.get("gain", {}).items()}
            for name, amount in gains.items():
                state[name] = _integer(state[name] + amount, name)
            events.append({"iteration": iteration + 1, "step": index + 1, "state": dict(state)})
        snapshots.append(dict(state))
    return {"completed": True, "initial": initial, "final": state,
            "iterations_completed": iterations, "snapshots": snapshots, "events": events,
            "infinite_proven": False}


def deck_counts(deck):
    return {section: sum(card.qty for card in getattr(deck, section)) for section in deck_model.SECTIONS}


def _count(deck, claim, evidence):
    sections = claim.get("sections", ["main"])
    if (not isinstance(sections, list) or not sections or len(set(sections)) != len(sections)
            or any(section not in deck_model.SECTIONS for section in sections)):
        raise ValueError("Count claim has invalid deck sections")
    names = claim.get("cards")
    if names is not None and (not isinstance(names, list) or not all(isinstance(n, str) for n in names)):
        raise ValueError("Count claim cards must be a list of names")
    allowed = {name.casefold() for name in names} if names is not None else None
    if allowed is not None:
        known = {name.casefold() for _, name, _ in deck.entries()}
        if not allowed.issubset(known):
            raise ValueError("Count claim names are absent from the deck: " + ", ".join(sorted(allowed - known)))
    type_pattern = re.compile(claim["type_pattern"], re.I) if "type_pattern" in claim else None
    if claim.get("face", "front") not in ("front", "any"):
        raise ValueError("Count claim face must be front or any")
    quantity, matched, seen = 0, [], set()
    for section in sections:
        for entry in getattr(deck, section):
            if allowed is not None and entry.name.casefold() not in allowed:
                continue
            card = None
            if type_pattern:
                if entry.name not in evidence:
                    evidence[entry.name] = facts.card_facts(entry.name)
                card = evidence[entry.name]["card"]
                if claim.get("face", "front") == "front" and card.get("card_faces"):
                    type_line = card["card_faces"][0].get("type_line", "")
                else:
                    type_line = card.get("type_line", "")
                if not type_pattern.search(type_line):
                    continue
            key = card.get("oracle_id") if card else entry.name.casefold()
            if claim.get("unique") and key in seen:
                continue
            seen.add(key)
            amount = 1 if claim.get("unique") else entry.qty
            quantity += amount
            matched.append({"name": entry.name, "quantity": amount, "section": section})
    return quantity, matched


def _text_checks(text, claim, expected):
    patterns = claim.get("text_patterns")
    if not isinstance(patterns, list) or not patterns or not all(isinstance(pattern, str) for pattern in patterns):
        raise ValueError("Every count/loop claim needs text_patterns with a named value group")
    occurrences, findings = [], []
    for pattern in patterns:
        compiled = re.compile(pattern, re.M)
        if "value" not in compiled.groupindex:
            raise ValueError("Claim pattern must capture (?P<value>...)")
        matches = list(compiled.finditer(text))
        if not matches:
            findings.append({"kind": "missing_text", "pattern": pattern})
        for match in matches:
            try:
                value = int(match.group("value"))
            except (TypeError, ValueError) as exc:
                raise ValueError("Claim pattern captured a non-integer value") from exc
            line = text.count("\n", 0, match.start()) + 1
            occurrences.append({"line": line, "text": match.group(), "value": value})
            if value != expected:
                findings.append({"kind": "wrong_number", "line": line, "actual": value, "expected": expected})
    if len({entry["value"] for entry in occurrences}) > 1:
        findings.append({"kind": "inconsistent_repetition"})
    return occurrences, findings


def _normalized(text):
    return " ".join(text.split())


def validate_claims(claims):
    if not isinstance(claims, dict) or claims.get("version") != 1:
        raise ValueError("Guide claims must have version: 1")
    if set(claims) - {"version", "counts", "loops", "rules"}:
        raise ValueError("Unknown guide claim group")
    for group in ("counts", "loops", "rules"):
        if not isinstance(claims.get(group, []), list) or not all(
                isinstance(claim, dict) for claim in claims.get(group, [])):
            raise ValueError("Claim groups must be lists of objects")
    for claim in claims.get("loops", []):
        if not isinstance(claim.get("steps"), list) or not all(isinstance(step, dict) for step in claim["steps"]):
            raise ValueError("Loop steps must be a list of objects")


def audit(deck, text, claims, evidence=None, rules_document=None):
    validate_claims(claims)
    evidence = evidence if evidence is not None else {}
    checks, findings, incomplete, ids = [], [], [], set()
    for group in ("counts", "loops", "rules"):
        items = claims.get(group, [])
        if not isinstance(items, list):
            raise ValueError("Claim groups must be lists")
        for claim in items:
            if not isinstance(claim, dict) or not isinstance(claim.get("id"), str) or not claim["id"]:
                raise ValueError("Every claim needs a nonempty id")
            if claim["id"] in ids:
                raise ValueError("Duplicate guide claim id")
            ids.add(claim["id"])
            check = {"id": claim["id"], "kind": group}
            failures = []
            if group == "counts":
                expected, cards = _count(deck, claim, evidence)
                check.update({"expected": expected, "cards": cards})
                check["occurrences"], failures = _text_checks(text, claim, expected)
            elif group == "loops":
                loop = simulate_loop(claim)
                check["simulation"] = loop
                if not loop["completed"]:
                    failures.append({"kind": "resource_deficit", "details": loop["deficits"]})
                resource, metric = claim.get("resource"), claim.get("metric", "final")
                if resource not in loop["final"] or metric not in ("final", "net", "per_cycle"):
                    raise ValueError("Loop needs a declared resource and valid comparison metric")
                expected = loop["final"][resource]
                if metric in ("net", "per_cycle"):
                    expected -= loop["initial"][resource]
                if metric == "per_cycle":
                    previous, deltas = loop["initial"][resource], []
                    for snapshot in loop["snapshots"]:
                        deltas.append(snapshot[resource] - previous)
                        previous = snapshot[resource]
                    if len(set(deltas)) != 1:
                        failures.append({"kind": "variable_cycle_yield", "deltas": deltas})
                    expected = deltas[0] if deltas else 0
                check["expected"] = expected
                check["occurrences"], numerical = _text_checks(text, claim, expected)
                failures.extend(numerical)
                for step in claim["steps"]:
                    name, quote = step.get("card"), step.get("oracle_quote")
                    if not isinstance(name, str) or not isinstance(quote, str) or not quote.strip():
                        raise ValueError("Each loop step needs a card and exact oracle_quote")
                    if not any(entry.name.casefold() == name.casefold() for entry in deck.main + deck.commander):
                        failures.append({"kind": "inactive_loop_component", "card": name})
                    if name not in evidence:
                        evidence[name] = facts.card_facts(name)
                    if _normalized(quote) not in _normalized(facts.oracle_text(evidence[name]["card"])):
                        failures.append({"kind": "oracle_quote_mismatch", "card": name})
                check["semantic_review_required"] = True
            else:
                if rules_document is None:
                    rules_document = rules.load_document()
                number, quote = claim.get("number"), claim.get("quote")
                if not isinstance(number, str) or not isinstance(quote, str) or not quote.strip():
                    raise ValueError("Rule claim needs a number and an exact quote")
                entry = rules_document["parsed"]["rules"].get(number)
                if entry is None:
                    failures.append({"kind": "rule_not_found", "number": number})
                elif _normalized(quote) not in _normalized(entry["text"]):
                    failures.append({"kind": "rule_quote_mismatch", "number": number})
                if number not in text or _normalized(quote) not in _normalized(text):
                    failures.append({"kind": "rule_citation_missing_from_guide", "number": number})
                if rules_document["stale"]:
                    incomplete.append("CR freshness/origin unverified")
                check.update({"number": number, "effective_date": rules_document["effective_date"],
                              "source_url": rules_document["source_url"], "semantic_review_required": True})
            for failure in failures:
                findings.append(dict(failure, claim=claim["id"]))
            check["status"] = "fail" if failures else "pass"
            checks.append(check)
    if not checks:
        raise ValueError("No guide claims registered")
    for name, item in evidence.items():
        if item.get("stale"):
            incomplete.append(name + ": Oracle evidence is stale")
    return {"status": "fail" if findings else "incomplete" if incomplete else "pass",
            "coverage": "registered-claims-only", "semantic_review_required": True,
            "deck_counts": deck_counts(deck), "claim_count": len(checks), "checks": checks,
            "findings": findings, "incomplete": sorted(set(incomplete)), "card_evidence": evidence}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck", type=Path)
    parser.add_argument("guide", type=Path)
    parser.add_argument("--claims", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        deck = deck_model.parse_deck(args.deck, strict=True)
        for qty, _, _ in deck.entries():
            _integer(qty, "card quantity", 1)
        claims = json.loads(args.claims.read_text(encoding="utf-8-sig"))
        validate_claims(claims)
        text = args.guide.read_text(encoding="utf-8-sig")
        # Only hydrate cards needed by registered claims; offline never contacts APIs.
        names = {step["card"] for claim in claims.get("loops", []) for step in claim.get("steps", [])
                 if isinstance(step.get("card"), str)}
        if any("type_pattern" in claim for claim in claims.get("counts", [])):
            names.update(name for _, name, _ in deck.entries())
        evidence = {name: facts.card_facts(name, offline=args.offline) for name in sorted(names)}
        document = rules.load_document(offline=args.offline) if claims.get("rules") else None
        result = audit(deck, text, claims, evidence, document)
        code = 4 if result["status"] == "fail" else 2 if result["status"] == "incomplete" else 0
    except (mtg_tool.MtgToolError, deck_model.DeckParseError, ValueError, OSError, SyntaxError, KeyError, TypeError) as exc:
        result = {"status": "error", "error": {"type": type(exc).__name__, "message": str(exc)}}
        code = 1 if isinstance(exc, mtg_tool.MtgToolError) else 2
    if args.out:
        try:
            rules._write_json(args.out, result)
        except OSError as exc:
            print("[error] Could not write output: " + str(exc), file=sys.stderr)
            runlog.log_run("mtg_guide_audit", "error", str(exc))
            return 2
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif "error" in result:
        print("[error] " + result["error"]["message"], file=sys.stderr)
    else:
        print("{}: {} registered claims; semantic rules review still required".format(result["status"], result["claim_count"]))
        for finding in result["findings"]:
            print(json.dumps(finding, ensure_ascii=False))
        for item in result["incomplete"]:
            print("[incomplete] " + item)
    runlog.log_run("mtg_guide_audit", result["status"], "guide={} out={}".format(args.guide, args.out or "stdout"))
    return code


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(runlog.run_logged("mtg_guide_audit", main))
