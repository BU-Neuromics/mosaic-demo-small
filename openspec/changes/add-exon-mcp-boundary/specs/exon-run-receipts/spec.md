## ADDED Requirements

### Requirement: Every execution produces a self-contained receipt

Exon SHALL produce a receipt for every plan executed via `execute_query_plan`, containing at
minimum the original instruction (if any), the validated `QueryPlan` (in the same JSON shape
`emit_query_plan` produces), the GraphQL endpoint used, and `execute_plan`'s own unmodified result
(`{"steps": {...}, "final": {...}}`). When the plan was produced by the optional `plan_query`
tool, the receipt SHALL additionally carry planner metadata (protocol, model, usage, finish
reason, latency) sufficient to explain how the plan came to be, without embedding the raw model
response text.

#### Scenario: A receipt fully describes what was executed

- **WHEN** `execute_query_plan` successfully executes a plan
- **THEN** the returned receipt contains the plan, the endpoint, and the exact result
  `execute_plan` produced, sufficient to know what GraphQL calls were made and what they returned
  without re-running anything

#### Scenario: Planner metadata is present only when the planner was used

- **WHEN** a plan is supplied directly to `execute_query_plan` (not produced via `plan_query`)
- **THEN** the receipt's planner metadata field is absent, rather than populated with placeholder
  or guessed values

### Requirement: Receipts are replayable against current live data

Exon SHALL support replaying a saved receipt: re-validating its plan against a freshly fetched
(never cached) live `hippoSchema` and capability manifest, then re-executing it against the live
endpoint if re-validation succeeds. If re-validation fails — for example because a schema change
since the original run makes the plan no longer valid — Exon SHALL report that failure explicitly
rather than skipping validation or reusing the original run's result.

#### Scenario: Replay against unchanged schema reproduces an equivalent result

- **WHEN** a receipt is replayed and the live schema and underlying data are unchanged since the
  original run
- **THEN** the replay's result matches the original receipt's result

#### Scenario: Replay against a changed schema fails validation explicitly

- **WHEN** a receipt's plan filters an enum-backed field on a value that has since been removed
  from that field's live `enumValues`, and the receipt is replayed
- **THEN** replay reports a validation failure naming the now-invalid value, rather than silently
  executing an approximation or reusing the original receipt's result

### Requirement: Replay is distinguished from historical reproducibility

Exon's receipts SHALL be documented as supporting replay against current live data only. Exon
SHALL NOT claim, imply, or attempt to reproduce a plan's result as of the data state at original
execution time, since no `QueryPlan` field or executor argument threads Mosaic's `asOf` transaction-
time pinning through today.

#### Scenario: Replay documentation states its own limitation

- **WHEN** a user reads the documentation for the replay capability
- **THEN** it states plainly that replay re-runs the plan against the live endpoint's current
  state, and that reproducing the exact result as of the original execution time is not supported
