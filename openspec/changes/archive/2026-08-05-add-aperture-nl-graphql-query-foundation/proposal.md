# Change: Aperture NL-GraphQL query foundation — upstream refresh, tissue-request spike, and benchmark

## Why

Before any natural-language-to-GraphQL layer gets built for Aperture, the
team needs validated groundwork: an up-to-date Mosaic backend, a realistic
hand-written complex-query spike proving out the query shapes such a layer
would need to compile to, and a schema-derived capability manifest +
benchmark of what this demo's live GraphQL endpoint actually supports.
Two verification passes against the real Mosaic source and live upstream
GitHub state found concrete gaps between what was assumed and what's
actually there (see `design.md`) — this change captures all of that as one
piece of work, rather than as disconnected fragments.

## What Changes

1. **Upstream refresh** — pull the `../hippo` (Mosaic) sibling checkout to
   latest `origin/main`/v0.12.1+ (local checkout was 10 commits / two
   releases behind); re-verify against this demo's own data that
   mosaic#143 and #144 (migrate-idempotency crash, unescaped FTS5 MATCH
   crash) are fixed; remove the two workarounds this demo currently
   carries for them (`Workflow.input_samples` artificial non-required-ness,
   alphanumeric-only seeded search keywords) and update the README's
   "Known upstream issues" section.
2. **Tissue-request example fields** (query-design spike) — add
   `Sample.brain_region` (new `BrainRegionEnum`: `hippocampus`,
   `frontal_cortex`, `cerebellum`, `brainstem`), `Donor.history_of_rhi`
   (boolean), and `rna_seq` as a new value on the existing
   `Workflow.workflow_type` (`WorkflowTypeEnum`), plus matching
   `hints.yaml` entries; regenerate/migrate/ingest. These make a realistic
   motivating example runnable: "8 brain tissue samples across 4 regions,
   donors with a history of repetitive head impacts (RHI), plus whether
   RNA-seq data exists for them."
3. **Hand-written query spike** — clone
   `https://github.com/BU-Neuromics/aperture.git` to a sibling directory
   `../aperture-spike` on a new feature branch
   (`spike/nl-graphql-query-explore`); hand-write and run the example query
   against the live `localhost:8080/graphql` endpoint; document explicitly
   whether the "RNA-seq data available for these samples/donors" leg is
   server-side composable today, given the already-known platform
   limitation on reverse relationship traversal (see `design.md`) — do not
   silently work around it with an incomplete client-side scan.
4. **File an upstream issue** against `BU-Neuromics/mosaic` requesting
   reverse-lookup GraphQL support for relationships-table-backed
   multivalued references (the gap exercised by #3), mirroring how
   mosaic#143/#144 were filed for this same demo.
5. **Capability manifest + benchmark** — capture a live introspection +
   `hippoSchema`/`hippoEntityType` + capability-manifest snapshot under
   `evals/schema/`; author `evals/questions.yaml` (~25-40 questions across
   entity filtering, relationship traversal, search, provenance/lifecycle,
   pagination, and explicitly-unsupported categories) +
   `evals/expected-results.json`, with any question requiring the blocked
   reverse-traversal capability marked `capability: blocked`,
   `blocked_by: [mosaic#146]` rather than answered approximately.

## Impact

- **Affected specs**: `small-demo-schema` (adds the 3 tissue-request
  fields to the existing capability from `add-small-demo-schema`) and a
  new `query-benchmark` capability (the evals/introspection/benchmark
  surface).
- **Affected code (this repo)**: `schemas/demo.yaml`, `hints.yaml`,
  `README.md` (workaround removal), new `evals/` directory.
- **Affected code (outside this repo)**: `../hippo` gets pulled to latest
  (no local code changes, just a checkout update); a **new**, separate
  clone at `../aperture-spike` (not the `datahelix` repo's `aperture`
  submodule, not pushed anywhere); a new issue filed against
  `BU-Neuromics/mosaic` on GitHub.
- **Out of scope, tracked in `design.md` for continuity** — the full
  6-phase Aperture NL-GraphQL architecture (query-plan compiler, read-only
  LLM agent service, Aperture UI integration) is `datahelix`/`aperture`-repo
  work with no code footprint in this repo; preserved in full so nothing
  discussed is dropped, but not part of this change's `tasks.md`.
- **No breaking changes**: all schema additions are optional/additive.
