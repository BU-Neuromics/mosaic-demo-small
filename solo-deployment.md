# mosaic-demo-small — decisions, mechanics, and verification

Status: **done, verified, running.** This is a discussion-prep doc for
`mosaic-demo-small` — the small, from-scratch Mosaic demo (Donor/Sample/
Workflow/Dataset) deployed through the `datahelix` solo recipe. It replaces
the old `solo-deployment.md` (originally written for the *brainbank*
solo-deployment investigation, kept in git history if needed) — that
investigation's findings (the `entrypoint.sh` schema-imports bug, its fix and
archived OpenSpec change) are unrelated to this project and live on in
`datahelix`'s own history; nothing here supersedes them.

See `openspec/changes/add-small-demo-schema/` (proposal, design, tasks, delta
spec) for the formal record this doc summarizes for conversation, and
`README.md` for the day-to-day "how to run it" reference. This doc is the
"why did you build it this way, and what actually happened" version.

## Why this exists

The existing `hippo-benchmark`/brainbank demo (90 tables, thousands of rows)
is the wrong scale for *focused* Aperture testing — too much surface to scan,
too easy for a facet/search/traversal check to get lost in noise. This is a
**deliberately small, from-scratch** schema (not a trim of brainbank) sized to
exercise every mechanism Aperture's UX depends on, in one sitting.

## Schema design decisions

Four entity classes, each `is_a: Entity` (Mosaic's real built-in
`hippo_core.Entity` — `id` + `is_available`; it does **not** provide `name`,
unlike the assumption in the original design doc, so each class declares its
own), plus one inlined value-object:

| Class | Facets | Notable fields |
|---|---|---|
| `Donor` | `cohort`, `sex` | `age_at_death` (normal dist.), sparse `cause_of_death`, FTS `notes` |
| `Sample` | `sample_type`, `storage_condition` | single-valued `donor` ref, skewed `replicate_number`, exact-match `accession` |
| `Workflow` | `status`, `workflow_type` | multivalued `input_samples` ref, `started_at`/`completed_at`/`duration_hours` |
| `Dataset` | `dataset_type`, `access_level`, boolean `is_public` | single-valued `produced_by` ref, FTS `description`, inlined `quality_metrics` |

**Relationship chain**: `Donor —1:N—▶ Sample —N:M—▶ Workflow —1:N—▶ Dataset`,
deliberately mixing both of Mosaic's relationship-storage mechanisms rather
than using one throughout:

- `Sample.donor` / `Dataset.produced_by` — **single-valued** references. Plain
  FK columns; filterable in both directions by equality
  (`samples(filters:[{field:"donor", value:"<id>"}])` returns exactly that
  donor's samples — verified exact-match, not just non-empty).
- `Workflow.input_samples` — **multivalued** reference. Stored in Mosaic's
  shared `relationships` table (ADR-0002), forward-resolved only. There is
  **no reverse query** ("which workflows consumed this sample") anywhere in
  the schema-generated GraphQL/SDK query surface — confirmed by inspecting a
  Sample's Aperture detail page (only a `Donor` relationship appears, nothing
  reverse) and by reading `resolvers.py`/`schema_builder.py` directly. This is
  a deliberate, exercised platform limitation, not a bug to work around. (The
  lower-level `client.relationships.find_relationships(target_id=...)` SDK
  call *can* answer this off the same table — it's just not a
  schema-generated query field, so Aperture never surfaces it.)

**One inlined value-object**: `QualityMetrics` on `Dataset` has no
identifier, so it's embedded as structured JSON rather than getting its own
table/entity — exercises the `STRUCTURED` slot kind without adding a fifth
entity.

### Why there are two schema YAML files

`schemas/demo.yaml` is the real domain schema (what `mosaic migrate`/`mosaic
ingest --validate-schema` see). `generation_schema.yaml`, at the repo root —
**not** under `schemas/` — wraps it with a `tree_root` container class
(`DemoBundle`) purely so `linkml-data-gen`'s container mode has something to
build a connected, cross-referenced bundle around.

This split exists because of something discovered empirically, not
anticipated in the original design: declaring `DemoBundle` **inside**
`schemas/demo.yaml` made `mosaic migrate` create a real, unwanted fifth
table for it. Mosaic auto-synthesizes its *own* internal bundle root from a
schema's concrete classes and ignores any user-declared `tree_root` for
ingest purposes (ADR-0003) — but a user-declared `tree_root` class is not a
"value type" by Mosaic's own rules, so the migration DDL still builds a table
for it regardless. Moving the wrapper class out of `schemas/` — the directory
`mosaic migrate --schema-dir schemas` actually scans — sidesteps this
entirely: confirmed via `sqlite3 data/mosaic.db ".tables"` showing exactly
`Donor`/`Sample`/`Workflow`/`Dataset` plus Mosaic's standard system tables, no
`DemoBundle`.

## Data generation

`generate.py` uses `linkml-data-gen`'s **Python API**
(`DataGenerator`/`GenerationConfig`), not its CLI — the CLI clamps
`--count-for` to `[1, 1000]` per class, and two of this demo's targets
(`workflows`, `datasets`) are 1,200. Driven by `hints.yaml`: weighted enum
`choices`, `normal`/`lognormal`/`exponential` numeric distributions, `prob`
for sparsity, Poisson `cardinality` for multivalued fields.

Two things hints alone couldn't guarantee, handled as post-processing in
`generate.py`:
- **Seeded FTS keywords** (`cohortalpha42` in one donor's `notes`,
  `recalfreeze` in one dataset's `description`) so full-text search has a
  guaranteed, deterministic hit.
- **`completed_at` anchored to `started_at` + `duration_hours`** —
  independently sampling both dates from the same window put a workflow's
  completion before its start about half the time. Caught by eyeballing a
  Workflow's Aperture detail page (2018 completion, 2022 start) before it was
  fixed.

Target: 300 donors / 900 samples / 1,200 workflows / 1,200 datasets (3,600
total) — reproducible, `--seed 0` by default.

## What was verified, and how

- **Schema validity / table shape**: fresh `mosaic migrate` → exactly the 4
  entity tables + Mosaic's standard system tables + 2 FTS5 tables (see
  "System tables" below for what those are).
- **Ingest**: `mosaic ingest` → `created=3600 updated=0 errors=0`.
- **Facets**: every collection's documented facet fields, clicked live in
  Aperture (e.g. `dataset_type=bam` narrowed 1200 → 356 rows, all `bam`).
- **Full-text search**: both seeded keywords found their exact seeded record
  and nothing else, via Aperture's search box.
- **Single-valued FK, both directions**: `sample.donor` resolves forward; a
  `donor`-filtered `Sample` query was checked against the *donor with the
  most samples* (8) and returned **exactly** those 8 IDs, not just a nonzero
  count.
- **Multivalued reference, forward-only**: a Workflow's "Input samples"
  relationship (5 real Sample IDs, confirmed via its History/provenance log)
  resolves forward; no reverse UI/query path exists anywhere for it.
- **Multi-hop traversal**: `Dataset → producedBy → Workflow → inputSamples →
  Sample → donor → Donor`, followed hop-by-hop through Aperture's detail
  pages, landing on 5 distinct real donors.
- **Distribution shape**: `status` ~68% `completed` with a real tail;
  `replicate_number` skewed toward 1; sparse fields genuinely sometimes
  absent, never all-or-nothing.
- **Isolation from `hippo-benchmark`**: `deploy/recipes/solo/project/` (the
  existing brainbank demo, gitignored by the recipe) — identical checksum and
  mtime on its `data/mosaic.db` before and after every launch/restart in this
  session.

Launched via `PROJECT_DIR=<this-repo> make up` from `datahelix`'s
`deploy/recipes/solo/` — required zero changes to the recipe.

## System-only classes from `hippo_core` (and the one that got suppressed)

Importing `hippo_core` for the real `Entity` base class pulls in a handful of
other built-in classes declared in the same file, independent of this demo's
own schema. Most are already invisible to Aperture/GraphQL — Mosaic's
`schema_typing.py` hardcodes an `INFRASTRUCTURE_CLASSES` name-list
(`Entity`, `ProvenanceRecord`, `Process`, `Validator`, `ReferenceLoader`)
that's excluded from the exposed type surface regardless of what a downstream
schema does, and `ExternalReference` is separately excluded because it's a
value type (no identifier). `ProvenanceRecord` *is* populated — it's the
audit log, visible as each entity's "History" section — the rest of that
list simply never gets a GraphQL type or an Aperture collection at all.

**`ExternalID` was the one exception**, and the one that prompted this
section: it's a **deprecated** built-in Mosaic entity (since 0.6.0, per its
own docstring, issue #48; superseded by the newer `ExternalReference` +
`hippo_external_xref` pattern), but it's still `is_a: Entity` with an
identifier — not in the infrastructure list, not a value type — so it got a
real table and a real (permanently empty, since this demo never uses the
external-ID mechanism) Aperture collection, right alongside
`Donor`/`Sample`/etc.

**Fixed** by adding a local override to `schemas/demo.yaml` itself:

```yaml
classes:
  ExternalID:
    abstract: true
```

LinkML's import-merge semantics let a schema's own declaration of a
same-named class win over an imported one's shape — this is standard
`SchemaView` precedence, not a Mosaic-specific hack. Marking the local
`ExternalID` `abstract: true` makes it fail the same exposed-class check that
already filters out `Process`/`Validator`/`ReferenceLoader`, so it's now
excluded from the schema entirely (confirmed: not even in `mosaic migrate`'s
table-creation plan). No change to `hippo_core.yaml`, no change to Aperture,
and no effect on this demo's own `is_a: Entity` classes — verified in
Aperture: the sidebar now shows exactly the four domain collections.

(One operational note, not relevant going forward since this demo always
regenerates from scratch: applying this override against a database that
*already has* an `ExternalID` table is flagged by `mosaic schema
safe-deploy` as a breaking change, since Mosaic's migration model is
additive-only and never drops tables — a fresh `data/mosaic.db` sidesteps it
entirely.)

None of the *investigation* here is specific to `mosaic-demo-small` — any
from-scratch Mosaic schema importing `hippo_core` would see the same
always-present system classes and could apply the same override for
`ExternalID` if it doesn't use the deprecated external-ID mechanism.

## Known upstream issues (filed, not silently worked around)

Two genuine Mosaic bugs, found while building this demo, filed against
`BU-Neuromics/mosaic`:

- **[#143](https://github.com/BU-Neuromics/mosaic/issues/143)** — `mosaic
  migrate`, re-run against an already-migrated database, misidentifies a
  multivalued reference slot as a missing physical column. If that slot is
  `required: true`, it's a fatal `ALTER TABLE` crash on every subsequent
  migrate — which breaks the solo recipe's restart-always-migrates design for
  any schema shaped like this one. Reproduces identically on local 0.11.0 and
  the certified 0.12.1 image. **Workaround here**: `Workflow.input_samples`
  is not schema-`required` (kept populated ~98% of the time via a
  `hints.yaml prob`, not a schema constraint). With that change the extra
  migrate pass no longer crashes; it adds a harmless always-NULL
  `input_samples` column, and this demo's own `data/mosaic.db` has kept its
  other `NOT NULL` constraints intact across several re-migrates so far (an
  isolated repro *did* separately show those constraints disappear after a
  third consecutive migrate call — left for the maintainer, not reproduced
  against this demo's real data).
- **[#144](https://github.com/BU-Neuromics/mosaic/issues/144)** —
  `MosaicClient.search()` passes the query string to SQLite's FTS5 `MATCH`
  unescaped, so ordinary phrases with hyphens/colons are parsed as FTS5 query
  syntax and can raise `OperationalError`. **Workaround here**: the seeded
  search keywords (`cohortalpha42`/`recalfreeze`) are plain alphanumeric.

Also fixed, but a schema-authoring gotcha rather than a Mosaic bug:
`Dataset.file_size_bytes` is `range: float`, not `integer` — GraphQL's `Int`
is 32-bit signed, and this demo's file sizes realistically run into the tens
of gigabytes, which silently overflowed it (`[GraphQL] Int cannot represent
non 32-bit signed integer value`) until switched to `float`.

## Open items for discussion

- Whether to commit the working tree (nothing has been committed yet —
  `data/` is gitignored, everything else is untracked).
- Whether to archive `add-small-demo-schema` now (`openspec archive
  add-small-demo-schema`) or leave it open for further hint-tuning first
  (the design doc's own "Open Questions" flagged hint values as expected to
  be iterated on visually, which is exactly what happened with the
  `completed_at`/timestamp fix).
- Whether upstream #143/#144 warrant a nudge/PR from this side, or stay as
  filed reports for the Mosaic maintainers.
