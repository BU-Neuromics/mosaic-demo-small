## ADDED Requirements

### Requirement: Tissue-request example fields

The schema SHALL provide fields sufficient to answer a realistic
tissue-request query: filtering `Sample` by anatomical brain region and
tissue type, filtering `Donor` by clinical history of repetitive head
impacts (RHI), and identifying `Workflow` runs that are RNA sequencing
assays.

#### Scenario: Filtering brain tissue samples by region

- **WHEN** querying `samples(filters: [{field: "sampleType", value:
  "tissue"}, {field: "brainRegion", value: ["hippocampus",
  "frontal_cortex", "cerebellum", "brainstem"], op: IN}], filterMode: AND)`
- **THEN** it returns exactly the tissue samples whose `brainRegion` is one
  of the four specified regions, each resolving its `donor` field

#### Scenario: Filtering donors by RHI history

- **WHEN** querying `donors(filters: [{field: "historyOfRhi", value:
  true}])`
- **THEN** it returns exactly the donors with a recorded history of
  repetitive head impacts, and the field is present (non-null) on every
  donor since it is required

#### Scenario: RNA-seq dataset availability for a sample set is not server-side composable

- **WHEN** attempting to determine whether any RNA-seq dataset exists for
  a specific set of samples or donors (i.e. "does an `rna_seq`-typed
  `Workflow` exist whose `inputSamples` includes any of these samples")
- **THEN** no single filtered GraphQL query can answer this — there is no
  reverse lookup from `Sample` to the `Workflow`s that consumed it (the
  `relationships`-table-backed multivalued reference is forward-resolved
  only); answering it requires fetching all `rna_seq` workflows with
  nested `inputSamples` and matching ids client-side, which MUST be
  documented as a capability gap rather than presented as a supported
  query
