# Change: Cross-model reliability comparison in the Exon harness (Haiku vs Sonnet 5)

## Why

The harness measures reliability against exactly one target model per invocation, and comparing
two models today requires a manual workaround: `evals/schema/fingerprint.json` is a single shared
mutable path, overwritten whenever `--model` changes, so the Haiku-vs-Sonnet comparison the team
now wants would silently clobber whichever model's fingerprint was probed first — the same problem
already worked around by hand once, by manually copying `fingerprint.json` to a model-named file
after the Haiku baseline run. There is also no way to view two models' reliability numbers side by
side without opening two report files and comparing them by eye. This was flagged as an open,
unresolved question in the archived `add-exon-context-harness` change's `design.md` ("Whether to
add a `sweep` command comparing several Ollama tags") and never implemented.

The team now wants to keep alternating between Anthropic models (starting with the current
`bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0` default and a current Sonnet,
`bedrock/global.anthropic.claude-sonnet-5` — the originally-requested
`us.anthropic.claude-3-sonnet-20240229-v1:0` is a Claude 3 Sonnet model Anthropic retired
2025-07-21, absent from this account's `list-foundation-models` and only present as a stale
inference-profile entry, so it was swapped for a current model per user decision) and needs this
to not require a manual step every time.

## What Changes

- **Fingerprint paths keyed per exact model string.** `evals/schema/fingerprint-<slug>.json`,
  where `<slug>` is a mechanical, collision-free function of the model string — never a
  hand-maintained alias table, and never a "pretty" slug that strips version suffixes (that would
  make two different versions of the same model collide on one file).
- **`report --compare <path> <path> [...] [--out FILE]`** — a new mode on the existing `report`
  subcommand (not a new subcommand) that reads two or more already-written `report.json`-shaped
  files and renders their model/protocol/train/holdout/strict/flaky/token figures side by side
  plus deltas against the first, spending zero new model calls. Warns explicitly rather than
  silently comparing if the reports used a different samples-per-case or case-split size.
- **A real baseline (and refine-loop) run against `bedrock/global.anthropic.claude-sonnet-5`**,
  compared against the existing, still-valid Haiku baseline
  (`evals/baselines/2026-08-18-bedrock-haiku-4-5-seed-v000.json`), saved under `evals/baselines/`
  following the existing naming convention.
- `exon/README.md` / `DEMO.md` updated with the real comparative numbers, the `--compare` usage,
  and an explicit caveat that a score delta is model-*and*-protocol jointly whenever the two
  models' probed protocols differ.

## Impact

- Affected specs: `exon-context-harness` (2 added requirements — fingerprint keying, cross-run
  comparison; no existing requirement's semantics change).
- Affected code: `exon/harness/cli.py` (fingerprint path helper, `report --compare`); new/extended
  test coverage in `tests/test_harness_invariants.py` or a new `tests/test_harness_cli.py`.
- No changes to `exon/planner.py` or the product surface (`python -m exon`) — this is a
  measurement-only capability, not a runtime model-escalation feature.
- No breaking changes: `probe`/`run`/`loop`/`report --run` behave exactly as before; the
  fingerprint path change is transparent to existing single-model workflows (a stale
  `evals/schema/fingerprint.json` from before this change is simply no longer read or written).
