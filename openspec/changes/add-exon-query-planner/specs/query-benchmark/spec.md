## MODIFIED Requirements

### Requirement: Live capability manifest

The project SHALL maintain a capability manifest derived from live Mosaic
GraphQL introspection (standard `__schema` plus `hippoSchema`/
`hippoEntityType`) for each of the four entity classes, distinguishing
supported operations (list, get, search, equality/IN filters, AND/OR
filter composition, offset pagination, relationship traversal,
relationship-existence reverse lookup via `relatedTo`, provenance fields)
from unsupported ones (sorting, range filters, facet/group-by counts,
relationship counts, predicate/filter arguments on `relatedTo`'s returned
entities). The manifest SHALL also record that list-filter `field` values
must be the LinkML slot name (from `hippoSchema`), not the GraphQL type's
own field name.

#### Scenario: Manifest reflects live schema state

- **WHEN** `evals/schema/capabilities.json` is regenerated against a
  running Mosaic instance for this demo
- **THEN** every entity's manifest entry matches what live introspection
  and `hippoSchema` actually report — no capability is hard-coded or
  assumed without a corresponding introspection check, and the manifest
  records both that `relatedTo` exists without a predicate argument, and
  that filter field names must come from `hippoSchema`, not `__type`

### Requirement: Benchmark questions are honest about capability gaps

The benchmark SHALL mark any question that requires an unavailable
relationship-traversal or aggregation capability as `capability: blocked`
with a `blocked_by` reference to the tracking issue, and MUST NOT answer
such a question via an incomplete client-side page/scan approximation.
A question is achievable — not `blocked` — when it can be answered using
only: (a) server-side filtered/traversal queries already supported today
(built with the correct slot-name `field` values), and (b) zero or more
`relatedTo` calls, **each scoped to one already-identified entity id**
(obtained from (a) or from a prior `relatedTo` call), with any predicate
on the referenced entities' own fields applied client-side only over that
one call's own small, bounded result. This holds regardless of how many
such bounded calls the full answer requires — the defining property is
that every call is scoped to a specific, already-known id, never an
unfiltered scan across an entire entity table.

#### Scenario: Blocked question is labeled, not silently approximated

- **WHEN** a benchmark question requires a capability the manifest marks
  unsupported (e.g. an aggregation Mosaic doesn't support), or can only be
  answered by scanning entities whose ids are not already known from a
  prior filtered/traversal step
- **THEN** `evals/questions.yaml` marks it `capability: blocked` with
  `blocked_by` naming the specific upstream Mosaic issue, and
  `evals/expected-results.json` contains no computed answer for it

#### Scenario: Bounded per-id reverse lookup is achievable, not blocked

- **WHEN** a benchmark question requires knowing which entities reference
  one or more already-identified entities through a relationships-table-
  backed slot (e.g. "which workflows reference this donor's samples"),
  answerable via one `relatedTo(id, relationshipType)` call per already-
  identified id, each individually bounded
- **THEN** the question is marked with its ordinary traversal/filter
  capability category (not `blocked`), and `evals/expected-results.json`
  contains a result verified by actually running those calls against this
  demo's live data; the question's note names how many bounded calls the
  answer required and cites the predicate-pushdown gap as the reason it
  isn't a single composed query, without that gap making the question
  unanswerable

#### Scenario: Supported question has a verified expected result

- **WHEN** a benchmark question is marked with a supported capability
  category
- **THEN** `evals/expected-results.json` contains a result set that was
  actually produced by running the corresponding GraphQL query — built
  with slot-name `field` values, per the "Live capability manifest"
  requirement — against this demo's live data, not a hand-guessed value
