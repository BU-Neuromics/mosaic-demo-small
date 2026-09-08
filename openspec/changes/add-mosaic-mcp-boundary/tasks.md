## Phase 1 — Mosaic (external to this repo; owned by `hippo`'s own OpenSpec process)

Not implementable from `mosaic-demo-small`. Listed for traceability against the contract this
change depends on (`specs/mosaic-query-boundary-contract/spec.md`), not as actionable tasks here.

**All of Phase 1 shipped upstream (checked off 2026-09-08).** These were all still marked
*"(blocked — owned by `hippo`)"* long after they merged — a staleness found by an audit of this
repo's OpenSpec state, not by anything going wrong. ADR-0009 was ratified (`fe8f332`) and every
issue in its cluster is closed. Task 2.1's own re-verification against this repo's demo server is
the live proof, so nothing below is checked off on the strength of an issue tracker alone.

- [x] 1.1 Server-derived capability manifest, extending `hippoSchema`/`SchemaRegistry`, exposed as
      an MCP resource. Shipped as `mosaic#181` (PR #189, `mosaic.core.schema_typing.
      build_capability_manifest`); live at `mosaic://capabilities`.
- [x] 1.2 MCP server module (`mosaic/mcp/`) + `--mcp` CLI flag, mounted following the existing
      `mosaic/graphql/` conditional-mount pattern. Shipped as `mosaic#182` (PR #191). One
      deviation from ADR-0009's own hedge, reasoning recorded in the `mosaic/mcp` package
      docstring: the transport is Streamable HTTP, not stdio.
- [x] 1.3 Python `QuerySpec` parser + `validateQuerySpec`-equivalent validator (ported discipline
      from Aperture's TS implementation), including the enum-value check this repo's
      `add-exon-mcp-boundary` proposal originally targeted for Exon. Shipped as `mosaic#183`
      (PR #190, validator-only increment; PR #192 additionally rejects multi-column sort).
- [x] 1.4 `validate_query_spec`/`execute_query_spec` MCP tools; `execute_query_spec` validates
      unconditionally before compiling to Mosaic's `where:`/aggregation/search surface. Validation
      errors must be specific and actionable per-criterion (naming the offending slot/op/edge and,
      for enum/op mismatches, the valid set) — sufficient to support an iterative validate → fix →
      retry loop from any MCP client, not just a generic pass/fail. Shipped as `mosaic#183`
      (PR #193, with `mosaic/core/query_spec_compiler.py`). The actionable-error requirement is
      met and was exercised directly: an unknown slot comes back `UNKNOWN_SLOT` at
      `$.criteria[0].slot` (task 2.1). Note the aggregation/search half of this task's wording was
      NOT satisfied by #183 — it needed `mosaic#195`/`#196` (PRs #197/#198), see 2.5b.
- [x] 1.5 Auth decision for the new surface (mosaic issue #54 Part A) — at minimum, confirm no
      write/mutation tool exists and the `X-Mosaic-Actor` header is not mistaken for
      authorization. Resolved as `mosaic#185`: the surface ships read-only ahead of #54,
      consistent with #178's precedent (Mosaic stays auth-unaware; enforcement lives in Bridge).
      `mosaic#54` Part A itself has since landed (PR #140).
- [x] 1.6 `construct-query-spec` MCP Prompt carrying procedural "how to" guidance beyond raw
      schema/capability data — field-name resolution (LinkML slot names, never camelCase),
      relationship-predicate shape (`RelatedCondition`, never a client-side fan-out), `columns`'
      aggregate-vs-explode choice on to-many paths, and the `asOf` + relationship-predicate
      incompatibility. Shipped as `mosaic#184` (PR #194). One item of this wording was
      deliberately superseded as shipped: `columns`' aggregate-vs-explode guidance is moot because
      Phase 1 rejects `columns` outright with `COLUMNS_NOT_SUPPORTED` — see `design.md`
      Decision 2's own "superseded as shipped" annotation.

## Phase 2 — Exon (this repo; **blocked on Phase 1 shipping and being confirmed live**)

- [x] 2.1 Confirm Phase 1 has shipped and Mosaic's MCP boundary is reachable before starting any of
      the following — do not begin an incremental migration against a boundary that doesn't exist
      yet. **Verified 2026-09-07** against this repo's own demo schema (not the upstream test
      fixtures): `mosaic serve --config mosaic.yaml --graphql --mcp` exposes both resources
      (`mosaic://schema`, `mosaic://capabilities`), both tools, and the `construct_query_spec`
      prompt; `execute_query_spec` returned real rows (900 Samples), and an unknown slot came back
      as `UNKNOWN_SLOT` at `$.criteria[0].slot`.

      **Re-verified later the same day, boundary now six tools, not two.** `mosaic#195`/`#196`
      (aggregation/search) merged upstream (PRs #197/#198) after this task was first checked off.
      Re-ran the smoke test against the same demo server: `mosaic serve --mcp` now also exposes
      `count_query_spec`/`facet_query_spec`/`field_range_query_spec`/`search_query_spec`;
      `facet_query_spec` on `Donor.cohort` returned `control: 125, case: 104, at_risk: 71`. 2.3's
      migration should be scoped against this six-tool boundary, not the two-tool one this task
      originally confirmed — see 2.5c: routing to the aggregation tools instead of
      `execute_query_spec` is now part of what the migrated planner has to decide, not something
      deferred as "can't express yet."
- [x] 2.2 Add a `QuerySpec` emitter **alongside** `exon/planner.py`'s `QueryPlan` one, rather than
      retargeting `PLAN_TOOL` in place. Additive first so the harness can grade both shapes against
      the same cases and prove equivalence before anything is retired — a straight retarget would
      have left no trustworthy before/after. Shipped as `exon/spec_planner.py` (emits a plain dict,
      never local dataclasses; grounded in `mosaic://capabilities`, which the server generates,
      rather than the hand-authored `evals/schema/capabilities.json`). Note: this task previously
      described the artifact as `anchor`/`mode`/`criteria`/`columns` — `columns` is **not** part of
      it, since Phase 1 (#183) decided to reject `columns` outright rather than build a Mosaic-side
      compiler for its aggregate-vs-explode choice.
- [x] 2.3 Replace local calls to `validator.validate_plan`/`executor.execute_plan` with MCP client
      calls to Mosaic's `validate_query_spec`/`execute_query_spec`. Paused (`f430674`) on the
      aggregation/search gap this migration would otherwise regress on — that gap closed
      2026-09-07 (see 2.5b), and this shipped 2026-09-08 as `exon/mosaic_mcp.py` plus a retargeted
      `exon/cli.py`.

      One finding worth recording: this was not purely a call swap.
      `evals/schema/capabilities.json` is the OLD hand-authored manifest shape, and
      `render_capability_grounding` raises `KeyError: 'fields'` against it — so the QuerySpec path
      had **no manifest on disk it could actually run with**, and `fetch_capabilities()` reading
      `mosaic://capabilities` is what made the path viable at all, not just less drift-prone.

      `MosaicBoundaryError` separates "boundary unreachable" from "boundary rejected this spec"
      (`cli.py` exits 3 vs 2); collapsing them would make a stopped server look like a refused
      query. A `valid: false` verdict is returned as data with its coded errors intact — nothing
      is re-checked client-side, which is the duplication this migration removes.

      Verified live against the real demo server and Bedrock Haiku: 26 hippocampus tissue samples
      and 364 blood samples, both matching known-good numbers. Notable, though unmeasured (n=1):
      the emitter produced `sample_type="tissue"` — the correct value vocabulary — where the
      QueryPlan path is documented as guessing `"brain tissue"` and silently returning 0.
      Aggregation/search tools deliberately NOT wired; see 2.5c.
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
  - [ ] 2.5b **Re-baseline all three stale `expect_rejection` cases — none stay tagged `blocked`.**
        All three encode Mosaic limitations that no longer hold, verified live: `q32` ("donors
        older than 65 at death, sorted by age descending") — blocked on mosaic#96 having no range
        op or sort — the emitter produced `age_at_death gt 65` with `sort desc`, 174 rows; `q34`
        ("as a single composed query: which rna_seq workflows reference sample SMPL-0032") —
        blocked on mosaic#148 having no relationship predicate — the emitter produced one spec
        with a `RelatedCondition` on `input_samples`, 2 rows; `q33` ("how many donors per cohort")
        — answerable TODAY via GraphQL's `donorsFacetCounts` (control 125 / case 104 / at_risk 71)
        but NOT via the `QuerySpec` boundary, which has no aggregation tool at all. Leaving any of
        the three tagged `blocked` would score the new path *wrong* for correctly answering them
        (q32/q34) or hide a genuine boundary gap behind a stale "Mosaic can't do this" label (q33).
        `q33` specifically **blocked this task**, not just its own re-tag: it depended on
        `BU-Neuromics/mosaic#195` (aggregation tools) shipping — decided in `design.md` Decision 8
        as extend-the-boundary-then-migrate, not accept-the-regression. The pause wasn't waiting on
        someone else's schedule: `#195`/`#196` were filed *and* implemented upstream the same day
        (PRs #197/#198), under the interim dual reviewer/implementer role — the blocker cleared in
        hours, not on an external timeline.

        **Update (2026-09-07): unblocked.** `mosaic#195` (PR #197) and `mosaic#196` (search,
        PR #198) both shipped and merged upstream, and were verified live the same day against
        this repo's own demo server: `mosaic serve --mcp` now exposes `count_query_spec`/
        `facet_query_spec`/`field_range_query_spec`/`search_query_spec`, and `facet_query_spec` on
        `Donor.cohort` returned `control: 125, case: 104, at_risk: 71` — the exact q33 numbers.
        The eval-suite comparison in 2.5's parent task, and this task's own re-baseline, can
        proceed; `q33` no longer reads as a false regression against the old GraphQL-calling path.
  - [ ] 2.5c **Grade the silent-degradation gap, which validation structurally cannot catch.**
        `q33` demonstrated it even before #195: asked for a per-cohort facet count, the emitter
        returned a *valid* spec listing all 300 donors sorted by cohort — a confidently wrong
        answer to a question that asked for counts. Mosaic's validator checks shape and legality,
        never faithfulness to the instruction, so it will never reject this. This does NOT go away
        once `count_query_spec`/`facet_query_spec` (#195) exist — it becomes a routing problem
        instead of an impossibility: Exon must recognize a counting-style instruction and call the
        new tool, not silently degrade it into a row query. Either give the planner that
        recognition, or grade this class explicitly — do not assume shipping #195 alone fixes it.

        **Re-measured 2026-09-08 against the shipped 2.3 path** (live, Bedrock Haiku). The gap is
        real but **narrower and differently shaped** than the wording above assumes, and the
        difference matters for how it gets fixed:

        - *Single-count questions now come back CORRECT.* "How many donors are in the case
          cohort?" produced a plain filter spec and `execute_query_spec` returned `total: 104` —
          the right answer. `execute_query_spec`'s envelope carries `total` independently of the
          page, so a scalar count needs no aggregation tool to be **correct**. It is merely
          wasteful (104 rows materialized for one number). Grading this as wrong would be wrong.
        - *Per-category questions are still confidently WRONG.* "how many donors are there per
          cohort?" reproduced the original failure exactly: a valid spec for all 300 donors with
          `sort: cohort asc`, `total: 300` — not `control 125 / case 104 / at_risk 71`. `total` is
          a single scalar and **structurally cannot** express a grouped count, so no amount of row
          querying answers this.

        So the routing requirement is specifically about **facet- and range-shaped** questions
        (and search), not counting generally. That is a smaller, sharper target than "recognize a
        counting-style instruction."

        **Design note for whoever implements the planner half** (not yet decided, deliberately —
        this task offers two options and neither is chosen): the obvious move, adding a
        `result_shape` field to `SPEC_TOOL`, is a trap. `SPEC_TOOL["function"]["parameters"]` *is*
        the QuerySpec schema, and `conversational_planner.TURN_TOOL` reuses it verbatim as its
        `query_spec` property — so a routing field added there would leak into the conversational
        turn contract and break `add-exon-conversational-contract` task 2.4's
        "no aggregation by construction" guarantee. The non-breaking shape is a *separate*
        single-shot tool that composes the QuerySpec schema as one property alongside a sibling
        `result_shape` (exactly how `TURN_TOOL` already composes it), leaving `SPEC_TOOL` itself
        untouched.
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
