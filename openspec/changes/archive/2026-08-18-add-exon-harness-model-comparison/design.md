# Design: Cross-model reliability comparison in the Exon harness

## Context

This resolves an open question left in the archived `add-exon-context-harness` change's
`design.md` ("Open Questions"): *"Whether to add a `sweep` command comparing several Ollama
tags (cheap: same loop, run N times...)."* The need is now real and slightly different in shape:
comparing Bedrock-hosted Anthropic models (Haiku, Sonnet) rather than local Ollama tags, driven
by wanting to keep alternating target models and measuring reliability each time without a manual
step.

Two things were confirmed by reading the code before designing this (see `exon/harness/cli.py`):

- `FINGERPRINT_PATH` is a single shared mutable file (`evals/schema/fingerprint.json`),
  overwritten by `_load_or_probe` whenever the requested model doesn't match what's stored. The
  Haiku baseline work already hit this and worked around it by hand (`cp
  evals/schema/fingerprint.json evals/schema/fingerprint-bedrock-claude-haiku-4-5.json`).
- Nothing reads two `report.json` files together. `report` only re-renders one run directory.

Everything else needed already exists and is model-agnostic by design: `planner.request_plan`
takes a per-call `model` override, `ContextArtifact.assert_fingerprint()` already refuses to
reuse a context fitted to a different model, and `SuiteReport.to_dict()` already carries every
figure a comparison would need.

## Goals / Non-Goals

**Goals**: stop the fingerprint-clobbering from requiring a manual step; make it possible to see
two (or more) models' numbers side by side from artifacts that already exist on disk, spending no
new tokens to do so; produce one real comparison (Haiku vs Sonnet 5) as evidence.

**Non-Goals**: no runtime model-escalation or fallback behavior in the product CLI (`python -m
exon`) — this is a measurement capability in the harness only. No new report schema or dataclass.
No orchestration command that runs multiple models in one invocation — running against each model
is still just an ordinary `run`/`loop` invocation with a different `--model`.

## Decisions

### 1. Extend `report`, don't add a `compare`/`sweep` subcommand

Running the harness against two models is already just two invocations of the existing `run`
(or `loop`) command with different `--model`/`--out`. The only genuinely new capability is
reading two already-produced reports together — a `report`-shaped concern, not a `run`-shaped
one. A dedicated `compare`/`sweep` subcommand that internally invoked `run` twice would duplicate
`cmd_run`'s logic and hardcode a model list somewhere it doesn't belong, for no benefit over two
explicit command lines. This also matches this codebase's consistent preference for minimal,
single-purpose additions over new orchestration layers (visible throughout `exon/`'s existing
comments and structure).

**Alternative considered**: a `compare`/`sweep` subcommand that takes `--models a,b` and runs
both internally. Rejected: it would need to duplicate every `run`/`loop` flag (`--samples`,
`--workers`, `--endpoint`, `--context`, `--auto-refine`, ...) or arbitrarily restrict them, and
provides no capability beyond "call `run` twice, then compare" — which is already fully expressible
today, once the comparison-reading half exists.

### 2. Fingerprint path = mechanical function of the exact model string

`_fingerprint_path(model) -> evals/schema/fingerprint-<slug(model)>.json`, where `slug` is a pure
character-substitution function (lowercase, non-alphanumeric runs → `-`) — no hardcoded
model-name-to-slug alias table, and no stripping of version-identifying suffixes.

**Alternative considered**: a hand-maintained alias table (e.g. `{"bedrock/...haiku...":
"haiku-4-5", "bedrock/...sonnet-5": "sonnet-5"}`), matching the existing hand-named files
(`fingerprint-bedrock-claude-haiku-4-5.json`). Rejected: it reintroduces a manual step for every
new model tried — exactly what this change exists to eliminate — and silently does nothing (falls
through to some default) for a model string nobody thought to add yet.

**Alternative considered**: a "pretty" slug that strips date/version suffixes, to look like the
existing hand-named files. Rejected: two different versions of the same model (e.g. a Haiku
release before and after a version bump) would then collide on one fingerprint file, silently
serving one version's measured capabilities for the other — reintroducing the exact class of bug
being fixed, just at a coarser grain. Correctness was chosen over cosmetic naming; this is called
out plainly in `tasks.md` and the README rather than hidden.

**Consequence, stated plainly**: the two existing hand-named files
(`fingerprint-bedrock-claude-haiku-4-5.json`, `fingerprint-gemma4-12b.json`) are historical
artifacts of the old manual process and won't match the new mechanical naming scheme going
forward. They are left in place, untouched. The old shared `evals/schema/fingerprint.json` path
is simply no longer written.

## Risks / Trade-offs

- The mechanical slug is uglier than a hand-named file (e.g.
  `fingerprint-bedrock-global-anthropic-claude-sonnet-5.json` rather than
  `fingerprint-bedrock-claude-sonnet-5.json`). Accepted: correctness (no collision risk, no
  maintenance) over cosmetics.
- A comparison across models with different probed protocols conflates "model" and "protocol" as
  variables — the harness's own design already treats protocol as part of what's tuned per model
  (`exon-context-harness`'s existing "tuned artifact includes decoding parameters and output
  protocol" requirement), so this isn't new risk, but the comparison output and docs must state
  it explicitly rather than imply a single-variable A/B result.

## Migration Plan

None required. `probe`/`run`/`loop`/`report --run` are unaffected for existing single-model
workflows; the fingerprint path change is transparent (a stale `fingerprint.json` from before this
change is simply ignored going forward, not migrated).

## Addendum: temperature capability detection (found during implementation)

The first real probe of `bedrock/global.anthropic.claude-sonnet-5` came back 0/5 on every
single check — system role, all five output protocols, preamble tendency. A uniform-zero
pattern across otherwise-unrelated checks is, by this project's own established rule ("two
unrelated models producing an identical error means the defect is ours," from the earlier
entity/accessor bug), a sign of an environment problem, not a genuine capability finding. The
raw evidence confirmed it: every call failed with `litellm.UnsupportedParamsError:
global.anthropic.claude-sonnet-5 does not support temperature=0. Only temperature=1 is
supported.` — and the probe, every downstream check, and `DecodeParams`'s seed default all
unconditionally assumed `temperature=0`.

This was explicitly NOT the Ollama `think`-forces-temperature pattern already handled elsewhere
in this codebase: passing `thinking={"type": "disabled"}` explicitly still rejected
`temperature=0`. It is a hard, provider-side constraint on this specific model/inference
profile, unconditional on any other setting.

**Decision (confirmed with the user before implementing, since it touches a core assumption —
"determinism at temperature 0" is a first-class measured capability throughout this harness):**
add `_detect_temperature(model)` to the probe — one cheap call at `temperature=0`; on the
specific `UnsupportedParamsError` pattern, parse and use the required temperature instead; any
other error propagates rather than being guessed away. Thread the detected value through every
probe check and into the seeded `DecodeParams`, rather than hardcoding a per-model exception.
This is the same "measure, don't assume" rule already applied to `seed` (rejected by Bedrock,
found during the Haiku work) and to Ollama's `num_ctx`/`think` — extended here to the value of
`temperature` itself, not just which named parameters a provider accepts.

**Alternative considered**: hardcode `temperature=1` for this one model string. Rejected for the
same reason the fingerprint-path alias table was rejected above — it doesn't generalize to the
next model with the same constraint, and silently does nothing useful for a model string nobody
thought to special-case yet.

**Consequence, stated plainly**: `determinism_at_temp_0` (the field name, and its published
95%-of-the-time meaning) is measured at whatever temperature the model actually accepts, not
always literally 0. The field name is kept unchanged for compatibility with existing stored
fingerprints and call sites; every place that reports it now also states the actual probe
temperature alongside it. For Sonnet 5 specifically, determinism at the forced temperature=1 is
40% — a real, expected reliability ceiling caused by not being able to run at temperature=0, not
a bug in the measurement.

## Open Questions

None — this change fully resolves the prior open question it was scoped to answer, plus the
temperature-detection gap found and fixed along the way.
