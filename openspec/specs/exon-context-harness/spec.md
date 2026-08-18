# exon-context-harness Specification

## Purpose
TBD - created by archiving change add-exon-context-harness. Update Purpose after archive.
## Requirements
### Requirement: Reliability is measured as a distribution, not a single pass or fail

The harness SHALL execute every test case multiple times per iteration and report per-case pass
rate, mean pass rate, strict k-of-k count, and flake rate separately, gating on a configurable
reliability threshold that is not required to be 1.0. The runner MUST NOT retry a generation
internally, since a retry conceals the unreliability being measured; transport errors are distinct,
retried, and recorded rather than graded.

#### Scenario: An intermittent failure is visible rather than averaged away

- **WHEN** a case passes on some samples and fails on others
- **THEN** the report shows it as flaky with its pass rate, rather than a single binary outcome that
  would depend on which sample happened to run

#### Scenario: Partial progress is reported

- **WHEN** a case's pass rate rises from 0.2 to 0.8 between iterations without reaching the
  threshold
- **THEN** the improvement is visible in the per-iteration report, not hidden behind an unchanged
  "still failing" verdict

### Requirement: The target model's capabilities are probed, never assumed

The harness SHALL empirically probe the target model before the first tuning iteration and MUST
select the output protocol from that evidence rather than from library metadata or configuration.
The probe MUST measure system-role adherence, protocol support, stop-sequence handling,
determinism at the model's working temperature, and preamble tendency, and MUST record the
resulting fingerprint alongside any context it produces. The probe SHALL NOT assume temperature 0
is accepted by every target model or provider: it MUST detect the working temperature empirically
and use that value for every subsequent check and for the seeded decode parameters, rather than
hardcoding temperature 0 or a per-model exception list.

#### Scenario: Protocol is chosen by evidence, unanimously

- **WHEN** the probe attempts each output protocol in descending strictness
- **THEN** it selects the strictest tier that succeeded on every probe attempt, and a tier that
  succeeded only intermittently is not selected

#### Scenario: A context is not reused across models

- **WHEN** a stored context's fingerprint does not match the current target model
- **THEN** the harness re-probes rather than reusing that context, because a context tuned for one
  local model is not valid for another

#### Scenario: A model that rejects temperature 0 is probed at its actual working temperature

- **WHEN** the target model or provider rejects `temperature=0` (e.g. a provider error naming the
  only value it accepts)
- **THEN** the probe detects the accepted temperature empirically and uses it for every check and
  for the fingerprint's `determinism_at_temp_0` reading and the seeded `DecodeParams`, rather than
  every check silently failing as if the model had no capabilities at all

### Requirement: The tuned artifact includes decoding parameters and output protocol

The harness SHALL treat decoding parameters and the output protocol as part of the versioned,
tunable context artifact on equal footing with prose blocks, so that reliability problems can be
addressed by the mechanism that actually fixes them.

#### Scenario: Nondeterminism is addressed by decode settings

- **WHEN** failures are classified as nondeterministic across samples of the same case
- **THEN** the failure bundle states that the remedy is a decode-parameter or protocol change rather
  than additional prose, and the refiner may set those parameters

#### Scenario: Schema facts stay live

- **WHEN** a candidate revision omits a required schema placeholder
- **THEN** it is rejected, because hardcoding schema facts into the artifact defeats live
  introspection and reintroduces hallucinated field names

#### Scenario: A decode parameter unsupported by the target provider is withheld, not sent

- **WHEN** the artifact's decode parameters are rendered into the actual API call for the
  target model
- **THEN** a parameter the provider does not accept for that model is left out rather than sent
  and left to error, checked via the provider's own capability introspection rather than a
  hardcoded per-parameter provider list — the same rule this project already applies to the
  model's own capabilities, not just to Ollama-specific parameters. Observed live: `seed`
  is accepted by Ollama but rejected outright by Bedrock's Claude with a hard
  `UnsupportedParamsError`, which failed 100% of calls in the first real run against a
  Bedrock-hosted model until this was caught

### Requirement: Refinement arrives as bounded, attributable patches

The harness SHALL accept context revisions only as patches limited to at most three block changes or
one decode/protocol change per iteration, each carrying a rationale, the failure codes it targets, a
changelog, and a stated hypothesis. The context MUST be able to shrink: a block that did not reduce
its target failure code is a candidate for removal.

#### Scenario: Causality stays recoverable

- **WHEN** a revision changes more than the permitted number of blocks in one iteration
- **THEN** it is rejected, because a larger change makes it impossible to attribute a score movement
  to any particular block

#### Scenario: An ineffective block is removed rather than accumulated

- **WHEN** a block introduced in the previous iteration did not reduce the failure code it targeted
- **THEN** its removal is proposed, so the context does not grow monotonically until it exceeds the
  model's context window

### Requirement: Evaluation is stateless and independent of prior runs

The harness SHALL issue every sample as an independent single-turn completion whose only schema
knowledge is the injected context. No conversation history, prior plan, prior failure, expectation,
case id, or expected result may reach the target model's prompt, and the model MUST NOT be
fine-tuned or carry state between samples or iterations.

#### Scenario: The target never receives the answer key

- **WHEN** any prompt is assembled for the target model
- **THEN** it contains no expectation, no case id, and no expected-result content, so a rising score
  cannot be explained by the model having been shown what to produce

### Requirement: Refinement is guarded against memorizing the test suite

The harness SHALL withhold the holdout split from the refiner entirely, enforced at the type level,
and MUST reject any revision embedding a case id or a verbatim span of eight or more consecutive
words from a test question. Convergence and artifact selection are judged on holdout score.

#### Scenario: Answer-key revision is rejected

- **WHEN** a candidate revision quotes a test question at length or names a case id
- **THEN** the harness rejects it, because such a context raises the score without improving
  generalization

#### Scenario: The best version is returned, not the last

- **WHEN** the loop terminates
- **THEN** it returns the context version with the best holdout score, rolling back revisions that
  regressed it

### Requirement: The suite tests natural-language questions end to end

The harness SHALL build its cases from the natural-language questions already curated in
`evals/questions.yaml`, joined by id to expectations describing the required query semantics, and
MUST fail loudly when an expectation names an unknown id. Expectations describe the set of
operations required to answer a question, since some questions legitimately require more than one.

#### Scenario: A multi-operation answer is expressible

- **WHEN** a question requires one bounded reverse lookup per already-identified entity in addition
  to a filtered query
- **THEN** its expectation describes that set of operations, rather than assuming a single query

#### Scenario: Correct answers are not failed on spelling

- **WHEN** an expectation requires a filter on a slot and the answer uses the equivalent camelCase
  spelling, both valid upstream
- **THEN** the expectation is satisfied, because the assertion is about query semantics rather than
  formatting

### Requirement: Fingerprints are keyed per exact target model string

The harness SHALL derive the on-disk fingerprint path as a collision-free, mechanical function of
the exact target model string, rather than a single shared path, so probing one model never
overwrites or is mistaken for another model's measured capabilities. The function SHALL NOT rely
on a hand-maintained alias table and SHALL NOT strip version-identifying suffixes from the model
string, since doing so could make two distinct versions of the same model collide on one file.

#### Scenario: Probing a second model does not erase the first model's fingerprint

- **WHEN** the harness is invoked against model A, probed and its fingerprint saved, and is then
  invoked against model B
- **THEN** model A's fingerprint file on disk is unchanged and model B's fingerprint is written
  to its own, distinct path

#### Scenario: A version change produces a distinct path, not a collision

- **WHEN** two model strings differ only in a version-identifying suffix (e.g. a date or version
  tag)
- **THEN** they resolve to two distinct fingerprint paths, never the same one

### Requirement: Finished runs can be compared without re-invoking the target model

The harness SHALL provide a way to read two or more previously written run reports and render
their key reliability figures (model, protocol, train/holdout pass rate, strict k-of-k count,
flake rate, total tokens) side by side, plus the difference against the first report, without
issuing any new call to any target model. If the reports being compared do not share the same
samples-per-case or the same train/holdout case-split size, the comparison SHALL surface an
explicit warning rather than presenting the scores as a clean, directly comparable difference.

#### Scenario: Two finished runs are compared without spending any new tokens

- **WHEN** the harness is asked to compare two paths that each resolve to an existing run report
- **THEN** it prints (and, if requested, saves) a side-by-side comparison table including the
  delta between them, and issues no new call to either model

#### Scenario: Mismatched sampling is surfaced, not silently compared

- **WHEN** the two reports being compared were produced with a different samples-per-case or a
  different train/holdout case-split size
- **THEN** the comparison output includes an explicit warning identifying the mismatch, rather
  than presenting the scores as a clean apples-to-apples model difference

