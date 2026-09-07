## Context

This follows a brainstorm session that started from a meeting idea — "should the MCP
boundary and typed query plan sit before the Assistant/LLM Planner rather than after it, hosted by
Mosaic rather than Exon?" — explicitly flagged by the user as "not the source of truth, just an
idea." Three read-only research agents grounded the question in current code and design docs
(handoff doc re-extraction; Mosaic upstream feasibility; Aperture/Reel capability model and query
IR). The user then chose, via explicit clarifying questions: the full Mosaic-hosted boundary
(resources and validate/execute tools, not just a thin resource layer), a new OpenSpec proposal as
the deliverable, and explicit `QueryPlan`/`QuerySpec` reconciliation now rather than deferred.

A follow-up direct read of Aperture's `origin/main` `querySpec.ts` and `ADR-0035` (rather than
relying on a subagent's secondhand summary) then changed the shape of the reconciliation decision
— see proposal.md's "Why" section. This design.md records the resulting architecture, the
rationale, and — critically — what this change does *not* claim authority over.

## Goals / Non-Goals

**Goals**
- Stop three independent, drifting representations of "what can this Mosaic deployment do"
  (Mosaic: none; Exon: hand-maintained JSON; Aperture: independently live-derived) by centralizing
  capability/schema grounding at Mosaic, the actual source of truth.
- Adopt Aperture's already-designed, already-Mosaic-co-designed `QuerySpec` (ADR-0035) as the one
  canonical typed query artifact, rather than inventing a new one or perpetuating `QueryPlan`'s
  workaround-shaped algebra.
- Give Exon (and, in the future, Reel, and Aperture's own builder) one shared, validated
  execution boundary hosted where the schema authority already lives.
- Preserve the reject-don't-approximate discipline throughout — moving it to Mosaic strengthens it
  (in-process schema access) rather than weakening it.

**Non-Goals**
- **Designing Mosaic's authn/authz model.** Mosaic has none today (`core/middleware.py`'s
  `PassThroughAuthMiddleware` is provenance-only, per its own `graphql/router.py` docstring, which
  cites **mosaic issue #54 Part A**). This change states only what Mosaic's MCP surface must not do
  (see Decision 4) and names the rest as Mosaic's own decision to make.
- **Implementing anything inside `hippo` (Mosaic) or `aperture`.** This repo's OpenSpec tooling and
  authority stop at this repo's boundary. The `mosaic-query-boundary-contract` capability states
  what this repo depends on, not what Mosaic's team must build or when.
- **Resolving the `asOf` + relationship-predicate conflict.** Mosaic's `asOf` (transaction-time
  pinning) cannot combine with relationship predicates (`ASOF_RELATIONSHIP_FILTER_UNSUPPORTED`,
  per Mosaic ADR-0001). `QuerySpec` carries a top-level `asOf` field alongside `RelatedCondition`,
  so adopting `QuerySpec` inherits this restriction rather than resolving it. Named here so it
  isn't silently dropped; not solved by this change.
- **Pinning down `ColumnSpec`'s field-level schema**, in particular whether a to-many column's
  `explode: true` output can be filtered to match a `RelatedCondition`'s own sub-criteria on the
  same edge. ADR-0035 itself states "field-level schema lives with the implementation" — i.e. this
  isn't resolved even in the source ADR. This matters concretely for Exon's own driving example
  ("...any rnaSeq data associated with them, distinguishing no RNA-seq workflow found from not
  checked") — flagged as a genuinely open question (see Open Questions), not assumed away.
- **Requiring Aperture to change anything.** Aperture's existing `ScopedDataClient`/GraphQL-
  passthrough path continues to work unmodified; pointing its `QuerySpec` builder at Mosaic's new
  MCP boundary is noted as a compatible future option, not a requirement.
- **General aggregation/sort/search query-language growth beyond what `QuerySpec` (ADR-0035)
  already specifies.** This change adopts an already-designed artifact; it does not expand it.

## Decisions

### 1. Canonical typed query IR: adopt `QuerySpec` (ADR-0035), not `QueryPlan`

`QuerySpec`'s normative shape (`v: 1`, `anchor`, `mode: AND|OR`, `criteria: (FieldCondition |
RelatedCondition)[]`, plus `columns`/`sort`/`asOf` per the full ADR text) already expresses
everything `QueryPlan` expresses:

- `QueryPlan.FilterStep` + `FieldFilter` ↔ `QuerySpec`'s top-level `FieldCondition` criteria on the
  anchor.
- `QueryPlan.FilterStep.forward_relation` ↔ a `RelatedCondition` (forward edge) or a `ColumnSpec`
  to-one traversal path, depending on whether the intent is filtering or selecting.
- `QueryPlan.RelatedLookupStep` (bounded `relatedTo` fan-out, one call per id) ↔ a single
  `RelatedCondition` with `quantifier: 'some'`/`'none'`, compiled by Mosaic's own planner into one
  `where:` relationship-predicate call — no client-side fan-out needed, since mosaic#148's
  resolution (confirmed closed, live-verified this session) is exactly this capability.
- `QueryPlan` has **no equivalent** of `ColumnSpec`'s explicit `aggregate`-vs-`explode` choice on
  to-many selection paths — `QuerySpec` is strictly more expressive here, not just differently
  shaped.

`QuerySpec` was accepted 2026-08-19 and explicitly co-designed against Mosaic's own capability
rollout (ADR-0035's own "Related:" list cites Mosaic ADR-0006/0007 by name). Confirmed directly in
the `hippo` checkout: the four OpenSpec changes implementing that rollout
(`typed-filter-inputs`, `aggregation-and-ordering`, `search-composition`, `heterogeneous-roots`)
exist in `hippo/openspec/changes/` and their tracking issues (mosaic#153–#158) are **all closed**.
This is the exact capability surface this project's own live verification (this session) already
exercised successfully against the running demo server. Building a fourth, Exon-specific IR when
two repos have already jointly designed and shipped the real solution would be pure duplication.

### 2. Mosaic hosts the full MCP boundary (resources + validate/execute tools)

Per the user's explicit choice: not the thinner "resources only" option. Mosaic's MCP server
(external to this repo):
- Exposes live schema and a real, server-derived capability manifest as MCP resources — built from
  `hippoSchema`/`SchemaRegistry`, which Mosaic already owns, rather than the hand-maintained JSON
  file this repo currently carries.
- Exposes `validate_query_spec`/`execute_query_spec` tools implementing the same discipline
  Aperture's client-side `validateQuerySpec()` (in `web/src/query/querySpec.ts`) already
  demonstrates — total, introspection-driven, every anchor/slot/op/edge checked against what the
  endpoint actually advertises — but server-side, in Python, with direct in-process access to
  `enumValues` and the rest of the schema (no HTTP round-trip needed to fetch what Mosaic already
  has in memory).
- `execute_query_spec` validates unconditionally before compiling the validated `QuerySpec` into
  Mosaic's own already-shipped `where:`/aggregation/search GraphQL surface (or calling internal
  resolvers directly, in-process — implementation choice left to Mosaic's own team).
- **Exposes a `construct-query-spec` MCP Prompt** carrying the procedural "how to" knowledge that
  raw schema/capability data doesn't convey on its own — e.g. always resolve field names as LinkML
  slot names, never camelCase; express relationship existence/predicates as a single
  `RelatedCondition` with `quantifier: 'some'/'none'`, never a client-side fan-out; `columns` is
  not supported at all and must be omitted (**superseded as shipped**: this originally read that a
  to-many `columns` path needs an explicit `aggregate`-vs-`explode` choice — Phase 1 instead
  rejected `columns` outright with a coded `COLUMNS_NOT_SUPPORTED` error, since no Mosaic-side
  compiler exists for that choice; the shipped Prompt teaches the rejection, and a regression test
  guards it against being re-copied from this paragraph's earlier wording); `asOf` cannot combine
  with a `RelatedCondition` on the same `QuerySpec`. This is exactly the kind of empirically-derived,
  hard-won guidance Exon's own `planner.py` currently hand-curates in
  `render_relationship_types()`/`render_limitations()` — without a shared Prompt, every future MCP
  client (Exon, Reel, a generic coding agent) either reinvents it or gets it wrong the way Exon's
  own harness has already caught models doing. Centralizing it here closes the same duplication
  gap Decision 1/5 close for capabilities and enum values, one layer up, at the "how do you use
  this correctly" layer rather than only the "what exists" layer.
- **`validate_query_spec`'s errors SHALL be specific and actionable enough to support iterative
  self-correction** — per-criterion, naming the offending slot/op/edge and (for enum/op mismatches)
  the valid set, mirroring the specificity Aperture's TS `validateQuerySpec()` already demonstrates
  (e.g. "Criterion 2: 'xyz' is not filterable on Donor," not a generic "invalid plan"). This is not
  a nice-to-have: a capable LLM connected directly to Mosaic's MCP server with no Exon-specific code
  at all can plausibly construct a correct `QuerySpec` through nothing more than an iterative
  validate → read error → fix → retry loop — which would actually be an improvement over Exon's
  current one-shot forced-tool-call design, whose retries are blind resamples rather than
  error-informed. Vague errors would foreclose that capability for every client, not just Exon.

This is external work; this change specifies the contract (see the `mosaic-query-boundary-contract`
capability) and does not schedule or implement it.

### 3. Exon becomes a thin MCP client; local validator/executor retire — but only after Mosaic ships

Exon's `planner.py` tool schema (`PLAN_TOOL`) changes to request a `QuerySpec`-shaped artifact
instead of the current `steps`-array `QueryPlan` shape. Once Mosaic's boundary exists, Exon calls
`validate_query_spec`/`execute_query_spec` as an MCP client rather than running
`validator.validate_plan`/`executor.execute_plan` locally — those two modules, plus `ops.py`'s
`QueryPlan`/`FilterStep`/`RelatedLookupStep` types, are retired.

**This is a hard dependency, not two independently schedulable pieces of work.** Exon's local
pipeline cannot be retired before Mosaic's boundary is live — doing so would leave Exon with no
validation at all in the gap. `tasks.md` sequences Phase 2 explicitly behind Phase 1.

### 4. Auth: state constraints, not a design

This change states only:
- Mosaic's MCP surface exposes no write/mutation tool (same constraint the original
  `add-exon-mcp-boundary` proposal carried, still correct here).
- The existing `X-Mosaic-Actor` header is provenance-only and must not be treated as
  authentication or authorization by any client of the new boundary, including Exon.
- Anything beyond this (real authn/authz, rate limiting, multi-tenant scoping) is Mosaic's own
  decision, already tracked as **mosaic issue #54 Part A** — cited, not solved, here.

### 5. Enum-value validation relocates to Mosaic and improves

The gap found earlier this session — `hippoSchema` already returns `enumValues` per field, but
Exon's `validator.py` never checked a filter's value against it — no longer needs an Exon-side fix.
It becomes part of Mosaic's `validate_query_spec` (Decision 2), which has `enumValues` in-process
with zero introspection round-trip, a strictly better home than the original Exon-side design. The
superseded `add-exon-mcp-boundary` proposal's version of this fix is not implemented; this is not a
loss, since the same fix now happens correctly, once, closer to the data.

### 6. Single-repo authorship; explicit contract capability for the external dependency

This OpenSpec change lives entirely in `mosaic-demo-small`. For the pieces this repo depends on but
does not own (Mosaic's boundary; Aperture's optional integration), `mosaic-query-boundary-contract`
states SHALL-worded expectations framed as *this repo's dependency*, e.g. "Exon's integration
assumes Mosaic exposes X" rather than asserting control over Mosaic's implementation or timeline.
This matches the original handoff's own instruction: "define the contract now rather than forcing
cross-repo implementation into one change."

### 7. Exon's long-term role: a harness/reference-planner sitting between Aperture and Mosaic's MCP boundary — not required infrastructure for either

Once Decision 3 lands, Exon is no longer necessary for correctness or safety — Mosaic's
`validate_query_spec` owns that regardless of what constructs the `QuerySpec` or how. What Exon
remains genuinely, distinctly useful for:

- **A controlled, repeatable reliability-evaluation methodology** (`exon/harness/`: probe/run/loop/
  compare, fingerprinting, temperature detection, cross-model grading) — a fundamentally different
  kind of thing than "being the planner." An open-ended agentic tool-calling loop against Mosaic's
  MCP boundary cannot substitute for this: it has no fixed, scriptable, comparable-across-models
  call shape, so it can't answer "does this model reliably produce correct plans," only "did this
  particular session eventually get there."
- **A stable, versioned, product-owned planning surface** that Aperture (or a future Reel) can call
  when they want NL-driven `QuerySpec` construction as a first-class product feature, without
  requiring their own end users to bring a separate MCP-connected LLM client, and without Aperture
  itself owning LLM credentials or orchestration — which its own `scopedClient.ts` design already
  says the browser should not do.

Exon is explicitly **not** a required layer for either Aperture or Mosaic: Aperture's `QuerySpec`
builder can call Mosaic's MCP boundary directly for typed, human-constructed queries (Decision 2;
Phase 3 note in `tasks.md`), with no dependency on Exon at all. Exon becomes relevant specifically
when NL-driven planning is wanted as a product feature — at that point it sits as an optional
service between whichever product wants that feature (Aperture today, conceivably Reel later) and
Mosaic's MCP boundary, not below Mosaic or in front of it as a required gate. This is a narrowing,
not a promotion: Exon trades "the only place with the know-how" for "a harness plus one reference
implementation of a role any sufficiently well-prompted MCP client could otherwise fill" — see the
Decision 2 additions above on the `construct-query-spec` Prompt and actionable validation errors,
which further shrink what's actually Exon-specific down to the harness and the product-integration
surface, nothing more.

## Risks / Trade-offs

- **This repo cannot unilaterally make Mosaic build its half.** Mitigated by writing the contract
  capability now, so whoever picks up Mosaic-side work has a concrete, reviewed target rather than
  starting from scratch — but there is real schedule risk this change's Phase 2 waits indefinitely.
- **`QuerySpec`'s field-level `ColumnSpec` schema is genuinely unresolved** (Non-Goals). Exon's
  driving example may not be fully expressible until that's pinned down upstream. Named as an open
  question, not silently assumed solvable.
- **Two independent validators (Aperture's TS `validateQuerySpec`, Mosaic's new Python
  `validate_query_spec`) checking the same rules is acceptable defense-in-depth**, not a
  consistency risk this change needs to solve — Mosaic's server-side check is authoritative;
  Aperture's client-side check is a UX optimization that can safely lag or diverge slightly without
  correctness risk, since Mosaic's check is unconditional before execution either way.

## Migration Plan

Phase 1 (Mosaic, external, not owned by this change) must ship before Phase 2 (Exon, this repo)
begins. Phase 3 (Aperture, external) is optional and independent of Phase 2. No data migration.
`add-exon-mcp-boundary` remains in `openspec/changes/` marked superseded, not archived and not
deleted, preserving its decision history. Implementation of Phase 2 proceeds only after this
proposal is reviewed and approved, and only after Phase 1's external dependency is confirmed
shipped — per the standing "create the OpenSpec only, then stop" instruction for this session.

## Open Questions

1. **`ColumnSpec` field-level schema** (Non-Goals) — specifically whether a to-many `explode`
   column can be scoped to match a `RelatedCondition`'s own sub-criteria on the same edge. Needed
   for Exon's "distinguish not-checked from none-found" scenario. Owned by whoever implements
   `ColumnSpec` server-side (Mosaic) and client-side (Aperture) — not resolved here.
2. **Exact MCP tool/resource naming and transport** (stdio vs. Streamable HTTP) for Mosaic's
   server — inherited from the original `add-exon-mcp-boundary` proposal's Decision 1 reasoning
   (stdio first, matching MCP dev conventions; HTTP deferred until an actual deployed-service need
   exists) but now Mosaic's call to make, not Exon's.
3. **Whether Reel, when built, should also be an MCP client of Mosaic's boundary directly** (very
   likely, per Reel's own per-turn design already wanting "NL → typed spec → validate → execute")
   — noted as a strong future-fit, not committed to here since Reel has zero code today.
4. **Whether Aperture should point its existing `QuerySpec` builder at Mosaic's new MCP boundary**
   as an alternate execution path to its current direct-GraphQL `ScopedDataClient` — Aperture's own
   team's call; this change does not require it. Sharpened by Decision 7: this is a question about
   *execution*, independent of whether Aperture ever wants NL-driven *planning* (which, if wanted,
   would route through Exon or a successor sitting between Aperture and Mosaic's boundary, not
   through Aperture reimplementing planning itself — see the earlier brainstorm on incorporating
   Exon-specific features into Aperture, which this repo declined in favor of keeping Exon as an
   optional, external harness/reference-planner).
5. **Exact content and ownership of the `construct-query-spec` MCP Prompt** (Decision 2) — Mosaic's
   own call once Phase 1 is picked up; this proposal names the categories of guidance it should
   cover (field-name resolution, relationship-predicate shape, `columns` aggregate/explode choice,
   the `asOf` restriction) but not its exact wording.
