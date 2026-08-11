## Context

The workflow being implemented, one module per node:

```
[0] probe target model  (what can this thing actually do?)
         |
[A] test suite (reuse evals/questions.yaml)
         |
         v
[B] run suite against target, k samples each,  <---------------.
    with an EDITABLE CONTEXT                                   |
         |                                                     |
[C] grade -> pass rate per case                                |
         |                                                     |
    < failures? > --yes--> [D] triage into a classified    [E] refine
         |                     failure bundle -------------> context (patch)
         no
         v
    [F] done: return best-scoring context
```

The **editable context** is the only thing the loop may change. Test suite, grader, schema, and
model weights are fixed within a run. That constraint is what makes any score attributable.

## Goals

- Turn "does Exon work?" into a number: per-case pass rate over `k` samples, tracked per iteration.
- Raise that number substantially by tuning the context, and know *which* change raised it.
- Work against a model whose capabilities we don't know in advance.
- Keep `python -m exon "<question>"` — the natural-language product surface — working through the
  same render path the harness tunes.

## Non-Goals

- Perfection. Residual failure rate is reported, not hidden.
- Prose-fallback parsing of a malformed reply.
- Tuning anything but the context artifact.

## Decisions

### 1. What gets measured: NL in, GraphQL out

The suite is end-to-end. A case gives a natural-language question and asserts on what comes back.
Exon's internal `QueryPlan` is not a separate contract to satisfy — it is where diagnostic signal
comes from when a case fails, letting triage say *which* stage broke rather than just "wrong
answer."

Grading ladder, first failure stops that sample:

| Tier | Check |
|---|---|
| 0 | A structured answer was produced at all (protocol honoured) |
| 1 | The resulting GraphQL parses and validates against the **live** schema |
| 2 | It matches the case's expected semantics — required filters/fields present, no silently-added extras |
| 3 | *(tagged subset)* Executed, it returns the expected data |

Tier 2 asserts semantics, not spelling: post-#150 both `sample_type` and `sampleType` are valid, so
comparison resolves through `hippoSchema` rather than string-matching. Never fail a correct answer
on cosmetics — that sends the refiner chasing ghosts.

Some questions legitimately require **several** operations (the rnaSeq leg is one bounded
`relatedTo` call per already-identified sample). Expectations therefore describe the required set of
operations, not a single query string.

### 2. Reliability is a distribution

Each case runs `k` times (default 5) at the probed decode settings. `pass_rate = passing / k`.

- Report **mean pass rate**, **strict count** (cases at k-of-k), and **flake rate** (cases with
  `0 < pass_rate < 1`) separately.
- The loop's gate is a configurable `reliability_threshold` (default **0.8**, not 1.0). Perfection
  was never the goal; against a 7B–12B local model a 1.0 gate would simply never terminate.
- Never retry a generation inside the runner — a retry hides the very unreliability being measured.
  Transport errors are distinct, retried up to 3×, and recorded rather than graded.

### 3. Probe the model before assuming anything

Runs once per run, before the loop. Empirical and adversarial: a local model's *declared* capability
and its actual behaviour diverge routinely, so the probe's finding wins over any library metadata.

For each check, 5 calls at temperature 0:

1. **System-role adherence** — does it obey a system instruction exactly.
2. **Protocol ladder** — try `json_schema` → `tool_call` → `json_object` → `delimited` → `raw`;
   select the strictest tier that succeeds **5/5**. Anything less than unanimous is not reliable.
   This is the direct answer to gemma4:12b intermittently ignoring forced `tool_choice`.
3. **Stop sequences** — honoured or not.
4. **Determinism at temp 0** — fraction of byte-identical repeats. Below 1.0 this caps everything
   downstream; surface it prominently.
5. **Preamble tendency** — how often it wraps output in prose or code fences.
6. **Context window** — read if reachable; guards against silently truncating the context.

Output: a persisted `ModelFingerprint` plus a seed context (v0) whose protocol and decode params are
derived from it. Re-probe when the model string changes; never reuse a context fitted to a different
fingerprint.

### 4. The context artifact is data, versioned, and includes decode params

Typed blocks (`ROLE`, `SCHEMA`, `OUTPUT_CONTRACT`, `EXEMPLAR`, `CONSTRAINT`, `GLOSSARY`,
`RECOVERY`), each with a required `rationale` and the failure codes it targets. Plus
`DecodeParams` (`temperature`, `seed`, `num_ctx`, `top_p`, …) and the chosen `OutputProtocol` — all
on equal footing with prose, because on local models these often dominate wording. The `num_ctx`
truncation found by hand this session is exactly this class of fix.

Schema facts are **rendered from live introspection** at run time via required placeholders, never
written into the artifact — a revision that drops a placeholder is rejected, since hardcoding schema
facts reintroduces the hallucination class this project keeps finding.

### 5. Refinement is a bounded patch, not a rewrite

The refiner returns `add_blocks` / `remove_block_ids` / `modify_blocks` / `toggle_blocks`, optional
`decode_params` and `protocol`, plus a required `changelog` and `hypothesis` (which failure codes
should drop). Capped at **3 block changes or 1 decode/protocol change per iteration** — beyond that,
causality is unrecoverable.

Preference order given to the refiner: decode/protocol changes for format and determinism failures →
schema presentation for hallucinated fields → glossary for vocabulary misses → constraints for
systematic over/under-fetch → exemplars last (most token-expensive, most overfit-prone).

**The context must be able to shrink.** If a block introduced last iteration didn't reduce its
target failure code, propose removing it — otherwise the context grows monotonically into a wall of
text that eventually exceeds `num_ctx` and degrades everything at once.

### 6. Model independence, and context that generalises

Two distinct requirements, both enforced structurally:

- **Stateless evaluation.** Every sample is an independent single-turn call. No conversation
  history, no prior plans, no expectations, case ids, or expected results in the prompt, no
  fine-tuning. Otherwise a rising score measures memorisation, not context quality.
- **Anti-answer-key.** Train/holdout split (~70/30, stratified by capability). The refiner sees only
  train failures, never holdout cases or scores — enforced at the type level, not by convention.
  Plus a lint rejecting any revision embedding a case id or an ≥8-word verbatim span of a test
  question, and a size cap.

### 7. Failure taxonomy, split by who can fix it

Codes cover: no output / prose wrapper / fence / protocol violation (tier 0); syntax error (tier 1);
unknown field / unknown argument / type mismatch / missing selection (tier 2); missing field / extra
field / wrong argument / wrong nesting (tier 3); plus `NONDETERMINISTIC` (0 < pass_rate < 1) and
`TRANSPORT_ERROR`.

The triage bundle carries, per code: count, affected tags, up to 3 verbatim examples, and **the
currently-enabled blocks that were supposed to prevent it** — turning refinement from guesswork into
a review of what was already tried. `NONDETERMINISTIC`'s remedy is almost never more prose; the
bundle says so explicitly and points at decode params.

`TRANSPORT_ERROR` and context-window truncation are environment problems and are excluded from the
refiner's bundle — it must not try to fix a config bug by rewording.

### 8. Post-#150 validator correction (prerequisite)

Accept either field-name spelling (resolved via `hippoSchema`, never by guessing a transformation);
still reject genuinely unknown names; newly reject filters on multivalued reference slots and on
computed/temporal fields, mirroring the server's two `UNFILTERABLE_FIELD` cases.

## Module layout

```
exon/context/template.py     # ContextArtifact, blocks, decode params, render/patch/version
exon/context/templates/      # v000.json … versioned, diffable
exon/harness/probe.py        # [0] capability fingerprint
exon/harness/cases.py        # [A] load suite from evals/*.yaml
exon/harness/runner.py       # [B] k samples/case, concurrent, stateless
exon/harness/grading.py      # [C] tier ladder
exon/harness/triage.py       # [D] failure taxonomy + bundle (train split only)
exon/harness/refine.py       # [E] patch via litellm
exon/harness/loop.py         # [F] orchestration, rollback, resume
exon/harness/cli.py          # run | loop | report | resume
exon/harness/runs/<ts>/      # config, fingerprint, suite, contexts/, iterations/, transcripts/
```

All LLM traffic — target and refiner — goes through `litellm`, reusing `planner.py`'s existing
conventions. `plan_query` gains an injected-context parameter; default behaviour unchanged.

## Risks / Trade-offs

- **Cost.** 34 × 5 samples ≈ an hour locally. `k=3` before abandoning multi-sampling.
- **Refiner credentials absent.** `--no-auto-refine` (report and stop) is fully runnable today; the
  closed loop needs `EXON_REFINER_MODEL`'s key.
- **Determinism may cap achievable reliability.** If the probe reports < 1.0 determinism at
  temperature 0, no amount of context tuning fixes it — report it rather than chasing it.
- **A clean seed run means the harness is broken,** not that the planner is fixed. The known
  dropped-filter failure must reproduce before any score is trusted.

## Testing the harness

The harness is the measuring instrument; if it is wrong, every number is noise.

- **Fake target** at the litellm layer returning scripted responses — deterministic end-to-end loop
  tests with zero model calls.
- **Grader golden set**: hand-written (candidate, expected, verdict) triples covering every failure
  code, including ≥10 formatting-divergent but semantically identical pairs that **must** pass.
- **Holdout isolation test**: no holdout case text appears anywhere in a serialized refiner bundle.
- **Render determinism**: same artifact → byte-identical prompt.

## Open Questions

- `reliability_threshold` default 0.8 — confirm against the first real baseline.
- Whether to add a `sweep` command comparing several Ollama tags (cheap: same loop, run N times;
  `llama2:7b` advertises no tool support, so the probe would route it to a delimited protocol).
