# schema-field-browsing Specification Delta

## ADDED Requirements

### Requirement: The query surface presents the schema rather than an empty state

The query surface SHALL show the fields available on the entity currently anchored,
whenever it has no results to show. It SHALL NOT present an empty or decorative
placeholder in that situation.

A user who has run nothing is the user who most needs to see what can be asked. "Nothing
to show" is never true on this surface: the schema is always known, and rendering a
drawing in its place withholds the one thing that would help.

#### Scenario: A user who has run nothing sees what they can ask about

- **WHEN** the query surface is opened and no query has been run
- **THEN** it lists the anchored entity's fields, and does not present a placeholder
  standing in for content it could have shown

#### Scenario: An answer that produces no query still fills the surface

- **WHEN** a conversational turn answers a question about the data model without producing
  a query
- **THEN** the surface presents the fields relevant to that answer, rather than leaving the
  reply as text beside an empty region

#### Scenario: Results take precedence, and the fields remain reachable

- **WHEN** a query has been run and returned rows
- **THEN** the results are shown in place of the field listing, and the listing remains
  reachable without re-running or discarding the query

### Requirement: Field presentation carries what a user needs to choose a field

Each field SHALL be presented with the facts a user needs in order to decide whether to
include it: what it is called, what kind of value it holds, what the schema's author said
it means, the values it permits when constrained, and what it points at when it is a
reference.

Where the endpoint advertises richer per-field metadata than the generic type surface
carries, the surface SHALL read it. Where it does not, the surface SHALL present what it
can and SHALL NOT fail, blank, or misreport.

#### Scenario: A field carries its author's description

- **WHEN** the endpoint advertises a per-field description
- **THEN** it is shown with the field, because the description is what lets a user match
  their own vocabulary to a field whose name shares none of their words

#### Scenario: A constrained field shows what it accepts

- **WHEN** a field admits only a fixed set of values
- **THEN** those values are shown with it, so a user learns what may be asked for without
  running a query to find out

#### Scenario: An endpoint without the richer surface still works

- **WHEN** the endpoint advertises no per-field metadata beyond the generic type surface
- **THEN** the fields are still listed with the facts that surface does carry, and nothing
  errors or renders blank

### Requirement: A presented field can be acted on without leaving the surface

A user SHALL be able to act on a presented field directly — adding it as a criterion, or
choosing whether it appears in results — without composing another instruction.

Identifying a data element is the point of asking; requiring a further sentence to use one
returns the user to the position the surface exists to relieve.

#### Scenario: Adding a field as a criterion does not run anything

- **WHEN** a user adds a presented field as a query criterion
- **THEN** it appears in the query under construction, and **no query is executed** — the
  user's decision to run remains a separate, deliberate act

#### Scenario: Choosing result fields is the same control as browsing them

- **WHEN** a user chooses which fields appear in results
- **THEN** they do so from the same presentation that lists the fields, rather than from a
  second control describing the same set

### Requirement: The schema is read live and never stored

The surface SHALL obtain field information from the endpoint's own introspection at the
time it is displayed. It SHALL NOT persist, ingest, generate, or cache to storage any
representation of the schema, and SHALL NOT require a user to run a query in order to see
what the schema contains.

This is the distinction from the superseded approach that described the schema as ingested
rows. That representation could disagree with the schema it described and needed a drift
check to say so; it also made a metadata answer into a query the user had to run. Reading
live introspection has neither property: there is nothing to regenerate, nothing that can
drift, and nothing to execute.

#### Scenario: A schema change is reflected without regeneration

- **WHEN** the deployment's schema changes and the surface is opened again
- **THEN** it presents the new fields, with no regeneration step, no ingest, and no
  possibility of showing a description that no longer matches the schema

#### Scenario: Seeing the schema is not a query

- **WHEN** a user views the fields available on an entity
- **THEN** no query is executed and no query result is consumed — the presentation is not
  an answer returned by the query path
