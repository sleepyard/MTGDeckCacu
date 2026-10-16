"""Conservative, directional Oracle hints for constructed candidate ranking.

Signals connect an action/resource producer to an explicit payoff. They are
heuristics for ordering candidates, not rules validation or combo discovery.
"""
import re


PATTERNS = {
    "mutate": (r"\bmutate\b", r"\bmutates\b|if it has mutate"),
    "tokens": (r"\bcreate\b[^.\n]*\btoken", r"tokens? you control (?:get|have)|whenever you create|whenever[^.\n]*token[^.\n]*enters"),
    "counters": (r"\bput\b[^.\n]*\+1/\+1 counters?", r"whenever[^.\n]*counters?[^.\n]*(?:put|placed)|with (?:a |one or more )?\+1/\+1 counters?|for each[^.\n]*counter"),
    "graveyard": (r"(?:^|[.\n] )mill (?:\w+|\d+) cards?\b|\byou mill\b|draw[^.\n]*then discard", r"(?:from|in) your graveyard"),
    "artifacts": (None, r"artifacts? you control|artifact spells?|affinity for artifacts|whenever[^.\n]*artifact[^.\n]*enters"),
    "lifegain": (r"\b(?:you )?gain (?:\d+|one|two|three|four|five|x|that much) life", r"whenever you gain life|if you gained life"),
}
LABELS = {"mutate": "合变", "tokens": "衍生物", "counters": "+1/+1指示物",
          "graveyard": "自身坟场", "spells": "非生物咒语", "artifacts": "神器", "lifegain": "回血"}


def _text(card):
    text = card.get("oracle_text")
    if text is None:
        text = "\n".join(face.get("oracle_text", "") for face in card.get("card_faces", []))
    return str(text or "").lower().replace("’", "'")


def _types(card):
    faces = card.get("card_faces") or []
    return str((faces[0] if faces else card).get("type_line") or card.get("type_line") or "").split(" // ")[0]


def signals(card):
    text, types = _text(card), _types(card)
    produced, rewarded = set(), set()
    for key, (source, payoff) in PATTERNS.items():
        if source and re.search(source, text):
            produced.add(key)
        if re.search(payoff, text):
            rewarded.add(key)
    if types and "Land" not in types and "Creature" not in types:
        produced.add("cast:noncreature")
    for kind in ("instant", "sorcery"):
        if kind.title() in types:
            produced.add("cast:" + kind)
    for phrase in re.findall(r"whenever you cast (?:an? )?([a-z ]+?) spell", text):
        if phrase in ("instant", "sorcery", "noncreature", "instant or sorcery"):
            rewarded.update("cast:" + kind for kind in phrase.split(" or "))
    if "Artifact" in types:
        produced.add("artifacts")
    if "Creature" in types:
        parts = re.split(r"\s(?:—|-)\s", types, maxsplit=1)
        if len(parts) == 2:
            produced.update("type:" + subtype.lower() for subtype in parts[1].split())
    # Match explicit tribe rewards, not two creatures merely sharing a type.
    words = re.findall(r"\b([a-z]+) (?:creatures? you control|you control (?:get|have)|spells? you cast)", text)
    singular = {"elves": "elf", "dwarves": "dwarf", "wolves": "wolf", "mice": "mouse", "allies": "ally"}
    for word in words:
        tribe = singular.get(word, word[:-1] if word.endswith("s") else word)
        if tribe not in {"creature", "artifact", "token", "permanent", "spell", "other", "noncreature"}:
            rewarded.add("type:" + tribe)
    return produced, rewarded


def score_candidate(card, context):
    """Return bounded score and named supporting cards, ignoring self-pairs."""
    produced, rewarded = signals(card)
    matches = {}
    for other in context:
        if str(other.get("name", "")).casefold() == str(card.get("name", "")).casefold():
            continue
        other_produced, other_rewarded = signals(other)
        for key in (produced & other_rewarded) | (rewarded & other_produced):
            key = "spells" if key.startswith("cast:") else key
            matches.setdefault(key, []).append(str(other.get("name") or "?"))
    evidence = []
    for key, names in sorted(matches.items()):
        label = key[5:] + "类别" if key.startswith("type:") else LABELS[key]
        evidence.append({"signal": key, "label": label, "cards": sorted(set(names))[:3]})
    return {"score": min(2.0, 0.75 * len(matches)), "evidence": evidence}
