## ADDED Requirements

### Requirement: Exon is an MCP client of Mosaic's boundary, not a server hosting its own

Exon SHALL connect to Mosaic's MCP server as a client to obtain live schema/capability grounding
and to validate/execute `QuerySpec` artifacts, rather than hosting its own MCP server wrapping a
local validator/executor. Exon SHALL NOT implement or expose a competing `validate_query_plan`/
`execute_query_plan` (or equivalent) tool of its own once Mosaic's boundary is live.

#### Scenario: Exon reads grounding from Mosaic's MCP resources

- **WHEN** Exon's planner needs live schema/capability grounding to construct a `QuerySpec`
- **THEN** it reads Mosaic's MCP capability/schema resources fresh on every use, never a cached or
  hand-maintained local copy

#### Scenario: Exon delegates validation and execution to Mosaic

- **WHEN** Exon has a constructed `QuerySpec` ready to run
- **THEN** it calls Mosaic's `validate_query_spec` and `execute_query_spec` MCP tools rather than
  running any local Python validation/execution logic of its own

### Requirement: Exon does not silently operate without Mosaic's boundary

Exon's planner, harness, and CLI SHALL fail explicitly, with a clear diagnostic naming Mosaic's MCP
boundary as unreachable, rather than falling back to a partial or unvalidated execution path, if
Mosaic's MCP server cannot be reached.

#### Scenario: Missing Mosaic MCP boundary fails loudly

- **WHEN** Exon attempts to call Mosaic's MCP tools and the connection fails or the tools are not
  present
- **THEN** Exon raises a clear error identifying the missing MCP boundary as the cause, and does
  not fall back to constructing or executing a `QuerySpec` without validation

### Requirement: Local `QueryPlan` validator/executor are retired, not maintained in parallel

This repo SHALL remove `exon/validator.py`, `exon/executor.py`, and the `QueryPlan`/`FilterStep`/
`RelatedLookupStep` types in `exon/ops.py` once Exon operates as an MCP client of Mosaic's
boundary, rather than keeping them as an unused or partially-maintained parallel path.

#### Scenario: No dead local validation code remains

- **WHEN** this change's Phase 2 tasks are complete
- **THEN** `exon/validator.py` and `exon/executor.py` no longer exist in the repo, and nothing in
  `exon/planner.py`, `exon/harness/`, or `python -m exon` references the retired `QueryPlan` shape
