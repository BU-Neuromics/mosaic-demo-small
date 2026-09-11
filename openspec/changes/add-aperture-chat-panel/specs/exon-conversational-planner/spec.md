## ADDED Requirements

### Requirement: Turn-taking grounding offers FK-backed reverse relationship edges

Exon's turn-taking grounding SHALL include, for each candidate anchor entity, both forward
relationship edges (fields the anchor entity itself holds) and reverse relationship edges backed
by a single-valued foreign-key reference on another entity type pointing at the anchor —
mirroring the same forward/reverse edge derivation Aperture's own query-builder planner already
performs client-side. Exon SHALL NOT offer a reverse edge backed by a multivalued,
relationships-table-stored reference, since no GraphQL query exists to compensate against such a
lookup.

#### Scenario: A reverse FK-backed edge is offered and usable

- **WHEN** the capability manifest advertises a single-valued reference field on entity B pointing
  at entity A (e.g. `Sample.donor` pointing at `Donor`)
- **THEN** Exon's turn-taking grounding for anchor `Donor` includes a `related` edge reaching
  `Sample` through that field, and a conversational turn requesting "donors who have a sample of
  type X" can express it as a `RelatedCondition` on that edge

#### Scenario: A multivalued relationships-table reverse edge is never offered

- **WHEN** an entity's only path to another anchor is a multivalued reference resolved through
  Mosaic's shared relationships table (e.g. `Workflow.input_samples`), with no reverse GraphQL
  query available
- **THEN** Exon's grounding does not present that direction as a traversable edge for a
  `RelatedCondition`, and a turn requesting it receives a clarification/limitation response rather
  than an edge that would fail at validation or execution time
