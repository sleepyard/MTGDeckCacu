# Registered guide claims

Store claims beside a versioned deck/guide or in `AuditReport/`; generated files
remain local. Use version `1` with `counts`, `loops`, and/or `rules` lists. Give
every claim a distinct `id`. Empty claims and unknown group names are errors.

Unknown keys inside a claim are also errors (the tool reports the key, the group,
and the claim's position/id), so a misspelled optional key cannot silently fall
back to a default. Allowed keys per group:

- `counts` (required: `id`, `text_patterns`): `sections`, `cards`,
  `type_pattern`, `face`, `unique`
- `loops` (required: `id`, `initial`, `steps`, `resource`, `text_patterns`):
  `iterations`, `metric`. Each step allows `card`, `oracle_quote`, `require`,
  `pay`, `gain` and requires `card` plus `oracle_quote`
- `rules` (required: `id`, `number`, `quote`): no optional keys

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
max 1000) and ordered `steps`. A loop may declare at most 100 steps. Each step has
a real deck `card`, an exact
`oracle_quote`, and optional `require`, `pay`, `gain` maps. Requirements and
payments use the pre-step state; gains use the state after payments. All gain
expressions are evaluated before applying those gains. Resource names must be
declared initially. Expressions support integers, resource names, `+`, `-`, `*`,
`//` and parentheses; calls, attributes and other operations are rejected. Each
expression must be at most 200 characters, and every computed `require`/`pay`/
`gain` value must be nonnegative — a step expression evaluating to a negative
number is an input error, not a deficit. This applies to the expressions
themselves; a negative *net* result compared against the guide text is still
capturable (see below). Expression bounds do not imply gameplay bounds.

Use a `resource` and `metric`; `metric` defaults to `final` when omitted. `final`
compares the final amount, `net` compares
the change after all iterations, and `per_cycle` requires the same net gain each
cycle. A varying or depleted loop fails a constant-yield claim. Negative net
numbers can be captured with `-?\d+` in the guide pattern. `infinite_proven` is
always false: the model is an arithmetic helper, and a reviewer must check its
semantics and finite-resource assumptions separately.

Rules specify `number` and exact `quote`. Both must appear in the guide, and the
quote must occur in that current CR rule's text after whitespace normalization.
Number matching accepts the number itself or the number plus lowercase subrule
letters, so citing `603.3b` also satisfies a `603.3` claim, but a longer number
such as `603.10` never satisfies a `603.1` claim. When the number is cited in
more than one place, every citation must agree (a body citing `603.3` and a
quick-reference table citing `603.3b` is an `inconsistent_repetition` finding),
and any line that cites the number with prose after it must carry the registered
quote, so a summary that paraphrases or garbles the quote is also caught.
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
