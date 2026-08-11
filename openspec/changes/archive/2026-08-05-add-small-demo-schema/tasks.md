## 1. Environment prerequisite

- [x] 1.1 Switch the local `linkml-data-gen` checkout
      (`/Users/christianlandaverde/Documents/schemas/linkml-data-gen`) to
      `origin/main` (currently on a stale single-commit branch missing the
      hints system and an id-collision fix).

## 2. Schema

- [x] 2.1 Author `schemas/demo.yaml`: `Donor`, `Sample`, `Workflow`,
      `Dataset` concrete classes, each `is_a: Entity` (Mosaic's real
      runtime-provided `hippo_core` base — `id`/`is_available`, no `name`,
      so each class declares its own `name`); `QualityMetrics` inlined
      value-object (no identifier). The tree-root container
      (`DemoBundle`: `donors`/`samples`/`workflows`/`datasets`) lives in a
      *separate* `generation_schema.yaml` at the repo root, not inside
      `schemas/` — see README's "Why there's a second schema file"
      (discovered empirically: a user-declared `tree_root` class inside
      `schemas/` gets its own real, unwanted 5th table; Mosaic ignores it
      for ingest purposes per ADR-0003 but the migration DDL still creates
      it, since it isn't a value type).
- [x] 2.2 Validate schema is self-contained: no `requires:` on any external
      reference-loader package, no imports from `hippo-benchmark` or any
      other schema (only `linkml:types` and Mosaic's bundled `hippo_core`).
- [x] 2.3 `mosaic migrate --schema-dir schemas --db-path data/mosaic.db`
      against a fresh (nonexistent) db — confirmed exactly the four entity
      tables (`Donor`/`Sample`/`Workflow`/`Dataset`) plus the standard
      supporting system tables and two FTS5 tables; no `DemoBundle`, no
      separate `QualityMetrics` table (correctly inlined as JSON).

## 3. Data generation

- [x] 3.1 Author `hints.yaml` — weighted `choices` for every facet enum,
      `distribution` (normal/lognormal/exponential) for numeric fields,
      `prob` for every sparse/optional field, `cardinality` (Poisson) for
      `Sample.tags` and `Workflow.input_samples`, plus a global
      `slots.is_available: {const: true}` (discovered: without a hint,
      Entity's required `is_available` boolean is generated ~50/50).
- [x] 3.2 Author `generate.py` using `linkml_data_gen.DataGenerator` +
      `GenerationConfig` with `count_overrides={"donors": 300, "samples":
      900, "workflows": 1200, "datasets": 1200}` and `max_count=1200`
      (Python API, not CLI). Also builds the `SchemaView` by hand with an
      explicit `importmap` (`hippo_core` + `demo`) since linkml-data-gen
      loads schemas with plain `SchemaView(path)`, not Mosaic's own
      importmap-injecting loader. Post-processing: seeds two FTS keywords
      and anchors `Workflow.completed_at` to `started_at + duration_hours`
      (otherwise independently-sampled dates put completion before start
      ~50% of the time).
- [x] 3.3 Run generation, spot-check the output bundle for referential
      integrity (no dangling `donor`/`produced_by`/`input_samples` ids)
      before ingesting — automated in `generate.py`, confirmed 300/900/
      1200/1200 with zero dangling references.

## 4. Ingest and project wiring

- [x] 4.1 Author `mosaic.yaml` (`schema_path: schemas/demo.yaml`,
      `storage_backend: sqlite`, `database_url: data/mosaic.db`).
- [x] 4.2 `mosaic ingest --file data/bundle.yaml --db-path data/mosaic.db
      --validate-schema schemas/demo.yaml` — confirmed `created=3600
      updated=0 errors=0`.
- [x] 4.3 Author a `Makefile` (targets: `generate`, `migrate`, `ingest`,
      `query`, `test`, `clean`) mirroring `hippo-example`'s Makefile shape.
      `query` runs a new `query_demo.py` (SDK-direct: counts, facets, a
      single-valued-FK filter query, full-text search, and the full
      multi-hop traversal) — useful independent of Aperture.

## 5. Launch and manual verification via Aperture

- [x] 5.1 From the `datahelix` sibling checkout's `deploy/recipes/solo/`:
      `PROJECT_DIR=<this-repo-path> make up` — required zero changes to
      `datahelix`/`solo` recipe code.
- [x] 5.2 Confirmed `deploy/recipes/solo/project/` (the existing
      `hippo-benchmark` demo) untouched throughout — identical checksum
      and mtime on its `data/mosaic.db` before and after.
- [x] 5.3 In Aperture (`localhost:8080`): faceted Donors by `cohort`/`sex`,
      Samples by `sample_type`/`storage_condition`, Workflows by
      `status`/`workflow_type`, Datasets by `dataset_type`/`access_level`
      (and the boolean `is_public` facet) — all confirmed via browser.
- [x] 5.4 Full-text search confirmed for the seeded keyword in both
      `Donor.notes` and `Dataset.description`.
- [x] 5.5 Traversed `Dataset → producedBy → Workflow → inputSamples →
      Sample → donor → Donor` via each entity's detail page
      (Relationships/History sections) — confirmed correct, consistent
      data at each hop.
- [x] 5.6 Confirmed (and documented, not "fixed") that no reverse query
      exists for "which Workflows consumed a given Sample" — the Sample
      detail page shows only its `Donor` relationship, nothing reverse.
- [x] 5.7 Visually confirmed realistic distributions in Aperture: `status`
      mostly `completed` (~68%) with a real tail, `replicate_number`
      mostly `1`, sparse fields genuinely sometimes absent.

      **Two bugs found and fixed during this step** (both outside the
      original task list, both documented in README's "Known upstream
      issues"): (a) `mosaic migrate` crashes on re-run against an
      already-migrated db when a class has a `required: true` multivalued
      reference slot — filed upstream as
      [BU-Neuromics/mosaic#143](https://github.com/BU-Neuromics/mosaic/issues/143);
      worked around by making `Workflow.input_samples` non-required
      (backed by a `hints.yaml` `prob: 0.98`). (b) `Dataset.file_size_bytes`
      was `range: integer`, which overflowed GraphQL's 32-bit `Int` at
      realistic large-file byte counts — fixed by changing it to `range:
      float`.

## 6. Regression / documentation

- [x] 6.1 `README.md` describing the demo's purpose, schema, generation
      approach, the two schema files and why, the two upstream issues
      found/filed, and exact commands to regenerate/reload it.
