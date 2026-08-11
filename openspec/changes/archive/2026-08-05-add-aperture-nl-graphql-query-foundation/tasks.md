## 1. Upstream refresh (Mosaic)

- [x] 1.1 Pull `../hippo` to latest `origin/main` (v0.12.1+) — landed at
      `ec59c90`
- [x] 1.2 Re-run `make migrate && make ingest` in this repo against the
      refreshed Mosaic; confirm mosaic#143 (migrate-idempotency crash) and
      mosaic#144 (unescaped FTS5 MATCH crash) stay fixed against this
      demo's own data
- [x] 1.3 Remove the two workarounds now that they're confirmed
      unnecessary: `Workflow.input_samples` artificial non-required-ness
      (`schemas/demo.yaml`), alphanumeric-only seeded search keywords
      (`generate.py`); update README's "Known upstream issues" section
- [x] 1.4 Check whether the `aperture` clone (task 3.1) selects any raw
      `*_id`/`*_ids` GraphQL scalar that ADR-0005 removed upstream; note
      findings in `design.md` if so — negative result, see design.md

## 2. Tissue-request example fields

- [x] 2.1 Add `BrainRegionEnum` (`hippocampus`, `frontal_cortex`,
      `cerebellum`, `brainstem`) and `Sample.brain_region` (sparse,
      optional) to `schemas/demo.yaml`
- [x] 2.2 Add `Donor.history_of_rhi` (boolean, required) to
      `schemas/demo.yaml`
- [x] 2.3 Add `rna_seq` as a new permissible value on the existing
      `WorkflowTypeEnum`
- [x] 2.4 Add matching `hints.yaml` entries (brain_region 0.35 prob,
      equal-weighted across the 4 regions; history_of_rhi 18% true;
      rna_seq 15% share of workflow_type, other 4 values rebalanced
      proportionally)
- [x] 2.5 `make clean && make generate && make migrate && make ingest`;
      confirm the running instance reflects the new fields — done via a
      **host-side `mosaic serve --config mosaic.yaml --graphql`**, not a
      restarted solo container: the certified container is pinned to a
      pre-`ec59c90` published Mosaic image and crash-loops on
      `input_samples: required: true` (see design.md's "Second genuine
      gap found during execution" and README's "Two Mosaic builds in
      play")

## 3. Hand-written query spike

- [x] 3.1 Clone `https://github.com/BU-Neuromics/aperture.git` to
      `../aperture-spike`; create branch `spike/nl-graphql-query-explore`
- [x] 3.2 Hand-write and run against `localhost:8080/graphql` (host-side
      serve, see 2.5): samples filtered by `sample_type: tissue` AND
      `brain_region IN [4 regions]`, nested `donor { cohort sex
      historyOfRhi }` — 115 matches; note the filter `field` values must
      be LinkML slot names (`sample_type`), not GraphQL field names
      (`sampleType`), and the default 100-row page size silently
      truncated the first draft's result
- [x] 3.3 Attempt the "RNA-seq data available for these
      samples/donors" leg; confirm and document whether it requires the
      known reverse-relationship-traversal gap (§ design.md) — do not
      ship a client-side-matched approximation as if it were a supported
      query — confirmed blocked (mosaic#146); illustrated via a fully
      paginated client-side scan (45/115 matched), explicitly labeled
      non-supported
- [x] 3.4 Write up the spike's findings (query text, results, the
      RNA-seq-leg limitation) as a note committed on the spike branch —
      `aperture-spike/docs/nl-graphql-query-spike.md` +
      `nl_graphql_spike_query.py`, commit `adee80f`

## 4. Upstream issue

- [x] 4.1 File the drafted issue against `BU-Neuromics/mosaic` (title:
      "GraphQL API: no reverse-lookup query for relationships-table-backed
      multivalued references") — confirm with the user immediately before
      filing, since this is an external/shared action — filed as
      [mosaic#146](https://github.com/BU-Neuromics/mosaic/issues/146)

## 5. Capability manifest + benchmark

- [x] 5.1 Capture `evals/schema/introspection.json` (standard `__schema`
      introspection)
- [x] 5.2 Capture `evals/schema/mosaic-domain-schema.json`
      (`hippoSchema`/`hippoEntityType` for all 4 entities)
- [x] 5.3 Write `evals/schema/capabilities.json` (capability manifest per
      entity: list/get/search/equality_filters/range_filters/sorting/
      facet_counts/relationships)
- [x] 5.4 Write `evals/questions.yaml` (33 questions across entity
      filtering, relationship traversal, search, provenance/lifecycle,
      pagination, and explicitly-unsupported categories), with the
      reverse-traversal questions marked `capability: blocked`,
      `blocked_by: [mosaic#146]`
- [x] 5.5 Write `evals/expected-results.json` against this demo's actual
      generated data/ids — captured live against the host-side serve
      instance (see 2.5); `_meta` records which Mosaic build served it

## 6. Validation

- [x] 6.1 `openspec validate add-aperture-nl-graphql-query-foundation --strict`
