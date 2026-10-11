"""Exact card identity and versioned Oracle evidence shared by MTG audits."""
import hashlib
import json
from pathlib import Path

import mtg_tool
from mtg_rules_tool import _fresh, _now, _read_json, _write_json, RulesDataError

CACHE_DIR = Path(mtg_tool.CACHE_DIR) / "card_facts"
TTL = 24 * 3600
CARD_FIELDS = ("name", "id", "oracle_id", "mana_cost", "cmc", "type_line", "oracle_text",
               "keywords", "color_identity", "colors", "legalities", "games", "flavor_name",
               "printed_name", "layout", "power", "toughness", "loyalty")


def oracle_text(card):
    return card.get("oracle_text") or "\n//\n".join(
        face.get("oracle_text", "") for face in card.get("card_faces", []))


def aliases(card):
    names = set()
    for entry in [card] + card.get("card_faces", []):
        for field in ("name", "printed_name", "flavor_name"):
            if isinstance(entry.get(field), str):
                names.add(entry[field].strip().casefold())
    return names


def _get(path, params=None):
    status, payload = mtg_tool.http_get_json(mtg_tool.SCRYFALL_BASE + path, "scryfall",
                                            params, use_cache=False)
    if status >= 400:
        if status == 404 and isinstance(payload, dict) and payload.get("code") == "not_found":
            raise mtg_tool.CardNotFound(payload.get("details") or "Card not found")
        raise mtg_tool.HttpError("Scryfall HTTP {}: {}".format(status, path))
    if not isinstance(payload, dict):
        raise RulesDataError("Invalid Scryfall card response")
    return payload


def card_facts(name, platform="any", refresh=False, offline=False, cache_dir=None):
    if refresh and offline:
        raise RulesDataError("--refresh cannot be combined with --offline")
    if platform not in ("any", "arena", "paper", "mtgo"):
        raise RulesDataError("Unknown platform: " + platform)
    name = name.strip()
    if not name:
        raise RulesDataError("Card name must not be empty")
    root = Path(cache_dir) if cache_dir is not None else CACHE_DIR
    digest = hashlib.sha256((platform + "\n" + name.casefold()).encode("utf-8")).hexdigest()
    path = root / (digest + ".json")
    cached = _read_json(path)
    if (not isinstance(cached, dict) or cached.get("version") != 1
            or cached.get("query_name", "").casefold() != name.casefold()
            or cached.get("platform") != platform
            or not isinstance(cached.get("card"), dict)
            or not cached["card"].get("oracle_id")
            or name.casefold() not in aliases(cached["card"])):
        cached = None
    if offline and not cached:
        raise mtg_tool.HttpError("No card evidence cache in offline mode: " + name)
    if not offline and (refresh or not cached or cached.get("refresh_error")
                        or not _fresh(cached.get("fetched_at"), TTL)):
        try:
            card = _get("/cards/named", {"exact": name})
            if (card.get("object") != "card" or not card.get("oracle_id")
                    or not card.get("name") or not card.get("id")):
                raise RulesDataError("Scryfall returned no Oracle card identity")
            if name.casefold() not in aliases(card):
                raise mtg_tool.CardNotFound("Exact card name mismatch: " + name)
            available = platform == "any" or platform in card.get("games", [])
            if not available:
                query = "!" + json.dumps(card["name"]) + " game:" + platform
                try:
                    prints = _get("/cards/search", {"q": query, "unique": "prints"})
                except mtg_tool.CardNotFound:
                    available = False
                else:
                    if (prints.get("object") != "list" or not isinstance(prints.get("data"), list)
                            or not prints["data"]):
                        raise RulesDataError("Invalid platform printing response")
                    available = any(entry.get("oracle_id") == card["oracle_id"] and
                                    platform in entry.get("games", []) for entry in prints["data"])
                    if not available:
                        raise RulesDataError("Platform search did not return the requested card")
            cached = {"version": 1, "query_name": name, "platform": platform,
                      "platform_available": available, "card": card,
                      "source": "scryfall-oracle", "source_url": mtg_tool.SCRYFALL_BASE + "/cards/" + card["id"],
                      "fetched_at": _now().isoformat()}
            _write_json(path, cached)
        except mtg_tool.CardNotFound:
            raise
        except (mtg_tool.MtgToolError, RulesDataError) as exc:
            if not cached:
                raise
            cached = dict(cached, refresh_error=str(exc), refresh_failed_at=_now().isoformat())
            _write_json(path, cached)
    result = dict(cached)
    result.pop("version", None)
    error = result.pop("refresh_error", None)
    result["stale"] = bool(error) or not _fresh(result.get("fetched_at"), TTL)
    result["warnings"] = ["Card evidence refresh failed: " + error] if error else []
    raw = result["card"]
    result["card"] = {key: raw[key] for key in CARD_FIELDS if key in raw}
    if raw.get("card_faces"):
        result["card"]["card_faces"] = [{key: face[key] for key in CARD_FIELDS if key in face}
                                          for face in raw["card_faces"]]
    return result


def deck_facts(deck, platform="any", refresh=False, offline=False):
    records = {}
    for _, name, _ in deck.entries():
        if name not in records:
            records[name] = card_facts(name, platform, refresh, offline)
    return records
