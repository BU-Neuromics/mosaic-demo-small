# query-benchmark Specification

## Purpose
TBD - created by archiving change add-aperture-nl-graphql-query-foundation. Update Purpose after archive.
## Requirements
### Requirement: Live capability manifest

The project SHALL maintain a capability manifest derived from live Mosaic
GraphQL introspection (standard `__schema` plus `hippoSchema`/
`hippoEntityType`) for each of the four entity classes, distinguishing
supported operations (list, get, search, equality/IN filters, AND/OR
filter composition, offset pagination, relationship traversal, provenance
fields) from unsupported ones (sorting, range filters, facet/group-by
counts, relationship counts).

#### Scenario: Manifest reflects live schema state

- **WHEN** `evals/schema/capabilities.json` is regenerated against a
  running Mosaic instance for this demo
- **THEN** every entity's manifest entry matches what live introspection
  and `hippoSchema` actually report — no capability is hard-coded or
  assumed without a corresponding introspection check

### Requirement: Benchmark questions are honest about capability gaps

The benchmark SHALL mark any question that requires an unavailable
relationship-traversal or aggregation capability as `capability: blocked`
with a `blocked_by` reference to the tracking issue, and MUST NOT answer
such a question via an incomplete client-side page/scan approximation.

#### Scenario: Blocked question is labeled, not silently approximated

- **WHEN** a benchmark question requires reverse traversal through a
  relationships-table-backed multivalued reference (e.g. "which workflows
  consumed this sample," or any question chaining through it) or an
  aggregation Mosaic doesn't support (count/sort/facet/range)
- **THEN** `evals/questions.yaml` marks it `capability: blocked` with
  `blocked_by` naming the specific upstream Mosaic issue, and
  `evals/expected-results.json` contains no computed answer for it

#### Scenario: Supported question has a verified expected result

- **WHEN** a benchmark question is marked `capability: supported`
- **THEN** `evals/expected-results.json` contains a result set that was
  actually produced by running the corresponding GraphQL query against
  this demo's live data, not a hand-guessed value

