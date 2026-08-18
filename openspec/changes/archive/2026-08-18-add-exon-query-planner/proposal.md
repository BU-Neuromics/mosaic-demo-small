# Change: Exon — an NL query-composition assistant for this schema

## Why

A GUI query builder expressive enough to compose a complex query on this schema — pick a class,
possibly nested several hops down, filter it, pull in related data — doesn't hide the schema's
complexity, it just re-renders it as a wall of options (the CAD-tool problem: a tool meant to aid
you derails you once it exposes everything at once). Designing that builder well is itself a hard
problem: many classes, a query centered on any one of them, arbitrary nesting depth.

The better fit is a natural-language assistant — **Exon** — that a user can ask directly, e.g.
verbatim: *"Hi Exon, bring me back all of the brain tissue samples that we have for the {brain
region(s) that makes sense given our data} with the {donor attribute(s) that makes sense given our
data} and also possibly any rnaSeq data associated with them."* Same idea as asking Alexa to set an
alarm: natural language in, a correct, bounded action out — not a picker UI.

This change builds the first working slice of Exon, entirely within this repo, against this
repo's own schema and live data. It does **not** depend on or borrow architecture from any other
component or repo (in particular, not `BU-Neuromics/reel` — a separate, differently-scoped
component; conflating the two in an earlier draft of this change was a mistake, corrected here).

Two live-verified platform facts shape what Exon can rely on today, found while grounding this
change in the real schema/API rather than assumptions:

1. `relatedTo(id, relationshipType)` (mosaic#146/PR#147, merged 2026-08-01, unreleased) now
   answers "does a relationship exist" for the multivalued/relationships-table-backed reference
   Exon's driving example needs (sample → RNA-seq workflow) — previously impossible. It takes no
   predicate on the referenced entity's own fields, so "workflows of type `rna_seq` that
   reference this sample" needs the existence call plus a small, bounded client-side filter — not
   a single composed query, but not a blocked question either.
2. **The GraphQL list filter's `field` argument silently requires the snake_case LinkML slot
   name** (e.g. `sample_type`), not the GraphQL-exposed camelCase field name (`sampleType`) — a
   mismatch returns a valid-shaped, empty result, not an error. This is exactly the kind of
   silent-wrong-answer failure Exon's dry-run validator must never let through, and it isn't
   catchable by ordinary schema-conformance checks (the camelCase name *is* a valid field on the
   GraphQL type). This is not a regression: this repo's own executable benchmark question (q05)
   already uses the correct snake_case form and is verified working (`total: 50`); the
   already-archived spec's illustrative prose example uses the camelCase form instead and, as far
   as can be determined, was never executed in that exact form — a documentation error confined
   to the spec's prose, not a change in platform behavior.

## What Changes

- Refresh this repo's capability manifest against current upstream Mosaic (`../hippo` pulled to
  `origin/main`, now includes `relatedTo`).
- **MODIFIED**: correct `small-demo-schema`'s "RNA-seq dataset availability... not server-side
  composable" scenario to reflect `relatedTo`'s existence-lookup capability and its narrower
  remaining predicate gap.
- **MODIFIED**: correct `query-benchmark`'s capability-gap requirement and reclassify benchmark
  questions q24/q25 from `blocked` (citing the now-closed mosaic#146) to their ordinary traversal
  capability — both are achievable via bounded per-id `relatedTo` calls, never an unfiltered scan.
- **ADDED**: a new `exon-query-planner` capability — a schema-grounded LLM query planner in this
  repo (`exon/`) that takes one NL instruction, produces typed query ops grounded in live
  `hippoSchema` (never in assumed field-name casing), dry-run validates the plan against the live
  capability manifest, executes it against this repo's GraphQL endpoint, and returns the raw
  result. One-shot (one instruction in, one validated result out) — not a multi-turn conversation
  engine.
- Run Exon end-to-end on the project's own driving example (the verbatim quote above).
- Filed two new upstream `BU-Neuromics/mosaic` issues: (a) no
  predicate/filter argument on `relatedTo`; (b) filter `field` silently needs the snake_case slot
  name, with no documentation and no error on mismatch.

## Non-Goals

- No dependency on `BU-Neuromics/reel`, its ADRs, or its instruction-path/data-story model. Exon
  is this project's own, independently-scoped assistant.
- No GUI query builder.
- No multi-turn conversation, rewind/edit, as-of watermark reproducibility, or rendering/View
  Contract — v1 is one NL instruction → one validated result.
- No aggregation (group-by/count/sort/range) — still unsupported upstream (mosaic#96, open); the
  validator rejects plans needing it rather than approximating.

## Impact

- Affected specs (this repo): `small-demo-schema` (1 modified requirement), `query-benchmark`
  (2 modified requirements), new `exon-query-planner` capability (this change).
- Affected code (this repo): `evals/schema/*.json` regenerated; `evals/questions.yaml` /
  `expected-results.json` updated for reclassified questions; new `exon/` package.
- External: two new upstream Mosaic issues filed (mosaic#148, mosaic#149).
- No breaking changes to this repo's schema or data. No other repo touched.
