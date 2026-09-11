## Phase 0 — Aperture, records (external to this repo; informational, no tasks owned here)

- [ ] 0.1 *(informational)* File an ADR in `BU-Neuromics/aperture` recording the chat panel as an
      additive, capability-gated surface (ADR-0029) — not a reversal of ADR-0021/0026's MVP
      deferral of in-app chat, since it appears only when Mosaic advertises
      `converseQuerySpec`/`MOSAIC_EXON_URL`.
- [ ] 0.2 *(informational)* File the GitHub issue(s) in `BU-Neuromics/aperture` tracking Phase 4
      below, per that repo's own ADR + issue convention (no `openspec/` there).

## Phase 1 — Mosaic (external to this repo; not implementable from `mosaic-demo-small`)

- [ ] 1.1 *(informational, track as an issue in `BU-Neuromics/mosaic`)* Expose
      `converse_query_spec`'s existing in-process handler as a `converseQuerySpec` GraphQL
      mutation on the generated Mutation root, registered only when `MOSAIC_EXON_URL` is set —
      see `specs/mosaic-query-boundary-contract/spec.md` for the exact request/response contract.
      Precedent: `hippoSchema`, the existing hand-written meta field on the generated Query root.

## Phase 2 — Exon (this repo; independent of Phase 1, can proceed in parallel)

**Blocked, found while implementing (2026-09-11): Mosaic's QuerySpec layer has no reverse-edge
support at all, at any level — this is a real capability gap, not a documentation lag.**
`_validate_related_condition` (`mosaic/src/mosaic/core/query_spec.py:357`) resolves `cond.edge`
only via `entity.fields_by_name.get(cond.edge)` — the anchor entity's *own* forward reference
slots — and rejects anything else with `UNKNOWN_EDGE`, enumerating only those forward names in its
own error message. `_compile_related_condition`
(`mosaic/src/mosaic/core/query_spec_compiler.py:60`) makes the identical assumption, and the
storage `where:` node it emits (`{"edge": <anchor's own slot>, "where": ...}`) can only join in the
forward direction — a reverse traversal needs the opposite join, which would touch the validator,
the compiler, *and* both storage adapters (sqlite, postgres). This is a real feature request, not
a pass-through.

Design Decision 3's stated precedent — "mirroring what Aperture's own `planner.ts`'s `deriveEdges`
already does client-side" — does not transfer to the wire format. Checked directly
(`aperture` `origin/main`, `web/src/query/querySpec.ts`/`planner.ts`): Aperture's `rev:<collection>.
<field>` edges are a purely client-side compensation tier — `runQuerySpec` never sends a
`RelatedCondition` to Mosaic for either direction; it fetches the related collection, collects
linking ids client-side, and filters the anchor with one flat `IN` condition. No reverse (or even
forward) edge name is ever validated server-side in Aperture's existing execution path. There is
no precedent here that transfers to Exon emitting a server-validated reverse `edge`.

Consequence: Mosaic's own `converse_query_spec` tool (shipped, `mosaic` PR #199) authoritatively
re-validates every candidate `QuerySpec` via this same validator before ever returning a
`proposal` turn (contract Decision 8/task 1.2). If Exon offered a reverse edge and a user asked
the contract's own flagship example ("show me the donors of those samples instead"), Mosaic would
downgrade the resulting turn to `error` — the opposite of what 2.1/2.2 set out to achieve. Filed
upstream: `BU-Neuromics/mosaic#204`.

- [ ] 2.1 ~~Extend `exon/spec_planner.py`'s `render_traversable_edges` to include FK-backed
      single-valued reverse edges...~~ **Blocked** on the Mosaic-side gap above. Shipping this
      without matching server support would produce specs Mosaic's own re-validation rejects.
- [x] 2.2 *(negative half only — see blocked note above for why the positive half is deferred)*
      Updated the shared grounding (`exon/spec_planner.py`'s `render_traversable_edges`, consumed
      by both `spec_planner.py` and `conversational_planner.py`) to state explicitly that only the
      forward direction is offered and that reverse traversal is a real capability limitation to
      name plainly (or ask about, in turn mode) rather than guess an edge name that isn't listed.
      Verified no regression: `pytest tests/test_spec_planner.py tests/test_conversational_planner.py
      tests/test_conversational_orchestrator.py tests/test_conversational_server.py` — 72 passed.
- [ ] 2.3 ~~Add multi-turn conversational fixtures to the eval harness...~~ **Blocked-by-2.1**: this
      task exists to measure 2.1/2.2's positive half, which is blocked (see above). Checked while
      scoping: `exon/harness/` has zero wiring to `conversational_orchestrator` today — its grading
      DSL (`StepExpectation`/`FilterExpectation`, `evals/plan-expectations.yaml`) is shaped
      entirely around single-shot plans. Building that instrument for a change that can't land
      yet is the wrong order; revisit once 2.1 unblocks.
- [ ] 2.4 ~~Run the harness's existing model-comparison/fingerprint tooling... before/after...~~
      **N/A as scoped**: with no "after" (2.1 blocked), there is no before/after to measure. Not
      substituted with a single run — that would answer a different question than this task asked.
- [ ] 2.5 ~~Update `exon/README.md`'s "Conversational mode" section to document the new edge
      vocabulary.~~ **Blocked-by-2.1**: no new vocabulary shipped to document.

## Phase 3 — This repo's local demo infrastructure (independent of Phases 1/2; needs only that Aperture's `web/` exists locally to test against)

- [x] 3.1 Extend `run-chat-demo.sh` to start Aperture's web dev server as a third managed service,
      reusing `require_free_port`/`wait_for`/the cleanup trap already proven for Mosaic and Exon —
      see `specs/conversational-demo-launcher/spec.md`. Gated on `APERTURE_WEB_DIR` being set (no
      hardcoded sibling-repo path, matching the design rationale) — steps renumber 1/3→1/4 etc.
      when enabled.
- [x] 3.2 Added `APERTURE_WEB_DIR` (unset by default — no assumed checkout location) and
      `APERTURE_WEB_PORT` (default `5173`, vite's own default), matching the script's existing
      env-var-with-default pattern (`MOSAIC_PORT`, `EXON_TURN_PORT`). Wires
      `VITE_HIPPO_GRAPHQL_URL` at the checkout's own runtime-config convention
      (`web/src/config/runtime.ts`) so the started dev server points at this run's Mosaic.
- [x] 3.3 Updated `APERTURE_EXON_CONTRACT.md`'s two stale claims (header, "Validation and
      execution" section, and the dependency-graph diagram — the same two facts recur in three
      places, all updated for consistency): mosaic#186 is shipped (`mosaic` PR #199, merged
      2026-09-08, closed), and the end-to-end validation guarantee is enforced now that both that
      PR and this repo's conversational core exist.
- [ ] 3.4 ~~Manually verify the full local loop once Phase 1 and Aperture's Phase 4 panel exist...~~
      **Not yet possible**: Aperture has no `converseQuerySpec` GraphQL mutation to call (Phase 1
      is Mosaic's own GraphQL mutation, tracked as an issue there — separate from the already-
      shipped MCP tool) and no chat panel (Phase 4, external). The launcher change (3.1/3.2) is
      independently verifiable — and was, by inspection and `bash -n` — but the end-to-end loop
      this task describes has nothing to click yet.

## Phase 4 — Aperture (external to this repo; informational only, no tasks owned here; sequenced internally as noted)

- [ ] 4.1 *(informational, sequenced first within this phase)* Canonicalize `QuerySpec` v1→v2 onto
      LinkML type/slot names (Decision 2), with a tolerant v1 read for existing saved views.
- [ ] 4.2 *(informational, depends on 4.1)* Add the `headerNavMainInspector` layout to the layout
      registry (Decision 4).
- [ ] 4.3 *(informational, depends on 4.1, 4.2, and Phase 1 shipping)* Build the chat panel to full
      parity with `chat.py` (Decision 5): turn history, spec view, rewind-and-edit, run.
- [ ] 4.4 *(informational, part of 4.3)* Implement the three UI-feel decisions: suspended-turn
      inline+banner treatment (Decision 9), in-flight typing-indicator+timer+cancel (Decision 10),
      and the builder-lock/reset affordance (Decision 11).
- [ ] 4.5 *(informational)* Start this work from a fresh branch off `origin/main` (Decision 6),
      cherry-picking the spike branch's two docs-only files if desired.
- [ ] 4.6 *(informational)* At least one `npm run build && npm run preview` rehearsal before the
      actual national-meeting presentation (Decision 8).
- [ ] 4.7 *(informational, Aperture's own follow-up, not tracked further here)* Add a
      `converseQuerySpec` assertion to `contracts/hippo-graphql-contract.json` and regenerate
      `web/src/data/testing/realIntrospection.json`.

## Validation

- [x] 5.1 `openspec validate add-aperture-chat-panel --strict` passes. Confirmed.
- [x] 5.2 `openspec validate --all --strict` passes alongside `add-exon-conversational-contract`,
      `add-mosaic-mcp-boundary`, and `add-exon-mcp-boundary`. Confirmed: 8/8 passed.
- [x] 5.3 ~~No code implementation in this pass — proposal, design, spec deltas, and tasks only, per
      the standing "create the OpenSpec only, then stop for review" instruction.~~ **Correction
      (2026-09-11):** scaffold boilerplate carried over from the proposal template (the sibling
      change `add-exon-conversational-contract` carries an identical line alongside a dozen
      genuinely implemented tasks) — not a standing instruction for this change specifically. The
      user explicitly requested implementation this pass; see Phase 2/3 above for what shipped,
      what's blocked, and why.
