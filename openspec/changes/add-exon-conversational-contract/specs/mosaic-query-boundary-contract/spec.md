# mosaic-query-boundary-contract (extension)

Scope note: extends the external-dependency contract capability introduced by
`add-mosaic-mcp-boundary` with one more dependency, needed specifically for Exon's conversational
turn-taking entry point (`exon-conversational-planner`). Same scope discipline applies: this is not
implementable from `mosaic-demo-small`, and does not assert control over Mosaic's own codebase or
release process — it states what this repo's Exon integration depends on.

## ADDED Requirements

### Requirement: Exon's conversational integration reaches Mosaic's converse_query_spec tool, never a bespoke Exon-facing endpoint

Exon's integration SHALL expose its turn-taking capability to external callers (e.g. Aperture's
browser client) only through Mosaic's `converse_query_spec` MCP tool, which delegates
server-to-server to Exon's planning core. Exon's integration SHALL NOT require or advertise any
direct, browser-reachable endpoint of its own for this capability.

#### Scenario: The only reachable path to conversational planning is through Mosaic

- **WHEN** an external caller (e.g. Aperture) wants to use Exon's turn-taking capability
- **THEN** it does so by calling Mosaic's `converse_query_spec` tool, and Exon's integration
  assumes no other network path to this capability is advertised or required

### Requirement: Exon's conversational integration assumes converse_query_spec inherits the same safety constraints as validate/execute

Exon's integration SHALL assume Mosaic's `converse_query_spec` tool is read-only (no write or
mutation capability reachable through it), and SHALL assume it does not bypass the validation
`validate_query_spec` already performs on any `QuerySpec` it produces or returns.

#### Scenario: Exon's integration assumes no escape hatch through the conversational tool

- **WHEN** Mosaic's `converse_query_spec` tool is inspected
- **THEN** Exon's integration assumes it carries the same read-only, always-validated guarantees as
  `execute_query_spec`, and treats any deviation from that as a breaking change to this contract
  requiring re-evaluation

### Requirement: converse_query_spec calls Exon's endpoint using the wire shape Decision 8 specifies

Exon's integration SHALL assume Mosaic's `converse_query_spec` tool, once configured with this
repo's turn endpoint URL via `MOSAIC_EXON_URL`, calls it using the request/response/`Turn` shapes
specified in `design.md` Decision 8 and in `exon-conversational-planner`'s own wire-shape
requirement — no bespoke per-deployment translation layer exists or is needed on either side.

#### Scenario: Exon's integration does not treat its own validation as the last word

- **WHEN** Exon's turn endpoint returns a candidate `QuerySpec` with status `proposal`
- **THEN** Exon's integration assumes Mosaic re-validates that `QuerySpec` in-process before
  forwarding it to the caller, and does not skip its own generation-time validation calls on the
  assumption that Mosaic's re-check makes them unnecessary — both exist as defense-in-depth, per
  `design.md` Decision 8
