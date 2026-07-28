## 1. Environment prerequisite

- [ ] 1.1 Switch the local `linkml-data-gen` checkout
      (`/Users/christianlandaverde/Documents/schemas/linkml-data-gen`) to
      `origin/main` (currently on a stale single-commit branch missing the
      hints system and an id-collision fix).

## 2. Schema

- [ ] 2.1 Author `schemas/demo.yaml`: abstract `Entity` base (`id`, `name`);
      `Donor`, `Sample`, `Workflow`, `Dataset` concrete classes per the
      design doc's field list; `QualityMetrics` inlined value-object
      (no identifier); `DemoBundle` tree-root container
      (`donors`/`samples`/`workflows`/`datasets`, `multivalued` +
      `inlined_as_list`).
- [ ] 2.2 Validate schema is self-contained: no `requires:` on any external
      reference-loader package, no imports from `hippo-benchmark` or any
      other schema.
- [ ] 2.3 `mosaic migrate --schema-dir schemas --db-path data/mosaic.db`
      against a fresh (nonexistent) db — confirms the schema is valid
      LinkML and Mosaic-compatible before generating any data.

## 3. Data generation

- [ ] 3.1 Author `hints.yaml` — weighted `choices` for every facet enum,
      `distribution` (normal/lognormal) for numeric fields, `prob` for
      every sparse/optional field, `cardinality` (Poisson) for
      `Sample.tags` and `Workflow.input_samples`, per the design doc's
      per-field list.
- [ ] 3.2 Author `generate.py` using `linkml_data_gen.DataGenerator` +
      `GenerationConfig` with `count_overrides={"donors": 300, "samples":
      900, "workflows": 1200, "datasets": 1200}` and `max_count=1200`
      (Python API, not CLI, to avoid the 1000-per-class clamp).
- [ ] 3.3 Run generation, spot-check the output bundle for referential
      integrity (no dangling `donor`/`produced_by`/`input_samples` ids)
      before ingesting.

## 4. Ingest and project wiring

- [ ] 4.1 Author `mosaic.yaml` (`schema_path: schemas/demo.yaml`,
      `storage_backend: sqlite`, `database_url: data/mosaic.db`).
- [ ] 4.2 `mosaic ingest --file data/bundle.yaml --db-path data/mosaic.db
      --validate-schema schemas/demo.yaml` — confirm zero errors and
      `created` counts match the target per class.
- [ ] 4.3 Author a `Makefile` (targets: `generate`, `migrate`, `ingest`,
      `query`, `test`) mirroring `hippo-example`'s Makefile shape for
      consistency with the platform's established per-project convention.

## 5. Launch and manual verification via Aperture

- [ ] 5.1 From the `datahelix` sibling checkout's `deploy/recipes/solo/`:
      `PROJECT_DIR=<this-repo-path> make up` — confirm this requires zero
      changes to `datahelix`/`solo` recipe code.
- [ ] 5.2 Confirm `deploy/recipes/solo/project/` (the existing
      `hippo-benchmark` demo) is untouched throughout (mtime/checksum
      check on its `data/mosaic.db`, same discipline as prior work).
- [ ] 5.3 In Aperture (`localhost:8080`): facet Donors by `cohort`/`sex`,
      Samples by `sample_type`/`storage_condition`, Workflows by
      `status`/`workflow_type`, Datasets by `dataset_type`/`access_level`.
- [ ] 5.4 Full-text search a seeded keyword in `Donor.notes` and
      `Dataset.description`.
- [ ] 5.5 Traverse `Dataset → producedBy → Workflow → inputSamples →
      Sample → donor → Donor` (multi-hop, forward direction) and confirm
      correct, consistent data at each hop.
- [ ] 5.6 Confirm (and document, not "fix") that no reverse query exists
      for "which Workflows consumed a given Sample" — the multivalued
      relationship has no reverse query surface, per design.
- [ ] 5.7 Visually confirm distributions look realistic in Aperture: e.g.
      `status` mostly `completed` with a real tail of failures,
      `replicate_number` mostly `1`, sparse fields genuinely sometimes
      absent (not all-populated, not all-empty).

## 6. Regression / documentation

- [ ] 6.1 `README.md` describing the demo's purpose, schema, generation
      approach, and exact commands to regenerate/reload it.
