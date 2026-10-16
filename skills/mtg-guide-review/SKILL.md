---
name: mtg-guide-review
description: Verify an MTG deck's strategy guide before delivery or after edits, independently checking card counts, combo resource arithmetic, Oracle/CR citations and repeated claims across sections. Preserve the deck; this is a review of the guide's factual claims.
---

# MTG Guide Review

Use the final versioned deck and its matching guide. Read the whole guide and
inventory its numerical and rules-dependent claims: card/land/source counts,
loop costs and yields, turn sequences, summoning sickness, triggers, replacement
effects, layers and commander/companion conditions. Include claims repeated in
the summary, body, sideboard instructions and quick reference.

Recalculate independently from `deck_model`'s parsed quantities and current
Oracle text. A land option on a modal DFC is not automatically a front-face land,
and a conditional color source is not an unconditional source. Record the exact
cards/conditions supporting these counts. For an explicit postboard line, use
the postboard deck and retain its companion restrictions.

For combo arithmetic, write out each payment and yield in resolution order,
track finite resources, and simulate several iterations, including the initially
break-even case. Verify that your model matches each card's actual abilities,
zones, legal targets, restrictions and costs; an Oracle quotation alone does
not establish that your interpretation is correct. Finite simulations do not
prove an infinite loop. Turn claims require the project's actual simulator/log
evidence under the existing deck workflow.

Use `skills/mtg-rules/SKILL.md` to query every rule number and load-bearing rule
quotation, and check applicability separately. Use Spellbook results as evidence
to inspect, not as automatic approval of a line. Clearly distinguish unavailable
or stale evidence from factual errors.

For machine-checkable counts, quotations and resource models, register claims
in a local JSON file following [references/claims.md](references/claims.md),
then run:

```powershell
python tools/mtg_guide_audit.py deck.txt guide.md --claims guide.claims.json --out AuditReport/guide_audit.json
```

The tool matches all registered numeric patterns across the guide and reports
wrong values, inconsistent repetitions, missing text, unpaid resources and
quotation mismatches. Its `pass` covers registered claims only; inspect
`coverage`, `semantic_review_required`, stale evidence and omitted claims before
completing your own full-guide review. Do not use its output to certify an entire
guide automatically. The tool uses exact quotations; verify translated claims
against source text during the semantic pass.

Fix each finding in all locations, re-read any new supporting rule, and rerun
only checks affected by the edits. Report unresolved or unchecked claims with
their locations and needed evidence. Write an audit note beside the deck/guide
with verified items, corrected errors and remaining limitations. Review does
not authorize deck changes or publishing artifacts.
