# Change: Ground schema discovery in slot descriptions, and retire the metadata rows

## Why

The use case Exon needs to support is **schema discovery in service of query
construction**: a researcher asks what the data model holds so they can decide
which data elements to pull back. The motivating question is not "list the
fields on Dataset" but:

> what information do we have on donors about toxicology reports?

The only useful response is one that names the relevant slots so the next turn
can build a QuerySpec over them. A rendered table of field metadata does not
serve that, and is not otherwise useful in the app.

`add-schema-as-queryable-metadata` solved a different problem — getting a
*table* of field metadata on screen — by describing the schema as data
(`SchemaEntityType` / `SchemaField` rows, generated from the live endpoint and
ingested). Against the reframed goal that approach is not merely unnecessary,
it is actively in the way:

- **`converse_query_spec` never executes** (ADR-0009; `resolvers.py:426`). Exon
  cannot consult the rows while planning. The only in-contract path is to return
  a *proposal* anchored on `SchemaField`, which the user must then execute, read
  as a table, and follow up on. The rows **mandate** the artifact we have just
  established is useless, as a required intermediate step, at the cost of a round
  trip through the UI.
- **The rows are a fourth copy** of facts already carried by `__schema`,
  `hippoSchema`/`MosaicSlotInfo`, and `mosaic://schema` — the only copy that is
  materialized into storage, and therefore the only one that can go stale.

### The actual gap

`render_capability_grounding` (`exon/spec_planner.py:166`) **drops the slot
descriptions**. The capability manifest carries them — `slot_model_to_dict`
includes `description` (`mosaic/src/mosaic/mcp/serialize.py:29`), spread into
every field by `entity_capability_to_dict` (`:54`) — but the renderer emits only
name, range, ops, permissible values and orderability. The planner currently
sees:

```
    tox_screen_result: string -- ops: eq, contains
```

and has no way to know that field concerns toxicology unless the name says so.
`schemas/demo.yaml` annotates all 39 slots with a `description:`, and none of
that prose reaches the model.

Seen this way, the rows were a workaround for grounding that omits the
descriptions: they put the prose into an FTS-indexed column so the planner could
*retrieve* what it should simply have been *shown*.

### Correcting the record

The superseded proposal asserts that "the status enum is exactly
`proposal | clarification`… so declining is the only in-contract move." Both
halves are wrong, and the error is load-bearing for the decision it justified:

- The enum is `{proposal, clarification, suspended}` (`converse_query_spec.py:49`),
  plus `error`.
- `_reject_malformed_turn` (`:120`) requires a clarification to carry a `message`
  string and `query_spec: null`. **Nothing constrains that message to be a
  question.** A clarification whose message names the relevant slots is
  in-contract today, with no change to any repo.

What remains true from that proposal's analysis is the *cascade* objection, and
this change addresses it directly rather than accepting it — see `design.md`
Decision 2.

## What Changes

- **Slot descriptions enter the planner's grounding.** Both branches of
  `render_capability_grounding` — the reference-field branch `continue`s before
  the detail line is built, so it needs the addition too.
- **Schema discovery is answered in-conversation as a `clarification`**, naming
  the relevant slots and inviting the follow-up that builds the spec. No new turn
  status, no contract change, no Mosaic release.
- **The edit-cascade rule is recalibrated.** Today any recomputed `clarification`
  is marked `suspended` and cascades to every later turn
  (`exon/conversational_orchestrator.py:186`). That was correct when a
  clarification meant "I could not build a spec"; under this change a
  clarification is how discovery *succeeds*, so the rule now suspends
  conversations that are fine.
- **The schema-metadata recipe is retired** — `recipes/schema-metadata/`, the
  generator, `make metadata` / `make check-metadata`, the grounding note at the
  end of `render_capability_grounding`, and the two classes.
- **The benchmark's schema questions are rewritten**, from row-count assertions
  over `schemaFields(...)` to plan-level assertions: given a discovery question,
  does the conversation converge on a QuerySpec naming the right slots?
- **BREAKING (demo-local):** `SchemaEntityType` and `SchemaField` stop being
  queryable collections and disappear from Aperture's navigation.

## Impact

- **Affected specs:** `exon-query-planner` (MODIFIED), `query-benchmark` (ADDED)
- **Affected pending change:** `add-exon-conversational-contract` owns the
  `exon-conversational-planner` capability, which is still a proposal rather than
  truth in `openspec/specs/`. Its two affected requirements — "Response is
  discriminated between a proposal and a clarification" and "Each turn is
  individually addressable and editable" — are **amended in place** rather than
  deltaed against, since a delta applies to `specs/`, not to another proposal.
  Recorded as task 4.
- **Affected code:** `exon/spec_planner.py`, `exon/conversational_orchestrator.py`,
  `recipes/schema-metadata/` (removed), `Makefile`, `mosaic.yaml`,
  `evals/questions.yaml`, `evals/expected-results.json`, `DEMO.md`
- **Supersedes:** `add-schema-as-queryable-metadata`
- **Outside this repo, not tracked here:** Aperture has no OpenSpec, only
  `design/decisions/`. Two pieces land there as an ADR or go untracked —
  the `ChatPanel.tsx:329` status label ("needs an answer" is wrong chrome for an
  answer), and client-side column visibility in the results table. Named in
  `design.md` Decision 4.
