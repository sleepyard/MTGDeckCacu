---
name: mtg-combo
description: Find MTG combo candidates through Commander Spellbook, checking component quantities, mainboard/sideboard/commander zones, target format and platform. Use for combo builds, missing-piece discovery or auditing an existing deck's claimed combos.
---

# MTG Combo

Run from the repository root with Python 3.7+ and the standard library:

```powershell
python tools/mtg_combo_tool.py search deck.txt --format pioneer --platform arena --out AuditReport/combos.json
python tools/mtg_combo_tool.py search deck.txt --postboard swapped.txt --format pioneer --platform arena
python tools/mtg_combo_tool.py discover --card "All Will Be One" --format pioneer --platform arena --limit 10
```

`discover` accepts repeated `--card`, an optional `--result` outcome, and optional
`--colors WUBRG`. `--offline` uses saved evidence only; `--refresh` revalidates
Spellbook and Oracle evidence. Do not combine them. The JSON output preserves
component quantities, zone/state requirements, prerequisites, steps, costs,
results, source URLs and current card legality/platform evidence.

Interpret groups by their exact scope:

- `main_available`: named and supported generic components are present in the
  mainboard/commander zone. This does not establish a currently executable line.
- `sideboard_candidates`: components fit somewhere in the full main+sideboard
  pool. Work out explicit cuts/adds before claiming a postboard combo.
- `postboard_available`: components fit a supplied postboard list that conserves
  original zone counts and total inventory. Run the existing final deck/companion
  legality checks on the swap plan as well.
- `missing_components`: lists absent copy quantities or unmet generic templates.
- `needs_verification`: unsupported templates, commander mismatches, missing
  steps, stale evidence or unknown legality prevent a firm availability claim.
- `excluded`: card legality, platform or commander-color constraints fail.

Companion cards are retained in the model but not automatically treated as active
combo components. Supported generic templates use conservative AND-only type,
Oracle text and keyword predicates. Complex syntax stays unverified; do not
interpret it as impossible. Different template ingredients need distinct card
copies, and named ingredients also consume copies.

`--limit` caps analyzed candidates, prioritizing format-compatible results and
then API included groups before near misses. Inspect `truncated` and
`unexamined_variant_count`; a limited result is not an exhaustive combo audit.
Empty successful results and query errors are separate. Spellbook coverage is
not complete, and its missing/empty result does not disprove an independently
verified interaction.

Before recommending a combo, read its actual Oracle text, prerequisites, zones
and steps, then use `skills/mtg-rules/SKILL.md` for relevant CR/rulings evidence.
Re-derive payments, resource yields, triggers and timing. Keep Spellbook's stated
outcome separate from your rules-verified conclusion. For delivery, apply
`skills/mtg-guide-review/SKILL.md` to every resulting numerical/rules claim.
