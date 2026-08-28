# Change: Add a standards-based MCP boundary to Exon, close the enum-value validity gap, and make results replayable via receipts

## Superseded

**2 Superseded by `add-mosaic-mcp-boundary`.** After this proposal was reviewed, a
follow-up brainstorm (grounded in Aperture's ADR-0035/`QuerySpec` and Mosaic's ADR-0006/0007,
which co-design the same typed-query capability this proposal approached independently) concluded
the MCP boundary should be hosted by Mosaic, not Exon, with Exon becoming a thin MCP client over a
shared `QuerySpec`-shaped canonical IR rather than its own `QueryPlan`. This proposal is kept for
its decision history (in particular, the enum-value validity gap and the two upstream-status
corrections it documents remain accurate observations) but is not the direction being implemented.
See `add-mosaic-mcp-boundary/proposal.md` for the current direction.

## Why

Exon's validator/executor pipeline (`ops.py` → `validator.py` → `executor.py`) is safety-oriented by
design — reject, don't approximate — but today it is reachable only from this repo's own harness
and `python -m exon` CLI. Any external planner (Aperture, Reel, an IDE agent, the MCP Inspector)
that wants to hand Exon a plan, or read its live schema/capability grounding, has no
standards-based way in. At the same time, two concrete gaps sit inside the pipeline itself:

1. **A real, verified validity gap.** `_validate_filter_step` (`exon/validator.py:80-94`) checks
   `f.op` and resolves `f.field` against `hippoSchema`, but never checks `f.value` against that
   same field's `enumValues` — which `hippoSchema` already returns today (`exon/schema.py:28-29`,
   live-verified: `sample_type` → `['blood','tissue','csf','urine','saliva']`, etc.). A plan
   filtering `sample_type EQ "unknown_tissue"` passes validation and either fails at the server or,
   depending on the op, silently matches zero rows — exactly the "plausible-looking but wrong"
   failure this validator exists to prevent, for a field kind it doesn't yet cover.
2. **No receipt.** `execute_plan` (`exon/executor.py:39-48`) returns a dict and nothing is kept.
   There is no way to see what GraphQL a run actually issued, save that run, replay it, or diff two
   runs — Exon's results are a black box once the call returns.

This change adds the smallest coherent next step toward the target shape (external planner → MCP
boundary → Exon validator → Exon executor → Mosaic): an MCP server exposing Exon's existing
grounding and validate/execute pipeline over the standard resources/tools contract, enum-value
validation closing the gap above, and a receipt/replay capability so every execution is inspectable
and reproducible-enough rather than opaque. It does not redesign `ops.py`'s algebra, does not add
aggregation/sort/range/search capabilities, and does not touch the harness or model-comparison work.

## Discrepancies found vs. prior assumptions (current code/live behavior wins)

- **mosaic#148 (relatedTo has no predicate) is CLOSED**, not open. Its resolution is a new typed
  `where:` relationship-predicate capability on the *forward* root query (e.g.
  `workflows(where: {inputSamples: {some: {...}}})`), not a `relatedTo(predicate: ...)` argument.
  Live-verified against this demo's real data: querying 26 hippocampus/tissue samples then one
  `workflows(where: {inputSamples: {some: {id: {in: [...]}}}, workflowType: {eq: rna_seq}})` call
  reproduces this project's documented reference figure (9 matching samples) that the current
  bounded `relatedTo` fan-out also produces via up to 26 calls. **This is a verified, ready-to-build
  optimization — deliberately left out of this change's scope; see "Non-goals" in `design.md` for
  why (it collides with `asOf`-based historical pinning on the same step).**
- **`validator.py:14`'s comment is now factually wrong.** `SUPPORTED_FILTER_OPS = ("EQ", "IN")` is
  commented `# FilterOp enum has no gt/lt/ne/contains -- mosaic#96, open`. mosaic#96 (order_by,
  totalCount, facet counts, range filters, relationship counts) **is** still open, but items
  1-4 of its own listed scope are live today (verified: `donors(where: {ageAtDeath: {gt: 60}})` →
  232 results; `samplesFacetCounts`, `donorsFieldRange`, and `orderBy`/`orderDir` args all work
  live). Only the fifth sub-item, relationship/derived counts, appears to still be outstanding.
  The comment asserts a capability gap that no longer exists as the reason for a scope choice that
  is still correct for other reasons (see `design.md` Non-goals) — this change corrects the comment
  to state the real reason.
- **A pre-existing, unrelated inconsistency found during this research**: `validator.py`'s own
  `_resolve_or_raise` tells the caller to use the `asOf` argument for computed temporal fields
  (`validator.py:64-65`), but `FilterStep` (`ops.py`) has no field to carry `asOf` and `executor.py`
  never sends it — the escape hatch the validator points users at does not exist yet anywhere in
  the pipeline. This change corrects that message to state the true current limitation rather than
  pointing at a nonexistent option; adding real `asOf` support is left as a documented future item.
- **Aperture's actual conversational/NL layer was split into a separate repo, `BU-Neuromics/reel`**
  (2026-06-22, ADR-0021) — Aperture itself now plans an MCP server for external *coding agents*,
  not an in-app chat UI, and has its own typed query IR, `QuerySpec` (ADR-0035, accepted
  2026-08-19), which may overlap with `QueryPlan`. This change does not resolve that overlap; it
  defines Exon's MCP contract generically enough for either Aperture or Reel (or any other MCP
  client) to consume, and names the reconciliation as an open question owned by a future,
  cross-repo change (see `design.md`).

## What Changes

- **New `exon-mcp-boundary` capability**: an MCP server module exposing (a) two read-only
  resources — live `hippoSchema` introspection and the capability manifest, fetched fresh on every
  read, never cached — and (b) two tools, `validate_query_plan` and `execute_query_plan`, that
  wrap the existing `validator.validate_plan`/`executor.execute_plan` functions unchanged.
  `execute_query_plan` always validates before executing; there is no tool that reaches the
  executor without going through the validator first. No raw-GraphQL tool, no mutation tool, no
  escape hatch of any kind is added.
- An optional, clearly-labeled `plan_query` tool wraps the existing NL planner
  (`planner.plan_query`) unchanged, for experimentation only (e.g. the MCP Inspector). Any client
  with its own planner (Aperture, Reel) is expected to call `validate_query_plan`/
  `execute_query_plan` directly with its own emitted plan and never route through `plan_query` —
  this is how the boundary avoids introducing a second competing LLM planner into a single request
  path.
- **`exon-query-planner` capability, MODIFIED**: `_validate_filter_step` now checks each filter's
  `value` (for `EQ`) or each element of `value` (for `IN`) against the field's `enumValues` when
  `hippoSchema` reports the field as enum-backed, rejecting a value outside that set before
  execution rather than letting it reach the server or silently match nothing. The stale
  `mosaic#96, open` comment on `SUPPORTED_FILTER_OPS` is corrected to state the real, current
  reason for the EQ/IN-only scope. The `asOf` reference in `_resolve_or_raise`'s error message is
  corrected to no longer imply an option that does not exist in the pipeline today.
- **New `exon-run-receipts` capability**: every `execute_query_plan` call returns a self-contained
  receipt (instruction, the validated plan, the endpoint, `execute_plan`'s own per-step result
  dict, and — only when the plan came from `plan_query` — planner metadata) that can be saved to
  disk and replayed (re-validated against a **fresh** live schema fetch, then re-executed) or
  diffed against another receipt. Replay is against current live data, not a historically-pinned
  state; true historical reproducibility is explicitly out of scope for this change (see
  `design.md`).
- README/DEMO updates documenting the MCP server, the corrected validator comments, and the
  receipt/replay workflow, once implemented.

## Impact

- Affected specs: `exon-mcp-boundary` (new), `exon-run-receipts` (new), `exon-query-planner`
  (modified: enum-value validation requirement).
- Affected code: `exon/mcp_server.py` (new), `exon/receipts.py` (new), `exon/validator.py`
  (enum-value check, two comment corrections), `exon/requirements.txt` (new dependency: the
  official MCP Python SDK). No change to `exon/ops.py`, `exon/executor.py`'s GraphQL-building
  logic, `exon/planner.py`'s tool schema, or anything under `exon/harness/`.
- **No implementation in this change** — proposal, design, spec deltas, and tasks only, per
  explicit instruction. Implementation is a separate, later approval gate.
