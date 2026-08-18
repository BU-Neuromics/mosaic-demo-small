## 0. Temperature capability detection (discovered mid-implementation, scope expanded with user approval)

- [x] 0.1 First probe of `bedrock/global.anthropic.claude-sonnet-5` came back 0/5 on every
      single check (system role, all 5 protocols, preamble) — a uniform-zero pattern that (per
      this project's own "unrelated failures identical -> the defect is ours" rule) pointed at
      an environment problem, not a capability one. Root cause, found from the raw evidence:
      `litellm.UnsupportedParamsError: global.anthropic.claude-sonnet-5 does not support
      temperature=0. Only temperature=1 is supported.` — every probe call and the whole
      `DecodeParams`/seed-context machinery unconditionally assumed `temperature=0`. Confirmed
      this is NOT the Ollama-style "thinking forces temp=1" pattern: explicitly passing
      `thinking={"type":"disabled"}` still rejected `temperature=0`.
- [x] 0.2 `exon/harness/probe.py`: added `_detect_temperature(model)` — one cheap call at
      temperature=0; on `UnsupportedParamsError` matching "Only temperature=X is supported",
      returns that X; any other error propagates (a real auth/transport/model-id problem must
      surface, never be guessed away). Threaded the detected `temperature` through every check
      function (`_check_system_role`, `_try_protocol`, `_check_stop_sequences`,
      `_check_determinism`, `_check_preamble`, `_check_protocol_under_load`) instead of the
      previous hardcoded `temperature=0`. Added `ModelFingerprint.probe_temperature` (default
      0.0, so old stored fingerprints still deserialize) and included it in `compute_id()`'s
      hash. `determinism_at_temp_0`'s field NAME is unchanged (avoids touching every downstream
      consumer) but what it measures is now honestly "at `probe_temperature`", logged as such.
- [x] 0.3 `exon/context/seed.py`: `DecodeParams(temperature=...)` now reads
      `fingerprint.probe_temperature` instead of a hardcoded `0.0`.
- [x] 0.4 Re-probed Sonnet 5 after the fix: real signal this time —
      `temperature=1.0` detected; `system_role=5/5`; `tool_call` protocol `5/5` isolated and
      `3/3` under load (qualifies); `json_schema=0/5` (rejected under this config);
      `stop_sequences=3/5`; **`determinism @ temp 1 = 40%`** — a real, expected consequence of
      being forced off temp=0, not a bug, and it caps this model's achievable reliability
      ceiling regardless of context tuning. Confirmed Haiku is unaffected:
      `_detect_temperature` returns `0.0` for it, unchanged behavior.
- [x] 0.5 Full existing 66-check suite re-verified green after this fix, before proceeding.

## 1. Fingerprint path fix

- [x] 1.1 `exon/harness/cli.py`: add `_model_slug(model: str) -> str` (mechanical, no alias
      table) and `_fingerprint_path(model: str) -> Path`; replace the module-level
      `FINGERPRINT_PATH` constant and all 6 references inside `_load_or_probe` with a call to
      `_fingerprint_path(model)`. `cmd_probe`/`cmd_run`/`cmd_loop` call sites unchanged.
- [x] 1.2 Confirmed `evals/schema/fingerprint.json` (the old shared path) is no longer written
      by any code path; left in place, untouched (already untracked).
- [x] 1.3 Unit tests added to `tests/test_harness_invariants.py`: two distinct model strings
      never collide; a version-suffix-only change produces a distinct path; same model string is
      idempotent.

## 2. `report --compare`

- [x] 2.1 `exon/harness/cli.py`: added `--compare` (nargs="+") and `--out` (a file path, not a
      dir) to the `report` subparser; exactly one of `--run`/`--compare` enforced, and
      `--compare` requires ≥2 paths.
- [x] 2.2 Implemented as a pure `_compare_reports(paths) -> str` (no side effects, easy to unit
      test) plus a thin `_cmd_compare(args)` CLI wrapper that prints and optionally writes
      `--out`. Resolves a directory to `<dir>/report.json` if present (a `run` output dir);
      otherwise reads the path directly as a file — this also covers pointing at a `loop` run's
      `iterations/iterNN.json` (a bare `loop` dir has no top-level `report.json` and raises
      rather than guessing). One block per report: model/protocol/context_version/fingerprint,
      train/holdout/strict_train/strict_holdout/flaky/tokens/wall_clock_s, plus Δ-lines against
      the first report.
- [x] 2.3 Mismatch guard implemented: differing samples-per-case or train/holdout case counts
      prints an explicit `WARNING:` line ahead of the table. A protocol-mismatch note is also
      printed when compared reports used different protocols (model-AND-protocol jointly, not a
      clean single-variable delta).
- [x] 2.4 10 unit tests added to `tests/test_harness_invariants.py` covering: normal compare
      (both models named, no warning), a `run`-dir resolving via its own `report.json`, the
      samples-per-case mismatch warning, the differing-protocol caveat, `<2` paths raising
      `ValueError`, and a directory with no `report.json` raising `FileNotFoundError` rather than
      guessing. All spend zero model calls (fixture `SuiteReport`s written to a temp dir).
      Full suite: 66 -> 76 checks, all passing.

## 3. Real evidence run

- [x] 3.1 Probed Sonnet 5 — see Section 0 (this is where the temperature-rejection bug was
      found and fixed). After the fix: `temperature=1.0` detected; `system_role=5/5`;
      `tool_call` qualifies (5/5 isolated, 3/3 under load); `json_schema=0/5`;
      `stop_sequences=3/5`; `determinism @ temp 1 = 40%`.
- [x] 3.2 Real baseline, `--samples 3` (matching Haiku): **train=0.38, holdout=0.50,
      strict_train=8/21, strict_holdout=4/8, flaky=0, tokens=226409**. Fingerprint auto-saved to
      its own path (`evals/schema/fingerprint-bedrock-global-anthropic-claude-sonnet-5.json`) —
      no manual copy step this time, unlike the Haiku work. Report saved to
      `evals/baselines/2026-08-18-bedrock-sonnet-5-seed-v000.json`. Notable finding: Sonnet 5
      passes `q21` (100%) — the "queries `Donor` when asked which *samples* a donor contributed"
      bug that BOTH gemma4 and Haiku failed — but shares Haiku's exact `select_fields`
      reference-field mistake on `q09/q17/q18/q23/q24/q35`, suggesting that specific failure is a
      grounding/prompt gap common to both models, not a model-specific quirk.
- [x] 3.3 `loop --auto-refine --max-iter 4 --samples 3` — first attempt with `--workers 6`
      stalled at the OS/network level (TCP retransmit counts in the thousands per connection,
      zero CPU progress for 20+ minutes; killed and not counted as a finding about Sonnet 5
      itself). Retried with `--workers 3` and completed cleanly. Real result:
      **iter 0 (v000): train=0.38, holdout=0.50** (matches 3.2). **iter 1 (v001): train=0.41,
      holdout=0.67, flaky=2** — the refiner's patch (constraint block requiring every stated
      constraint as a filter) genuinely improved holdout. **iter 2 (v002): every one of 87
      samples failed** — the refiner's decode-param change set `temperature=0.7`, which this
      model rejects (`UnsupportedParamsError`, the same constraint found in Section 0, now hit
      by the refiner rather than the probe). Correctly classified as `PROVIDER_ERROR`
      (environment, not context-addressable), correctly rolled back to v001, and the loop
      correctly stopped ("only environment/config failures remain") rather than erroring out or
      looping further. **Final: baseline holdout 0.50 -> best 0.67 (+0.17) at v001** — a real
      improvement, unlike Haiku's flat +0.00 on the same treatment. Loop report saved to
      `evals/baselines/2026-08-18-bedrock-sonnet-5-loop-report.md`.
- [x] 3.4 `report --compare evals/baselines/2026-08-18-bedrock-haiku-4-5-seed-v000.json
      evals/baselines/2026-08-18-bedrock-sonnet-5-seed-v000.json --out
      evals/baselines/2026-08-18-compare-haiku-vs-sonnet-5.md` — both models used the same
      protocol (`tool_call`) and sampling (3/case, 21 train + 8 holdout), so the comparison is a
      clean model-only delta: **Δtrain=+0.05, Δholdout=+0.00, Δstrict_train=+1** (Sonnet 5 over
      Haiku, at the seed context before any refinement).

## 4. Documentation

- [x] 4.1 `exon/README.md`: documented `report --compare` and the per-model fingerprint path;
      added a full "Haiku vs Sonnet 5" findings subsection with the real numbers, the
      temperature-detection bug and fix, the shared `select_fields` grounding gap, and the
      +0.17 loop result; updated the test-count claim (66 -> 77 checks).
- [x] 4.2 `DEMO.md`: added a runnable `--compare` example using the two real saved baseline
      files (verified it actually runs and matches the documented output); updated "what works
      today"/"what does not work yet" and the "Progress" line with the comparison findings and
      both archived changes.

## 5. Validate and wrap up

- [x] 5.1 Full test suite: 77 checks (66 existing + 11 new in `test_harness_invariants.py`: 4
      for fingerprint-path collision-freedom, 7 for `report --compare`), all passing.
- [x] 5.2 `openspec validate add-exon-harness-model-comparison --strict` passes.
- [ ] 5.3 Archive via `openspec archive add-exon-harness-model-comparison --yes` once the real
      comparison results are reviewed and accepted.
