# Change: Add a Mosaic-hosted MCP query boundary; retire Exon's local QueryPlan pipeline in favor of it

## Why

Exon (`add-exon-mcp-boundary`, superseded by this change) proposed hosting the MCP boundary inside
Exon itself, wrapping Exon's own `QueryPlan` → validator → executor pipeline. That design was
correct given what was known when it was drafted, but a follow-up cross-repo brainstorm surfaced
two things that change the right answer:

1. **A real, present-tense duplication/drift problem, not a hypothetical one.** Three places
   independently maintain "what can this Mosaic deployment do": Mosaic has no capability-manifest
   concept of its own (only raw `hippoSchema` introspection); Exon hand-maintains
   `evals/schema/capabilities.json` by probing Mosaic from outside; Aperture derives its own
   `Capabilities` object from live introspection independently. This is not speculative —
   Aperture's own accepted ADR-0029 already asserts "no facet counts, no server sort, no range
   filters" against Mosaic, an assumption this project's own live verification (this session)
   proved **already false**. Reel's own open design question DS-2 ("does Mosaic support
   relationship-existence/join filters and group-by+count?") is likewise already answered — yes,
   as of Mosaic's `where:` relationship-predicate rollout — but Reel's designers don't know it.
2. **Exon's `QueryPlan` vs. Aperture's `QuerySpec` is a timing artifact, not a principled
   divergence.** `QueryPlan` is an ordered, multi-step pipeline built around a bounded `relatedTo`
   fan-out — a necessary workaround for a Mosaic that didn't yet support relationship predicates.
   Aperture's `QuerySpec` (ADR-0035, accepted 2026-08-19) was explicitly co-designed with Mosaic's
   own capability rollout (Mosaic ADR-0006 "typed filter contract," tracked mosaic#153; Mosaic
   ADR-0007 "aggregation & ordering," tracked mosaic#154; implemented via Mosaic OpenSpec changes
   `typed-filter-inputs`/`aggregation-and-ordering`/`search-composition`/`heterogeneous-roots`,
   tracked mosaic#155–#158 — all six issues confirmed **closed** in the upstream `hippo` repo).
   `QuerySpec`'s normative shape (a single declarative anchor + criteria tree, with `columns`
   selection including an explicit `aggregate`-vs-`explode` choice on to-many paths) already covers
   everything `QueryPlan` covers, and more. Exon simply wasn't part of that co-design loop. The
   right fix is not a third, arbitrating IR — it's for Exon to adopt `QuerySpec`'s already-designed
   shape.

Given both findings, the smallest coherent fix that doesn't leave Exon permanently out of sync with
where Mosaic and Aperture have already converged is to move the query-planning boundary to where
the schema authority already lives — Mosaic — and have Exon become a client of it, the same way a
future Reel engine or Aperture's own `QuerySpec` builder could.

## What Changes

- **Mosaic hosts an MCP server** (new, external to this repo — see "Impact" and the
  `mosaic-query-boundary-contract` capability below) exposing live schema/capability resources and
  `validate_query_spec`/`execute_query_spec` tools, implementing the same total,
  introspection-driven, reject-not-approximate discipline Aperture's client-side
  `validateQuerySpec()` already demonstrates, but server-side in Python, with `enumValues` and the
  rest of `hippoSchema` available in-process (no introspection round-trip).
- **Exon's planner (`planner.py`) is retargeted** to emit a `QuerySpec`-shaped artifact instead of
  the current `QueryPlan` steps-array, and Exon becomes a thin MCP client of Mosaic's new boundary.
- **`exon/validator.py`, `exon/executor.py`, and `exon/ops.py` are retired** once Mosaic's boundary
  ships — their reject-don't-approximate logic and enum-value-validation responsibility move to
  Mosaic's `validate_query_spec`, which is a strictly better home for it (in-process schema access
  vs. Exon's live-but-remote introspection fetch).
- **This has a hard dependency, stated explicitly rather than glossed over**: Exon cannot retire
  its local pipeline before Mosaic's boundary exists and ships. The two are sequenced, not
  parallel, in `tasks.md`.
- **`add-exon-mcp-boundary` is marked superseded** (not deleted — it remains accurate decision
  history, including its enum-value-gap finding and its two upstream-status corrections, which
  this change carries forward).
- **No implementation in this change** — proposal, design, spec deltas, and tasks only, matching
  the standing "create the OpenSpec only" instruction. In particular, nothing in Mosaic's or
  Aperture's own repositories is implemented here — see the `mosaic-query-boundary-contract`
  capability, which states this repo's dependency on Mosaic's future behavior as an explicit
  external contract rather than pretending to schedule or own that work.

## Impact

- **Affected specs (this repo)**: `exon-query-planner` (MODIFIED — plan shape changes from
  `QueryPlan` to `QuerySpec`; validation delegates to Mosaic instead of running locally),
  `exon-mosaic-mcp-client` (ADDED — Exon's role as an MCP client, replacing the superseded
  `exon-mcp-boundary` framing where Exon hosted the server), `mosaic-query-boundary-contract`
  (ADDED — the external contract this repo depends on Mosaic satisfying; not implementable from
  this repo).
- **Affected code (this repo, Phase 2 only, blocked on Mosaic's boundary shipping)**:
  `exon/planner.py` (tool schema swap), `exon/validator.py`/`exon/executor.py`/`exon/ops.py`
  (retired), `exon/harness/` (regraded against the new shape), `exon/README.md`/`DEMO.md`.
- **External dependencies, not implemented by this change**: Mosaic (`BU-Neuromics/mosaic`)
  gaining an MCP server module, a server-derived capability manifest, and
  `validate_query_spec`/`execute_query_spec` tools — owned by Mosaic's own repo/OpenSpec process.
  Aperture (`BU-Neuromics/aperture`) optionally pointing its existing `QuerySpec` builder at
  Mosaic's new boundary as an alternate execution path — owned by Aperture's own team, noted here
  only as a compatible future option, not a requirement of this change.
