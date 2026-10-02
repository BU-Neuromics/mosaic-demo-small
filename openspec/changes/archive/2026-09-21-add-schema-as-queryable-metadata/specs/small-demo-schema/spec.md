# small-demo-schema Specification Delta

## ADDED Requirements

### Requirement: The schema describes itself as queryable data

The project SHALL model its own schema as ordinary entities — one row per entity
type and one row per field — so that questions about the data model are answered
by the same query path as questions about the data. These rows SHALL carry the
field's name, type, requiredness, cardinality, human-authored description, and
permissible values where the field is enum-backed.

The rows SHALL be derived from the live schema, never hand-authored, and SHALL
be regenerated whenever the schema changes.

#### Scenario: A metadata question is answered as an ordinary query

- **WHEN** a user asks which fields are available on an entity type
- **THEN** the conversational planner returns a `proposal` carrying a QuerySpec
  anchored on the schema-field entity and filtered to that entity type — not a
  `clarification` declining the question — and the result renders in the same
  results table as any other query

#### Scenario: Field rows match what the server actually serves

- **WHEN** the generated rows are compared against the running instance's own
  schema introspection for the same entity type
- **THEN** every advertised field is present exactly once, with the same type,
  requiredness and description, and enum-backed fields carry the same
  permissible values — a row that disagrees means the generator read a source
  other than the one the server answers from

#### Scenario: No component outside this repository is modified

- **WHEN** the companion schema is migrated and its rows ingested
- **THEN** the new entity types are queryable, appear in the planner's capability
  grounding, are exposed over the endpoint's schema introspection, and are
  listed as collections by the browser client — with no change to the runtime,
  the browser client, or the conversational reply contract

### Requirement: Derived schema rows fail loudly when they drift

Because the rows are a second representation of the schema, the project SHALL
detect disagreement between the stored rows and the live schema and fail, rather
than serving a description that no longer matches the data. Regeneration during
migration is not sufficient on its own, since it depends on the migration
actually being run.

#### Scenario: A schema edit without regeneration is caught

- **WHEN** a field's description, type or requiredness is changed in the schema
  and the rows are not regenerated
- **THEN** the drift check fails and names the field that disagrees, rather than
  the stale row being served as though it were current

#### Scenario: Regeneration is idempotent

- **WHEN** the generator runs twice against an unchanged schema
- **THEN** the resulting rows are identical, and a field removed from the schema
  has its row deleted rather than left orphaned

### Requirement: The description is complete and schema-agnostic

The self-description SHALL carry every fact the runtime models about a slot, and
SHALL be produced by walking the schema's own class list rather than any
hardcoded set of entity types. A partial description is a defect, not a
simplification: without the slot's kind a reference cannot be distinguished from
a scalar, without its target a reference does not say what it points to, and
without its role a user-authored field cannot be told apart from a system one.

The description SHALL be packaged so that a schema authored later acquires its
metadata with no per-project work.

#### Scenario: Every slot kind is represented

- **WHEN** the description is generated for a schema using scalar, enum,
  reference and structured slots
- **THEN** each kind appears in the output carrying the facts specific to it —
  permissible values for an enum, the referenced entity type for a reference —
  rather than being flattened to a name and a type string

#### Scenario: A newly modelled slot attribute fails loudly

- **WHEN** the runtime begins modelling an attribute of a slot that the
  description does not carry
- **THEN** the drift check fails and names the missing attribute, so the
  description is extended deliberately rather than silently omitting it

#### Scenario: An unrelated schema is described without code changes

- **WHEN** the description is applied to a schema other than this project's own
- **THEN** it produces a complete description of that schema's entity types and
  slots with no modification to the generator, which is what distinguishes a
  reusable capability from a project-local script
