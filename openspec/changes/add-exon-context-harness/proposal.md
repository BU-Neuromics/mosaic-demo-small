# Change: NL → GraphQL test suite + context-tuning loop (make reliability a measured number)

## Why

Exon lets a user ask in plain English — *"bring me back all the brain tissue samples for the
hippocampus region, with the donor's cohort, sex and RHI history, and any rnaSeq data associated
with them"* — and get back real data. That functionality exists and is in scope here, not just the
test harness around it.

What's missing is any honest measure of how often it works. Running it against
`ollama_chat/gemma4:12b` showed the problem isn't that the model is *wrong*, it's that it's
**unreliable**: the same question produced a good plan on one attempt and, on another, a
structurally-valid one that had silently dropped the "hippocampus" filter entirely. Sometimes it
ignored the forced tool call and emitted prose instead. Hand-inspection caught three bugs this way;
it will not catch the fourth.

**The goal is not perfection.** It is to convert "does this work?" from an anecdote into a
statistic — run each question many times, measure the pass rate, then tune the one thing we're
allowed to change (the context given to the model) until that rate goes up substantially and
stays up.

## What Changes

- **A NL → GraphQL test suite.** Reuses the 34 curated questions already in
  `evals/questions.yaml` by id, adding `evals/plan-expectations.yaml` with what each answer must
  contain. No new NL questions invented; their expected results were already executed against live
  data.
- **Reliability measured as a distribution, not a boolean.** Every case runs `k` times (default 5).
  Report per-case pass rate, mean pass rate, and strict (k-of-k) count. A case moving 0.2 → 0.8 is
  progress and must be visible as such.
- **A capability probe before anything else.** We deliberately do not assume the target model's
  abilities. Probe it empirically at startup — does it honour system prompts, tool calls, JSON
  schema, stop sequences; how deterministic is it at temperature 0 — and pick the strictest output
  protocol it actually satisfies. This is what makes the harness work against a model we haven't
  seen before, and it directly addresses gemma4 ignoring forced `tool_choice`.
- **The tuned artifact includes decode parameters,** not just prose: `temperature`, `seed`,
  `num_ctx`, `top_p`, and the output protocol. On local models these usually matter more for
  reliability than wording. (The `num_ctx` bug found by hand this session is exactly this class.)
- **Refinement arrives as patches, not rewrites** — bounded per iteration, each block carrying why
  it exists and which failures it targets, so we can tell which change actually helped and remove
  the ones that didn't.
- **`python -m exon "<question>"` stays the product surface**; the harness measures it through the
  same code path it ships with.

## Upstream reconciliation (verified live 2026-08-05 — must be handled first)

**`mosaic#149` was fixed upstream today** (`7669fac`, PR #150): filters now accept both the LinkML
slot name and the camelCase spelling, and an unknown name raises `UNKNOWN_FILTER_FIELD` loudly
instead of silently returning zero rows. Two new loud errors were added (computed/temporal fields →
use `asOf`; multivalued reference slots → use `relatedTo`).

Consequence: **`exon/validator.py` is now wrong relative to the server.** It rejects any filter
field that isn't a `hippoSchema` slot, which now rejects legitimate camelCase queries. Left alone,
the harness would score valid answers as failures and tune the context against a constraint that no
longer exists. Local `../hippo` is one commit behind and the running server still shows the old
behaviour (verified: `field: "sampleType"` → `total: 0`).

**`mosaic#148` (no predicate on `relatedTo`) remains open**, so the bounded per-id lookup pattern is
unaffected.

## Non-Goals

- Perfect reliability. The target is a large, measured improvement with the residual failure rate
  reported honestly, not a green checkmark.
- Free-text GraphQL generation by the model, or prose-fallback parsing of a malformed reply — the
  validator stays ahead of execution.
- A general prompt-optimization framework. This tunes one context, for this schema.
- The refiner editing code, the test suite, or the schema. Structurally excluded.

## Impact

- Affected specs: new `exon-context-harness` capability. `add-exon-query-planner` (still open,
  17/19) has stale `#149`-as-open language to correct — tracked as task section 0.
- Affected code: new `exon/harness/` and `exon/context/`; edits to `exon/validator.py` and
  `exon/planner.py`; refreshed `evals/schema/capabilities.json`; new `evals/plan-expectations.yaml`.
- Cost: 34 cases × 5 samples against a local model is roughly an hour; `--samples 1 --split dev` is
  the fast inner loop.
