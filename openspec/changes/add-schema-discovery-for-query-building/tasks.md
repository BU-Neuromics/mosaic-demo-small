## 1. Ground the planner in slot descriptions

- [x] 1.1 Render each field's `description` in `render_capability_grounding`
      (`exon/spec_planner.py:166`), in BOTH branches — the reference-field branch
      `continue`s at `:188` before the detail line is assembled (design.md
      Decision 3)
- [x] 1.2 Remove the schema-metadata grounding note at the end of that function
      (`:198-211`), which instructs the model to treat schema questions as queries
      over the retired collections
- [x] 1.3 Measure the prompt-size delta and confirm no truncation regressions.
      MEASURED LIVE against `mosaic://capabilities` (4 entity types, local
      `mosaic serve`): grounding 3,393 -> 8,014 chars; full grounding context
      4,702 -> 9,323 chars, i.e. ~1,175 -> ~2,330 tokens (+1,155). No truncation
      in any live run — every discovery and proposal turn completed normally

## 2. Answer discovery in conversation

- [x] 2.1 Teach the planner to answer a schema-discovery question as a
      `clarification` naming the relevant slots and inviting the follow-up that
      builds the spec — `query_spec: null`, per `_reject_malformed_turn`
- [x] 2.2 Verify the turn passes Mosaic's boundary unchanged. Unit-tested for
      shape, and confirmed live: the proposal built from a discovery answer
      passed `validate_query_spec` (`{"valid": true, "errors": []}`) and
      `execute_query_spec` returned 50 donors, matching q05's captured result
- [x] 2.3 Verify the follow-up turn produces a valid QuerySpec over the slots
      named in 2.1. VERIFIED LIVE (bedrock haiku-4-5): "what do we have on donors
      about head injuries?" returned `clarification` / `resolution: answered`
      naming `history_of_rhi`, `cause_of_death` and `notes`; "yes, donors with a
      documented history of RHI" then returned a `proposal` with
      `history_of_rhi eq true`. q37 named both `access_level` and `is_public`;
      q38 named `storage_condition`. Three for three, no misses

## 3. Recalibrate the edit cascade

- [x] 3.1 Distinguish an ANSWERED clarification (draft unchanged, nothing needed
      from the user) from a BLOCKING one in Exon's own result dict
- [x] 3.2 In `edit_turn` (`exon/conversational_orchestrator.py:186`), cascade only
      on a blocking clarification; an answered one passes through as an ordinary
      recomputed turn
- [x] 3.3 Confirm the marker is only ever read from the fresh
      `_request_turn_with_retry` result, never from `prior_turns` — it must not
      need to survive the Mosaic round trip (design.md Decision 2)
- [x] 3.4 Test: edit a turn upstream of a discovery turn; every later proposal
      survives rather than cascade-suspending. Unit-tested, and confirmed live:
      editing the discovery turn returned `suspended == []` with statuses
      `[clarification, proposal]` and the spec intact. Under the old rule the
      proposal would have been suspended

## 4. Reconcile the pending conversational contract

Turn-taking semantics — what a clarification may carry, and when one suspends —
belong to the `exon-conversational-planner` capability, which
`add-exon-conversational-contract` owns and which is still a proposal rather than
truth in `openspec/specs/`. A delta applies to `specs/`, not to another proposal,
so these land as amendments there rather than as requirements in this change.
This section is their ONLY home: do not restate them under `exon-query-planner`,
whose scope is translating an instruction into a plan.

- [x] 4.1 Amend "Response is discriminated between a proposal and a
      clarification" (`add-exon-conversational-contract/specs/exon-conversational-planner/spec.md:35`)
      so a clarification MAY carry an answer rather than only a question, and so
      a schema-discovery question is answered by naming the relevant slots in the
      message — never as a proposal anchored on a schema-describing entity type,
      and never as a refusal. Add scenarios for: a discovery question naming the
      slots that answer it; the following turn producing a proposal over those
      slots; and a discovery question not being declined as "a reference lookup
      rather than a query refinement"
- [x] 4.2 Amend "Each turn is individually addressable and editable" (`:73`) so
      suspension-on-edit is scoped to clarifications that BLOCK. A clarification
      that SUCCEEDED — draft unchanged, nothing required from the user — is
      returned as an ordinary recomputed turn. Add scenarios for both: an edit
      upstream of a discovery turn preserving later proposals, and a blocking
      clarification still cascading
- [x] 4.3 Re-validate that change: `openspec validate add-exon-conversational-contract --strict`

## 5. Retire the schema-metadata rows

- [x] 5.1 Delete `recipes/schema-metadata/` (recipe, schema, generator). NOTE:
      `git rm` alone is NOT enough — it leaves the directory alive via untracked
      `__pycache__`, and Mosaic auto-discovers `recipes/` next to the config
      (ADR-0005), so the server kept serving `SchemaEntityType`/`SchemaField`
      from a directory that looked deleted. `rm -rf` the directory
- [x] 5.2 Remove `metadata` and `check-metadata` from the `Makefile`, and the
      `mosaic recipe import` step from `migrate`
- [x] 5.3 Leave BOTH `ingest --validate-schema schemas` and `mosaic.yaml`
      pointing at the `schemas/` DIRECTORY. The directory form was adopted in
      `a5d1553` for the recipe but is correct independent of it — `mosaic.yaml`
      pointing at the single `schemas/demo.yaml` was a latent bug (migration and
      ingest already used the directory). Do not revert either
- [x] 5.4 Delete `schemas/schema_metadata.yaml` and `data/schema_metadata.yaml`
- [x] 5.5 Confirm `make clean && make generate && make migrate && make ingest`
      runs green with the two collections gone

## 6. Rewrite the benchmark's schema questions

- [x] 6.1 Replace q36–q38 with discovery questions asserting on the produced
      QuerySpec's slots, not on a row count — including the motivating question,
      "what information do we have on donors about toxicology reports?"
- [x] 6.2 Remove the `q36`, `q37` and `q38` entries from
      `evals/expected-results.json` (lines 1762, 1772, 1782) — a plan-level
      assertion has no row-count expectation
- [x] 6.3 Confirm no regression across q1–q35. RAN, but the result is vacuous
      and the reason matters: `harness/runner.py:26` imports `request_plan` from
      `planner.py`, and `context/template.py:211` renders `render_schema_slots`.
      The suite grades the QueryPlan path. This change touches
      `spec_planner.render_capability_grounding`, which feeds `query_router.py`
      and `conversational_planner.py` — neither of which the suite exercises.
      So the benchmark cannot regress on this change, and could not have caught
      a regression either. See design.md's findings section

## 7. Documentation

- [x] 7.1 `DEMO.md`: replace the "Ask about the schema itself" section with the
      discovery flow, and the "You can ask about the data itself" bullet in
      "Where it stands"; drop the recipe-reload caveat
- [x] 7.2 Refresh the benchmark count in `DEMO.md`. "31 of 35 executable
      questions" — q36–q38 no longer carry expected results, and the figure is
      unchanged from the pre-recipe baseline because the suite never covered the
      changed path (see 6.3)
- [x] 7.3 Confirm no other file still references `SchemaField` / `schema-metadata`

## 8. Supersede the previous change

- [x] 8.1 Add a `## Superseded` note to
      `openspec/changes/add-schema-as-queryable-metadata/proposal.md`, correcting
      the "status enum is exactly `proposal | clarification`" claim
- [x] 8.2 Resolve or deliberately strike its one open task (3.2) rather than
      letting `--yes` paper over it
- [x] 8.3 `openspec archive add-schema-as-queryable-metadata --skip-specs --yes`
      — `--skip-specs` keeps its requirements out of `openspec/specs/`, which is
      why this change needs no REMOVED deltas
- [x] 8.4 `openspec validate --strict` across the repo

## 9. Upstream (blocked)

- [ ] 9.1 File: `slot_model_to_dict` omits `is_external_xref` (`mosaic://schema`
      carries 12 of 13)
- [ ] 9.2 File: `MosaicSlotInfo` omits `is_external_xref` and `has_default`
      (`hippoSchema` carries 11 of 13)
- [ ] 9.3 File: the "mirrors REST `GET /schemas`" claims at
      `resolvers.py:608-610`, `:1527`, `mcp/server.py:206` overstate the
      correspondence — REST emits 5 slot attributes and no descriptions
- [ ] 9.4 BLOCKED: the GitHub MCP server failed to connect
      (`Authorization header is badly formatted`); file once fixed
