## ADDED Requirements

### Requirement: Schema-grounded natural-language query planning

Exon SHALL translate one natural-language instruction into a typed query
plan grounded in live `hippoSchema` introspection and the live capability
manifest, never in assumed field names, casing, or capabilities. Filter
field names in any generated plan SHALL be resolved from `hippoSchema`'s
slot names, never from the GraphQL type's own (camelCase) field names.

#### Scenario: Plan uses live schema-derived filter field names

- **WHEN** Exon translates an instruction referencing a sample's tissue
  type and brain region
- **THEN** the generated plan's filter ops use `sample_type` and
  `brain_region` (the `hippoSchema` slot names), never `sampleType` or
  `brainRegion`

#### Scenario: Driving example produces a correct result

- **WHEN** Exon is given the instruction "bring me back all of the brain
  tissue samples that we have for {a brain region present in the data}
  with {a donor attribute present in the data}, and also possibly any
  rnaSeq data associated with them"
- **THEN** it returns the matching tissue samples (filtered by
  `sample_type`/`brain_region`), each with its donor's matching attributes
  resolved, and — for each matching sample — any `rna_seq`-typed workflow
  referencing it via a bounded `relatedTo` call, with the result
  distinguishing "no RNA-seq workflow found" from "not checked"

### Requirement: Dry-run validation before execution

Exon SHALL validate every planned op against the live capability manifest
and `hippoSchema` before executing anything against the GraphQL endpoint.
A plan requiring an unsupported capability (aggregation, sort, range,
predicate-filtered `relatedTo`) or referencing a filter field name absent
from `hippoSchema` SHALL be rejected with a stated reason, never
silently executed or approximated.

#### Scenario: Unsupported capability is rejected, not approximated

- **WHEN** a translated plan requires group-by+count or a sort/range
  filter
- **THEN** Exon rejects the plan before execution, citing the specific
  unsupported capability, and does not attempt a client-side approximation

#### Scenario: Unrecognized filter field name is rejected before execution

- **WHEN** a translated plan's filter op names a field that resolves to no
  slot on that entity under either accepted spelling
- **THEN** Exon rejects the plan before execution with the list of valid
  slots, rather than sending a filter the server would reject

#### Scenario: A field that exists but cannot be filtered is rejected

- **WHEN** a translated plan filters on a multivalued reference slot
  (stored as relationship edges, not a column) or on a computed provenance
  field such as `created_at`
- **THEN** Exon rejects the plan before execution and names the supported
  alternative — a `related_lookup` step for the former, the `asOf`
  argument for the latter

### Requirement: Bounded relationship-existence traversal only

Exon SHALL scope every reverse relationship-existence lookup (`relatedTo`)
in a validated plan to one or more already-identified entity ids
(obtained from a prior filtered query or prior `relatedTo` call). Exon
SHALL NOT approximate an unavailable predicate-filtered reverse lookup by
scanning an entire entity table and matching client-side.

#### Scenario: Reverse lookup is scoped to known ids

- **WHEN** a plan needs to know which workflows reference a set of
  already-filtered samples
- **THEN** Exon issues one `relatedTo` call per sample id in that set,
  filtering each call's own small result client-side by `workflow_type`,
  and never issues an unfiltered query across the full `Workflow` table
