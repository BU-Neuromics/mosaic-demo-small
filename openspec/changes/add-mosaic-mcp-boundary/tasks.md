## Phase 1 — Mosaic (external to this repo; owned by `hippo`'s own OpenSpec process)

Not implementable from `mosaic-demo-small`. Listed for traceability against the contract this
change depends on (`specs/mosaic-query-boundary-contract/spec.md`), not as actionable tasks here.

- [ ] 1.1 *(blocked — owned by `hippo`)* Server-derived capability manifest, extending
      `hippoSchema`/`SchemaRegistry`, exposed as an MCP resource.
- [ ] 1.2 *(blocked — owned by `hippo`)* MCP server module (`mosaic/mcp/`) + `--mcp` CLI flag,
      mounted following the existing `mosaic/graphql/` conditional-mount pattern.
- [ ] 1.3 *(blocked — owned by `hippo`)* Python `QuerySpec` parser + `validateQuerySpec`-equivalent
      validator (ported discipline from Aperture's TS implementation), including the enum-value
      check this repo's `add-exon-mcp-boundary` proposal originally targeted for Exon.
- [ ] 1.4 *(blocked — owned by `hippo`)* `validate_query_spec`/`execute_query_spec` MCP tools;
      `execute_query_spec` validates unconditionally before compiling to Mosaic's `where:`/
      aggregation/search surface. Validation errors must be specific and actionable per-criterion
      (naming the offending slot/op/edge and, for enum/op mismatches, the valid set) — sufficient
      to support an iterative validate → fix → retry loop from any MCP client, not just a generic
      pass/fail.
- [ ] 1.5 *(blocked — owned by `hippo`)* Auth decision for the new surface (mosaic issue #54 Part
      A) — at minimum, confirm no write/mutation tool exists and the `X-Mosaic-Actor` header is not
      mistaken for authorization.
- [ ] 1.6 *(blocked — owned by `hippo`)* `construct-query-spec` MCP Prompt carrying procedural
      "how to" guidance beyond raw schema/capability data — field-name resolution (LinkML slot
      names, never camelCase), relationship-predicate shape (`RelatedCondition`, never a client-side
      fan-out), `columns`' aggregate-vs-explode choice on to-many paths, and the `asOf` +
      relationship-predicate incompatibility. See `design.md` Decision 2/Open Question 5.

## Phase 2 — Exon (this repo; **blocked on Phase 1 shipping and being confirmed live**)

- [ ] 2.1 Confirm Phase 1 has shipped and Mosaic's MCP boundary is reachable before starting any of
      the following — do not begin an incremental migration against a boundary that doesn't exist
      yet.
- [ ] 2.2 Retarget `exon/planner.py`'s `PLAN_TOOL` schema to request a `QuerySpec`-shaped artifact
      (`anchor`/`mode`/`criteria`/`columns`) instead of the current `QueryPlan` `steps`-array shape.
- [ ] 2.3 Replace local calls to `validator.validate_plan`/`executor.execute_plan` with MCP client
      calls to Mosaic's `validate_query_spec`/`execute_query_spec`.
- [ ] 2.4 Retire `exon/validator.py`, `exon/executor.py`, `exon/ops.py` (the `QueryPlan`/
      `FilterStep`/`RelatedLookupStep` types and their validation/execution logic) once 2.3 is
      confirmed working end-to-end.
- [ ] 2.5 Update `exon/harness/` to grade plans/results against the `QuerySpec` shape instead of
      `QueryPlan`; re-baseline the existing eval cases as needed.
- [ ] 2.6 Update `exon/README.md`/`DEMO.md` to describe the new architecture and remove references
      to the retired local validator/executor.
- [ ] 2.7 Update `openspec/specs/exon-query-planner/spec.md` and add
      `openspec/specs/exon-mosaic-mcp-client/spec.md` to reflect the shipped state (at archive
      time, not before).

## Phase 3 — Aperture (external to this repo; informational only, no tasks owned here)

- [ ] 3.1 *(informational, not tracked as a task of this change)* Aperture's own team may choose to
      point its existing `QuerySpec` builder at Mosaic's new MCP boundary as an alternate/additional
      execution path to its current `ScopedDataClient` GraphQL passthrough. No action required by
      this change for Aperture to remain fully functional as-is.

## Validation

- [ ] 4.1 `openspec validate add-mosaic-mcp-boundary --strict` passes.
- [ ] 4.2 `openspec validate --specs --strict` passes with `add-exon-mcp-boundary` present and
      marked superseded alongside this change.
- [ ] 4.3 No code implementation in this pass — proposal, design, spec deltas, and tasks only, per
      the standing "create the OpenSpec only, then stop for review" instruction.
