# query-benchmark Specification Delta

## ADDED Requirements

### Requirement: Benchmark runs against the certified deployment

The benchmark SHALL be runnable against the certified DataHelix `solo`
container for this project, and the repository SHALL record which Mosaic
version that container provides. Where the project documents a host-side
`mosaic serve` path instead, it SHALL name the specific capability that
requires it and the upstream issue gating a released alternative, rather
than presenting host-serve as the ordinary way to run the demo.

#### Scenario: Certified container boots against this project

- **WHEN** the certified `solo` recipe is booted with `PROJECT_DIR` pointing
  at this repository, from a DataHelix checkout whose
  `certification/composition.lock.json` pins a Mosaic version containing
  `ec59c90`
- **THEN** the container reaches a serving state without crash-looping, no
  `Workflow.input_samples: required: true` migration error appears in its
  logs, and the GraphQL endpoint answers introspection

#### Scenario: Host-serve is documented as scoped, not default

- **WHEN** the project documents running Mosaic from a host-side editable
  checkout
- **THEN** the documentation names the capability that is unavailable in the
  pinned container release (e.g. `converseQuerySpec`, which exists only on
  Mosaic `main`), so a reader cannot mistake the container for a build that
  carries unreleased work

### Requirement: Parity with the recorded baseline is demonstrated by diff

When the serving path changes, the project SHALL demonstrate that benchmark
behaviour is unchanged by diffing a fresh run against a recorded baseline in
`evals/baselines/`, and SHALL NOT treat a visually-inspected endpoint as
evidence of parity. Every divergence SHALL be classified as an expected
improvement, expected parity, or a regression.

#### Scenario: Divergence from baseline is classified, not absorbed

- **WHEN** a benchmark run against a new serving path differs from the
  recorded baseline for the same fixture seed
- **THEN** each differing question is classified, an expected improvement is
  tied to the specific upstream issue that closed, and a regression blocks
  the change instead of the baseline being rewritten to match

## MODIFIED Requirements

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

A `blocked` marker SHALL be scoped to the Mosaic version actually being
served, because a marker whose upstream issue has closed may be stale, and a
benchmark run that skips a stale-blocked question can report green while
concealing a capability that should now pass. When a `blocked_by` issue
closes, the marker SHALL be re-audited empirically against the running
instance rather than inferred from the issue's state.

#### Scenario: Blocked question is labeled, not silently approximated

- **WHEN** a benchmark question requires a capability the manifest marks
  unsupported (e.g. an aggregation Mosaic doesn't support), or can only be
  answered by scanning entities whose ids are not already known from a
  prior filtered/traversal step
- **THEN** `evals/questions.yaml` marks it `capability: blocked` with
  `blocked_by` naming the specific upstream Mosaic issue, and
  `evals/expected-results.json` contains no computed answer for it

#### Scenario: A closed blocker forces an empirical re-audit

- **WHEN** an issue named in a question's `blocked_by` has closed upstream
- **THEN** the question is re-run against the running instance at the served
  Mosaic version, and the marker is either cleared (with a verified entry
  added to `evals/expected-results.json`) or retained with the served version
  recorded — the issue being closed is not on its own sufficient to clear it,
  since the fix may not be in the released version the container pins

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
