# mosaic-demo-small

A small, self-contained Mosaic demo: fifteen entity classes modeling a
simplified biobank/omics pipeline — a core chain of `Donor` → `Sample` →
`Workflow` → `Dataset`, plus clinical, governance, specimen-handling,
instrumentation and publication collections around it — with ~8,800 realistic
synthetic records. Built to seriously exercise Aperture's
faceting, full-text search, and relationship traversal at a scale that's easy
to scan and reason about — deliberately independent of the much larger
`hippo-benchmark`/brainbank demo (see sibling repo
`brainbank-hippo-performance/hippo-benchmark/`), not a reduction of it.

See `openspec/changes/add-small-demo-schema/` (proposal, design, tasks, delta
spec) for the full rationale and acceptance criteria this implementation
satisfies.

## A note on "hippo" vs "mosaic"

The product was renamed Hippo → Mosaic (upstream ADR-0004), and this repo's own
code and docs use **Mosaic** throughout. Some `hippo*` spellings remain, and
every one of them is deliberate — **do not bulk-rename them**, because each is
either someone else's identifier or not the product name at all:

| Spelling | Why it stays |
|---|---|
| `hippocampus` | An anatomical brain region — real data values in this schema. Nothing to do with the product. |
| `hippoSchema`, `hippoEntityType` | **Live GraphQL field/type names** that upstream Mosaic still serves. Renaming breaks every query. |
| `hippo_core`, `hippo_ext`, `hippo_search`, `hippo_index`, `hippo_meta`, `hippo_external_xref` | Data-contract identifiers and LinkML annotation keys, **deliberately not renamed** by ADR-0004. Upstream reads these exact strings. |
| `hippo-benchmark`, `brainbank-hippo-performance`, `hippo-reference-ensembl` | Names of other real repos. |
| `hippoSource.ts`, `VITE_HIPPO_GRAPHQL_URL` | Aperture's own file and env-var names. |
| `../hippo@<commit>` in `captured_against` / "last verified" strings | Provenance records. At capture time the repo really was named `hippo`; rewriting them would falsify the record. The `../hippo` clone was a stale duplicate of `../mosaic` and was **deleted 2026-09-17**; the live editable install is `../mosaic` (`BU-Neuromics/mosaic`). |

Exon's own local Python names for the schema it fetches *were* renamed
(`fetch_mosaic_schema`, `mosaic_schema`, `MOSAIC_SCHEMA_QUERY`) — those are
ours, internal, and carry no wire meaning. The GraphQL query string they send
still asks for `hippoSchema`, because that is what the server answers to.

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
moved out, exactly the schema's own entity tables are created (fifteen, as of
`grow-demo-schema-collections`).

## Generating data

`generate.py` uses `linkml-data-gen`'s **Python API** (`DataGenerator` +
`GenerationConfig`), not its CLI, because the CLI clamps `--count-for` to
`[1, 1000]` per class and four of our targets (`workflows`, `datasets`,
`aliquots`, `run_configurations`) are 1,200. `max_count` is a per-collection
clamp, not a global one, so adding collections does not eat into the others'
budgets. Driven by `hints.yaml` (weighted enums, normal/lognormal numeric
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

**The solo container is the default path** — see "Two Mosaic builds in play"
below; it was verified working on 2026-09-17 and serves the Aperture SPA as
well as GraphQL. Serve from a host checkout only when you need something newer
than the last release (`converseQuerySpec`, CORS, `relatedTo` predicates):

```bash
mosaic serve --config mosaic.yaml --host 127.0.0.1 --port 8080 --graphql --mcp
# -> http://localhost:8080/graphql (GraphiQL)
# --mcp is only needed by exon/ (see exon/README.md), harmless otherwise -- but it is
# easier to start it once with the flag than to rediscover why `python -m exon` 404s.
```

The certified-frontier pin has since moved past `ec59c90` (mosaic 0.13.0), so
the solo recipe below runs the full Aperture SPA, not just the GraphQL API:

```bash
cd ../datahelix/deploy/recipes/solo
PROJECT_DIR=/path/to/mosaic-demo-small make up
# -> http://localhost:8080
```

This requires zero changes to the `datahelix`/solo recipe — `PROJECT_DIR`
already supports pointing at an arbitrary project directory. The recipe's own
default `project/` (the existing `hippo-benchmark` demo) is never touched;
confirmed by checksum/mtime on its `data/mosaic.db` before and after.

Manually verified in Aperture: enum/boolean faceting on all classes,
full-text search on both seeded keywords, the full `Dataset → producedBy →
Workflow → inputSamples → Sample → donor → Donor` traversal (via each
entity's detail page and its `Relationships`/`History` sections), and the
absence of any reverse query for `input_samples`.

## Known upstream issues (filed, fixed on `main`, not yet released)

Two genuine Mosaic bugs were found and filed while building this demo
(BU-Neuromics/mosaic). Both are fixed by commit `ec59c90`, which **shipped in mosaic v0.13.0**
(2026-08-20) and is what the certified solo container now runs — see "Two
Mosaic builds in play" below.

- **[#143](https://github.com/BU-Neuromics/mosaic/issues/143)** (fixed, released in v0.13.0) — `mosaic migrate`, re-run against an
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

**The container path works. Use it.** Verified 2026-09-17 against
`mosaic 0.13.0` (digest `sha256:ded2942…`): boots healthy, `RestartCount: 0`,
no `Workflow.input_samples: required: true` error, SPA and `/docs` both 200,
and all 300 donors / 900 samples / 1200 workflows served.

```bash
cd ../datahelix/deploy/recipes/solo
PROJECT_DIR=/abs/path/to/mosaic-demo-small make up
# -> http://localhost:8080  (Aperture SPA + GraphQL + /docs)
```

The historical crash-loop (#143/#144) is gone: mosaic **v0.13.0** contains
`ec59c90`, and `datahelix` `main` pins that digest. Run the recipe from
datahelix **`main`** — an older checkout may still pin `v0.12.1`
(`sha256:2ac3e3c…`), which is the digest that crash-looped. The
`ARG MOSAIC_IMAGE` line in `deploy/recipes/solo/Dockerfile` is the evidence;
`make check-pins` verifies it against the certification lock.

**What the container does NOT have.** It serves the last *release*, and two
things this repo cares about landed after it:

| Capability | In v0.13.0 (container)? |
|---|---|
| `relatedTo` reverse lookup (#146) | ✅ yes |
| sort / `orderBy` + facet counts (#96) | ✅ yes — `donorsFacetCounts`, `orderBy: AGE_AT_DEATH` |
| `relatedTo` **predicate** (#148) | ❌ no — still `(id, relationshipType)` only |
| **`converseQuerySpec`** (#205) | ❌ no — mosaic `main` only, 34 commits past the tag |
| CORS middleware (#207) | ❌ no — also post-tag |

So the conversational work (Exon, Aperture's chat panel) still needs a Mosaic
newer than any release. For that, prefer `datahelix/deploy/recipes/ide/`, which
is built for running unreleased/source Aperture and Mosaic behind one gateway
(`make dev`, or `MOSAIC_VERSION=local`) and is formally exempt from the
ADR-0001 deploy gate. A host-side `mosaic serve --config mosaic.yaml --graphql
--mcp` also still works.

**One API change to know about.** v0.13.0 returns search results as a page
envelope, so `{ searchDonors(q: …) { id name } }` is now invalid — it must be
`{ searchDonors(q: …) { total items { id name } } }`. The underlying data is
unchanged; `evals/questions.yaml` and `evals/expected-results.json` still carry
the old bare-list shape and need updating.

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
