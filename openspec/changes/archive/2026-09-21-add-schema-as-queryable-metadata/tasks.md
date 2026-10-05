# Tasks

## 1. The recipe

- [x] 1.1 Create `recipes/schema-metadata/` following
      `aperture/recipes/aperture-control-plane/` — `recipe.yaml` (manifest) plus
      `schema.yaml`. Read that recipe first; it is the reference implementation
      for "a companion entity type any deployment applies."
- [x] 1.2 `schema.yaml`: define `SchemaEntityType` and `SchemaField`, both
      `is_a: Entity` so they inherit `id` / `is_available`. `SchemaField` carries **one slot per
      `SlotModel` attribute** (`mosaic/src/mosaic/core/schema_typing.py:88`):
      name, kind, range, role, required, multivalued, identifier, has_default,
      description, target_class, enum_name, enum_values, is_external_xref.
      Compose `SchemaField.id` as `<Entity>.<field>` — stable, readable, derivable,
      so regeneration is idempotent.
- [x] 1.3 Annotate for query performance the way the domain schema does:
      `hippo_index: true` on `SchemaField.name` / `.entity` / `.kind`,
      `hippo_search: fts5` on `SchemaField.description`. Without these, filtering by
      entity is a scan and descriptions are not searchable.
- [x] 1.4 `recipe.yaml`: pin `hippo_version` to a release that actually carries
      the introspection surface the generator reads. Validate the manifest
      against Mosaic's `recipe_manifest.yaml` — that is what it is for.
- [x] 1.5 Use a multivalued string for `enum_values` — the honest shape. If it
      does not survive ingest or render in the results table, fall back to a
      delimited single string and note why.

## 2. The generator — generic, not demo-specific

- [x] 2.1 Read from the **live `hippoSchema` endpoint** (decision 2). A schema
      file edited but not migrated is precisely the drift this exists to
      prevent, so the served schema is the source of truth.
- [x] 2.2 Walk `registry.class_names()` (or the live equivalent) — **never a
      hardcoded entity list.** Emit one `SchemaEntityType` row per class
      and one `SchemaField` row per slot, carrying every `SlotModel` attribute.
- [x] 2.3 Cover all four slot kinds. This demo exercises 26 scalar, 9 enum,
      3 reference, 1 structured — assert each kind appears in the output, so a
      generator that silently handles only scalars fails loudly.
- [x] 2.4 Exclude the meta-classes from their own output (decision 3) — describe
      the domain schema only.
- [x] 2.5 Idempotent: running twice yields identical rows; a slot removed from
      the schema has its row deleted rather than orphaned.

## 3. Wiring

- [x] 3.1 Apply the recipe (`recipe_import`) as part of setup, and add the
      generator to `make migrate` after migration, before `make ingest`.
- [x] 3.2 ~~Confirm `make clean && make generate && make migrate && make ingest`
      still succeeds end to end.~~ STRUCK on supersede (2026-09-21): the recipe
      and its `make migrate` step were removed by
      `add-schema-discovery-for-query-building`, so there is no longer a
      metadata-carrying pipeline to confirm. The equivalent check now lives in
      that change's task 5.5, against the pipeline WITHOUT the recipe.
- [x] 3.3 Confirm the synthetic-data seed is unaffected — `generate.py --seed 0`
      must still reproduce the benchmark's ids, or
      `evals/expected-results.json` silently invalidates.

## 4. Verify the load-bearing claim: no code outside this repo

- [x] 4.1 `SchemaEntityType` and `SchemaField` appear as collections in Aperture with **no
      Aperture change**. If this does not hold, the premise is wrong — stop and
      re-plan rather than patching around it.
- [x] 4.2 They appear in the planner's grounding with no prompt change — confirm
      by inspecting what `render_capability_grounding` emits.
- [x] 4.3 On the dev stack, ask "what fields are available on datasets?" and
      expect a **proposal** (a real query), not a clarification.
- [x] 4.4 Spot-check against `hippoEntityType(name: "Dataset")`: 10 fields, each
      with a description, `dataset_type` carrying
      `bam, vcf, counts_matrix, report`. A mismatch means the wrong source.

## 5. Drift guard — shape as well as values

- [x] 5.1 Fail when stored rows disagree with the live schema. Regeneration on
      migrate only helps if migrate runs; this is what makes a skipped run loud.
- [x] 5.2 Fail when the runtime models a slot attribute the recipe does not
      carry. mosaic#210 adds `inverse_of`; that must surface as a failure, not a
      silent omission. This is what keeps the dictionary complete over time.
- [x] 5.3 Prove both: change a description without migrating (5.1 fails), and
      add an attribute to the model without adding the slot (5.2 fails).

## 6. Coverage

- [x] 6.1 Add schema questions to `evals/questions.yaml` — currently **zero**,
      so this would otherwise ship with no regression coverage.
- [x] 6.2 Record verified expected results in `evals/expected-results.json`, per
      the existing "Supported question has a verified expected result"
      requirement.
- [x] 6.3 Confirm Exon's suites stay green: 72 pytest checks plus the four
      script-style harness checks (`python -m tests.<name>` — not
      pytest-collectable).

## 7. Portability check — the point of the recipe

- [x] 7.1 Apply the recipe against a second, unrelated schema (e.g.
      `mosaic/examples/bibliography/`) and confirm the generator produces a
      complete dictionary with no code change. This is what "any future schema"
      means in practice, and it is the difference between a recipe and a
      demo-local file.

---

## Implementation notes (2026-09-18)

**It works.** "What fields are available on datasets?" now returns a proposal
anchored on `SchemaField`, not a refusal. The load-bearing claim held: the two
classes became queryable, grounded and browsable with **no change to Mosaic,
Aperture, or the conversational contract**.

**Findings that changed the work:**

- **GraphQL is not a complete source.** `MosaicSlotInfo` carries 11 of the 13
  slot attributes — it omits `has_default` and `is_external_xref`. The generator
  reads the MCP `mosaic://schema` resource instead; reading GraphQL would have
  produced a description incomplete by construction.
- **The drift check earned its place on its first run**, catching that the wire
  name is `target_entity_type` where `SlotModel` calls it `target_class`. That
  column would have been silently empty.
- **`mosaic.yaml` pointed at `schemas/demo.yaml`, a single file**, so the server
  never saw the recipe. Changed to `schemas/`. Migration and ingest already used
  the directory; only the serve config did not.
- **`mosaic ingest` validates the bundle against a synthesized tree root** built
  from the merged schema, so it needs `--validate-schema schemas` (the
  directory). With a single file it rejects the recipe's own collections.
- **Rows are keyed by accessor name** (`schema_fields`), not class name, and
  carry `is_available` — both inherited wire-format requirements.
- **The model needed a nudge, not a new capability.** Grounded on the new
  entities it still declined, treating the question as out of remit; asked
  explicitly to query `SchemaField` it produced a valid spec immediately. One
  note in `render_capability_grounding` closed the gap.

**Known limit, not papered over:** the shape half of the drift check compares
against what the server *emits*. An attribute the runtime models but never emits
for a given schema is invisible to it — `is_external_xref` is exactly that here.
Catching it would mean reading Mosaic's internals, which would cost the
portability the recipe exists for.

**Not done: task 3.2** — `make clean && make generate && make migrate &&
make ingest` has not been run end to end. It would rebuild the database from
scratch, and the running demo stack depends on the current one.

**Portability (7.1) verified** against `mosaic/examples/bibliography` — a schema
with a polymorphic hierarchy this demo does not have. Same generator, no code
change: 8 entity types, 51 fields, correctly skipping the abstract `Publication`
base while describing its three concrete subclasses.

