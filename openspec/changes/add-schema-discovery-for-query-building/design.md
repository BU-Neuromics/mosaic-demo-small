## Context

Four introspection surfaces already describe this deployment's schema, all
projections of one tap — `SchemaRegistry` → `build_type_model()` →
`EntityTypeModel`/`SlotModel` (`mosaic/src/mosaic/core/schema_typing.py:88`):

| Surface | Adapter | Slot coverage |
| --- | --- | --- |
| `__schema` | `graphql/schema_builder.py:438,497,511,663` | generated GraphQL types; carries descriptions |
| `hippoSchema` | `graphql/resolvers.py:634` (`MosaicSlotInfo`) | 11 of 13 |
| `mosaic://schema` | `mcp/serialize.py:20` | 12 of 13 |
| `mosaic://capabilities` | `mcp/serialize.py:46` | 12 of 13, plus per-field query capability |

(REST `GET /schemas` is a fifth, off a *different* tap: `serve/routers/schema.py:19`
reads `registry.induced_slots()` directly and emits 5 slot attributes with no
descriptions. The "mirrors REST `GET /schemas`" claims at `resolvers.py:608-610`,
`:1527` and `mcp/server.py:206` overstate the correspondence.)

The planner is grounded on `mosaic://capabilities`. The facts needed for schema
discovery are therefore already in the process that needs them — they are simply
not rendered into the prompt.

## Goals / Non-Goals

**Goals**
- A researcher can ask what the schema holds, in their own vocabulary, and get an
  answer that names the slots they need.
- That answer leads directly into a QuerySpec over those slots, in the next turn.
- No new copy of the schema, in storage or anywhere else.

**Non-Goals**
- Rendering a browsable field dictionary. Explicitly dropped: the reframed goal
  says a table of field metadata is not useful in the app.
- Server-side field projection. `columns` is reserved and hard-rejected
  (`COLUMNS_NOT_SUPPORTED`, `query_spec.py:221`, ADR-0035) — see Decision 4.
- Retrieval (embedding or FTS) over slot descriptions — see Decision 6.

## Decisions

### Decision 1: Discovery is answered as a `clarification`, not a new status

`_reject_malformed_turn` (`converse_query_spec.py:120`) requires a clarification
to carry a `message` string and `query_spec: null`, and constrains the message no
further. A turn reading *"three fields on Donor bear on toxicology:
`tox_screen_result` (…), `cause_of_death_notes` (…), `autopsy_performed` (…) —
want those in the query?"* is in-contract today.

**Alternatives considered:**
- *A new `answer` status carrying a structured payload.* Coordinated changes in
  three repos, and Mosaic hard-rejects unrecognised statuses — replacing the
  whole turn with an `error` rather than degrading — so Exon could not emit one
  until a Mosaic release shipped.
- *Describing the schema as queryable rows* (the superseded change). Cannot serve
  the goal at all: `converse_query_spec` never executes, so the planner cannot
  read the rows while planning.

### Decision 2: The edit-cascade branches on whether a clarification is blocking

`edit_turn` marks every recomputed `clarification` as `suspended` and sets
`cascading = True`, suspending all later turns
(`exon/conversational_orchestrator.py:186`). That default was calibrated for a
distribution in which a clarification is exceptional — the planner failed to
build a spec. Under this change a clarification is how discovery *succeeds*, and
discovery is the normal opening move, so an edit anywhere upstream of a discovery
turn would suspend the rest of a conversation that is entirely fine.

Exon distinguishes the two in its own result dict — an *answered* clarification
(the draft is unchanged and nothing is needed from the user) from a *blocking*
one (the planner needs input) — and only the blocking kind cascades.

**Why this is available to us:** the cascade decision is made at recompute time
from the fresh `_request_turn_with_retry` result, and never reads `prior_turns`.
So the marker never has to survive the Mosaic round trip, where GraphQL's typed
`ConversationTurn` would drop an unknown key. Confirmed against
`conversational_orchestrator.py:139-197`.

**Risk if we got this wrong:** an answered discovery turn that *is* treated as
blocking degrades to today's behavior (over-suspension on edit), not to
incorrectness. `_current_query_spec` already reads past a trailing clarification
to the last real draft.

### Decision 3: Descriptions are rendered for every field, in both branches

`render_capability_grounding` returns early for reference fields with a
predicate (`spec_planner.py:181-188`) before the detail line is assembled. A
description added only to the scalar branch would silently omit every reference
field — the fields most likely to be the answer to "what do we have *about* X",
since that is where traversal targets are named.

### Decision 4: Field selection is client-side projection, not `columns`

`columns` is parsed and hard-rejected: *"'columns' (aggregate-vs-explode
selection, ADR-0035) has no Mosaic-side compiler yet — omit it, or request full
envelopes and project client-side"* (`query_spec.py:221`).

The rejection prescribes its own workaround, and Aperture is close to it:
`CollectionTable.tsx` renders every derived column with no visibility state, but
TanStack Table supports `columnVisibility` natively, and `export.ts:80` is
already `toCSV(columns, rows)` — it takes a column list as a parameter and would
accept a filtered one unchanged.

This lands in Aperture, which carries no OpenSpec. It belongs in an ADR there,
alongside the `ChatPanel.tsx:329` status-label fix. Flagged in the proposal's
Impact so the split is visible rather than assumed. `columns` becomes a
wire-efficiency optimization, not a blocker.

### Decision 5: The recipe is removed, not kept alongside

Keeping the rows as a browsable dictionary while discovery moves into the
conversation would preserve the staleness surface and the regeneration chore for
a capability the reframed goal says is not wanted. `make migrate` truncates the
database (`: > $(DB)`), so removal strands no data and needs no migration.

### Decision 6: Retrieval over descriptions is deferred

The FTS annotation on `SchemaField.description` was reaching for retrieval: find
the relevant slots without putting every description in the prompt. That earns
its place when a schema outgrows the prompt budget. At 39 slots across 4 entity
types it does not. Recorded as a scale note, not a reason to keep the rows.

## Risks / Trade-offs

- **Prompt growth.** 39 descriptions enter every planning call. Measurable
  against the benchmark; the mitigation if it bites is Decision 6, not a return
  to rows.
- **Discovery turns render as "needs an answer"** until the Aperture ADR lands.
  Cosmetic, and visible in the demo in the meantime.
- **The benchmark changes shape**, from row counts to plan-level assertions. That
  is the point — the old assertions tested the capability being removed — but it
  means q36–q38 are rewritten rather than ported, and their `expected-results.json`
  entries are removed rather than updated.

## Migration Plan

1. Land grounding + discovery + cascade in `exon/`.
2. Rewrite the benchmark questions; confirm no regression on q1–q35.
3. Remove the recipe, the generator, the Makefile targets, and the grounding note.
4. `make clean && make generate && make migrate && make ingest` — the two
   collections are gone; nothing else changes.

Rollback is `git revert`: no persisted state depends on any of it.

## Upstream findings (outlive this change)

Discovered while building the superseded change; worth filing against Mosaic
regardless of this repo's direction:

- `slot_model_to_dict` (`mcp/serialize.py:20`) omits `is_external_xref`, so
  `mosaic://schema` carries 12 of `SlotModel`'s 13 attributes.
- `MosaicSlotInfo` (`graphql/resolvers.py:593`) omits `is_external_xref` **and**
  `has_default`, so `hippoSchema` carries 11.
- The GraphQL field names are `hippoSchema` / `hippoEntityType` — part of the
  `hippo_*` surface debt (mosaic#124/#35/#57).

**Not yet filed:** the GitHub MCP server failed to connect this session
(`Authorization header is badly formatted`). These need filing once it is fixed.

## Findings from implementation

### The benchmark does not cover this change, in either direction

`harness/runner.py:26` imports `request_plan` from `planner.py`, and
`context/template.py:211` renders `render_schema_slots`. The suite grades the
**QueryPlan** path. This change touches `spec_planner.render_capability_grounding`,
which feeds `query_router.py` and `conversational_planner.py` — neither of which the
suite exercises. A full suite run therefore proves nothing about this change.

This widens the follow-up recorded in `evals/plan-expectations.yaml`: it is not just
that the three discovery questions have no shape to be asserted in, it is that the
whole QuerySpec/conversational surface is ungraded. Verification here was done by
direct live runs (see tasks 1.3, 2.2, 2.3, 3.4), which is honest but not repeatable
in CI.

Separately, the suite's default `json_schema` protocol is currently broken against
Bedrock — `output_config.format.schema: Empty schema ({}) ... is not supported`,
triggered by `"value": {}` in `SPEC_TOOL`'s criteria items (present at `HEAD`, not
introduced here). The stored fingerprint still records `supports_json_schema: true`
from 2026-08-18. Pre-existing and out of scope, but it will block the next person who
runs the harness; the run above forced `tool_call` to get around it.

### Removing a recipe means removing the DIRECTORY

`git rm` leaves the directory alive via untracked `__pycache__`, and Mosaic
auto-discovers `recipes/` next to the config (ADR-0005). The server went on serving
`SchemaEntityType` and `SchemaField` from a recipe whose tracked files were all
deleted — visible in `GET /schemas` and in `mosaic://capabilities`, with no
corresponding tables in the database. `rm -rf` the directory, and re-check the
served schema rather than the file listing.

## Open Questions

None blocking. The prompt-growth measurement (Risks) is a task, not a question.
