#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Versioned Comprehensive Rules and Scryfall rulings queries (stdlib only).

CR parsing is adapted from dan-blanchard/mtg-skills (0BSD), revision
eaae97c7b74f016c03a4da99497eb403990a9ee7, rules_lookup.py.
Copyright (C) 2026 Dan Blanchard.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlparse

import mtg_tool
import runlog

RULES_URL = "https://magic.wizards.com/en/rules"
CACHE_DIR = Path(mtg_tool.CACHE_DIR) / "rules"
CR_TTL = 24 * 3600
RULINGS_TTL = 30 * 24 * 3600
CACHE_VERSION = 1
PARSER_VERSION = 1

_SECTION_RE = re.compile(r"^([1-9])\. (.+)$")
_CATEGORY_RE = re.compile(r"^(\d{3})\. (.+)$")
_SUBRULE_RE = re.compile(r"^(\d{3}\.\d+[a-z])\.?\s*(.+)$")
_RULE_RE = re.compile(r"^(\d{3}\.\d+)\.?\s*(.+)$")
_REF_RE = re.compile(r"\b(\d{3}(?:\.\d+[a-z]?)?)\b")
_DATE_RE = re.compile(r"effective as of ([A-Z][a-z]+ \d+, \d{4})")
_TXT_RE = re.compile(r"MagicCompRules[\s_-]?(\d{8})\.txt$", re.I)


class RulesDataError(ValueError):
    """Missing or malformed source data, cache, or query."""


def _now():
    return datetime.now(timezone.utc)


def _fresh(timestamp, ttl):
    try:
        stamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        age = (_now() - stamp).total_seconds()
        return 0 <= age < ttl
    except (AttributeError, TypeError, ValueError):
        return False


def _atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, str(path))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_json(path, payload):
    _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _read_json(path):
    try:
        with Path(path).open(encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return None


def _read_json_report(path):
    """Read a cache JSON file, distinguishing "never cached" from "corrupt".

    Returns (payload, error): (None, None) when the file is absent,
    (None, reason) when it exists but cannot be decoded, else (payload, None).
    """
    try:
        with Path(path).open(encoding="utf-8") as stream:
            return json.load(stream), None
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        return None, "cannot be read: " + str(exc)
    except ValueError as exc:
        return None, "is not valid JSON: " + str(exc)


def _references(text, rules, own=None):
    return sorted({number for number in _REF_RE.findall(text)
                   if number != own and (number in rules or
                   any(key.startswith(number + ".") for key in rules))})


def parse_rules(text):
    """Parse the body (not the TOC), numbered rules, examples and glossary."""
    lines = text.lstrip("\ufeff").splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip() == "1. Game Concepts"]
    if len(starts) < 2:
        raise RulesDataError("Could not find CR body after its table of contents")
    dates = _DATE_RE.findall("\n".join(lines[:20]))
    if not dates:
        raise RulesDataError("CR source has no effective date")
    try:
        effective_date = datetime.strptime(dates[0], "%B %d, %Y").date().isoformat()
    except ValueError as exc:
        raise RulesDataError("Invalid CR effective date") from exc
    start = starts[1]
    glossary_start = next((i for i in range(start, len(lines))
                           if lines[i].strip() == "Glossary"), None)
    if glossary_start is None:
        raise RulesDataError("CR body has no glossary")
    end = next((i for i in range(glossary_start + 1, len(lines))
                if lines[i].strip() == "Credits"), None)
    if end is None:
        raise RulesDataError("CR body has no credits section")

    sections, rules = {}, {}
    section, current, in_example = None, None, False
    for line in lines[start:glossary_start]:
        line = line.strip()
        if not line:
            in_example = False
            continue
        match = _SECTION_RE.match(line)
        if match:
            section = match.group(1)
            sections[section] = {"title": match.group(2), "categories": []}
            current = None
            continue
        match = _CATEGORY_RE.match(line)
        if match:
            current = match.group(1)
            rules[current] = {"rule_number": current, "kind": "category",
                              "text": match.group(2), "section": section,
                              "examples": []}
            if section is not None:
                sections[section]["categories"].append(current)
            in_example = False
            continue
        # Subrules must precede the permissive top-level rule regex.
        match = _SUBRULE_RE.match(line) or _RULE_RE.match(line)
        if match:
            current = match.group(1)
            is_subrule = current[-1].isalpha()
            rules[current] = {"rule_number": current,
                              "kind": "subrule" if is_subrule else "rule",
                              "text": match.group(2), "section": section,
                              "category": current.split(".")[0], "examples": []}
            if is_subrule:
                rules[current]["parent"] = current[:-1]
            in_example = False
            continue
        if current and line.startswith("Example:"):
            rules[current]["examples"].append(line[len("Example:"):].strip())
            in_example = True
        elif current and in_example:
            rules[current]["examples"][-1] += " " + line
        elif current and rules[current]["kind"] != "category":
            rules[current]["text"] += " " + line
    if not any(entry["kind"] != "category" for entry in rules.values()):
        raise RulesDataError("CR body contains no numbered rules")
    for number, entry in rules.items():
        entry["see_rules"] = _references(entry["text"], rules, number)

    glossary = {}
    blocks = re.split(r"\n\s*\n", "\n".join(lines[glossary_start + 1:end]).strip())
    for block in blocks:
        parts = [line.strip() for line in block.splitlines() if line.strip()]
        if len(parts) < 2:
            continue
        term, definition = parts[0], "\n".join(parts[1:])
        glossary[term.casefold()] = {"term": term, "text": definition,
                                   "see_rules": _references(definition, rules)}
    if not glossary:
        raise RulesDataError("CR glossary contains no definitions")
    return {"effective_date": effective_date, "sections": sections,
            "rules": rules, "glossary": glossary}


def _parsed(text, cache_dir):
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path = cache_dir / ("parsed-" + digest + ".json")
    cached = _read_json(path)
    if (isinstance(cached, dict) and cached.get("parser_version") == PARSER_VERSION
            and cached.get("sha256") == digest):
        parsed = cached.get("parsed")
        if (isinstance(parsed, dict) and isinstance(parsed.get("rules"), dict)
                and isinstance(parsed.get("glossary"), dict)
                and parsed.get("effective_date")):
            return parsed
    parsed = parse_rules(text)
    _write_json(path, {"parser_version": PARSER_VERSION, "sha256": digest,
                       "parsed": parsed})
    return parsed


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key == "href" and value:
                self.urls.append(value)


def discover_rules_url(html):
    links = _Links()
    links.feed(html)
    urls = links.urls + re.findall(r'https?://[^\s"\'<>]+', html)
    candidates = []
    for value in urls:
        url = quote(urljoin(RULES_URL, unescape(value)), safe=":/?#[]@!$&'()*+,;=%")
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not (host == "wizards.com" or
                                             host.endswith(".wizards.com")):
            continue
        match = _TXT_RE.search(unquote(parsed.path))
        if match:
            try:
                datetime.strptime(match.group(1), "%Y%m%d")
            except ValueError:
                continue
            candidates.append((match.group(1), url))
    if not candidates:
        raise RulesDataError("No Comprehensive Rules TXT link found on " + RULES_URL)
    return max(candidates)[1]


def _text_from_url(url, accept):
    status, text = mtg_tool.http_get_text(url, accept=accept)
    if status >= 400:
        raise mtg_tool.HttpError("HTTP {}: {}".format(status, url))
    return text


def _cached_cr(cache_dir):
    manifest, error = _read_json_report(cache_dir / "current.json")
    if error is not None:
        raise RulesDataError("CR cache manifest " + error)
    if manifest is None:
        return None
    if (not isinstance(manifest, dict) or manifest.get("cache_version") != CACHE_VERSION
            or not re.fullmatch(r"comprehensive-rules-\d{8}\.txt",
                                str(manifest.get("filename", "")))):
        raise RulesDataError("Invalid CR cache manifest")
    path = cache_dir / manifest["filename"]
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise RulesDataError("Cached CR file cannot be read: " + str(path)) from exc
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != manifest.get("sha256"):
        raise RulesDataError("Cached CR file does not match its manifest")
    if not manifest.get("source_url") or not manifest.get("fetched_at"):
        raise RulesDataError("CR cache has no source or fetch timestamp")
    return path, text, manifest


def _document(path, text, cache_dir, manifest=None, warnings=None):
    parsed = _parsed(text, cache_dir)
    verified = manifest is not None
    warnings = list(warnings or [])
    if verified and manifest.get("refresh_error"):
        warnings.append("CR refresh failed; using cached rules: " + manifest["refresh_error"])
    stale = (not verified or bool(manifest.get("refresh_error"))
             or not _fresh(manifest.get("checked_at"), CR_TTL))
    return {"parsed": parsed, "source": "wotc-comprehensive-rules" if verified else "local-cr-file",
            "source_url": manifest.get("source_url") if verified else None,
            "effective_date": parsed["effective_date"],
            "fetched_at": manifest.get("fetched_at") if verified else None,
            "checked_at": manifest.get("checked_at") if verified else None,
            "stale": stale, "freshness": ("stale" if stale else "fresh") if verified else "unknown",
            "refresh_failed_at": manifest.get("refresh_failed_at") if verified else None,
            "rules_file": str(path.resolve()), "warnings": warnings}


def load_document(cache_dir=None, rules_file=None, refresh=False, offline=False):
    cache_dir = Path(cache_dir) if cache_dir is not None else CACHE_DIR
    if refresh and (offline or rules_file is not None):
        raise RulesDataError("--refresh cannot be combined with --offline or --rules-file")
    if rules_file is not None:
        path = Path(rules_file)
        text = path.read_text(encoding="utf-8-sig")
        return _document(path, text, cache_dir, warnings=[
            "Local CR file: freshness and origin are unverified; check the effective date."])
    warnings = []
    try:
        cached = _cached_cr(cache_dir)
        if cached:
            document = _document(*cached[:2], cache_dir, manifest=cached[2])
    except RulesDataError as exc:
        warnings.append(str(exc))
        cached = None
    if offline:
        if not cached:
            detail = "; ".join(warnings) or "no CR cache has been downloaded yet"
            raise RulesDataError("No valid CR cache available in offline mode: " + detail)
        return document
    if cached and not refresh and not document["stale"]:
        return document
    try:
        html = _text_from_url(RULES_URL, "text/html")
        url = discover_rules_url(html)
        text = _text_from_url(url, "text/plain").lstrip("\ufeff")
        # Path.read_text normalizes newlines; hash the same representation.
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        parsed = _parsed(text, cache_dir)
        if cached and parsed["effective_date"] < document["effective_date"]:
            raise RulesDataError("Rules refresh would replace the cached CR with an older version")
        filename = "comprehensive-rules-" + parsed["effective_date"].replace("-", "") + ".txt"
        path = cache_dir / filename
        _atomic_write(path, text)
        timestamp = _now().isoformat()
        manifest = {"cache_version": CACHE_VERSION, "filename": filename,
                    "source_url": url, "fetched_at": timestamp, "checked_at": timestamp,
                    "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        _write_json(cache_dir / "current.json", manifest)
        return _document(path, text, cache_dir, manifest, warnings)
    except (mtg_tool.MtgToolError, RulesDataError) as exc:
        if not cached:
            if warnings:
                raise RulesDataError("{}; prior cache state: {}".format(exc, "; ".join(warnings))) from exc
            raise
        manifest = dict(cached[2], refresh_error=str(exc), refresh_failed_at=_now().isoformat())
        _write_json(cache_dir / "current.json", manifest)
        return _document(cached[0], cached[1], cache_dir, manifest, warnings)


def query_rules(document, mode, value, limit=20, section=False):
    if limit < 1:
        raise RulesDataError("Query limit must be positive")
    parsed = document["parsed"]
    value = value.strip()
    if not value:
        raise RulesDataError("Query must not be empty")
    referenced = []
    if mode == "rule":
        number = value.rstrip(".")
        matches = [entry for key, entry in parsed["rules"].items()
                   if key == number or (section and (key.startswith(number + ".")
                                                    or entry.get("parent") == number))]
    elif mode == "term":
        entry = parsed["glossary"].get(value.casefold())
        matches = [entry] if entry else []
        if entry:
            referenced = [parsed["rules"][number] for number in entry["see_rules"]
                          if number in parsed["rules"]]
    elif mode == "grep":
        try:
            pattern = re.compile(value, re.I)
        except re.error as exc:
            raise RulesDataError("Invalid regular expression: " + str(exc)) from exc
        matches = [entry for entry in parsed["rules"].values()
                   if pattern.search(entry["rule_number"] + " " + entry["text"])]
    else:
        raise RulesDataError("Unknown query mode: " + mode)
    result = {key: val for key, val in document.items() if key != "parsed"}
    result.update({"status": "ok" if matches else "not_found",
                   "query": {"mode": mode, "value": value, "section": section},
                   "matches": matches[:limit], "match_count": len(matches),
                   "truncated": len(matches) > limit, "referenced_rules": referenced})
    return result


def _scryfall_json(url, params=None, use_cache=False):
    status, payload = mtg_tool.http_get_json(url, "scryfall", params, use_cache=use_cache)
    if status == 404 and isinstance(payload, dict) and payload.get("code") == "not_found":
        raise mtg_tool.CardNotFound(payload.get("details") or "Card not found")
    if status >= 400:
        raise mtg_tool.HttpError("Scryfall HTTP {}: {}".format(status, url))
    if not isinstance(payload, dict):
        raise RulesDataError("Scryfall returned a non-object response")
    return payload


def _validate_rulings(entries):
    if not isinstance(entries, list):
        raise RulesDataError("Scryfall rulings data is not a list")
    for entry in entries:
        if (not isinstance(entry, dict) or not isinstance(entry.get("comment"), str)
                or not isinstance(entry.get("published_at"), str)):
            raise RulesDataError("Scryfall returned a malformed ruling")


def _rulings_result(cached):
    result = {key: val for key, val in cached.items() if key not in ("cache_version", "refresh_error")}
    warnings = []
    if cached.get("refresh_error"):
        warnings.append("Rulings refresh failed; using cached notes: " + cached["refresh_error"])
    stale = bool(cached.get("refresh_error")) or not _fresh(cached.get("fetched_at"), RULINGS_TTL)
    result.update({"status": "ok", "source": "scryfall-rulings", "effective_date": None,
                   "stale": stale, "freshness": "stale" if stale else "fresh",
                   "ruling_count": len(cached["rulings"]), "warnings": warnings})
    return result


def lookup_rulings(name, cache_dir=None, refresh=False, offline=False):
    if refresh and offline:
        raise RulesDataError("--refresh cannot be combined with --offline")
    name = name.strip()
    if not name:
        raise RulesDataError("Card name must not be empty")
    cache_dir = Path(cache_dir) if cache_dir is not None else CACHE_DIR
    key = hashlib.sha256(name.casefold().encode("utf-8")).hexdigest()
    path = cache_dir / "rulings" / (key + ".json")
    cached, read_error = _read_json_report(path)
    invalid_reason = ("rulings cache " + read_error) if read_error is not None else None
    if cached is not None:
        try:
            if not isinstance(cached, dict):
                raise RulesDataError("Rulings cache is not a JSON object")
            query_name = cached.get("query_name")
            if (cached.get("cache_version") != CACHE_VERSION
                    or not isinstance(query_name, str)
                    or query_name.casefold() != name.casefold()
                    or not all(cached.get(field) for field in
                               ("name", "oracle_id", "card_id", "source_url", "fetched_at"))):
                raise RulesDataError("Invalid rulings cache")
            _validate_rulings(cached.get("rulings"))
        except RulesDataError as exc:
            invalid_reason = str(exc)
            cached = None
    if offline:
        if not cached:
            message = "No valid rulings cache available in offline mode: " + name
            if invalid_reason:
                message += " (" + invalid_reason + ")"
            raise mtg_tool.HttpError(message)
        return _rulings_result(cached)
    if (cached and not refresh and not cached.get("refresh_error")
            and _fresh(cached.get("fetched_at"), RULINGS_TTL)):
        return _rulings_result(cached)
    try:
        # The rulings cache owns freshness for both the identity and its notes.
        card = _scryfall_json(mtg_tool.SCRYFALL_BASE + "/cards/named", {"exact": name})
        if card.get("object") != "card" or not card.get("id") or not card.get("oracle_id"):
            raise RulesDataError("Scryfall card response has no card/oracle identity")
        if not mtg_tool.name_matches(name, card):
            raise mtg_tool.CardNotFound("Exact card name did not match: " + name)
        url = mtg_tool.SCRYFALL_BASE + "/cards/" + card["id"] + "/rulings"
        page, entries = _scryfall_json(url), []
        for _ in range(mtg_tool.MAX_PAGES):
            if page.get("object") != "list" or not isinstance(page.get("has_more"), bool):
                raise RulesDataError("Scryfall rulings response is not a complete List object")
            _validate_rulings(page.get("data"))
            entries.extend(page["data"])
            if not page["has_more"]:
                break
            next_url = page.get("next_page")
            if not isinstance(next_url, str) or not next_url.startswith(mtg_tool.SCRYFALL_BASE + "/"):
                raise mtg_tool.PaginationIncomplete("Rulings pagination has no valid next_page")
            page = _scryfall_json(next_url)
        else:
            raise mtg_tool.PaginationIncomplete("Rulings pagination exceeded the page limit")
        cached = {"cache_version": CACHE_VERSION, "query_name": name, "name": card["name"],
                  "oracle_id": card["oracle_id"], "card_id": card["id"],
                  "source_url": url, "fetched_at": _now().isoformat(), "rulings": entries}
        _write_json(path, cached)
        result = _rulings_result(cached)
        if invalid_reason:
            result["warnings"].append(
                "Rulings cache discarded as invalid: " + invalid_reason)
        return result
    except mtg_tool.CardNotFound:
        raise
    except (mtg_tool.MtgToolError, RulesDataError) as exc:
        if not cached:
            if invalid_reason:
                raise mtg_tool.HttpError("{}; prior rulings cache: {}".format(
                    exc, invalid_reason)) from exc
            raise
        cached = dict(cached, refresh_error=str(exc), refresh_failed_at=_now().isoformat())
        _write_json(path, cached)
        return _rulings_result(cached)


def _positive_int(value):
    value = int(value)
    if value < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (("fetch", "Download/check the latest Comprehensive Rules"),
                               ("rule", "Look up a CR number"),
                               ("term", "Look up a glossary term and its cited rules"),
                               ("grep", "Search rule numbers/text with a regex"),
                               ("rulings", "Look up per-card Scryfall rulings")):
        child = sub.add_parser(command, help=help_text)
        if command != "fetch":
            child.add_argument("value", help="Card name, rule number, term or regex")
        child.add_argument("--cache-dir", type=Path, default=None)
        child.add_argument("--offline", action="store_true", help="Use local data only")
        child.add_argument("--refresh", action="store_true", help="Force source revalidation")
        child.add_argument("--json", action="store_true", dest="as_json")
        child.add_argument("--out", type=Path, help="Write the result envelope as JSON")
        if command in ("rule", "term", "grep"):
            child.add_argument("--rules-file", type=Path, help="Query a specific local CR version")
            child.add_argument("--limit", type=_positive_int, default=20)
        if command == "rule":
            child.add_argument("--section", action="store_true", help="Include descendant rules")
    return parser


def _emit(result, args):
    if args.out:
        _write_json(args.out, result)
    for warning in result.get("warnings", []):
        print("[warn] " + warning, file=sys.stderr)
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif "error" in result:
        print("[error] " + result["error"]["message"], file=sys.stderr)
    else:
        print("Source: {} | effective: {} | freshness: {}".format(
            result["source"], result.get("effective_date") or "n/a", result["freshness"]))
        print("URL: " + (result.get("source_url") or "local file"))
        if args.command == "fetch":
            print("{} | {} rules, {} terms".format(result["rules_file"],
                                                   result["rule_count"], result["term_count"]))
        elif args.command == "rulings":
            print("{}: {} rulings".format(result["name"], result["ruling_count"]))
            for entry in result["rulings"]:
                print("{} [{}]: {}".format(entry["published_at"], entry.get("source", "unknown"),
                                           entry["comment"]))
        else:
            for entry in result["matches"] + result["referenced_rules"]:
                print("{}: {}".format(entry.get("rule_number") or entry.get("term"), entry["text"]))
                for example in entry.get("examples", []):
                    print("  Example: " + example)
            if result["status"] == "not_found":
                print("No matching rule or glossary term.")
            if result["truncated"]:
                print("Showing {} of {} matches; increase --limit to see more.".format(
                    len(result["matches"]), result["match_count"]))
    runlog.log_run("mtg_rules_tool", "warning" if result.get("stale") else result["status"],
                   "{} status={} source={} out={}".format(args.command, result["status"],
                   result.get("source", "unknown"), str(args.out or "stdout")))


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "rulings":
            result = lookup_rulings(args.value, args.cache_dir, args.refresh, args.offline)
        else:
            document = load_document(args.cache_dir, getattr(args, "rules_file", None),
                                     args.refresh, args.offline)
            if args.command == "fetch":
                result = {key: val for key, val in document.items() if key != "parsed"}
                result.update({"status": "ok", "rule_count": len(document["parsed"]["rules"]),
                               "term_count": len(document["parsed"]["glossary"])})
            else:
                result = query_rules(document, args.command, args.value, args.limit,
                                     getattr(args, "section", False))
        code = 3 if result["status"] == "not_found" else 0
    except mtg_tool.CardNotFound as exc:
        result, code = {"status": "not_found", "error": {"type": type(exc).__name__, "message": str(exc)}}, 3
    except (mtg_tool.MtgToolError, OSError, ValueError) as exc:
        result = {"status": "error", "error": {"type": type(exc).__name__, "message": str(exc)}}
        code = 1 if isinstance(exc, mtg_tool.MtgToolError) else 2
    try:
        _emit(result, args)
    except OSError as exc:
        print("[error] Could not write output: " + str(exc), file=sys.stderr)
        runlog.log_run("mtg_rules_tool", "error", str(exc))
        return 2
    return code


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(runlog.run_logged("mtg_rules_tool", main))
