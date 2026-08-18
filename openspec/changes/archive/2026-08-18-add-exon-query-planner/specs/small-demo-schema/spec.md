## MODIFIED Requirements

### Requirement: Tissue-request example fields

The schema SHALL provide fields sufficient to answer a realistic
tissue-request query: filtering `Sample` by anatomical brain region and
tissue type, filtering `Donor` by clinical history of repetitive head
impacts (RHI), and identifying `Workflow` runs that are RNA sequencing
assays.

#### Scenario: Filtering brain tissue samples by region

- **WHEN** querying `samples(filters: [{field: "sample_type", value:
  "tissue"}, {field: "brain_region", value: ["hippocampus",
  "frontal_cortex", "cerebellum", "brainstem"], op: IN}], filterMode: AND)`
  (the `field` values are the LinkML slot names, as listed by `hippoSchema`
  and matching this repo's benchmark question q05; since mosaic#149/PR#150
  the camelCase spellings `sampleType`/`brainRegion` resolve identically,
  and an unrecognized name raises `UNKNOWN_FILTER_FIELD` rather than
  matching zero rows)
- **THEN** it returns exactly the tissue samples whose `brainRegion` is one
  of the four specified regions, each resolving its `donor` field

#### Scenario: Filtering donors by RHI history

- **WHEN** querying `donors(filters: [{field: "history_of_rhi", value:
  true}])` (verified live; since mosaic#149/PR#150 the camelCase
  `historyOfRhi` form resolves to the same slot)
- **THEN** it returns exactly the donors with a recorded history of
  repetitive head impacts, and the field is present (non-null) on every
  donor since it is required

#### Scenario: RNA-seq workflow existence for a sample is queryable; type-filtered lookup is not

- **WHEN** querying `relatedTo(id: "<sampleId>", relationshipType:
  "input_samples")` (verified live: `relationshipType` takes the LinkML
  slot name; each returned entry's `data` is the raw envelope payload, so
  `workflow_type` — snake_case — not `workflowType`)
- **THEN** it returns every `Workflow` that references the sample through
  `inputSamples` (existence is answerable directly, unlike before mosaic
  PR #147/`relatedTo` existed — confirmed via live introspection of
  `Query.relatedTo`'s argument list: `id: ID!, relationshipType: String`,
  no third argument) — but the query accepts no filter on the returned
  workflows' own fields, so identifying specifically the `rna_seq`-typed
  workflow(s) among them requires filtering the returned list client-side
  by `data.workflow_type`, bounded to that one sample's own relationship
  fan-out; this narrower gap MUST be documented as a capability limitation,
  distinct from — and much narrower than — the pre-fix "no reverse lookup
  exists at all" limitation this scenario previously described
