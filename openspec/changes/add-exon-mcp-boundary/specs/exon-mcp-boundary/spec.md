## ADDED Requirements

### Requirement: MCP resources expose live schema and capabilities, read-only

Exon SHALL run an MCP server exposing two resources — the live `hippoSchema` introspection result
and the live capability manifest — each re-fetched fresh on every read. Neither resource SHALL be
cached across reads or served from a snapshot taken at server startup.

#### Scenario: Resource reads reflect the current live schema

- **WHEN** an MCP client reads the `hippoSchema` resource, and the underlying Mosaic schema then
  changes, and the client reads the resource again
- **THEN** the second read reflects the changed schema, never the first read's cached content

#### Scenario: Resources are read-only

- **WHEN** an MCP client attempts to write to either resource
- **THEN** the MCP server offers no such operation — resources are exposed for reading only

### Requirement: MCP tools validate before executing, never bypass the validator

Exon's MCP server SHALL expose `validate_query_plan` and `execute_query_plan` tools, both
accepting a `QueryPlan` in the same JSON shape the existing planner's `emit_query_plan` tool call
schema produces. `execute_query_plan` SHALL call `validator.validate_plan` internally and SHALL
NOT call `executor.execute_plan` unless validation raises nothing. No tool SHALL provide any way
to execute a plan that has not passed validation.

#### Scenario: A plan that fails validation is never executed

- **WHEN** an MCP client calls `execute_query_plan` with a plan that `validator.validate_plan`
  would reject (e.g. an unrecognized filter field, or a value outside a field's `enumValues`)
- **THEN** the tool returns the validation error and does not attempt to execute anything against
  the live GraphQL endpoint

#### Scenario: `validate_query_plan` reports validity without executing

- **WHEN** an MCP client calls `validate_query_plan` with a plan
- **THEN** the tool reports whether the plan is valid (and, if not, the specific rejection reason)
  and never issues any GraphQL call against the live endpoint

#### Scenario: A valid plan executes and returns the same result shape `execute_plan` already produces

- **WHEN** an MCP client calls `execute_query_plan` with a plan that passes validation
- **THEN** the tool executes it via the existing `executor.execute_plan` and returns its
  unmodified `{"steps": {...}, "final": {...}}` result

### Requirement: No raw GraphQL, mutation, or escape-hatch tool exists

Exon's MCP server SHALL NOT expose any tool that accepts free-text or raw GraphQL, any tool that
performs a mutation, or any tool that reaches the GraphQL endpoint other than through
`executor.execute_plan` on a plan that has passed `validator.validate_plan`.

#### Scenario: No tool accepts arbitrary GraphQL

- **WHEN** the MCP server's tool list is inspected
- **THEN** every tool's input is either a typed `QueryPlan` JSON payload or a natural-language
  instruction routed through the existing planner (`plan_query`) — none accept a raw GraphQL
  query string

#### Scenario: No tool performs a write

- **WHEN** the MCP server's tool list is inspected
- **THEN** no tool issues a GraphQL mutation or otherwise modifies stored data

### Requirement: The NL planner is exposed only as an optional, experimentation-only tool

Exon's MCP server SHALL treat `plan_query` as optional and experimentation-only. If exposed, it wraps the existing `planner.plan_query` unchanged, for use by clients with no planner of their own (e.g. the MCP Inspector), and Exon SHALL document that a client with its own planner (Aperture, Reel, or similar) SHOULD call `validate_query_plan`/`execute_query_plan` directly with its own emitted plan and SHOULD NOT route through `plan_query`.

#### Scenario: `plan_query` produces the same plan shape `validate_query_plan`/`execute_query_plan` accept

- **WHEN** `plan_query` is called with a natural-language instruction and succeeds
- **THEN** its output is a `QueryPlan` in the exact JSON shape `validate_query_plan` and
  `execute_query_plan` accept as input, requiring no translation step
