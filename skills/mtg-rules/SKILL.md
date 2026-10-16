---
name: mtg-rules
description: Verify MTG rules questions and card interactions using versioned Comprehensive Rules text and Scryfall per-card rulings. Use for stack, timing, keyword, replacement-effect and layer questions, or rules claims in deck reports.
---

# MTG Rules

Run commands from the repository root. `tools/mtg_rules_tool.py` uses Python 3.7+
and the standard library; no upstream skill installation or card bulk download
is required. See `tools/README.md` for caching, JSON fields and exit codes.

Start with the narrowest useful query:

```powershell
python tools/mtg_rules_tool.py rulings "Card Name" --json
python tools/mtg_rules_tool.py term trample --json
python tools/mtg_rules_tool.py rule 702.19 --section --json
python tools/mtg_rules_tool.py grep "replacement effect" --limit 10 --json
```

The first CR query downloads the latest TXT linked by Wizards' rules page.
`fetch --refresh` forces a check; `--offline` forbids network access.
`--rules-file path/to/comprehensive-rules.txt` selects a historical or supplied
local version whose freshness and origin are reported as unknown.

For a specific card interaction, verify the Oracle text through the existing
`mtg_tool.py` card search/check, read per-card rulings, and query the relevant CR
terms or rule numbers. Use `rule NUMBER --section` when a category heading alone
does not explain the interaction. A glossary query includes the rules it cites.
Check `truncated` and increase `--limit` when needed.

Ground rule numbers and quotations in tool output. Distinguish the cited rule
from your reasoning about its application; a matching keyword alone does not
prove an interaction. State the verdict, relevant conditions and concise source
citations, including the CR effective date. For combo claims, independently
derive costs, yields, timing and finite resources from the verified card text.

Inspect `status`, `source`, `effective_date`, `fetched_at`, `freshness`, `stale`
and `warnings` before using a result. `not_found` means the lookup succeeded
without a match; `error` means no usable answer was obtained. Successful empty
per-card rulings mean no notes were returned, not that any proposed play is legal.
If refresh fails, cached data carries a warning and `stale: true`; name that
limitation when using it and avoid presenting it as the current verified rule.

Only official CR files and Scryfall rulings are queried by this tool. Arena
digital mechanics may have no CR entry; use current official Arena material and
card text as separate evidence, without inventing CR numbers. Queries support
rules analysis; existing legality, Chinese-name, rotation and delivery gates
continue to apply to deck work.
