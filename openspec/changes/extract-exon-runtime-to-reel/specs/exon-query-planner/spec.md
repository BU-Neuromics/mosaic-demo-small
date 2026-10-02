# exon-query-planner Specification Delta

## ADDED Requirements

### Requirement: The planner runtime is a separately packaged, deployable service

The query planner SHALL be distributed as its own package and container image,
versioned and pinned, rather than as source inside a demonstration repository. A
deployment SHALL obtain the planner by referencing that artifact, and SHALL NOT
require a checkout of the demo repository in order to run the conversational
path.

The artifact SHALL carry no domain fixtures. A schema, its generated data and
its evaluation cases belong to the deployment being described, not to the
planner that plans against it; a planner that embedded them could only ever plan
for one project.

#### Scenario: A deployment runs the planner without the demo repository

- **WHEN** a deployment starts the query boundary and the planning service from
  published artifacts
- **THEN** the conversational path answers a discovery question and produces a
  validated QuerySpec, with no demo-repository source present on the host

#### Scenario: The planner carries no schema of its own

- **WHEN** the planner's artifact is inspected
- **THEN** it contains no LinkML schema, no generated data and no evaluation
  cases — it reads the entity types, fields and descriptions it plans against
  from the live capability manifest instead

### Requirement: The extraction carries the turn path without the retired plan path

The extraction SHALL carry the modules that serve the conversational turn
contract and SHALL NOT carry the retired plan-emitting path — its emitter, its
local validator, its local executor, or its operation types. Those are deleted
where they stand rather than relocated.

Where the carried modules depend on the retired path only for configuration
constants, those constants SHALL be relocated to a module of their own rather
than justifying carrying the retired path to satisfy the import.

#### Scenario: The retired path does not follow the runtime

- **WHEN** the extracted artifact is inspected
- **THEN** the retired plan emitter, validator, executor and operation types are
  absent from it, and remain present in the repository they are deleted from
  later

#### Scenario: Configuration constants survive the split

- **WHEN** a carried module previously imported configuration constants from the
  retired emitter
- **THEN** it imports them from a dedicated configuration module instead, and
  behaves identically — the values are unchanged by the move

### Requirement: The wire contract is unchanged by the extraction

The turn contract SHALL be byte-for-byte identical across the extraction. The
statuses a turn may carry, the fields it carries, the shape of the QuerySpec it
proposes, and the endpoint's request and response shapes SHALL NOT change
because the code moved.

A deployment SHALL therefore be able to substitute the extracted service for the
in-repository one without any change to the boundary that delegates to it, other
than the address it is reached at.

#### Scenario: The relay is unaffected by the substitution

- **WHEN** the boundary's delegation target is repointed from the
  in-repository planner to the extracted service
- **THEN** a conversation produces the same statuses and the same QuerySpec for
  the same utterances, and the boundary requires no change beyond the address

#### Scenario: Discovery survives the move intact

- **WHEN** a discovery question is asked of the extracted service
- **THEN** it is answered in the conversation by naming the relevant slots, as
  before the move — the grounding still carries each slot's description, and the
  answered reply still leaves the draft untouched
