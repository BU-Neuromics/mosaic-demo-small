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

- [x] 2.1 Confirm Phase 1 has shipped and Mosaic's MCP boundary is reachable before starting any of
      the following — do not begin an incremental migration against a boundary that doesn't exist
      yet. **Verified 2026-09-07** against this repo's own demo schema (not the upstream test
      fixtures): `mosaic serve --config mosaic.yaml --graphql --mcp` exposes both resources
      (`mosaic://schema`, `mosaic://capabilities`), both tools, and the `construct_query_spec`
      prompt; `execute_query_spec` returned real rows (900 Samples), and an unknown slot came back
      as `UNKNOWN_SLOT` at `$.criteria[0].slot`.
- [x] 2.2 Add a `QuerySpec` emitter **alongside** `exon/planner.py`'s `QueryPlan` one, rather than
      retargeting `PLAN_TOOL` in place. Additive first so the harness can grade both shapes against
      the same cases and prove equivalence before anything is retired — a straight retarget would
      have left no trustworthy before/after. Shipped as `exon/spec_planner.py` (emits a plain dict,
      never local dataclasses; grounded in `mosaic://capabilities`, which the server generates,
      rather than the hand-authored `evals/schema/capabilities.json`). Note: this task previously
      described the artifact as `anchor`/`mode`/`criteria`/`columns` — `columns` is **not** part of
      it, since Phase 1 (#183) decided to reject `columns` outright rather than build a Mosaic-side
      compiler for its aggregate-vs-explode choice.
- [ ] 2.3 Replace local calls to `validator.validate_plan`/`executor.execute_plan` with MCP client
      calls to Mosaic's `validate_query_spec`/`execute_query_spec`.
- [ ] 2.4 Retire `exon/validator.py`, `exon/executor.py`, `exon/ops.py` (the `QueryPlan`/
      `FilterStep`/`RelatedLookupStep` types and their validation/execution logic) once 2.3 is
      confirmed working end-to-end. Confirmed safe in principle: every check `validator.py`
      performs (unknown entity/field, unsupported op, `source_step` bounds) has a coded equivalent
      in Mosaic's validator, and it never checked instruction-faithfulness — that is
      `harness/grading.py`'s job, which is NOT retired. `harness/grading.py` does import
      `validator.resolve_field`, so 2.5 must supply a slot-resolution equivalent before 2.4 lands.
- [ ] 2.5 Update `exon/harness/` to grade against the `QuerySpec` shape, and re-baseline the eval
      cases. Four findings from 2.2's live verification shape this task and are recorded here so it
      is not attempted as a mechanical translation:
  - [ ] 2.5a **Grade on result equivalence, not structural diff.** `QuerySpec` collapses
        `QueryPlan`'s `source_step`-chained multi-step plans into one artifact, so a case the old
        grader scored correct as *two steps* and the new path expresses as *one* `RelatedCondition`
        is not structurally comparable — a structural diff would report every relationship case as
        a false regression. `evals/expected-results.json` already carries real executed totals for
        35 cases against the same data snapshot the demo server serves (3600 records, seed 0), so
        result equivalence is available as the primary signal; keep structural checks secondary.
  - [ ] 2.5b **Re-baseline the stale `expect_rejection` cases.** Two of the three encode Mosaic
        limitations that the ADR-0006/0007 rollout has since closed, and both were verified live to
        be answerable now: `q32` ("donors older than 65 at death, sorted by age descending") was
        blocked on mosaic#96 having no range op or sort — the emitter produced `age_at_death gt 65`
        with `sort desc`, 174 rows; `q34` ("as a single composed query: which rna_seq workflows
        reference sample SMPL-0032") was blocked on mosaic#148 having no relationship predicate —
        the emitter produced one spec with a `RelatedCondition` on `input_samples`, 2 rows. Leaving
        these tagged `blocked` would score the new path *wrong* for correctly answering them.
        `q33` (facet count / group-by) is still genuinely unsupported and stays a rejection case.
  - [ ] 2.5c **Grade the silent-degradation gap, which validation structurally cannot catch.**
        `q33` demonstrated it: asked for a per-cohort facet count, the emitter returned a *valid*
        spec listing all 300 donors sorted by cohort — a confidently wrong answer to a question
        that asked for counts. Mosaic's validator checks shape and legality, never faithfulness to
        the instruction, so it will never reject this. The old architecture's correct answer was
        refusal; `spec_planner` has no refusal path at all. Either give it one, or grade this class
        explicitly — but do not assume the boundary covers it.
  - [ ] 2.5d **Treat a `related` criterion with empty `criteria` as a graded failure.** It
        validates clean and executes (Phase 1's compiler fills a trivially-true predicate on the
        target's identifier), returning every anchor record that has *any* related record — a
        silently dropped constraint that looks like a successful query.
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
