## MODIFIED Requirements

### Requirement: Dry-run validation before execution

Exon SHALL validate every planned op against the live capability manifest and `hippoSchema` before
executing anything against the GraphQL endpoint. A plan requiring an unsupported capability
(aggregation, sort, range, predicate-filtered `relatedTo`) or referencing a filter field name
absent from `hippoSchema` SHALL be rejected with a stated reason, never silently executed or
approximated. A filter on an enum-backed field (one with a non-empty `enumValues` list in
`hippoSchema`) whose value — or, for `IN`, any element of its value list — is not a member of that
field's `enumValues` SHALL be rejected with the same discipline, before execution, rather than
reaching the server or silently matching zero rows.

#### Scenario: Unsupported capability is rejected, not approximated

- **WHEN** a translated plan requires group-by+count or a sort/range filter
- **THEN** Exon rejects the plan before execution, citing the specific unsupported capability, and
  does not attempt a client-side approximation

#### Scenario: Unrecognized filter field name is rejected before execution

- **WHEN** a translated plan's filter op names a field that resolves to no slot on that entity
  under either accepted spelling
- **THEN** Exon rejects the plan before execution with the list of valid slots, rather than
  sending a filter the server would reject

#### Scenario: A field that exists but cannot be filtered is rejected

- **WHEN** a translated plan filters on a multivalued reference slot (stored as relationship edges,
  not a column) or on a computed provenance field such as `created_at`
- **THEN** Exon rejects the plan before execution and names the supported alternative — a
  `related_lookup` step for the former; for the latter, that no current alternative exists in this
  pipeline (the `asOf` GraphQL argument exists upstream but Exon does not yet thread it through
  any `QueryPlan` field)

#### Scenario: A reference field named directly in select_fields is rejected

- **WHEN** a translated plan's `select_fields` (root or `forward_relation`) names a reference-kind
  field directly, or a `forward_relation` is present with no `select_fields` at all
- **THEN** Exon rejects the plan before execution — a reference field has no scalar value to
  return, and GraphQL requires a non-empty subfield selection on a nested object field; the
  message points at `forward_relation` (single-valued) or `related_lookup` (multivalued) as the
  correct op. Observed live against `bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0`: the
  model named a `donor` reference both in plain `select_fields` and, separately, in a
  correctly-shaped `forward_relation` for the same step — this would otherwise reach the executor
  and fail with a GraphQL syntax error instead of being caught here

#### Scenario: A filter value outside the field's enum set is rejected

- **WHEN** a translated plan filters an enum-backed field (e.g. `sample_type`, whose live
  `enumValues` are `blood`/`tissue`/`csf`/`urine`/`saliva`) with a value — or, for `op: "IN"`, any
  element of its value list — not present in that field's `enumValues`
- **THEN** Exon rejects the plan before execution, naming the field and its valid enum values,
  rather than sending a filter that the server would either reject or (depending on op) silently
  match against zero rows
