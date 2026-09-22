## MODIFIED Requirements

### Requirement: Self-contained small schema
The demo SHALL define exactly fifteen concrete entity classes — the
original four (`Donor`, `Sample`, `Workflow`, `Dataset`) plus
`ToxicologyReport`, `Diagnosis`, `Assessment`, `ConsentRecord`,
`Aliquot`, `StorageLocation`, `RunConfiguration`, `Instrument`,
`ReagentLot`, `QcFlag` and `Publication` — plus one abstract base and at
most one inlined value-object class, with no dependency on any other
schema or external reference-loader package.

The original four classes SHALL remain unchanged: every new reference
slot points from a new class at an existing one, never the reverse, so
that candidate count is the only variable distinguishing this schema
from its four-class predecessor.

#### Scenario: Schema validates independently
- **WHEN** `mosaic migrate --schema-dir schemas --db-path data/mosaic.db`
  runs against a fresh database
- **THEN** it succeeds with no errors and creates exactly fifteen entity
  tables plus supporting system tables (`relationships`, provenance,
  etc.), and no table for `QualityMetrics` or `ExternalID`

#### Scenario: The original four classes are untouched
- **WHEN** the `Donor`, `Sample`, `Workflow` and `Dataset` class blocks
  are diffed against their four-class versions
- **THEN** no slot, range, description or annotation has changed, and no
  slot has been added or removed

#### Scenario: No dependency on the large-schema demo
- **WHEN** the schema is inspected for `requires:` declarations or
  `imports:` targeting `brainbank-hippo-schema` or `hippo-reference-ensembl`
- **THEN** none are found

### Requirement: Realistic, non-uniform synthetic data at thousands-of-records scale
Generated data SHALL total approximately 9,000 records — the original
~3,600 (300 donors / 900 samples / 1,200 workflows / 1,200 datasets) plus
approximately 5,400 across the eleven new collections — with weighted
categorical distributions, real numeric distributions, sparse optional
fields, and skewed repeated values; not uniform-random and not
near-identical rows.

Dimension collections SHALL be deliberately small (single- and
double-digit row counts) rather than scaled with the fact collections, so
that load time stays flat while the schema's grounding surface grows.

#### Scenario: Categorical fields are weighted, not uniform
- **WHEN** the generated `Workflow.status` values are tallied
- **THEN** `completed` is the clear majority with a smaller realistic tail
  of `failed`/`running`/`queued`/`cancelled` — not an even 20% split

#### Scenario: Numeric fields follow a real distribution
- **WHEN** the generated `Donor.age_at_death` values are examined
- **THEN** they cluster around a mean (~68) rather than being uniformly
  spread across the full valid range

#### Scenario: Optional fields are genuinely sparse
- **WHEN** the generated `Donor.cause_of_death`, `Dataset.description`,
  `ConsentRecord.withdrawn_at` and `QcFlag.resolved_at` values are
  examined
- **THEN** a meaningful fraction (not 0%, not 100%) are absent/null

#### Scenario: Some fields show deliberate repetition
- **WHEN** the generated `Sample.replicate_number` values are examined
- **THEN** the value `1` is the clear majority, with `2` and `3` appearing
  less frequently — exercising realistic repeated-value patterns

#### Scenario: Dimension collections stay small
- **WHEN** the row counts for `Instrument`, `StorageLocation`,
  `Publication` and `ReagentLot` are tallied
- **THEN** each is in the single or double digits, and each is greater
  than zero

### Requirement: Referential integrity across the full dataset
Every reference field in the generated and ingested data SHALL resolve to
an id that actually exists in the dataset, across all fifteen classes.

#### Scenario: No dangling references after generation
- **WHEN** the generated bundle is inspected before ingest
- **THEN** every `Sample.donor`, `Workflow.inputSamples[*]`,
  `Dataset.producedBy`, `ToxicologyReport.donor`, `Diagnosis.donor`,
  `Assessment.donor`, `ConsentRecord.donor`, `Aliquot.sample`,
  `Aliquot.location`, `RunConfiguration.workflow`,
  `RunConfiguration.instrument`, `RunConfiguration.reagentLots[*]`,
  `QcFlag.dataset` and `Publication.datasets[*]` id resolves to an
  instance present in the same bundle

#### Scenario: Every entity class has a generation pool
- **WHEN** `generate.py` runs
- **THEN** it first verifies that every concrete `is_a: Entity` class in
  `schemas/demo.yaml` has a corresponding multivalued slot in
  `generation_schema.yaml`'s `DemoBundle`, and raises a named error
  identifying the missing class if one does not — rather than silently
  producing an empty collection

#### Scenario: Date intervals are internally consistent
- **WHEN** the generated `ConsentRecord`, `QcFlag` and `ReagentLot`
  records are examined
- **THEN** `withdrawn_at` is absent or later than `signed_at`,
  `resolved_at` is absent or later than `raised_at`, and `expires_on` is
  later than `received_on`

#### Scenario: Ingest completes with zero errors
- **WHEN** `mosaic ingest --file data/bundle.yaml --db-path data/mosaic.db
  --validate-schema schemas/demo.yaml` runs
- **THEN** it reports the expected `created` count per class and zero
  errors

### Requirement: Aperture-facing facet, search, and traversal support
The schema SHALL expose enum-backed facets on at least two fields per
entity class, full-text search on at least one free-text field per class
that has one, and a multi-hop relationship traversal path spanning the
original four entity classes.

#### Scenario: Faceting works per class
- **WHEN** browsing any of the fifteen collections in Aperture
- **THEN** each offers at least two meaningful, non-degenerate facets
  (more than one value present, no facet with only a single possible
  value across the whole dataset)

#### Scenario: Full-text search returns expected results
- **WHEN** searching Donors, Datasets, Toxicology Reports, QC Flags or
  Publications for a keyword known to appear in a seeded free-text value
- **THEN** the matching record(s) are returned

#### Scenario: Multi-hop traversal is consistent
- **WHEN** traversing `Dataset → producedBy → Workflow → inputSamples →
  Sample → donor → Donor` for a given dataset
- **THEN** every hop returns real, internally-consistent data matching
  what was generated

#### Scenario: New collections are reachable from their parents
- **WHEN** querying `toxicologyReports(filters:[{field:"donor",
  value:"<donorId>"}])` or `qcFlags(filters:[{field:"dataset",
  value:"<datasetId>"}])`
- **THEN** each returns exactly the child records belonging to that
  parent, and the forward-resolved reference field returns the same
  parent

## ADDED Requirements

### Requirement: Grounding scale is a measured property of the schema
The demo SHALL measure, at both the four-collection and fifteen-collection
schema sizes, the token cost of the planner's capability-grounding block
and the discovery eval's score against a fixed case set, and SHALL record
the two together, so that the effect of schema size on field-selection
accuracy is evidence rather than assumption.

The grounding token cost SHALL be obtained by token counting against the
assembled block, not estimated from character counts or extrapolated from
a per-class average measured at a different schema size.

#### Scenario: Both arms of the comparison are recorded
- **WHEN** the change is complete
- **THEN** `CONVERSATIONAL-QUERY.md` records, for each of the two schema
  sizes, the collection count, the measured grounding token cost, the
  exact target model string, and the `discovery.yaml` d01–d11 score at
  the same `--samples` setting

#### Scenario: The comparison arm is the unmodified case set
- **WHEN** the fifteen-collection score is computed
- **THEN** it is computed from the same eleven cases (d01–d11), the same
  prompt and the same model as the four-collection baseline; cases added
  to cover the new collections are scored and reported separately and are
  not folded into the headline number

#### Scenario: A widened correct answer is distinguished from a regression
- **WHEN** an existing case's result changes because a new class
  legitimately became a second correct answer
- **THEN** its `expect_slots` is widened and the change is recorded as
  "right answer changed", distinct from a case that began failing
  against an unchanged correct answer

### Requirement: Every collection carries rows
Every collection the schema produces SHALL contain at least one record.
A class that yields a table but no rows — whether by omission from the
generation root or by being a non-entity class that Mosaic does not
exclude — is a defect, because no query against it returns anything and
no evaluation case can be graded on it.

#### Scenario: No empty collections after load
- **WHEN** the row count of every entity table is tallied after
  `mosaic ingest` completes
- **THEN** all fifteen counts are greater than zero

#### Scenario: Aperture lists no dead collections
- **WHEN** Aperture's collection navigation is rendered against the
  loaded database
- **THEN** it shows fifteen collections and none of them opens to an
  empty table
