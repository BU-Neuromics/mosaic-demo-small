# Project Context

## Purpose
A small, self-contained Mosaic (LinkML) demo instance — four core entity
classes (Dataset, Donor, Sample, Workflow) with thousands of realistic
synthetic records — for exercising Aperture (facets, filters, search,
relationship traversal) in a scale that's easy to scan and reason about.
Deliberately independent of the larger `hippo-benchmark`/brainbank demo
(see sibling repo `brainbank-hippo-performance/hippo-benchmark/`) — not a
reduction or refactor of it, a fresh, smaller schema from scratch.

## Tech Stack
- LinkML (schema authoring)
- `linkml-data-gen` (synthetic data generation; sibling repo at
  `../linkml-data-gen`, must be on `origin/main` for the hints system)
- Mosaic (`datahelix-mosaic` / `mosaic` CLI — sibling repo `../hippo`) for
  `migrate`/`ingest`/`serve`
- DataHelix `solo` deployment recipe (sibling repo `../datahelix`,
  `deploy/recipes/solo/`) for running Aperture against this project via
  `PROJECT_DIR`

## Project Conventions

### Code Style
LinkML YAML schema conventions borrowed from `hippo-benchmark/schema/`
(lightweight `Entity` abstract base with `id`/`name`; enums for anything
meant to be a facet; `hippo_search: fts5` for free-text fields;
`hippo_index: true` for exact-match lookup keys; inlined value-objects for
non-entity embedded data).

### Architecture Patterns
Standard Mosaic project layout: `mosaic.yaml` + `schemas/*.yaml` +
`data/mosaic.db`. Data generated via `linkml-data-gen`'s Python API (not
CLI, to avoid the 1000-per-class count clamp) driven by a `hints.yaml` file
for realistic (non-uniform) distributions, then loaded via
`mosaic ingest --file ... --db-path ... --validate-schema ...`.

### Testing Strategy
Validate schema via `mosaic migrate` on a fresh db; validate generated
bundle referential integrity before ingest; validate post-ingest via
GraphQL introspection, filtered/faceted queries, full-text search, and
multi-hop relationship traversal — see the `add-small-demo-schema` change's
acceptance criteria for the concrete checklist.

### Git Workflow
Published as a **private** repo under `BU-Neuromics/mosaic-demo-small` (2026-08-05), alongside the
`mosaic`/`aperture`/`reel` components this demo exercises. Previously local-only; the
"never pushed anywhere" rule that applied to sibling repos like `hippo-reference-ensembl` no
longer applies to this one. Generated artifacts (`*.db`, `data/bundle.yaml`) stay gitignored —
regenerate with `make generate migrate ingest`.

## Domain Context
Models a simplified biobank/omics pipeline: a `Donor` yields one or more
`Sample`s; a `Workflow` run consumes one or more `Sample`s and produces a
`Dataset`. Chosen specifically to exercise both of Mosaic's relationship-
storage patterns: single-valued FK references (bidirectionally queryable)
and multivalued references (forward-resolved only, stored in the
`relationships` table per Mosaic ADR-0002 — a real platform limitation
worth demonstrating, not a bug to work around).

## Important Constraints
- Schema must be self-contained — no `requires:` on external
  reference-loader packages, no dependency on `hippo-benchmark`'s schema or
  data.
- Data must be realistic and varied — enums with weighted distributions,
  real numeric distributions (normal/lognormal), sparse optional fields,
  skewed repeated values — not purely uniform-random and not thousands of
  near-identical rows.
- Never touch upstream/remote git state on **other** repos (`../hippo`, `../datahelix`,
  `../linkml-data-gen`, …) — read-only there, always. This repo has its own remote (see Git
  Workflow) and may be pushed to.

## External Dependencies
- `linkml-data-gen` (BU-Neuromics) — must be switched to `origin/main`
  locally for the hints system.
- `datahelix-mosaic` (`mosaic` CLI) — via the `../hippo` sibling checkout.
- DataHelix `solo` recipe — via the `../datahelix` sibling checkout.
