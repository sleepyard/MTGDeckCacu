#!/usr/bin/env python3
"""Commander Spellbook discovery with quantity, zone and evidence checks."""
import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import deck_model
import mtg_card_facts as facts
import mtg_tool
import runlog
from mtg_rules_tool import RulesDataError, _fresh, _now, _read_json, _write_json

API = "https://backend.commanderspellbook.com"
CACHE_DIR = Path(mtg_tool.CACHE_DIR) / "combos"
TTL = 24 * 3600
BUCKETS = ("included", "includedByChangingCommanders", "almostIncluded",
           "almostIncludedByAddingColors", "almostIncludedByChangingCommanders",
           "almostIncludedByAddingColorsAndChangingCommanders")
OUTPUT_BUCKETS = ("main_available", "postboard_available", "sideboard_candidates",
                  "missing_components", "needs_verification", "excluded")
_last_request_at = [0.0]


def _quantity(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RulesDataError("Component quantities must be positive integers")
    return value


def load_deck(path):
    deck = deck_model.parse_deck(path, strict=True)
    if not deck.main and not deck.commander:
        raise RulesDataError("Deck has no mainboard or commander cards")
    for qty, _, _ in deck.entries():
        _quantity(qty)
    return deck


def _scope(deck, evidence, sections):
    count = Counter()
    lookup = {name.casefold(): item for name, item in evidence.items()}
    for section in sections:
        for card in getattr(deck, section):
            count[lookup[card.name.casefold()]["card"]["name"]] += card.qty
    return count


def _postboard_check(deck, postboard):
    def counts(value, sections):
        result = Counter()
        for qty, name, section in value.entries():
            if section in sections:
                result[name.casefold()] += qty
        return result
    if counts(deck, deck_model.SECTIONS) != counts(postboard, deck_model.SECTIONS):
        raise RulesDataError("Postboard list must conserve the full deck's card quantities")
    for section in ("main", "sideboard", "commander", "companion"):
        if sum(c.qty for c in getattr(deck, section)) != sum(c.qty for c in getattr(postboard, section)):
            raise RulesDataError("Postboard list changed a zone's card count: " + section)
    for section in ("commander", "companion"):
        if counts(deck, (section,)) != counts(postboard, (section,)):
            raise RulesDataError("Postboard list changed " + section)


def _request(url, body, params):
    # Official API guidance suggests staying below 80 requests/minute.
    delay = 0.8 - (time.monotonic() - _last_request_at[0])
    if delay > 0:
        time.sleep(delay)
    try:
        if body is None:
            status, payload = mtg_tool.http_get_json(url, "spellbook", params, use_cache=False)
        else:
            status, payload = mtg_tool.http_post_json(url, body, params, timeout=30)
    finally:
        _last_request_at[0] = time.monotonic()
    if status >= 400:
        raise mtg_tool.HttpError("Spellbook HTTP {}: {}".format(status, url))
    if not isinstance(payload, dict):
        raise RulesDataError("Spellbook returned a non-object response")
    return payload


def _variants(page, search):
    results = page.get("results")
    if search:
        if not isinstance(results, dict) or not all(isinstance(results.get(key), list) for key in BUCKETS):
            raise RulesDataError("Spellbook response has missing or malformed combo groups")
        variants = [dict(variant, api_group=key) for key in BUCKETS for variant in results[key]
                    if isinstance(variant, dict)]
        if len(variants) != sum(len(results[key]) for key in BUCKETS):
            raise RulesDataError("Spellbook group contains a malformed variant")
    else:
        if not isinstance(results, list):
            raise RulesDataError("Spellbook variants response has no results list")
        variants = results
    if not all(isinstance(variant, dict) and isinstance(variant.get("id"), (str, int))
               and not isinstance(variant.get("id"), bool)
               and (variant.get("popularity") is None or
                    isinstance(variant.get("popularity"), int)) for variant in variants):
        raise RulesDataError("Spellbook variant has no identity")
    for variant in variants:
        normalize_variant(variant)
    return variants


def fetch_variants(endpoint, body=None, params=None, offline=False, refresh=False, cache_dir=None):
    if offline and refresh:
        raise RulesDataError("--refresh cannot be combined with --offline")
    search = endpoint == "/find-my-combos"
    root = Path(cache_dir) if cache_dir is not None else CACHE_DIR
    key = hashlib.sha256(json.dumps([endpoint, body, params], sort_keys=True).encode("utf-8")).hexdigest()
    path = root / (key + ".json")
    cached = _read_json(path)
    if (not isinstance(cached, dict) or cached.get("version") != 1
            or not isinstance(cached.get("variants"), list)
            or cached.get("variant_count") != len(cached["variants"])
            or cached.get("pagination_complete") is not True
            or not all(isinstance(item, dict) and item.get("id") is not None for item in cached["variants"])):
        cached = None
    if offline and not cached:
        raise mtg_tool.HttpError("No Spellbook cache available in offline mode")
    if not offline and (refresh or not cached or cached.get("refresh_error")
                        or not _fresh(cached.get("fetched_at"), TTL)):
        try:
            url, query = API + endpoint, dict(params or {}, limit=1000)
            seen_urls, variants = set(), {}
            count = None
            for _ in range(mtg_tool.MAX_PAGES):
                marker = url + json.dumps(query, sort_keys=True)
                if marker in seen_urls:
                    raise mtg_tool.PaginationIncomplete("Spellbook pagination repeated a page")
                seen_urls.add(marker)
                page = _request(url, body, query)
                if ("next" not in page or "count" not in page or
                        (page["count"] is not None and
                         (isinstance(page["count"], bool) or not isinstance(page["count"], int) or page["count"] < 0))):
                    raise RulesDataError("Spellbook pagination metadata is incomplete")
                if count is None:
                    count = page["count"]
                elif page["count"] is not None and count != page["count"]:
                    raise mtg_tool.PaginationIncomplete("Spellbook result count changed during pagination")
                for variant in _variants(page, search):
                    variants[str(variant["id"])] = variant
                next_url = page["next"]
                if next_url is None:
                    break
                if (not isinstance(next_url, str) or urlparse(next_url).scheme != "https"
                        or urlparse(next_url).netloc != urlparse(API).netloc
                        or urlparse(next_url).path.rstrip("/") != endpoint.rstrip("/")):
                    raise mtg_tool.PaginationIncomplete("Spellbook returned an invalid next-page URL")
                url, query = next_url, None
            else:
                raise mtg_tool.PaginationIncomplete("Spellbook page limit exceeded")
            if count is not None and len(variants) != count:
                raise mtg_tool.PaginationIncomplete("Spellbook returned {} of {} variants".format(len(variants), count))
            cached = {"version": 1, "source": "commander-spellbook", "source_url": API + endpoint,
                      "fetched_at": _now().isoformat(), "variants": list(variants.values()),
                      "variant_count": len(variants), "api_count": count,
                      "pagination_complete": True}
            _write_json(path, cached)
        except (mtg_tool.MtgToolError, RulesDataError) as exc:
            if not cached:
                raise
            cached = dict(cached, refresh_error=str(exc), refresh_failed_at=_now().isoformat())
            _write_json(path, cached)
    result = dict(cached)
    result.pop("version", None)
    error = result.pop("refresh_error", None)
    result["stale"] = bool(error) or not _fresh(result.get("fetched_at"), TTL)
    result["warnings"] = ["Spellbook refresh failed; cached results: " + error] if error else []
    return result


def normalize_variant(variant):
    uses, templates = variant.get("uses"), variant.get("requires")
    if not isinstance(uses, list) or not uses or not isinstance(templates, list):
        raise RulesDataError("Variant has malformed card/template requirements")
    components = []
    for use in uses:
        if (not isinstance(use, dict) or not isinstance(use.get("card"), dict)
                or not isinstance(use["card"].get("name"), str)):
            raise RulesDataError("Variant component has no card name")
        component = dict(use, name=use["card"]["name"], quantity=_quantity(use.get("quantity", 1)))
        component["card"] = {key: use["card"][key] for key in ("name", "id", "oracleId", "typeLine")
                             if key in use["card"]}
        components.append(component)
    requirements = []
    for item in templates:
        if not isinstance(item, dict) or not isinstance(item.get("template"), dict):
            raise RulesDataError("Variant template is malformed")
        requirements.append(dict(item, quantity=_quantity(item.get("quantity", 1))))
    produces = variant.get("produces")
    if not isinstance(produces, list):
        raise RulesDataError("Variant has no results list")
    if not isinstance(variant.get("legalities", {}), dict):
        raise RulesDataError("Variant legalities must be an object")
    return {"id": str(variant["id"]), "source_url": "https://commanderspellbook.com/combo/" + str(variant["id"]),
            "components": components, "templates": requirements, "results": produces,
            "mana_needed": variant.get("manaNeeded"), "mana_value_needed": variant.get("manaValueNeeded"),
            "easy_prerequisites": variant.get("easyPrerequisites"),
            "notable_prerequisites": variant.get("notablePrerequisites"),
            "description": variant.get("description"), "notes": variant.get("notes"),
            "legalities": variant.get("legalities", {}), "identity": variant.get("identity"),
            "popularity": variant.get("popularity") or 0,
            "rules_verified": False}


_TERM = re.compile(r'\s*(\w+):("(?:[^"\\]|\\.)*"|[^\s]+)')


def template_match(card, query):
    """Conservative AND-only predicates. Unsupported syntax remains unverified."""
    if not isinstance(query, str) or not query.strip():
        return None
    offset, tests = 0, []
    while offset < len(query):
        if not query[offset:].strip():
            break
        match = _TERM.match(query, offset)
        if not match:
            return None
        key, raw = match.groups()
        value = json.loads(raw) if raw.startswith('"') else raw
        if not value or any(token in value for token in ("(", ")", "/")):
            return None
        if key.lower() in ("t", "type"):
            tests.append(value.casefold() in card.get("type_line", "").casefold())
        elif key.lower() in ("o", "oracle"):
            tests.append(value.casefold() in facts.oracle_text(card).casefold())
        elif key.lower() in ("kw", "keyword"):
            tests.append(value.casefold() in {word.casefold() for word in card.get("keywords", [])})
        else:
            return None
        offset = match.end()
    return all(tests) if tests else None


def _availability(combo, counts, commanders, records, template_eligibility=None):
    remaining = counts.copy()
    missing, wrong_commanders = [], []
    required = Counter()
    for component in combo["components"]:
        required[component["name"]] += component["quantity"]
        if component.get("mustBeCommander") and commanders[component["name"]] < component["quantity"]:
            wrong_commanders.append(component["name"])
    for name, quantity in required.items():
        absent = max(0, quantity - remaining[name])
        if absent:
            missing.append({"name": name, "quantity": absent})
        remaining[name] = max(0, remaining[name] - quantity)
    template_count = sum(template["quantity"] for template in combo["templates"])
    if template_count > 1000:
        raise RulesDataError("Too many generic template components to evaluate")
    slots = [name for name, quantity in remaining.items() for _ in range(min(quantity, template_count))]
    needs, unknown = [], []
    for template in combo["templates"]:
        query = template["template"].get("scryfallQuery")
        candidates = []
        unsupported = template_match({}, query) is None
        if unsupported:
            unknown.append(template["template"].get("name") or query or "unnamed template")
            continue
        for index, name in enumerate(slots):
            commander_slot = slots[:index].count(name) < max(0, commanders[name] - required[name])
            if template.get("mustBeCommander") and not commander_slot:
                continue
            if template_match(records[name], query) is True:
                eligibility = (template_eligibility or {}).get(name, "legal")
                if eligibility == "unknown":
                    unknown.append(name + ": template card evidence unverified")
                if eligibility != "legal":
                    continue
                candidates.append(index)
        needs.extend([candidates] * template["quantity"])
    assigned = {}

    def match_slot(index, seen):
        for slot in needs[index]:
            if slot in seen:
                continue
            seen.add(slot)
            if slot not in assigned or match_slot(assigned[slot], seen):
                assigned[slot] = index
                return True
        return False

    unmet = sum(not match_slot(index, set()) for index in range(len(needs)))
    return {"missing_cards": missing, "unmet_template_quantity": unmet,
            "unverified_templates": unknown, "wrong_commanders": wrong_commanders,
            "complete": not (missing or unmet or unknown or wrong_commanders)}


def _legal(combo, evidence, format_name, platform):
    key = mtg_tool.FORMAT_LEGALITY_ALIAS.get(format_name, format_name)
    issues, unknown = [], []
    for name in {entry["name"] for entry in combo["components"]}:
        item = evidence[name]
        status = item["card"].get("legalities", {}).get(key)
        if item.get("stale"):
            unknown.append(name + ": current card evidence unverified")
            continue
        if status is None:
            unknown.append(name + ": current legality unverified")
        elif status not in ("legal", "restricted"):
            issues.append(name + ": " + status)
        if not item.get("platform_available"):
            issues.append(name + ": unavailable on " + platform)
        if status == "restricted" and sum(entry["quantity"] for entry in combo["components"] if entry["name"] == name) > 1:
            issues.append(name + ": combo requires multiple copies of a restricted card")
    return {"status": "illegal" if issues else "unknown" if unknown else "legal",
            "issues": issues, "unverified": unknown}


def analyze(deck, response, format_name, platform="arena", postboard=None, refresh=False, offline=False, deck_evidence=None):
    if postboard:
        _postboard_check(deck, postboard)
    evidence_by_input = deck_evidence if deck_evidence is not None else facts.deck_facts(deck, platform, refresh, offline)
    canonical = {item["card"]["name"]: item for item in evidence_by_input.values()}
    records = {name: item["card"] for name, item in canonical.items()}
    main = _scope(deck, evidence_by_input, ("main", "commander"))
    combined = main + _scope(deck, evidence_by_input, ("sideboard",))
    commanders = _scope(deck, evidence_by_input, ("commander",))
    after = _scope(postboard, evidence_by_input, ("main", "commander")) if postboard else None
    template_eligibility = {}
    for name, item in canonical.items():
        single = {"components": [{"name": name, "quantity": 1}]}
        template_eligibility[name] = _legal(single, canonical, format_name, platform)["status"]
        if commanders and format_name in ("commander", "brawl", "standardbrawl"):
            allowed = set().union(*(set(records[c].get("color_identity", [])) for c in commanders))
            if not set(records[name].get("color_identity", [])).issubset(allowed):
                template_eligibility[name] = "illegal"
    result = {key: [] for key in OUTPUT_BUCKETS}
    result.update({key: val for key, val in response.items() if key != "variants"})
    result.update({"status": "ok", "format": format_name, "platform": platform,
                   "scope": "component-availability", "warnings": list(response.get("warnings", []))})
    evidence_failed = 0
    for raw in sorted(response["variants"], key=lambda entry: entry.get("popularity") or 0, reverse=True):
        combo = normalize_variant(raw)
        evidence_error = None
        for component in combo["components"]:
            name = component["name"]
            if name not in canonical:
                try:
                    item = facts.card_facts(name, platform, refresh, offline)
                except mtg_tool.CardNotFound as exc:
                    evidence_error = "component card not found: {} ({})".format(name, exc)
                    break
                except (mtg_tool.HttpError, mtg_tool.NetworkError):
                    if not offline:
                        raise
                    evidence_error = "component evidence unavailable in offline mode: " + name
                    break
                if item["card"]["name"].casefold() != name.casefold():
                    raise RulesDataError("Spellbook/Scryfall component identity mismatch: " + name)
                canonical[name], records[name] = item, item["card"]
        if evidence_error is not None:
            combo["evidence_error"] = evidence_error
            result["needs_verification"].append(combo)
            evidence_failed += 1
            continue
        combo["legality"] = _legal(combo, canonical, format_name, platform)
        if commanders and format_name in ("commander", "brawl", "standardbrawl"):
            allowed = set().union(*(set(records[name].get("color_identity", [])) for name in commanders))
            overflow = [entry["name"] for entry in combo["components"]
                        if not set(records[entry["name"]].get("color_identity", [])).issubset(allowed)]
            if overflow:
                combo["legality"]["issues"].append("Outside commander color identity: " + ", ".join(overflow))
                combo["legality"]["status"] = "illegal"
        combo["main"] = _availability(combo, main, commanders, records, template_eligibility)
        combo["combined"] = _availability(combo, combined, commanders, records, template_eligibility)
        if after is not None:
            combo["postboard"] = _availability(combo, after, commanders, records, template_eligibility)
        if combo["legality"]["status"] == "illegal":
            bucket = "excluded"
        elif (combo["legality"]["status"] == "unknown" or response["stale"]
              or combo["combined"]["unverified_templates"] or not combo["description"]):
            bucket = "needs_verification"
        elif combo["main"]["complete"]:
            bucket = "main_available"
        elif after is not None and combo["postboard"]["complete"]:
            bucket = "postboard_available"
        elif combo["combined"]["complete"]:
            bucket = "sideboard_candidates"
        elif combo["combined"]["wrong_commanders"]:
            bucket = "needs_verification"
        else:
            bucket = "missing_components"
        result[bucket].append(combo)
    if evidence_failed:
        warning = ("Combo component evidence unavailable for every variant; "
                   "nothing could be verified" if evidence_failed == len(response["variants"])
                   else "Combo component evidence unavailable for {} of {} variant(s); "
                        "downgraded to needs_verification".format(evidence_failed, len(response["variants"])))
        result["warnings"].append(warning)
    result["card_evidence"] = canonical
    result["stale"] = response["stale"] or any(item.get("stale") for item in canonical.values())
    result["warnings"].extend(warning for item in canonical.values() for warning in item.get("warnings", []))
    return result


def _select(response, limit, format_name=None):
    selected = dict(response)
    key = mtg_tool.FORMAT_LEGALITY_ALIAS.get(format_name, format_name)
    ordered = sorted(response["variants"], key=lambda value: (
        1 if value.get("legalities", {}).get(key) is False else 0,
        0 if value.get("api_group", "").startswith("included") else 1,
        -(value.get("popularity") or 0)))
    selected["variants"] = ordered[:limit]
    selected["analyzed_variant_count"] = len(selected["variants"])
    selected["unexamined_variant_count"] = len(ordered) - len(selected["variants"])
    selected["truncated"] = len(ordered) > limit
    return selected


def search_deck(deck, format_name, platform="arena", postboard=None, refresh=False, offline=False, limit=20):
    if postboard:
        _postboard_check(deck, postboard)
    evidence = facts.deck_facts(deck, platform, refresh, offline)
    main = _scope(deck, evidence, ("main", "sideboard"))
    commanders = _scope(deck, evidence, ("commander",))
    ids = {item["card"]["name"]: item["card"]["oracle_id"] for item in evidence.values()}
    body = {"main": [{"card": ids[name], "quantity": qty} for name, qty in sorted(main.items())],
            "commanders": [{"card": ids[name], "quantity": qty} for name, qty in sorted(commanders.items())]}
    response = fetch_variants("/find-my-combos", body, offline=offline, refresh=refresh)
    return analyze(deck, _select(response, limit, format_name), format_name, platform, postboard,
                   refresh, offline, deck_evidence=evidence)


def discover(cards, outcome, colors, format_name, platform="arena", refresh=False, offline=False, limit=20):
    if not cards and not outcome:
        raise RulesDataError("Discovery needs at least one --card or --result")
    if colors and (not re.fullmatch(r"[WUBRGCwubrgc]+", colors) or len(set(colors.upper())) != len(colors)):
        raise RulesDataError("Invalid color identity")
    evidence = {name: facts.card_facts(name, platform, refresh, offline) for name in cards}
    parts = ["card:" + json.dumps(item["card"]["name"]) for item in evidence.values()]
    if outcome:
        parts.append("result:" + json.dumps(outcome))
    if colors:
        parts.append("ci:" + colors.upper())
    response = fetch_variants("/variants/", params={"q": " ".join(parts), "ordering": "-popularity"},
                              refresh=refresh, offline=offline)
    # Discovery has no assembled deck. Report what would still need to be acquired.
    seed = deck_model.Deck(main=tuple(deck_model.CardRef(1, name, "main") for name in cards))
    return analyze(seed, _select(response, limit, format_name), format_name, platform,
                   refresh=refresh, offline=offline, deck_evidence=evidence)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("search", "discover"):
        child = sub.add_parser(name)
        child.add_argument("--format", required=True)
        child.add_argument("--platform", choices=("arena", "paper", "mtgo", "any"), default="arena")
        child.add_argument("--refresh", action="store_true")
        child.add_argument("--offline", action="store_true")
        child.add_argument("--limit", type=int, default=20, help="Maximum variants to analyze; included groups first")
        child.add_argument("--json", action="store_true", dest="as_json")
        child.add_argument("--out", type=Path)
        if name == "search":
            child.add_argument("deck", type=Path)
            child.add_argument("--postboard", type=Path)
        else:
            child.add_argument("--card", action="append", default=[])
            child.add_argument("--result")
            child.add_argument("--colors")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.limit < 1:
            raise RulesDataError("--limit must be positive")
        if args.format not in ("standard", "pioneer", "explorer", "modern", "legacy", "vintage",
                               "commander", "brawl", "standardbrawl", "historic", "timeless",
                               "alchemy", "pauper"):
            raise RulesDataError("Unsupported format: " + args.format)
        if args.command == "search":
            deck = load_deck(args.deck)
            postboard = load_deck(args.postboard) if args.postboard else None
            result = search_deck(deck, args.format, args.platform, postboard, args.refresh, args.offline, args.limit)
        else:
            result = discover(args.card, args.result, args.colors, args.format, args.platform, args.refresh, args.offline, args.limit)
        result["group_counts"] = {key: len(result[key]) for key in OUTPUT_BUCKETS}
        code = 0
    except (mtg_tool.MtgToolError, deck_model.DeckParseError, ValueError, OSError) as exc:
        result = {"status": "error", "source": "commander-spellbook",
                  "error": {"type": type(exc).__name__, "message": str(exc)}}
        code = 1 if isinstance(exc, mtg_tool.MtgToolError) else 2
    if args.out:
        try:
            _write_json(args.out, result)
        except OSError as exc:
            print("[error] Could not write output: " + str(exc), file=sys.stderr)
            runlog.log_run("mtg_combo_tool", "error", str(exc))
            return 2
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif code:
        print("[error] " + result["error"]["message"], file=sys.stderr)
    else:
        print("Spellbook: {} variants | stale={}".format(result["variant_count"], result["stale"]))
        for key in OUTPUT_BUCKETS:
            print("{}: {}".format(key, result["group_counts"][key]))
            for combo in result[key]:
                print("  {}: {} | {}".format(combo["id"], " + ".join(c["name"] for c in combo["components"]),
                                             combo["source_url"]))
        if result.get("truncated"):
            print("Analyzed {} of {} variants; {} unexamined (truncated). Increase --limit to analyze more.".format(
                result.get("analyzed_variant_count", 0), result["variant_count"], result["unexamined_variant_count"]))
        print("Component availability only; verify prerequisites and rules before recommending a line.")
    for warning in result.get("warnings", []):
        print("[warn] " + warning, file=sys.stderr)
    runlog.log_run("mtg_combo_tool", "error" if code else "warning" if result.get("stale") else "ok",
                   "{} out={}".format(args.command, args.out or "stdout"))
    return code


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(runlog.run_logged("mtg_combo_tool", main))
