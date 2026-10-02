# exon-query-planner Specification Delta

## MODIFIED Requirements

### Requirement: Schema-grounded natural-language query planning

Exon SHALL translate one natural-language instruction into a typed query
plan grounded in live `hippoSchema` introspection and the live capability
manifest, never in assumed field names, casing, or capabilities. Filter
field names in any generated plan SHALL be resolved from `hippoSchema`'s
slot names, never from the GraphQL type's own (camelCase) field names.

The grounding SHALL carry each slot's human-authored `description` alongside
its name, type and legal operators, for every slot the manifest reports —
including reference slots, which are rendered as traversable edges rather than
filterable fields. A slot's description is what allows an instruction phrased in
the researcher's vocabulary to be resolved to the slot that holds it; grounding
that carries only names and types can resolve an instruction only when the slot
name happens to contain the researcher's word.

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

#### Scenario: A slot is resolved by its description, not its name

- **WHEN** an instruction names a concept in the researcher's own vocabulary
  that appears in a slot's `description` but not in its slot name
- **THEN** the grounding carries that description and the slot is a candidate
  for the plan — rather than the concept being unresolvable because no slot name
  contains the word

#### Scenario: Reference slots carry their descriptions too

- **WHEN** the grounding is rendered for an entity type having both scalar and
  reference slots
- **THEN** every slot carries its description, reference slots included — a
  reference rendered as a traversable edge without its description would omit
  exactly the slots that name where related information lives
