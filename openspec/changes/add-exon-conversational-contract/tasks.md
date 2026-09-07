## Phase 1 — Mosaic (external to this repo; tracked as `BU-Neuromics/mosaic#186`)

Not implementable from `mosaic-demo-small`. Tracked upstream as `BU-Neuromics/mosaic#186`, filed
alongside the #177 split (same batch as #182/#183, which this tool depends on) — Decision 8 below
is the wire contract #186's implementer needs; posting it as a comment there is this change's
remaining handoff step.

- [ ] 1.1 *(blocked — owned by `hippo`, tracked as mosaic#186)* `converse_query_spec` MCP tool implementing
      the wire contract in `design.md` Decision 8: `POST` to a `MOSAIC_EXON_URL`-configured
      endpoint with the `{utterance, query_spec, turns, edit_turn_id}` request /
      `{turn, suspended_turn_ids}` response shape; tool absent from the MCP server entirely when
      `MOSAIC_EXON_URL` is unset; hosted alongside the `validate_query_spec`/`execute_query_spec`
      tools from `add-mosaic-mcp-boundary` Phase 1.
- [ ] 1.2 *(blocked — owned by `hippo`, tracked as mosaic#186)* `converse_query_spec` re-validates the
      `QuerySpec` in Exon's HTTP response in-process (direct function call, not over MCP) before
      ever returning a `proposal`-status turn, and never calls `execute_query_spec` itself
      (Decision 8). Exon-unreachable/timeout/still-invalid-after-retry all surface as an `"error"`
      turn status, not a bare tool exception. Confirm the tool's auth/reachability model is
      otherwise consistent with `add-mosaic-mcp-boundary`'s existing constraints (no write/mutation
      path; `X-Mosaic-Actor` remains provenance-only).

## Phase 2 — Exon (this repo; **blocked on Phase 1 shipping and being confirmed live**)

- [ ] 2.1 Confirm Phase 1 has shipped and is reachable before starting any of the following.
- [ ] 2.2 Add a turn-mode HTTP entry point to Exon implementing Decision 8's wire contract exactly
      (`{utterance, query_spec, turns, edit_turn_id}` in, `{turn, suspended_turn_ids}` out; `Turn`
      shape as specified), alongside (not replacing) the single-shot entry point from
      `add-mosaic-mcp-boundary`.
- [ ] 2.3 Implement the discriminated response shape (`proposal` vs. `clarification`); Exon's own
      generation retry loop may call Mosaic's `validate_query_spec` as an MCP client (same
      relationship the single-shot planner already has) to iterate on a candidate before returning
      it — the authoritative re-validation happens on Mosaic's side per task 1.2, not here.
- [ ] 2.4 Restrict the turn-mode op vocabulary to `filter`/`exists-related-filter`
      (`FieldCondition`/`RelatedCondition`) — no aggregation, pivot, or set-op support.
- [ ] 2.5 Implement rewind-and-edit: each turn carries an `id`; editing an earlier turn recomputes
      turns after it; a later turn invalidated by the edit is marked `suspended`, never silently
      dropped or reinterpreted.
- [ ] 2.6 Implement anchor-pivot behavior: switching entity type always re-derives the relationship
      as a fresh filter rule against current data, never a reference to a frozen prior result set.
- [ ] 2.7 No persistence: conversation state lives only in the caller's (Aperture's) hands across
      calls; Exon's turn function stores nothing between calls beyond what's passed in.
- [ ] 2.8 Update `exon/README.md` and `APERTURE_EXON_CONTRACT.md` to reflect the shipped state.
- [ ] 2.9 Update `openspec/specs/exon-conversational-planner/spec.md` (new) and
      `openspec/specs/mosaic-query-boundary-contract/spec.md` at archive time.

## Phase 3 — Aperture (external to this repo; informational only, no tasks owned here)

- [ ] 3.1 *(informational, not tracked as a task of this change)* Aperture's own team builds the
      chat UI calling Mosaic's `converse_query_spec`, including the UI affordance for editing a
      specific earlier turn and surfacing suspended turns (Open Question 2 in `design.md`). No
      action required by this change for Aperture's existing non-chat `QuerySpec` builder to keep
      working unmodified.

## Validation

- [ ] 4.1 `openspec validate add-exon-conversational-contract --strict` passes.
- [ ] 4.2 `openspec validate --all --strict` passes with this change alongside
      `add-mosaic-mcp-boundary` and the superseded `add-exon-mcp-boundary`.
- [ ] 4.3 No code implementation in this pass — proposal, design, spec deltas, and tasks only, per
      the standing "create the OpenSpec only, then stop for review" instruction.
