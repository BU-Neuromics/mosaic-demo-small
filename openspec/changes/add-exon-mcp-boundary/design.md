## Context

This follows a handoff document requesting: preserve Exon's existing `QueryPlan` → validator →
executor pipeline, add a standards-based MCP boundary "where it is actually useful," close the
most important validity/faithfulness gaps, and make results easy to inspect/reproduce/replay. The
handoff explicitly instructed treating current executable code and live upstream behavior as the
source of truth over its own (partially dated) assumptions, and calling out any discrepancy found.
Several material discrepancies were found and live-verified against this repo's actual demo
server (after pulling `../hippo` to its current `origin/main` and restarting `mosaic serve`, since
the local checkout was 11 commits behind) — see `proposal.md`'s "Discrepancies found" section. This
document makes the scoping decisions those discrepancies force, and resolves or explicitly defers
the handoff's open questions.

## Goals / Non-Goals

**Goals**
- Give any MCP-speaking client (Aperture, Reel, an IDE agent, the MCP Inspector) a standards-based
  way to read Exon's live grounding and to validate/execute a `QueryPlan`, without giving it a way
  to bypass validation or reach raw GraphQL.
- Close the enum-value validity gap: reject a filter value that cannot possibly match before it
  reaches the server.
- Make a run's actual GraphQL calls and results inspectable and re-runnable after the fact, so
  "what did Exon actually do" is answerable from an artifact, not from re-reading logs.
- Correct now-stale prose (two validator comments) that misdescribes current capability.

**Non-Goals** (with rationale, since several are only non-goals *because of* what was discovered)
- **No new query-plan algebra for aggregation, sort, range, full-text search, or generic graph
  traversal**, even though Mosaic now exposes `{plural}FacetCounts`/`{plural}FieldRange`/
  `orderBy`/`search*`/`neighbors` live. mosaic#96 (the issue that motivated
  `SUPPORTED_FILTER_OPS = ("EQ", "IN")`) remains open for its relationship/derived-counts
  sub-item, and — independent of that issue's status — `QueryPlan` should grow only when a
  concrete instruction needs a capability it can't express, not preemptively because the surface
  now exists. No instruction in this project's evidence to date has needed sort, range, or facet
  counts.
- **No replacement of the bounded `relatedTo` fan-out with the new single-query
  `where:`-relationship-predicate pattern**, despite it being verified and ready to build (see
  proposal.md). Reason: `RelatedLookupStep` with a `client_filter` is exactly the shape a batched
  `where:` query would replace, but Mosaic's `asOf` argument cannot combine with relationship
  predicates (`ASOF_RELATIONSHIP_FILTER_UNSUPPORTED`, per Mosaic's own ADR-0001 restriction) —
  and this same change is adding a receipt/replay capability that wants to reason about
  time-pinned queries. Landing both in one change means specifying, in the same breath, a
  capability that can't co-exist with itself on one step. That is a real conflict, not extra
  scope — it is deferred to a follow-up that can make the `asOf`-vs-batched-relationship trade-off
  its own explicit decision, once real receipts/replay usage shows whether anyone actually needs
  time-pinned relationship queries.
- **No `asOf` field added to `FilterStep`/`ops.py`.** The validator's own error message currently
  claims this is the "correct alternative" for computed temporal fields — it isn't, yet. Rather
  than add speculative plumbing for a capability nothing in this change's receipt/replay design
  requires (replay in this MVP re-runs against *current* live state, never a pinned past state),
  the message is corrected to say so, and real `asOf` support is named as a future increment.
- **No resolution of the `QueryPlan` vs. Aperture's `QuerySpec` (ADR-0035) overlap.** Aperture's
  actual conversational/NL layer lives in a separate repo, `reel` (split 2026-06-22, ADR-0021);
  Aperture itself is now oriented toward an MCP server for external coding agents. Reconciling two
  independently-evolving typed query IRs across three repositories is a cross-repo design question
  with its own stakeholders, not something one Exon-side change should decide unilaterally. This
  change's MCP contract is deliberately generic (plain JSON in the `QueryPlan` shape Exon already
  defines) so either IR's owner can decide, later, whether to translate into it, adopt it, or keep
  both — see Open Questions.
- **No mutation tools, no raw-GraphQL passthrough tool, no arbitrary escape hatch** — explicitly
  forbidden by the handoff and consistent with the pipeline's existing reject-don't-approximate
  posture.
- **No change to `exon/harness/` or the Haiku/Sonnet-5 model-comparison work.** Unrelated surface.

## Decisions

### 1. MCP transport and SDK: stdio via the official Python SDK, deferring Streamable HTTP

Use the official MCP Python SDK's current (non-`FastMCP`) decorator API (`@mcp.tool()`,
`@mcp.resource()`), stdio transport for local development and the MCP Inspector, matching how
every other MCP server in this ecosystem is developed and debugged first. Streamable HTTP (the
documented choice for a deployed backend service) is left for whichever future change actually
deploys Exon's MCP server behind a network boundary — nothing in this MVP requires it, and
building it now would be securing a deployment shape that doesn't exist yet. `mcp` becomes a new
line in `exon/requirements.txt`; verify the exact current SDK API against its installed version
at implementation time rather than trusting any example predating this change, per the handoff's
own caution that MCP's SDK has moved past `FastMCP`/v1 shapes.

### 2. Tools operate on `QueryPlan` JSON, not natural language

`validate_query_plan` and `execute_query_plan` both take the same JSON shape the `emit_query_plan`
tool call already produces (`planner.PLAN_TOOL`'s `parameters` schema) and parse it with the
existing `planner._parse_plan`. This is the smallest possible interface: no new plan
representation, no new parsing logic, and it is exactly the shape an external planner (Aperture's
`QuerySpec`-emitting LLM, Reel, or anything else) would translate its own output into before
calling in. `execute_query_plan` internally calls `validate_plan` first and only proceeds to
`execute_plan` if it raises nothing — validation is not a separate opt-in step for this tool, it
is unconditional and non-bypassable.

### 3. Resources are live and uncached, matching `schema.py`'s existing discipline

Both resources (`hippo-schema`, `capability-manifest`) re-fetch on every read rather than caching
across the server process's lifetime. `schema.py`'s own module docstring already states the
project's rule here — "never cache these across sessions and never assume field names from
memory" — mosaic#149 was exactly this hazard once. An MCP resource that silently served a stale
schema snapshot would reintroduce that same class of bug at the MCP boundary instead of fixing it.

### 4. `plan_query` is optional, explicitly not the integration path for planner-equipped clients

Exposing Exon's own NL planner as an MCP tool is useful for the handoff's "simple
experimentation/playground" goal (ask-mode against the MCP Inspector, or a client with no LLM of
its own) but must not become the way Aperture or Reel integrate, since each already has its own
planner (Aperture's `QuerySpec`-emitting LLM). Routing a client's instruction through Exon's
planner *and* then having that client's own planner interpret or re-plan the result would be the
"two LLM planners" shape the handoff explicitly forbids. The tool is documented as
experimentation-only; the mandatory integration path for any planner-equipped client is
`validate_query_plan`/`execute_query_plan` directly.

### 5. Enum-value validation reads `enumValues` already present in `hippoSchema`

No new introspection. `HIPPO_SCHEMA_QUERY` (`schema.py:27-31`) already requests `enumName
enumValues` per field and passes them through unmodified. `_validate_filter_step` gains one check,
placed alongside the existing op/field checks: if `entity_fields[slot].get("enumValues")` is
truthy, `f.value` (for `op == "EQ"`) or every element of `f.value` (for `op == "IN"`) must be a
member of that list; otherwise raise `ValidationError` naming the field and the valid set. This
mirrors the existing multivalued-reference check's shape (read metadata already in hand, reject
with a specific, actionable reason) rather than introducing a new validation pattern.

### 6. Receipt schema: reuse existing return shapes, don't invent new ones

A receipt is:

```
{
  "receipt_version": "1",
  "instruction": <str>,
  "plan": <QueryPlan serialized to the same JSON shape emit_query_plan produces>,
  "endpoint": <str>,
  "result": <execute_plan's own unmodified return: {"steps": {...}, "final": {...}}>,
  "planner_metadata": <optional, present only when the plan was produced via plan_query:
                        {"protocol", "model", "usage", "finish_reason", "latency_s"} —
                        drawn from PlanAttempt, EXCLUDING raw_content/structured_arguments
                        to keep the receipt to structured data only>,
  "created_at": <ISO-8601 timestamp, real wall-clock>
}
```

`result` is `_execute_filter_step`'s `{"total", "items"}` / `_execute_related_lookup_step`'s
`{"call_count", "matches"}` nested under `execute_plan`'s existing `{"steps": {i: ...}, "final":
...}` wrapper — no new dataclass, no new schema for the part that already has one. Only
`instruction`, `plan`, `endpoint`, and `result` are mandatory; `planner_metadata` is absent when
the caller supplied an already-planned `QueryPlan` directly (the expected case for Aperture/Reel).
`PlanAttempt` does not itself carry the model string (confirmed: `planner.py`'s `PlanAttempt`
dataclass has no `model` field — it's a `request_plan` parameter, not stored on the result), so the
MCP tool layer must capture and pass it through explicitly when populating `planner_metadata`.

### 7. Replay, not historical reproducibility, for this MVP

`replay_receipt(receipt)` re-validates `receipt["plan"]` against a **freshly fetched** live
`hippoSchema`/capability manifest (never the receipt's own captured state, consistent with
Decision 3) and re-executes against the live endpoint. If re-validation fails — e.g. an enum value
the original run accepted has since been removed from the schema — that is reported as an explicit
re-validation failure, not silently skipped or approximated. This reproduces "the same plan against
today's data," which is achievable now with zero new Mosaic capability. True historical
reproducibility (the same plan against the *data as it was* at original-execution time) would
require `asOf` support Exon doesn't have (Decision on `asOf`, above) and is out of scope.

### 8. `compare_receipts(a, b)` is a thin diff, not a new comparison framework

Given two receipts, report: whether the plans are identical; for each step, the delta in
`total`/id-set (`FilterStep`) or `call_count`/matched-id-set (`RelatedLookupStep`); and whether
`endpoint` or `created_at` differ enough to explain a result change (e.g. different day → data may
have changed). This is deliberately much smaller than the harness's `_compare_reports` (which
compares *scores* across many graded cases) — a receipt comparison is about one run's actual
GraphQL result, not a suite grade.

## Risks / Trade-offs

- **New runtime dependency (`mcp` SDK)** → mitigated by pinning to a version verified against the
  current (2026-07-28-era) API at implementation time, and by keeping the MCP module a thin
  wrapper so a future SDK breaking change is a small, localized fix.
- **A client could send a plan Exon's validator doesn't yet understand well** (e.g. one that
  assumes the newer `where:`-relationship-predicate or aggregation capabilities this change
  deliberately doesn't add) → the validator already rejects unrecognized shapes rather than
  guessing; no new risk here beyond what exists today.
- **Enum-value validation could reject a value that's valid but differently cased/spelled** →
  mitigated by comparing against `hippoSchema`'s own `enumValues` list verbatim (the same
  live-source-of-truth discipline used for field-name resolution), not a hardcoded mirror.

## Migration Plan

Additive only. No existing requirement's external behavior changes except the enum-value check
(a stricter rejection of plans that were already producing wrong-but-passing results — not a
behavior anyone should be relying on) and the two comment corrections (no behavior change at all).
No data migration. Implementation proceeds only after this proposal is reviewed and approved,
per the standing instruction for this change.

## Open Questions

Resolved or explicitly deferred, per the handoff's list (items renumbered here to what's actually
load-bearing for this change's scope; items about capabilities this change doesn't touch — e.g.
aggregation, `asOf`, the `relatedTo` batching optimization — are answered above under Non-Goals
and are not repeated here):

1. **Should `plan_query` exist at all, given the "no second planner" constraint?** Resolved:
   yes, but documented as experimentation-only, never the integration path for a planner-equipped
   client (Decision 4).
2. **Should Exon's MCP contract be shaped around Aperture's `QuerySpec` instead of its own
   `QueryPlan`?** Deferred: `QuerySpec` (ADR-0035) and Reel's actual role weren't inspected deeply
   enough in this change's research to make that call responsibly, and doing so would make this
   change depend on decisions two other repos' owners haven't made yet. Exon exposes its own
   already-existing `QueryPlan` shape; a future cross-repo change should own reconciling the two
   IRs if that turns out to be worth doing.
3. **Should receipts persist automatically, or only on request?** Deferred to implementation-time
   product judgment (a CLI flag vs. always-on) — not architecturally significant enough to block
   this proposal; `tasks.md` will record whichever is actually built.
4. **Transport: stdio vs. Streamable HTTP?** Resolved: stdio for this change (Decision 1);
   HTTP explicitly deferred until an actual deployed-service use case exists.
5. **Apollo MCP Server** — remains explicitly deferred future context, not adopted here: this
   change builds directly on the official Python SDK against Exon's own validator/executor, not a
   generic GraphQL-fronting proxy; Apollo's `mutation_mode`/persisted-queries model would be worth
   revisiting only if Exon's MCP boundary ever needed to front raw GraphQL directly, which this
   change explicitly does not do.

## Design principles preserved

- The model plans, deterministic code executes — the MCP tools call the *same* `validate_plan`/
  `execute_plan` functions the harness and CLI already call; nothing about validation or execution
  becomes MCP-specific.
- Reject, don't approximate — extended to enum values, not weakened anywhere.
- Never cache schema/capability grounding across calls — extended to MCP resources.
- Resolve names from the live schema, never guess a transformation — untouched; enum-value
  checking reads the same `hippoSchema` metadata this principle already relies on.
- Small, mechanical, single-purpose changes over speculative generalization — the basis for every
  Non-Goal above.
