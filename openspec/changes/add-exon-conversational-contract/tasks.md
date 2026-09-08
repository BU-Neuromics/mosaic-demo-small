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

## Phase 2 — Exon (this repo; **only full end-to-end integration is blocked on Phase 1**)

**Correction found while implementing (2026-09-07):** the header above originally blocked *all* of
Phase 2 on Phase 1 shipping. That's stricter than the real dependency. Exon's own turn-mode planning
core and HTTP endpoint need only what `add-mosaic-mcp-boundary` Phase 1 already shipped
(`mosaic://capabilities`, `validate_query_spec`) — nothing here calls `converse_query_spec` itself;
that tool is Exon's *caller*, not a dependency. Building and proving the endpoint standalone first
(a real HTTP client hitting a real Exon server) is the same "build the callee before the caller, so
there's something real to verify against" order already used for `mosaic#195`/`#196`. Only the
*full* Aperture → Mosaic → Exon path is blocked on Phase 1 (`mosaic#186`) actually shipping.

- [x] 2.1 ~~Confirm Phase 1 has shipped and is reachable before starting any of the following.~~
      Superseded by the correction above — confirm instead that `add-mosaic-mcp-boundary` Phase 1
      (already shipped) is reachable, since that's what 2.2+ actually depend on. Confirmed, not
      assumed: slice 3's live verification (see 2.5) ran a real uvicorn server, hit by a real HTTP
      client over an actual socket, driving a full conversation against the real Mosaic demo
      server's own capability manifest.
- [x] 2.2 Add a turn-mode planning core and HTTP entry point to Exon implementing Decision 8's wire
      contract exactly (`{utterance, query_spec, turns, edit_turn_id}` in, `{turn,
      suspended_turn_ids}` out; `Turn` shape as specified), alongside (not replacing) the
      single-shot entry point from `add-mosaic-mcp-boundary`. Shipped across three slices, verified
      independently at each step (`exon/conversational_planner.py` — the stateless planning core;
      `exon/conversational_orchestrator.py` — turn-list/rewind-and-edit bookkeeping; the HTTP
      endpoint itself, next).
- [x] 2.2a **Decision 9 (`design.md`)**: resolved the tension between the wire's explicit
      `query_spec` field and the turn-history-derived current draft. For now, Aperture locks its
      point-and-click `QuerySpec` builder once a chat starts, so they can never genuinely diverge —
      the endpoint asserts they agree (400-level, naming both, if they don't) rather than silently
      trusting one or the other. `conversational_orchestrator.append_turn` already accepts an
      optional `existing_query_spec` override so lifting that lock later is a change to the HTTP
      layer alone (stop asserting equality, pass the wire value through as the override) — no change
      needed to the orchestrator, `edit_turn`, or the wire contract itself.
- [ ] 2.3 *(blocked, found while picking this back up — 2026-09-07)* The discriminated response
      shape (`proposal` vs. `clarification`) itself already shipped as part of 2.2
      (`conversational_planner.py`'s `emit_turn_response` tool) — what remains here is specifically
      an optional self-validation retry loop: Exon's own generation retry loop calling Mosaic's
      `validate_query_spec` as an MCP client to iterate on a candidate before returning it (the
      authoritative re-validation still happens on Mosaic's side per task 1.2, not here).

      **Correction: the task's original premise — "same relationship the single-shot planner
      already has" — is false about the code today.** No MCP client exists anywhere in this repo
      on either branch — `exon/requirements.txt` carries only `litellm`, `fastapi`, `uvicorn` (no
      `mcp`/`modelcontextprotocol`/`fastmcp`), and neither `conversational_planner.py` nor
      `spec_planner.py` calls one. The single-shot planner emits a `QuerySpec` and stops; Mosaic
      validates it after the fact, out of process, not because Exon called it as a client.
      Creating that client is `add-mosaic-mcp-boundary` task 2.3's job (still unchecked there).

      **Update (same day, later): the upstream reason that task was paused no longer applies.**
      `f430674` paused the whole Exon migration on an aggregation/search gap, tracked as
      `mosaic#195`/`#196`. Both shipped and merged upstream since — `mosaic#195` via PR #197,
      `mosaic#196` via PR #198 — and verified live just now against this repo's own demo server:
      `mosaic serve --mcp` exposes `count_query_spec`/`facet_query_spec`/`field_range_query_spec`/
      `search_query_spec` alongside `validate_query_spec`/`execute_query_spec`, and
      `facet_query_spec` on `Donor.cohort` returned `control: 125, case: 104, at_risk: 71` — the
      exact q33 numbers the gap was blocking. `add-mosaic-mcp-boundary` task 2.3 (and its 2.4-2.7)
      is therefore actionable now, not blocked on anything upstream — it just hasn't been done yet
      in this repo. This task (conversational 2.3) is blocked on that migration happening, not on
      any further upstream work.

      Even once `add-mosaic-mcp-boundary` 2.3 ships and this becomes actionable, it remains only a
      quality improvement, not a correctness requirement, since Mosaic's `converse_query_spec`
      already re-validates
      authoritatively regardless (task 1.2, also unbuilt).
- [x] 2.4 Restrict the turn-mode op vocabulary to `filter`/`exists-related-filter`
      (`FieldCondition`/`RelatedCondition`) — no aggregation, pivot, or set-op support. True by
      construction: `TURN_TOOL`'s `query_spec` property reuses `SPEC_TOOL`'s shape verbatim, which
      never exposes a `CriteriaGroup`/aggregation/pivot kind at all — there is nothing to restrict
      because nothing broader was ever offered to the model.
- [x] 2.5 Implement rewind-and-edit: each turn carries an `id`; editing an earlier turn recomputes
      turns after it; a later turn invalidated by the edit is marked `suspended`, never silently
      dropped or reinterpreted. Shipped in `conversational_orchestrator.py` (slice 2) and verified
      live twice: a scripted-stub cascade test proving no further model calls happen once
      suspension starts, and a real multi-turn conversation over real HTTP (slice 3) where an edit
      pivoting `Sample` → `Workflow` correctly suspended a later turn referencing a field that
      doesn't exist on the new anchor, with a useful re-prompt naming the exact conflict.
- [x] 2.6 Implement anchor-pivot behavior: switching entity type always re-derives the relationship
      as a fresh filter rule against current data, never a reference to a frozen prior result set.
      True by construction, not separately implemented: every turn emits a FULL `QuerySpec` (never
      a diff), grounded fresh in `mosaic://capabilities` each call, and this planning flow never
      executes anything (never calls `execute_query_spec`) — there is no result set anywhere in
      this code for a pivot to accidentally reference.
- [x] 2.7 No persistence: conversation state lives only in the caller's (Aperture's) hands across
      calls; Exon's turn function stores nothing between calls beyond what's passed in. True by
      construction: `conversational_orchestrator.py`'s functions are pure (`turns` is never
      mutated, always returned as a new list) and `conversational_server.py` holds no state between
      requests — every call reconstructs everything from the request body alone.
- [x] 2.8 Update `exon/README.md` and `APERTURE_EXON_CONTRACT.md` to reflect the shipped state.
      README gained a "Conversational mode" section (files, wire contract, Decision 9's lock as
      implemented, what's still deferred) and a fix to the now-stale "no multi-turn conversation"
      limitation line. The contract doc's status header now points at the formalized OpenSpec
      change and the shipped modules instead of reading as an unimplemented brainstorm; its
      dependency graph and decisions list were updated to match (mosaic#186 filed, Decision 9's
      resolution noted).
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
