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

- [ ] 2.1 Extend `exon/spec_planner.py`'s `render_traversable_edges` to include FK-backed
      single-valued reverse edges (mirroring Aperture's `planner.ts`'s `deriveEdges`), scoped
      explicitly to single-valued references only — see
      `specs/exon-conversational-planner/spec.md`.
- [ ] 2.2 Update `TURN_TOOL`'s grounding text/description so the model is told a reverse edge and
      a forward edge are both legal `edge` values, and that a multivalued-relationship direction
      is not offered at all (not merely unlisted, so a clarification/limitation response is
      produced rather than a guess).
- [ ] 2.3 Add multi-turn conversational fixtures to the eval harness (ordered utterance sequences
      that compose, plus at least one rewind-and-edit sequence exercising suspend-on-invalid) —
      see `specs/exon-context-harness/spec.md`.
- [ ] 2.4 Run the harness's existing model-comparison/fingerprint tooling against the new
      multi-turn fixture set **before** 2.1/2.2 land (baseline) and **after** (post-change), so
      the reverse-edge grounding change has a measured before/after rather than a shipped,
      unmeasured diff.
- [ ] 2.5 Update `exon/README.md`'s "Conversational mode" section to document the new edge
      vocabulary.

## Phase 3 — This repo's local demo infrastructure (independent of Phases 1/2; needs only that Aperture's `web/` exists locally to test against)

- [ ] 3.1 Extend `run-chat-demo.sh` to start Aperture's web dev server as a third managed service,
      reusing `require_free_port`/`wait_for`/the cleanup trap already proven for Mosaic and Exon —
      see `specs/conversational-demo-launcher/spec.md`.
- [ ] 3.2 Add the one new environment variable/path this needs (pointing at Aperture's `web/`
      checkout) with a sensible documented default, matching the script's existing
      env-var-with-default pattern (`MOSAIC_PORT`, `EXON_TURN_PORT`).
- [ ] 3.3 Update `APERTURE_EXON_CONTRACT.md`'s two stale claims: mosaic#186 is shipped (not
      "open"), and the end-to-end validation guarantee is enforced now that both `mosaic#199` and
      this repo's conversational core exist.
- [ ] 3.4 Manually verify the full local loop once Phase 1 and Aperture's Phase 4 panel exist:
      `run-chat-demo.sh` boots all three services, a browser chat produces a `QuerySpec`, and
      `QueryBuilderView` runs and renders it.

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

- [ ] 5.1 `openspec validate add-aperture-chat-panel --strict` passes.
- [ ] 5.2 `openspec validate --all --strict` passes alongside `add-exon-conversational-contract`,
      `add-mosaic-mcp-boundary`, and `add-exon-mcp-boundary`.
- [ ] 5.3 No code implementation in this pass — proposal, design, spec deltas, and tasks only, per
      the standing "create the OpenSpec only, then stop for review" instruction.
