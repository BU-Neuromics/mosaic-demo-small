# mosaic-demo-small

A small, self-contained Mosaic demo: four entity classes (`Donor`, `Sample`,
`Workflow`, `Dataset`) modeling a simplified biobank/omics pipeline, with
~3,600 realistic synthetic records. Built to seriously exercise Aperture's
faceting, full-text search, and relationship traversal at a scale that's easy
to scan and reason about — deliberately independent of the much larger
`hippo-benchmark`/brainbank demo (see sibling repo
`brainbank-hippo-performance/hippo-benchmark/`), not a reduction of it.

See `openspec/changes/add-small-demo-schema/` (proposal, design, tasks, delta
spec) for the full rationale and acceptance criteria this implementation
satisfies.

## Schema

`schemas/demo.yaml` — four concrete classes, each `is_a: Entity` (Mosaic's
built-in `hippo_core` base: `id` + `is_available`), plus one inlined
value-object:

- **`Donor`** — `cohort`/`sex` enum facets, `age_at_death` (normal
  distribution), sparse `cause_of_death`, full-text-searchable `notes`
  (`hippo_search: fts5`).
- **`Sample`** — `sample_type`/`storage_condition` enum facets, single-valued
  `donor` reference, skewed `replicate_number`, exact-match `accession`
  (`hippo_index: true`), sparse multivalued `tags`.
- **`Workflow`** — `status`/`workflow_type` enum facets, multivalued
  `input_samples` reference, `started_at`/`completed_at`/`duration_hours`.
- **`Dataset`** — `dataset_type`/`access_level` enum facets, boolean
  `is_public` facet, single-valued `produced_by` reference, full-text
  `description`, inlined `quality_metrics` (`QualityMetrics` value object —
  no identifier, so it's embedded as structured JSON, not its own table).

Relationship chain: `Donor —1:N—▶ Sample —N:M—▶ Workflow —1:N—▶ Dataset`,
deliberately mixing both of Mosaic's relationship-storage patterns:

- `Sample.donor` / `Dataset.produced_by` — single-valued references. Plain FK
  columns; filterable in both directions by equality
  (`samples(filters:[{field:"donor", value:"<id>"}])`).
- `Workflow.input_samples` — multivalued reference. Stored in Mosaic's shared
  `relationships` table (ADR-0002), forward-resolved only. **There is no
  reverse query** ("which workflows consumed this sample") in the
  GraphQL/schema-generated API — a real, deliberately-exercised platform
  limitation, not a bug. (The lower-level
  `client.relationships.find_relationships(target_id=...)` SDK escape hatch
  *can* answer this off the same table, but it's not a schema-generated query
  field and Aperture never exposes it.)

### Why there's a second schema file

`generation_schema.yaml` (repo root, **not** under `schemas/`) wraps
`schemas/demo.yaml` with a `tree_root` container class (`DemoBundle`) so
`linkml-data-gen`'s container mode can build a connected, cross-referenced
bundle. It's kept out of `schemas/` deliberately: `mosaic migrate`/`mosaic
ingest --validate-schema` always look only at `schemas/`, and Mosaic
auto-synthesizes its own bundle root from the schema's concrete classes
regardless of any user-declared `tree_root` (ADR-0003) — a user-declared
`tree_root` class is *not* a value type, so if it lived in `schemas/` it would
get its own real (unwanted) fifth table. Verified empirically: with
`DemoBundle` inside `schemas/`, `mosaic migrate` created a `DemoBundle` table;
moved out, exactly four entity tables are created.

## Generating data

`generate.py` uses `linkml-data-gen`'s **Python API** (`DataGenerator` +
`GenerationConfig`), not its CLI, because the CLI clamps `--count-for` to
`[1, 1000]` per class and two of our targets (`workflows`, `datasets`) are
1,200. Driven by `hints.yaml` (weighted enums, normal/lognormal numeric
distributions, sparsity probabilities, Poisson cardinalities — see
[linkml-data-gen's hints docs](../linkml-data-gen/docs/hints.md)).

Target counts: 300 donors / 900 samples / 1,200 workflows / 1,200 datasets
(~3,600 total).

Two small post-processing steps run after generation (hints alone can't
guarantee these):
- **Seeded FTS keywords** — one donor's `notes` and one dataset's
  `description` get a known keyword (`cohort-alpha:42` / `recall-freeze`)
  appended, so full-text search has a guaranteed hit.
- **`completed_at` anchored to `started_at` + `duration_hours`** —
  `started_at`/`completed_at` are otherwise sampled independently from the
  same date window, which would put a workflow's completion date before its
  start date about half the time.

## Running it

```bash
make generate   # -> data/bundle.yaml
make migrate    # fresh data/mosaic.db, schema only
make ingest      # load data/bundle.yaml
make query       # explore via the Mosaic SDK directly (no server needed)
make test        # schema-only validation
make clean       # wipe data/
```

### Serving GraphQL for Aperture

**As of this repo's current schema**, see "Two Mosaic builds in play" above:
the `datahelix` solo container is pinned to a pre-`ec59c90` published Mosaic
image and will crash-loop on `Workflow.input_samples: required: true`. Use
the host's fixed `../hippo` checkout directly instead, until a new Mosaic
release + digest bump lands:

```bash
mosaic serve --config mosaic.yaml --host 127.0.0.1 --port 8080 --graphql
# -> http://localhost:8080/graphql (GraphiQL)
```

Once `datahelix`'s certified-frontier pin moves past `ec59c90`, the solo
recipe below becomes safe to use again for the full Aperture SPA (not just
the GraphQL API):

```bash
cd ../datahelix/deploy/recipes/solo
PROJECT_DIR=/path/to/mosaic-demo-small make up
# -> http://localhost:8080
```

This requires zero changes to the `datahelix`/solo recipe — `PROJECT_DIR`
already supports pointing at an arbitrary project directory. The recipe's own
default `project/` (the existing `hippo-benchmark` demo) is never touched;
confirmed by checksum/mtime on its `data/mosaic.db` before and after.

Manually verified in Aperture: enum/boolean faceting on all four classes,
full-text search on both seeded keywords, the full `Dataset → producedBy →
Workflow → inputSamples → Sample → donor → Donor` traversal (via each
entity's detail page and its `Relationships`/`History` sections), and the
absence of any reverse query for `input_samples`.

## Known upstream issues (filed, fixed on `main`, not yet released)

Two genuine Mosaic bugs were found and filed while building this demo
(BU-Neuromics/mosaic). Both are fixed by commit `ec59c90`, which landed on
`main` **after** the `v0.12.1` tag was cut and has not shipped in a release
yet — see the "Two Mosaic builds in play" caveat below for what that means
for this repo in practice.

- **[#143](https://github.com/BU-Neuromics/mosaic/issues/143)** (fixed on
  `main`, unreleased) — `mosaic migrate`, re-run against an
  already-migrated database, used to misidentify any multivalued reference
  slot as a missing physical column, crashing on `ALTER TABLE` if that slot
  was `required: true`. Re-verified against an editable `../hippo` checkout
  at `ec59c90`: `Workflow.input_samples` is schema-`required` again, and
  three consecutive `mosaic migrate` passes against this demo's
  already-ingested `data/mosaic.db` reported "No schema changes detected"
  with `NOT NULL` on `started_at`/`status`/`workflow_type` intact
  throughout.
- **[#144](https://github.com/BU-Neuromics/mosaic/issues/144)** (fixed on
  `main`, unreleased) — `MosaicClient.search()` used to pass the query
  string unescaped to SQLite's FTS5 `MATCH`, so ordinary phrases containing
  hyphens/colons were parsed as FTS5 query syntax and could raise
  `OperationalError` instead of matching literally. Re-verified against the
  same checkout, both via the SDK and live through `searchDonors`/
  `searchDatasets` GraphQL queries: no crash on hyphens, colons, or quotes.
  The seeded search keywords (`cohort-alpha:42`/`recall-freeze`) now use
  that punctuation directly.

### Two Mosaic builds in play — container vs. host checkout

The `datahelix` solo recipe's container image is built `FROM` a
**digest-pinned, published** `ghcr.io/bu-neuromics/mosaic` image
(`v0.12.1`, see `datahelix/certification/composition.lock.json`) — by
design, per the Dockerfile's own comment, it never builds Mosaic from
source. That published `v0.12.1` image **predates** `ec59c90`, so the
*container* still has both bugs. Booting it against this repo's current
schema (`input_samples: required: true`) reproduces #143 immediately —
confirmed empirically: `docker restart` crash-loops in exactly the
ALTER-TABLE way #143 describes.

Only the **host's editable `../hippo` checkout** (used for this repo's own
`make migrate`/`make ingest`/`mosaic serve` CLI calls) has the fix. Until
BU-Neuromics/mosaic cuts a new release past `ec59c90` and `datahelix` bumps
`composition.lock.json` to its digest, **the certified solo container
cannot run this repo's current schema.** For this change's spike and
benchmark, a host-side `mosaic serve --config mosaic.yaml --graphql` (bound
to the same `:8080` the container would otherwise use) stands in for the
container — the GraphQL surface and behavior are otherwise identical, just
served by the fixed build rather than the pinned one. `evals/` snapshots
note which build served them.

Also worth knowing: `Dataset.file_size_bytes` is declared `range: float`, not
`integer` — GraphQL's `Int` scalar is 32-bit signed, and this demo's file
sizes realistically range into the tens of gigabytes (would silently overflow
as `Int`). Not a Mosaic bug, just a schema-authoring gotcha for any future
field with values that might exceed ~2.1 billion.

## Regenerating from scratch

```bash
make clean && make generate && make migrate && make ingest
```
`make generate` is deterministic (`--seed 0` by default in `generate.py`) —
re-running it without other changes reproduces byte-identical output.
