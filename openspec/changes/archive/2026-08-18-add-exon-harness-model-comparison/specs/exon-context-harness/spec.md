## MODIFIED Requirements

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

## ADDED Requirements

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
