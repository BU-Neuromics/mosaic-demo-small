# small-demo-schema Specification

## Purpose
TBD - created by archiving change add-small-demo-schema. Update Purpose after archive.
## Requirements
### Requirement: Self-contained small schema
The demo SHALL define exactly four concrete entity classes (`Donor`,
`Sample`, `Workflow`, `Dataset`) plus one abstract base and at most one
inlined value-object class, with no dependency on any other schema or
external reference-loader package.

#### Scenario: Schema validates independently
- **WHEN** `mosaic migrate --schema-dir schemas --db-path data/mosaic.db`
  runs against a fresh database
- **THEN** it succeeds with no errors and creates exactly the four entity
  tables plus supporting system tables (`relationships`, provenance, etc.)

#### Scenario: No dependency on the large-schema demo
- **WHEN** the schema is inspected for `requires:` declarations or
  `imports:` targeting `brainbank-hippo-schema` or `hippo-reference-ensembl`
- **THEN** none are found

### Requirement: Mixed relationship cardinality and storage patterns
The schema SHALL model the chain `Donor —1:N—▶ Sample —N:M—▶ Workflow —1:N—▶
Dataset`, using single-valued reference slots for the 1:N edges and a
multivalued reference slot for the N:M edge, so both of Mosaic's
relationship-storage mechanisms are exercised.

#### Scenario: Single-valued FK is bidirectionally queryable
- **WHEN** querying `samples(filters:[{field:"donor", value:"<donorId>"}])`
- **THEN** it returns exactly the samples belonging to that donor, and the
  forward-resolved field `sample.donor` returns the same donor

#### Scenario: Multivalued relationship is forward-only
- **WHEN** querying `workflow.inputSamples` for a given workflow
- **THEN** it returns the correct sample list via a batched resolver, but
  no GraphQL query exists to find workflows by a given input sample id
  (this is an expected, documented platform limitation, not a defect to
  fix in this change)

### Requirement: Realistic, non-uniform synthetic data at thousands-of-records scale
Generated data SHALL total approximately 3,600 records (300 donors / 900
samples / 1,200 workflows / 1,200 datasets), with weighted categorical
distributions, real numeric distributions, sparse optional fields, and
skewed repeated values — not uniform-random and not near-identical rows.

#### Scenario: Categorical fields are weighted, not uniform
- **WHEN** the generated `Workflow.status` values are tallied
- **THEN** `completed` is the clear majority with a smaller realistic tail
  of `failed`/`running`/`queued`/`cancelled` — not an even 20% split

#### Scenario: Numeric fields follow a real distribution
- **WHEN** the generated `Donor.age_at_death` values are examined
- **THEN** they cluster around a mean (~68) rather than being uniformly
  spread across the full valid range

#### Scenario: Optional fields are genuinely sparse
- **WHEN** the generated `Donor.cause_of_death` and `Dataset.description`
  values are examined
- **THEN** a meaningful fraction (not 0%, not 100%) are absent/null

#### Scenario: Some fields show deliberate repetition
- **WHEN** the generated `Sample.replicate_number` values are examined
- **THEN** the value `1` is the clear majority, with `2` and `3` appearing
  less frequently — exercising realistic repeated-value patterns

### Requirement: Referential integrity across the full dataset
Every reference field in the generated and ingested data SHALL resolve to
an id that actually exists in the dataset.

#### Scenario: No dangling references after generation
- **WHEN** the generated bundle is inspected before ingest
- **THEN** every `Sample.donor`, `Workflow.inputSamples[*]`, and
  `Dataset.producedBy` id resolves to an instance present in the same
  bundle

#### Scenario: Ingest completes with zero errors
- **WHEN** `mosaic ingest --file data/bundle.yaml --db-path data/mosaic.db
  --validate-schema schemas/demo.yaml` runs
- **THEN** it reports the expected `created` count per class and zero
  errors

### Requirement: Aperture-facing facet, search, and traversal support
The schema SHALL expose enum-backed facets on at least two fields per
entity class, full-text search on at least one free-text field per class
that has one, and a multi-hop relationship traversal path spanning all
four entity classes.

#### Scenario: Faceting works per class
- **WHEN** browsing Donors, Samples, Workflows, or Datasets in Aperture
- **THEN** each collection offers at least two meaningful, non-degenerate
  facets (more than one value present, no facet with only a single
  possible value across the whole dataset)

#### Scenario: Full-text search returns expected results
- **WHEN** searching Donors or Datasets for a keyword known to appear in a
  seeded `notes`/`description` value
- **THEN** the matching record(s) are returned

#### Scenario: Multi-hop traversal is consistent
- **WHEN** traversing `Dataset → producedBy → Workflow → inputSamples →
  Sample → donor → Donor` for a given dataset
- **THEN** every hop returns real, internally-consistent data matching
  what was generated

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

