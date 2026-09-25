# query-benchmark Specification Delta

## ADDED Requirements

### Requirement: Schema-discovery questions assert on the produced plan

The benchmark SHALL cover questions that ask what the schema holds, and SHALL
assert on the QuerySpec the conversation converges on — which slots it names —
rather than on a row count or a rendered result set. Such a question has no
expected result in `evals/expected-results.json`, because what is being measured
is whether the planner resolved the researcher's vocabulary to the right slots,
not how many records came back.

A discovery question SHALL be phrased in a researcher's own vocabulary rather
than in slot names, since a question whose wording already contains the slot name
measures string matching rather than the grounding this capability depends on.

#### Scenario: A discovery question is graded on the slots it resolves

- **WHEN** the benchmark runs a question asking what information is held about a
  topic, phrased without naming any slot
- **THEN** it passes when the conversation converges on a QuerySpec naming the
  slots that hold that information, and fails when it names the wrong slots,
  refuses, or produces no spec — with no row count consulted

#### Scenario: A discovery question carries no expected result set

- **WHEN** a question is categorised as schema discovery
- **THEN** `evals/expected-results.json` contains no entry for it, and its
  absence is not treated as an unverified question

#### Scenario: Discovery questions do not assume a schema-describing entity type

- **WHEN** the benchmark's schema-discovery questions are run against a
  deployment whose schema contains no entity type describing the schema itself
- **THEN** they are answerable, because the capability under test is the
  planner's grounding rather than the presence of schema-describing collections
