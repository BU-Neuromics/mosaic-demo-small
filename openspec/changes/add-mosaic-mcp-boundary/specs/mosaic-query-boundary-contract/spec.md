# mosaic-query-boundary-contract

Scope note: this capability documents an external contract Exon's integration depends on. It is
not implementable from `mosaic-demo-small`, and does not assert control over Mosaic's own codebase
or release process — each requirement below is worded as what *this repo's* Exon integration must
do in relation to that dependency, so the dependency itself is stated precisely. See
`add-mosaic-mcp-boundary/design.md` Decision 6.

## ADDED Requirements

### Requirement: Exon's integration treats Mosaic's live capability resource as sole grounding

Exon's integration SHALL treat Mosaic's MCP schema and capability resources (live schema
description; server-derived capability manifest covering supported filter ops per field kind,
enum values per enum-backed field, relationship-predicate support, and aggregation/sort/search
availability) as its sole source of grounding, refetched fresh on every use. Exon's integration
SHALL NOT depend on a cached response or a hand-maintained local copy remaining accurate.

#### Scenario: Exon's integration re-reads on every use, never caches

- **WHEN** Mosaic's schema or capabilities change while an MCP client session is open
- **THEN** Exon's integration reads the current value on its next resource read, never a value
  cached from an earlier read in the same or a prior session

### Requirement: Exon's integration never executes a `QuerySpec` without Mosaic's validation

Exon's integration SHALL call Mosaic's `execute_query_spec` MCP tool for every plan execution, and
SHALL treat any validation failure that tool returns as authoritative and final. Exon's integration
SHALL NOT execute a `QuerySpec` through any other path, and SHALL NOT treat its own prior belief
that a plan was valid as a reason to bypass Mosaic's validation.

#### Scenario: Exon's integration never bypasses Mosaic's validation

- **WHEN** Exon calls Mosaic's `execute_query_spec` with a `QuerySpec`
- **THEN** Exon's integration relies on that call's own validation outcome rather than skipping it
  based on an earlier local check, and surfaces a validation failure rather than retrying against
  a different, unvalidated execution path

### Requirement: Exon's integration treats Mosaic's MCP surface as read-only

Exon's integration SHALL NOT call any Mosaic MCP tool capable of a write or mutation, and SHALL NOT
treat the `X-Mosaic-Actor` header (or any successor identity header) as authentication or
authorization.

#### Scenario: Exon's integration never depends on a write-capable tool

- **WHEN** Mosaic's MCP tool list is inspected as part of this repo's integration
- **THEN** every tool this repo's integration calls is read-only, and the discovery of any
  write-capable tool is treated as a breaking change to this contract requiring re-evaluation
  before Exon's integration continues to depend on Mosaic's boundary

### Requirement: Exon's integration relies on actionable, per-criterion validation errors

Exon's integration SHALL treat a `validate_query_spec`/`execute_query_spec` validation failure as
containing enough detail (the offending slot, op, or edge, and — for enum/op mismatches — the valid
set) to construct a corrected `QuerySpec` without additional guesswork, and SHALL rely on this to
implement an iterative validate → fix → retry loop rather than a blind resample on failure.

#### Scenario: Exon's integration corrects a plan from the error alone

- **WHEN** Exon's integration receives a validation failure naming a specific invalid slot, op, or
  enum value
- **THEN** it constructs its next `QuerySpec` attempt using that detail directly, rather than
  resampling a fresh attempt with no information about what was wrong

### Requirement: Exon's integration reads procedural guidance from Mosaic's Prompt, not its own hand-curated copy

Exon's integration SHALL read Mosaic's `construct-query-spec` MCP Prompt for procedural "how to"
guidance on constructing a valid `QuerySpec` (field-name resolution, relationship-predicate shape,
`columns` aggregate/explode choice, the `asOf` restriction), and SHALL NOT maintain its own
independent, hand-curated copy of this guidance once Mosaic's Prompt is available.

#### Scenario: Exon's integration does not duplicate procedural guidance

- **WHEN** Mosaic's `construct-query-spec` Prompt is available
- **THEN** Exon's integration sources its planning guidance from that Prompt rather than from a
  separately maintained system-prompt fragment describing the same rules

### Requirement: Exon's integration pins to the `QuerySpec` artifact version

Exon's integration SHALL construct and interpret `QuerySpec` payloads according to the version
declared in the payload's own `v` field (per Aperture's ADR-0035 shape: `v`, `anchor`, `mode`,
`criteria`, `columns`, `sort`, `asOf`), and SHALL fail explicitly rather than silently
misinterpreting payload shape if Mosaic's boundary reports or requires a `v` this integration does
not recognize.

#### Scenario: Exon's integration fails explicitly on an unrecognized version

- **WHEN** Mosaic's boundary reports support for a `QuerySpec` version this integration does not
  recognize
- **THEN** Exon's integration raises a clear, explicit error naming the version mismatch rather
  than sending a payload shaped for a version it has not confirmed compatibility with
