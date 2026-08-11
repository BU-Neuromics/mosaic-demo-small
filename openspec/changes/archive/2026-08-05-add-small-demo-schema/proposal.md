# Change: Add a small, self-contained Mosaic demo schema (Dataset/Donor/Sample/Workflow)

## Why

The large `hippo-benchmark` (brainbank) demo — 90 tables, thousands of
rows — was useful for learning how DataHelix's pieces fit together, but
it's too large to scan or use for focused, meaningful testing in Aperture.
We need a new, deliberately small demo — independent of the brainbank
schema, not a reduction of it — with a handful of classes but thousands of
*realistic* synthetic records, to seriously exercise Aperture's faceting,
filtering, search, and relationship-traversal behavior.

## What Changes

- **New LinkML schema**, four concrete entity classes (`Donor`, `Sample`,
  `Workflow`, `Dataset`) plus a lightweight abstract base (`Entity`) and one
  inlined value-object (`QualityMetrics`, not an entity) — small enough to
  scan, rich enough to exercise every mechanism that drives Aperture's UX
  (enum facets, full-text search, both of Mosaic's relationship-storage
  patterns, sparse/optional values, weighted categoricals, real numeric
  distributions, repeated-value skew, boolean facets, an exact-match
  index).
- **Synthetic data generation** via `linkml-data-gen`'s Python API (not the
  CLI, to avoid its 1000-per-class count clamp) driven by a `hints.yaml`
  file, producing ~3,600 total records (300 donors / 900 samples / 1,200
  workflows / 1,200 datasets) with real referential integrity and
  non-uniform distributions.
- **Ingest** via `mosaic ingest`, loaded into a standalone
  `mosaic.yaml`/`schemas/`/`data/mosaic.db` project directory — the same
  layout the `solo` recipe already expects, with zero changes to
  `datahelix`/`solo` recipe code.
- Deployable via the already-proven `PROJECT_DIR=<this-repo> make up` from
  `deploy/recipes/solo/` in the `datahelix` sibling checkout, leaving the
  existing `hippo-benchmark` demo project completely untouched.

## Impact

- Affected specs: `small-demo-schema` (new capability, this repo only)
- Affected code: entirely new files in this repo (`schemas/demo.yaml`,
  `hints.yaml`, `generate.py`, `Makefile`, `mosaic.yaml`) — no changes to
  any other repo (`datahelix`, `hippo-benchmark`, `hippo`,
  `linkml-data-gen`) except switching the local `linkml-data-gen` checkout
  to `origin/main` (a branch switch on an unmodified sibling checkout, no
  code changes there either).
