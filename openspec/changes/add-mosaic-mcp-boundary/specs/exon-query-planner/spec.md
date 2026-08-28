## RENAMED Requirements

- FROM: `### Requirement: Bounded relationship-existence traversal only`
- TO: `### Requirement: Bounded, single-call relationship traversal`

## MODIFIED Requirements

### Requirement: Schema-grounded natural-language query planning

Exon SHALL translate one natural-language instruction into a typed `QuerySpec` artifact (ADR-0035
shape: `anchor`, `mode`, `criteria`, `columns`), grounded in Mosaic's live capability resource and
schema, never in assumed field names, casing, or capabilities. Field names (`FieldCondition.slot`)
in any generated `QuerySpec` SHALL be resolved from the LinkML slot names Mosaic's capability
resource exposes, never from the GraphQL type's own (camelCase) field names.

#### Scenario: Plan uses live schema-derived filter field names

- **WHEN** Exon translates an instruction referencing a sample's tissue type and brain region
- **THEN** the generated `QuerySpec`'s field conditions use `sample_type` and `brain_region` (the
  LinkML slot names), never `sampleType` or `brainRegion`

#### Scenario: Driving example produces a correct result

- **WHEN** Exon is given the instruction "bring me back all of the brain tissue samples that we
  have for {a brain region present in the data} with {a donor attribute present in the data}, and
  also possibly any rnaSeq data associated with them"
- **THEN** it returns the matching tissue samples (filtered by `sample_type`/`brain_region`), each
  with its donor's matching attributes resolved via a `RelatedCondition`/column traversal, and —
  for each matching sample — any `rna_seq`-typed workflow referencing it, expressed as a single
  `RelatedCondition`/`columns` combination compiled by Mosaic into one `where:` relationship-
  predicate query rather than a client-side per-id fan-out, with the result distinguishing "no
  RNA-seq workflow found" from "not checked." Whether `columns`' `explode` selection can itself be
  scoped to the same relationship-type match is an open question (see
  `add-mosaic-mcp-boundary/design.md` Open Questions #1) — this scenario's exact mechanism is
  pending that resolution, but the requirement that the two states remain distinguishable is not.

### Requirement: Dry-run validation before execution

Exon SHALL ensure every `QuerySpec` is validated against Mosaic's live capability manifest and
schema before anything executes against Mosaic. Validation is performed by Mosaic's
`validate_query_spec` MCP tool (see `exon-mosaic-mcp-client`), not by a local Exon-side validator.
A `QuerySpec` requiring an unsupported capability, referencing a field name absent from the live
schema, or filtering an enum-backed field with a value outside its `enumValues` SHALL be rejected
with a stated reason, never silently executed or approximated.

#### Scenario: Unsupported capability is rejected, not approximated

- **WHEN** a translated `QuerySpec` requires a capability the live endpoint does not advertise
- **THEN** Mosaic's `validate_query_spec` rejects it before execution, citing the specific
  unsupported capability, and Exon surfaces that rejection rather than attempting a client-side
  approximation

#### Scenario: Unrecognized filter field name is rejected before execution

- **WHEN** a translated `QuerySpec`'s field condition names a slot that resolves to no field on
  that anchor (or related) type
- **THEN** validation rejects the plan before execution with the list of valid slots, rather than
  sending a filter the server would reject

#### Scenario: A field that exists but cannot be filtered is rejected

- **WHEN** a translated `QuerySpec` filters on a field stored as relationship edges rather than a
  column, or on a computed provenance field such as `created_at`
- **THEN** validation rejects the plan before execution and names the supported alternative — a
  `RelatedCondition` for the former, the `asOf` field for the latter (noting `asOf` cannot combine
  with a `RelatedCondition` on the same `QuerySpec`, per Mosaic ADR-0001 — see
  `add-mosaic-mcp-boundary/design.md` Non-Goals)

#### Scenario: A filter value outside the field's enum set is rejected

- **WHEN** a translated `QuerySpec` filters an enum-backed field (e.g. `sample_type`) with a value
  not present in that field's live `enumValues`
- **THEN** validation rejects the plan before execution, naming the field and its valid enum
  values, rather than sending a filter that would either be rejected by the server or silently
  match zero rows

### Requirement: Bounded, single-call relationship traversal

Exon SHALL express every relationship-existence or relationship-predicate need as a
`RelatedCondition` (`quantifier: 'some'` or `'none'`) within a single `QuerySpec`, compiled by
Mosaic into one `where:` relationship-predicate GraphQL call. Exon SHALL NOT implement its own
per-id fan-out loop for this purpose — that responsibility, and the bounded-scope discipline it
existed to enforce, moves to Mosaic's compilation of the validated `QuerySpec`.

#### Scenario: Reverse relationship lookup compiles to one call

- **WHEN** a `QuerySpec` needs to know which workflows reference a set of already-filtered samples,
  filtered further by `workflow_type`
- **THEN** Exon expresses this as a single `RelatedCondition` (`edge` = the reverse relationship,
  `quantifier: 'some'`, `criteria` = the `workflow_type` filter) within one `QuerySpec`, and never
  issues its own per-sample-id loop of individual lookup calls
