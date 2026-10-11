# Registered guide claims

Store claims beside a versioned deck/guide or in `AuditReport/`; generated files
remain local. Use version `1` with `counts`, `loops`, and/or `rules` lists. Give
every claim a distinct `id`. Empty claims and unknown group names are errors.

Counts are recomputed from the deck. `sections` defaults to `["main"]`; supported
sections are `main`, `sideboard`, `commander`, `companion`. Optional `cards` filters
by the exact English names in the deck, `type_pattern` filters current card types,
and `unique: true` counts identities rather than copies. The default face is
`front`; explicitly use `face: "any"` for a count of DFC land options. For
conditional sources, independently identify the applicable card names and
conditions rather than treating all lands/colored pips as usable sources.

Each numeric claim supplies `text_patterns`, regular expressions with a named
integer capture `(?P<value>...)`. Register separate wording used in summaries and
body sections. All matches are checked; missing patterns and repeated values
that disagree fail. The supplied pattern controls coverage, so the review skill
must inventory the guide before trusting the result.

Loops declare nonnegative integer `initial` resources, `iterations` (default 3,
max 1000) and ordered `steps`. Each step has a real deck `card`, an exact
`oracle_quote`, and optional `require`, `pay`, `gain` maps. Requirements and
payments use the pre-step state; gains use the state after payments. All gain
expressions are evaluated before applying those gains. Resource names must be
declared initially. Expressions support integers, resource names, `+`, `-`, `*`,
`//` and parentheses; calls, attributes and other operations are rejected.
Expression bounds do not imply gameplay bounds.

Use a `resource` and `metric`: `final` compares the final amount, `net` compares
the change after all iterations, and `per_cycle` requires the same net gain each
cycle. A varying or depleted loop fails a constant-yield claim. Negative net
numbers can be captured with `-?\d+` in the guide pattern. `infinite_proven` is
always false: the model is an arithmetic helper, and a reviewer must check its
semantics and finite-resource assumptions separately.

Rules specify `number` and exact `quote`. Both must appear in the guide, and the
quote must occur in that current CR rule's text after whitespace normalization.
The tool checks reference integrity, not the validity of an inference or a
translation. Stale/unknown source evidence returns `incomplete` rather than
`pass`.

Minimal example:

```json
{
  "version": 1,
  "counts": [{
    "id": "main-total",
    "sections": ["main"],
    "text_patterns": ["Main deck: (?P<value>\\d+) cards"]
  }]
}
```

The deterministic fixture `tools/testdata/guide_claims_sample.json` demonstrates
the loop schema with synthetic cards; it is test data, not a valid MTG combo.
Use actual card names and independently verified Oracle clauses for real guides.

CLI exit codes: `0` registered checks pass, `1` network failure, `2` input or
evidence incomplete, `4` registered claims fail. `--offline` forbids network;
Oracle evidence is under `tools/cache/card_facts/`, CR under `tools/cache/rules/`.
JSON output preserves findings and their line numbers, resource states, evidence
and the coverage limit. `--out` also records business/input failures.
