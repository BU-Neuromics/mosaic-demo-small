## Context

Investigated three things before designing this (see sibling repos, no
code changes made there):

- **How the large-schema demo was built** (`hippo-benchmark/`): project
  shape (`mosaic.yaml`/`schemas/`/`data/mosaic.db`), the `linkml-data-gen`
  → `remap_accessors.py`-style bridge → `mosaic ingest` pipeline (also used
  by `datahelix/deploy/recipes/demo/`), and concrete LinkML conventions
  (`Entity`-style abstract base with `id`/`name`, enums for facets,
  `hippo_search`/`hippo_index` annotations, inlined value-objects for
  non-entity data).
- **`linkml-data-gen`'s capabilities**: the locally-checked-out branch was
  stale (single commit); `origin/main` adds a **hints file** mechanism
  (`src/linkml_data_gen/hints.py`) that's essentially required to avoid
  uniform-random-only generation — weighted enum choices, real numeric
  distributions (normal/lognormal/exponential/triangular), per-slot
  population probability (`prob`) for realistic sparsity, and cardinality
  distributions (including Poisson) for multivalued slots. Two-phase
  generation (id-shells before fill) guarantees referential integrity in
  container mode. The CLI clamps `--count-for` to `[1,1000]` per class; the
  Python API (`GenerationConfig`) does not.
- **What actually drives Aperture's behavior** (`hippo/src/mosaic/graphql/
  schema_builder.py`, `schema_typing.py`, ADR-0002, `reference_hippo_ext.md`):
  only **enum** slots get free, schema-declared discrete facet values via
  introspection; plain strings/floats are filterable (`EQ`/`IN` only, no
  range operator) but not facetable without client-side work. Single-valued
  reference slots become a real FK column, forward-resolved *and*
  reverse-queryable via an equality filter. Multivalued reference slots are
  stored in the `relationships` table (ADR-0002) and are
  forward-resolved-only — **no reverse query surface exists at all**, a
  real platform limitation worth deliberately exercising rather than
  avoiding. `hippo_search: fts5` drives full-text search (string slots
  only). A class needs an `identifier` slot to be a real, facetable entity;
  without one it's inlined as an opaque `JSON` scalar.

## Goals / Non-Goals

- Goals:
  - A schema small enough to scan and reason about in one sitting (4 entity
    classes), but rich enough to exercise every one of the above mechanisms
    at least once.
  - Thousands of records with genuine referential integrity, realistic
    (non-uniform) distributions, and deliberate optional/missing/repeated-
    value cases — not purely random and not near-identical rows.
  - Fully independent of `hippo-benchmark` — no shared schema files, no
    shared data, no code changes to it or to `datahelix`/`solo`.
- Non-Goals:
  - Reducing or refactoring the brainbank schema — this is a from-scratch
    design.
  - Achieving full ontology-backed dynamic enums (`reachable_from`) —
    plain static `permissible_values` are sufficient and simpler for a
    small demo.
  - Fixing or working around the "no reverse query for multivalued
    relationships" limitation — the plan is to *demonstrate* it, not
    solve it.

## Decisions

- **Decision: reuse the `Entity` abstract-base + enum-heavy pattern from
  `hippo-benchmark/schema/core.yaml`**, rather than inventing a new
  convention. Every concrete class is `is_a: Entity` (`id`, `name`
  inherited). Rationale: proven, minimal, and keeps this schema idiomatic
  with the rest of the platform's schemas.
- **Decision: the relationship chain is `Donor —1:N—▶ Sample —N:M(fwd-only)—▶
  Workflow —1:N—▶ Dataset`**, deliberately mixing both of Mosaic's
  relationship-storage patterns (single-valued FK vs. multivalued
  `relationships`-table edge) rather than using one pattern throughout.
  Rationale: the point of this demo is to seriously exercise Aperture, and
  relationship traversal is explicitly one of the things we're asked to
  test — using only one storage pattern would leave a whole class of
  platform behavior (and its real limitation) unexercised.
  - Alternative considered: also giving `Dataset` a direct multivalued
    `samples` reference (in addition to reaching samples via `Workflow`).
    Rejected as redundant complexity — the existing chain already reaches
    `Sample` from `Dataset` via a two-hop traversal, and the user
    explicitly asked to keep the schema intentionally small.
- **Decision: generate via the Python API with explicit `count_overrides`,
  not the CLI.** The CLI's `[1,1000]` clamp on `--count-for` would prevent
  reaching the target Workflow/Dataset counts (1,200 each) in one pass.
- **Decision: one inlined value-object (`QualityMetrics`) on `Dataset`
  only**, not a standalone entity. Rationale: demonstrates the
  `STRUCTURED`/JSON slot kind (a real, distinct code path in
  `schema_builder.py`) without adding a fifth entity table or its own
  facet/filter surface, keeping the schema's entity count at exactly four
  as requested.
- **Decision: switch the local `linkml-data-gen` checkout to `origin/main`**
  (approved by user) rather than working around the stale branch's
  uniform-random-only generation, since the hints system is close to a
  hard requirement for the "realistic, non-uniform, non-identical" data
  goal.

## Risks / Trade-offs

- **`linkml-data-gen` cannot enforce cross-field correlation** (e.g.
  `completed_at` being null exactly when `status` is `running`/`queued`;
  `access_level` correlating with `is_public`). Mitigated by choosing
  `prob`/`choices` weights that *approximate* the expected correlation
  independently per field — acknowledged as an approximation, not true
  correlation, in both this design and the acceptance criteria (don't
  expect the demo to assert exact cross-field consistency for these
  fields).
- **The reverse multivalued-relationship query genuinely doesn't work** —
  this is called out explicitly as an *expected*, documented result in
  acceptance criteria, not a bug to chase.
- **Switching `linkml-data-gen`'s branch** changes local repo state on a
  shared sibling checkout used by other work in this environment (e.g. the
  brainbank demo's generation scripts). Low risk — `origin/main` is a
  strict superset (adds the hints system, fixes an id-collision bug,
  documented as backward-compatible in that repo's own changelog per prior
  investigation) — but flagged here for visibility.

## Migration Plan

N/A — this is a new, standalone project with no existing state to migrate.

## Open Questions

- Exact hint parameter values (weights, distribution means/stds) are
  proposed in the delta spec's scenarios at a representative level of
  detail; final tuning happens during implementation and is expected to be
  iterated on visually in Aperture rather than locked in advance.
