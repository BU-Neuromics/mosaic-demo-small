# Describe the schema as data, shipped as a recipe

> ## SUPERSEDED (2026-09-21) by `add-schema-discovery-for-query-building`
>
> **The goal was restated.** What Exon needs to support is schema discovery *in
> service of query construction* — a researcher asks what the data model holds so
> they can decide which data elements to pull back ("what information do we have
> on donors about toxicology reports?"). A rendered table of field metadata does
> not serve that and is not otherwise useful in the app.
>
> Against that goal this change is not merely unnecessary but obstructive:
> `converse_query_spec` never executes, so the planner cannot read the rows while
> planning. The only in-contract path is a *proposal* over `SchemaField` that the
> user must execute and read before asking again — which makes the unwanted table
> a mandatory intermediate step.
>
> **Two claims below are wrong, and they were load-bearing for the decision:**
>
> 1. "The status enum is exactly `proposal | clarification`." It is
>    `{proposal, clarification, suspended}` (`converse_query_spec.py:49`), plus
>    `error`.
> 2. "A metadata answer is none of those, so declining is the only in-contract
>    move." `_reject_malformed_turn` (`:120`) requires a clarification to carry a
>    `message` string and `query_spec: null`, and constrains the message no
>    further. An answer in a clarification message was in-contract all along.
>
> **What survives:** the *cascade* objection under "Alternatives considered" is
> real and verified — `conversational_orchestrator.py:186` marks any recomputed
> `clarification` as suspended and cascades. The superseding change addresses it
> rather than accepting it (its `design.md` Decision 2), by branching the cascade
> on whether a clarification blocks.
>
> **The real gap this change worked around:** `render_capability_grounding`
> (`exon/spec_planner.py:166`) drops each slot's `description`, though the
> manifest carries it. The rows put that prose into an FTS-indexed column so the
> planner could *retrieve* what it should simply have been *shown*.
>
> **Also worth keeping:** the introspection-coverage findings this work turned up
> — `slot_model_to_dict` omits `is_external_xref`; `MosaicSlotInfo` omits it and
> `has_default`. Carried into the superseding change's `design.md` for filing
> upstream.
>
> The implementation described below shipped in `a5d1553` and is removed by the
> superseding change. This record is kept unarchived until that removal lands.

## Why

Asked "what fields are available on datasets?", the conversational panel refuses
— and contradicts itself doing it. Verified live 2026-09-17:

> **turn 1:** "are you asking me to describe the available fields on Dataset
> entities (in which case **I can list them from the manifest**)…"
>
> **turn 2**, taking it up on that offer: "describing the manifest's available
> fields isn't a query refinement — it's a reference lookup."

Not a data gap: the planner's grounding already carries every field, type and
enum, and `schemas/demo.yaml` annotates all 39 slots with a `description:`.

The gap is the **reply contract**. `tool_choice` is forced and the status enum is
exactly `proposal | clarification`, where `proposal` structurally requires a
`query_spec`. A metadata answer is none of those, so declining is the only
in-contract move.

**The reframe:** that question asks for *a table of fields*. A table is what a
query returns. Describe the schema as data and the question stops being a special
case — `anchor: SchemaField`, `entity = Dataset`, answered as an ordinary `proposal`
and rendered by the same results table as everything else.

## What Changes

**Ship it as a recipe**, following the established pattern:
`aperture/recipes/aperture-control-plane/` is a companion LinkML schema that
persists Aperture's own state as ordinary Mosaic entities, applied by any
deployment via `recipe_import`. Its own description: *"Mosaic ships no such type;
this recipe is the reference implementation any deployment applies."*

A recipe is `recipe.yaml` (the manifest, validated against Mosaic's
`recipe_manifest.yaml`) plus `schema.yaml`. That makes this portable and
versioned rather than welded to this demo — which is the requirement: **any
schema authored later gets its metadata for free, with no per-project work.**

- **`recipes/schema-metadata/schema.yaml`** — two classes:
  - `SchemaEntityType` — `id`, `name`, `description`
  - `SchemaField` — `id`, `entity` (reference → `SchemaEntityType`), plus **one slot for
    every fact the runtime models about a slot**: `name`, `kind`, `range`,
    `role`, `required`, `multivalued`, `identifier`, `has_default`,
    `description`, `target_class`, `enum_name`, `enum_values`,
    `is_external_xref`.
- **`recipes/schema-metadata/recipe.yaml`** — manifest, `hippo_version` pinned to
  a release carrying the introspection surface this reads.
- **A generator** that walks any schema and emits the rows. Derived, never
  hand-authored.
- **Wire the generator into `make migrate`** so rows regenerate on schema change.
- **A drift check** that fails when stored rows disagree with the live schema.
- **Schema questions in `evals/questions.yaml`**, which today has zero.

## Completeness is the contract

`SchemaField` mirrors Mosaic's `SlotModel` (`core/schema_typing.py:88`) attribute for
attribute, and the generator walks `registry.class_names()` rather than a list of
known entities.

A hand-picked subset looks fine against this demo and silently loses information
the moment a schema uses something it did not anticipate: without `kind` a
reference is indistinguishable from a scalar; without `target_class` a reference
does not say what it points to; without `role` a researcher cannot tell their own
fields from the system's `id` / `is_available`.

It must also not be frozen — mosaic#210 adds `inverse_of` to the slot model, and
a hand-picked list would drop it silently the day that merges. The drift check
covers the schema's *shape*, not only its values, so a new slot attribute
surfaces as a failure rather than an omission.

This demo exercises all four slot kinds today (26 scalar, 9 enum, 3 reference,
1 structured), so it is a genuine test of the generic path rather than of one
shape.

## Why this needs no code outside this repo

`build_capability_manifest()` (`mosaic/src/mosaic/core/schema_typing.py:334`)
iterates `registry.class_names()`. Every class in the schema automatically
becomes queryable, grounded in the planner's prompt, exposed over GraphQL,
filterable, sortable and renderable. The recipe's two classes inherit all of it
with no special casing.

Because they are ordinary collections, Aperture also lists them in navigation —
so the field dictionary is browsable without the chat, at no extra cost.

## Alternatives considered

- **A new `answer` turn status carrying a structured payload.** Disproportionate:
  coordinated changes in three repos, and Mosaic *hard-rejects* unrecognised
  statuses (`converse_query_spec.py:49`, `:124`) — replacing the whole turn with
  an error rather than degrading — so Exon could not emit one until a Mosaic
  release shipped.
- **`clarification` carrying the answer as prose.** No contract change, but it
  mislabels a completed turn as needing input, and
  `conversational_orchestrator.py:186` marks any recomputed `clarification` as
  suspended on edit — so a metadata turn would cascade-suspend every later turn.
  A correctness bug, not a cosmetic one.
- **A project-local schema file instead of a recipe.** Simpler to write, but
  welds the capability to this demo. The requirement is that future schemas get
  this without per-project work, which is what a recipe delivers.
- **`linkml-data-gen` as the generator.** Wrong tool — it produces *synthetic*
  data (every CLI option is a seed or probability); we need factual rows. It does
  show the API: `SchemaView.all_classes()` and `class_induced_slots()`.


## Decisions taken

Recorded here rather than left open, so implementation is unblocked. All four are
reversible before any data exists; revisit only with a reason.

1. **Class names are prefixed** — `SchemaEntityType` / `SchemaField`, following
   `ApertureDocument`. Bare `Field` and `EntityType` are names a future domain
   schema could plausibly want (a form builder, a survey tool, a data catalog),
   and a collision in a merged registry is painful to undo once rows exist.
2. **The generator reads the live endpoint**, not the local schema file. Drift is
   the failure this change exists to prevent, so the schema actually being served
   is the honest source. Costs a running server to regenerate — acceptable, since
   regeneration is wired into `make migrate`, which already assumes one.
3. **The metadata classes do not describe themselves.** Describing only the
   domain schema keeps the dictionary about the user's data and roughly halves
   the rows. Self-description is philosophically tidier and adds nothing a
   researcher asked for.
4. **The recipe lives in this repo for now** (`recipes/schema-metadata/`), to be
   proposed upstream once there is a working implementation to point at — the
   same path `aperture-control-plane` took.

## Risk

The rows are a second representation of the schema and will lie if they drift.
Regeneration during `make migrate` is the guard, but only if migrate is run —
hence the drift check, which is part of this change rather than a follow-up.

## Follow-up, not in scope

If this proves out, the natural home is Mosaic itself rather than a recipe each
deployment imports — ADR-0009 already anticipated the capability manifest
becoming "framework-level machinery other consumers could read from." File that
upstream once there is a working implementation to point at.
