# Exon

A schema-grounded NL query-composition assistant for this repo's Mosaic instance. See
`openspec/changes/add-exon-query-planner/` (proposal.md, design.md) for the full design and
rationale — this file documents what's actually built and what running it produced.

## Upstream status (2026-08-05)

- **mosaic#149 — FIXED** (`7669fac`/PR#150). Filter `field` now accepts both the LinkML slot
  name and its camelCase spelling, and an unrecognized name raises `UNKNOWN_FILTER_FIELD`
  instead of silently matching zero rows. Two new loud errors were added for fields that exist
  but can't be filtered: multivalued references (use `relatedTo`) and computed provenance
  fields (use `asOf`). The historical notes further down describe the pre-fix behaviour and are
  kept because they explain why this codebase resolves names rather than guessing them.
- **mosaic#148 — OPEN.** `relatedTo` still carries no predicate on the referenced entity, so
  narrowing by e.g. `workflow_type` remains a bounded client-side filter, one call per
  already-identified id.

## What this is

Exon takes one natural-language instruction and returns a validated result from this repo's
live GraphQL endpoint. It does **not** generate free-text GraphQL: an LLM planner emits a typed
`QueryPlan` (see `ops.py`), which a validator (`validator.py`) checks against the live schema
and capability manifest *before* anything executes, and only then does the executor
(`executor.py`) run it.

```
instruction --[planner.py, LLM]--> QueryPlan --[validator.py]--> validated plan
                                                                        |
                                                          [executor.py] v
                                                                    live result
```

## Modules

- `schema.py` — fetches `hippoSchema` (the source of field names and of the kind/multivalued
  metadata the validator needs) and loads the capability manifest.
- `ops.py` — the typed op catalog: `FilterStep` (a root list query, optionally with a forward
  single-valued-relation nested selection), `RelatedLookupStep` (a bounded reverse
  relationship-existence lookup via `relatedTo`, scoped to ids from an earlier step).
- `validator.py` — rejects, never approximates: unknown entities/fields, unsupported filter
  ops (mosaic#96), fields that exist but cannot be filtered on (multivalued references → use
  `relatedTo`; computed provenance fields → use `asOf`), and `related_lookup` steps not scoped
  to an earlier step's ids. Field names resolve through `hippoSchema` in either the slot-name
  or camelCase spelling, both accepted upstream since mosaic#149/PR#150.
- `executor.py` — runs a validated plan against the live GraphQL endpoint, paginating until
  every matching record is retrieved. Converts slot names to camelCase for output *selection*
  (which requires it); filter `field` values need no conversion since both spellings are
  accepted. (This distinction bit the executor itself once during development; see "What
  actually happened" below.)
- `planner.py` — the LLM planner. Calls the model via `litellm` (provider-agnostic — see
  below), forcing structured output (`tool_choice`) so the model can only emit the typed op
  shapes above, never prose or raw GraphQL.
- `cli.py` / `__main__.py` — `python -m exon "<instruction>"` runs the full pipeline.

## Running it

```bash
pip install -r exon/requirements.txt
mosaic serve --config mosaic.yaml --graphql --port 8080   # if not already running

# Pick a provider by setting EXON_MODEL to a litellm model string, then set that
# provider's own credential (litellm infers which one from the model prefix):
export EXON_MODEL=bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0   # default if unset
# credential: an AWS Bedrock bearer token (AWS_BEARER_TOKEN_BEDROCK) or standard AWS credentials
#   -- or --
export EXON_MODEL=anthropic/claude-opus-5-20251101
export ANTHROPIC_API_KEY=...
#   -- or --
export EXON_MODEL=openai/gpt-4o
export OPENAI_API_KEY=...
#   -- or --
export EXON_MODEL=gemini/gemini-1.5-pro
export GEMINI_API_KEY=...
#   -- or any other litellm-supported provider (azure/..., ollama/..., etc.)

python -m exon "Hi Exon, bring me back all of the brain tissue samples that we have for the hippocampus region, with the donor's cohort, sex, and RHI history, and also possibly any rnaSeq data associated with them"
```

The provider is a deployment-time choice (`EXON_MODEL` + that provider's credential), never a
code change — `planner.py` has no vendor-specific branching.

## What actually happened

**Update: the planner has now been run for real, end-to-end, against a local Ollama model
(`ollama_chat/gemma4:12b`, no cloud API key available in this environment).** This is the
single most informative result in this build — it exercised the whole pipeline against a real
model for the first time, and the outcome is genuinely mixed, not a clean win:

- **A real, previously-undiscovered bug, found immediately**: Ollama's default context window
  (`num_ctx`) is 4096 tokens *total* (prompt + completion), independent of `max_tokens`. This
  "thinking"-capable model spends a large, variable number of tokens reasoning before ever
  emitting the tool call, and the default window wasn't remotely enough — it truncated with
  `finish_reason="length"` and empty content, silently (no error) until the token-usage numbers
  were inspected directly. Fixed: `planner.py` now passes `num_ctx` explicitly for `ollama*`
  models (`EXON_OLLAMA_NUM_CTX`, default 32768) — irrelevant/unset for other providers.
- **A second real bug, found from reading two of the model's actual plans**: the capability
  manifest's human-authored descriptive keys (e.g. `workflows_via_input_samples`) were being
  fed to the model as part of its grounding context, and the model — reasonably — used that
  descriptive key *as if it were the literal `relationship_type` value* to pass to
  `related_lookup`. The real value is `input_samples` (the actual relationships-table slot
  name); the manifest's key is documentation, not an API parameter. This wouldn't error, it
  would silently match nothing (`relatedTo` finds zero edges for a relationship type that was
  never written). Fixed: the grounding context now derives valid `relationship_type` values
  directly from `hippoSchema`'s field metadata (any `reference` + `multivalued` field), never
  from the manifest's prose, and is roughly half the length as a result.
- **Reliability with this specific local model is genuinely low, even after both fixes.**
  Across repeated full end-to-end runs with identical grounding and instruction: sometimes the
  model doesn't invoke the forced tool call at all (emits the same JSON as markdown-fenced
  prose instead — added a bounded retry, `EXON_MAX_ATTEMPTS`, for this specific sampling
  variance, without ever falling back to parsing that prose); when it *does* call the tool, one
  run produced a plan with `filters: []` — silently dropping the "hippocampus" constraint and
  the RNA-seq lookup entirely, structurally valid (validator correctly accepted it, since an
  empty filter list isn't itself invalid) but not a correct answer to the actual instruction.
  **This is a faithfulness problem the validator cannot catch by design** — the validator's job
  is "is this plan executable and safe against the live schema/capabilities," not "does this
  plan correctly represent the NL instruction"; those are different problems, and only the
  first one is in scope for what was built here.
- **Then tried for real (2026-08-18)**, once a Bedrock credential became available: default
  switched to `bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0`. The stronger model
  resolved the reliability half of the mixed result above — forced-tool-call compliance is no
  longer the problem, and the driving example's plan was structurally faithful (every filter
  present, `forward_relation` and `related_lookup` both correctly shaped, no dropped steps). But
  it returned **0 results instead of 26**: the model filled `sample_type` with `"brain tissue"`
  (paraphrasing the instruction) instead of the real data value `"tissue"` (verified live:
  `sample_type="tissue"` -> 26 matches with the hippocampus filter; `sample_type="brain tissue"`
  -> 0). Structurally valid, validator correctly accepted it, silently wrong — the same failure
  *class* as gemma4's dropped filter, but a different mechanism: a value guessed from NL wording
  rather than grounded in the schema's actual vocabulary, and the harness's full suite run found
  the identical pattern on other cases (q02: `'at-risk'`/`'at_risk'`; q08: `'chemically
  fixed'`/`'fixed'` — see `add-exon-context-harness`'s baseline). Two further real bugs were found
  and fixed in the same session: the validator let a reference field (e.g. `donor`) appear
  directly in `select_fields` instead of through `forward_relation`, which passed validation and
  then crashed the executor with a GraphQL syntax error (fixed — see the validator section
  above); and `DecodeParams` sent `seed` unconditionally, which Bedrock's Claude rejects outright
  (fixed in `exon/context/template.py`, via litellm's own `get_supported_openai_params` rather
  than a hardcoded provider list).

**Earlier in the build, before any of the above, the planner's LLM call could not be exercised
at all** — no provider credentials were available yet. The planner fails loudly and clearly on
an auth/provider error (`RuntimeError`, not a silent fallback) rather than faking a result — see
"Provider-agnostic via litellm" below for how that path was verified without real credentials.

**The validator and executor — the safety-critical half of the pipeline — were fully proven
against live data**, using a hand-built `QueryPlan` standing in for what the LLM planner should
produce for this project's own driving example:

- Validator: confirmed it rejects a camelCase filter field (`sampleType` instead of
  `sample_type`), an unsupported filter op (`GT`), and an unscoped `related_lookup` (no
  `source_step`) — each with a specific, actionable reason. Confirmed it accepts a correctly-
  shaped plan.
- Executor, running the actual driving example (hippocampus tissue samples, donor cohort/sex/
  RHI history, plus any `rna_seq`-referencing workflow) against the live server: **26 matching
  samples**, each with donor attributes correctly resolved, and **9 of those 26** had at least
  one `rna_seq`-typed referencing workflow found via 26 bounded `relatedTo` calls (one per
  sample, per the "never an unfiltered scan" rule) — consistent in proportion with the
  full-tissue-request-set figure already verified in `evals/expected-results.json` (45/115
  across all four brain regions).

**Real bugs were found and fixed during this same build, not before it** — a second, independent
review pass caught three more after the driving example first "worked":

- The executor initially applied snake_case field names to GraphQL *output selection* (which
  needs camelCase), conflating it with the filter vocabulary (which needs snake_case) — the
  exact mosaic#149 distinction this whole project is about, made by the code meant to guard
  against it. Query errors (`Cannot query field 'brain_region' on type 'Sample'. Did you mean
  'brainRegion'?`) caught it immediately; fixed with a dedicated `_to_camel` conversion used
  only for output selection, never for filter values.
- `_execute_filter_step` returned whatever one page gave it without comparing `items` to
  `total` — so a result larger than `FilterStep.limit` (default 100; the full tissue-request
  set is 115) would have silently truncated, and everything downstream (the bounded
  `relatedTo` calls) would silently run on an incomplete set. The driving example's first run
  only "passed" because `limit=200` was hand-set, papering over the bug. Fixed: the executor
  now paginates until `len(items) == total`, verified by re-running with the default `limit=100`
  against the full 115-sample set and confirming all 115 (and the correct 45 rna_seq matches)
  come back.
- `_accessor_for` guessed the GraphQL root query name (`Sample` → `samples`) instead of reading
  `accessor_name` from the already-fetched `hippoSchema` — the same "guess instead of read"
  mistake mosaic#149 is about, in the module meant to prevent exactly that. Fixed: the accessor
  name now comes from `hippo_schema`, passed into `execute_plan` explicitly.
- The validator checked `filters[].field` and `forward_relation.field` against `hippoSchema` but
  not plain `select_fields` — a bogus output field would fail loudly at execution rather than
  at validation (not dangerous, but a hole in "validate before execute"). Closed: `select_fields`
  and `forward_relation.select_fields` are now checked too.

## The context-tuning harness (`exon/harness/`)

Exon's reliability is now a measured number rather than an anecdote. The harness runs each
benchmark question `k` times against an editable context, grades the distribution, and (with
`--auto-refine`) tunes the context until the pass rate rises.

```bash
python -m exon.harness probe                    # fingerprint the target model
python -m exon.harness run --samples 3          # one pass; prints per-case pass rates
python -m exon.harness loop --auto-refine       # the full measure -> refine -> re-measure cycle
python -m exon.harness report --run <dir>
python -m exon.harness report --compare <a.json> <b.json> [--out FILE]   # compare 2+ finished
                                                                          # runs, zero new tokens
```

Defaults to report-and-stop; `--auto-refine` needs `EXON_REFINER_MODEL` and its credential.
Each target model gets its own fingerprint path (`evals/schema/fingerprint-<slug>.json`, derived
mechanically from the exact model string — no alias table, no manual copy-and-rename), so probing
model B never overwrites model A's measured capabilities. `report --compare` reads any two
already-written run reports (a `run` command's `<dir>/report.json`, or a specific `loop`
iteration's `iterations/iterNN.json`) and prints them side by side plus deltas — no model call,
zero cost. It warns explicitly if the two runs used different samples-per-case or case-split
sizes, and notes if they used different output protocols (a score delta is then model-*and*-
protocol jointly, not model alone, since each model's protocol comes from its own probe).

**What it measures.** Per-case pass rate over k samples, plus strict (k-of-k) count and flake
rate reported separately — the failures that motivated this were intermittent, and a
single-sample suite would have called them green about half the time. The gate is
`--threshold` (default **0.8**, not 1.0): perfection was never the goal, and a 1.0 gate against a
local model would simply never terminate.

**The tier that matters.** The validator answers "is this plan safe and executable". It cannot
answer "does this plan represent what was asked" — and the real failure passed the first while
failing the second. Tier 3 checks faithfulness: every stated constraint present, none silently
added. Comparison is on semantics, never spelling.

**What it will not do.** Environment failures (num_ctx truncation, provider errors) are reported
to you but withheld from the refiner, which would otherwise try to fix a config bug by rewording
prose. The holdout split is withheld too, enforced by `build_bundle` raising rather than by
convention. Candidate contexts are rejected if they drop a schema placeholder, exceed the size
cap, name a test case, or quote a question verbatim — a context that encodes answers raises the
score without improving anything.

### Findings from the first real run against `ollama_chat/gemma4:12b`

**The capability probe contradicted itself, and that was the most useful result.** In isolation
every output protocol passed 5/5, determinism read 100%, preamble tendency 0%. Under a
realistically sized request:

| protocol | isolated | under load |
|---|---|---|
| `json_schema` | 5/5 | 0/3 |
| `tool_call` | 5/5 | 0/3 |
| `json_object` | 5/5 | 0/3 |

An isolated-only probe — which is what both this project's original spec and the `ctxtune` spec
called for — would have told the loop "protocol is fine, this must be a prose problem" and sent
the refiner to reword instructions that were never the cause. The under-load check exists because
of this result.

**Is the unreliability a budget problem or a model problem? Partly measured, partly not.** One
clean sample at `max_tokens=8192` finished normally (`finish=stop`) after only 3632 completion
tokens and still returned markdown-fenced JSON instead of the forced tool call. So budget is not
the sole cause: this model does ignore forced `tool_choice` under load. A separate sample
truncated at the 8192 ceiling, which *is* budget-shaped — and whether a larger budget fixes that
half is **still unmeasured**, because the `max_tokens=16384` arm was entirely invalidated by
litellm request timeouts before `EXON_REQUEST_TIMEOUT` was raised.

**Load is the variable, not the protocol.** The heavy driving question fails every structured
protocol, while a light question (`q01`) produced a parseable plan through `json_schema`. That
points at shrinking the grounding as a real lever, which is exactly the kind of change the loop
can make and measure.

### Findings from the first full-suite run against `bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0` (2026-08-18)

The target model default moved off local Ollama entirely once a Bedrock credential became
available. First full run (29 cases x 3 samples, seed context v000):
**train=0.33, holdout=0.50, strict=7/21, 0 flaky, 186600 tokens** — a real, non-trivial failure
signal (17/29 cases fail), across three distinct failure classes:

- `PLAN_UNFAITHFUL` on 12 cases, mostly a value-vocabulary gap: the model fills a filter with a
  value paraphrased from the NL instruction (`'at-risk'`, `'chemically fixed'`, `'brain tissue'`)
  instead of the schema's real enum value (`'at_risk'`, `'fixed'`, `'tissue'`). The schema
  grounding lists field *names*, never the actual values a field takes — this project's `q35`
  driving-example case fails exactly this way.
- `PLAN_INVALID` on 3 cases — the reference-field-in-`select_fields` validator gap (see above),
  caught pre-execution now rather than crashing the executor.
- `MISSING_REJECTION` on all 3 capability-gap questions (q32/q33/q34) — the model accepts a plan
  for a question mosaic#96/#148 make genuinely unanswerable, where refusing is the correct
  behavior.

Running the closed loop (`--auto-refine --max-iter 4`) against this baseline for the first time
ever end-to-end (previously blocked on a refiner credential — `EXON_REFINER_MODEL` now defaults
to the same reachable Bedrock model): train rose on 2 of 3 patch attempts (0.33 -> 0.43, strict
7 -> 9), but **holdout stayed flat at 0.50 on every iteration**, and the loop correctly rolled
back each time rather than keep a context that only helped train. It stopped on plateau after 3
non-improving iterations, exactly as designed — **baseline holdout 0.50 -> best 0.50 (+0.00)**.
Honest reading: block/prose tuning alone, in 4 iterations, did not move the metric that matters
against this model. The three failure classes above look like they need a different kind of fix
(actual data-vocabulary grounding for the first; the validator fix already applied for the
second; an explicit refusal exemplar for the third) rather than more of the same prose patches.
Full numbers: `evals/baselines/2026-08-18-bedrock-haiku-4-5-seed-v000.json` and
`evals/baselines/2026-08-18-bedrock-haiku-4-5-loop-report.md`.

### Haiku vs Sonnet 5 (2026-08-18) — the harness's first real cross-model comparison

Same suite, same sampling (3/case), same protocol (`tool_call` qualified for both), run against
`bedrock/global.anthropic.claude-sonnet-5` and compared with `report --compare` against the
existing Haiku baseline above — no re-run of Haiku needed, since nothing it depends on had
changed:

```
[0] bedrock/...claude-haiku-4-5...   train=0.33  holdout=0.50  strict_train=7/21
[1] bedrock/...claude-sonnet-5       train=0.38  holdout=0.50  strict_train=8/21
    Δtrain=+0.05  Δholdout=+0.00  Δstrict_train=+1
```

Full output: `evals/baselines/2026-08-18-compare-haiku-vs-sonnet-5.md`.

**A real, load-bearing bug was found and fixed before this comparison meant anything.** The
first probe of Sonnet 5 came back 0/5 on *every single check* — system role, all five protocols,
preamble. A uniform-zero pattern across unrelated checks is this project's own signal that the
defect is environmental, not behavioral (the same rule that caught the entity/accessor
ambiguity earlier). Root cause: `litellm.UnsupportedParamsError: ... does not support
temperature=0. Only temperature=1 is supported.` — every probe check and the seeded
`DecodeParams` unconditionally assumed `temperature=0`, so 100% of calls failed before any
capability was actually measured. This is not the same as Ollama's `thinking`-forces-temperature
pattern (explicitly tested: passing `thinking={"type":"disabled"}` still rejected
`temperature=0`) — it's a hard, unconditional provider/model constraint. Fixed the same way the
`seed` param bug was fixed during the Haiku work: measure, don't assume. `probe.py` now detects
the model's actual working temperature with one cheap call and threads it through every
subsequent check and into the seeded decode params, rather than hardcoding 0 or special-casing
one model string.

**With that fixed, the findings are real:**

- Isolated ladder: `system_role=5/5`, `tool_call` qualifies (5/5 isolated, 3/3 under load),
  `json_schema=0/5`, `stop_sequences=3/5`.
- **`determinism @ temp 1 = 40%`** — a real, expected reliability ceiling from being forced off
  temperature 0, not a measurement bug. No amount of context tuning raises this; it's a hard cap
  on this model/provider combination as configured.
- Baseline (seed context v000): **train=0.38, holdout=0.50, strict_train=8/21** — matches Haiku's
  holdout exactly, edges it slightly on train/strict.
- Sonnet 5 correctly handles `q21` (100% — "which samples did this donor contribute," where both
  gemma4 and Haiku queried `Donor` instead of `Sample`), but shares Haiku's *exact*
  `select_fields` reference-field mistake on `q09`/`q17`/`q18`/`q23`/`q24`/`q35` — put a reference
  field (e.g. `donor`) directly in `select_fields` instead of through `forward_relation`. Two
  unrelated models sharing one specific failure mode is, again by this project's own rule, a sign
  the grounding doesn't make the distinction clear enough — not a coincidence.
- **The refine loop moved a real number this time**: iteration 1's patch (a constraint requiring
  every stated constraint to appear as a filter) raised holdout from 0.50 to **0.67** — the first
  time in this project a refine iteration has improved holdout at all (Haiku's loop stayed flat
  at +0.00). Iteration 2 then hit the exact temperature constraint above from the *other*
  direction: the refiner, free to tune decode params, set `temperature=0.7`, which this model
  also rejects. Every one of that iteration's 87 samples failed with the same
  `UnsupportedParamsError`, correctly classified `PROVIDER_ERROR` (environment, withheld from
  the refiner's own bundle), correctly rolled back to iteration 1's context, and the loop
  correctly stopped ("only environment/config failures remain") instead of erroring out or
  spinning. **Final: baseline holdout 0.50 -> best 0.67 (+0.17) at v001.** Full numbers:
  `evals/baselines/2026-08-18-bedrock-sonnet-5-seed-v000.json` and
  `evals/baselines/2026-08-18-bedrock-sonnet-5-loop-report.md`.

### Test suite

Four files, 77 checks, no model calls required:

- `tests/test_grading.py` — the golden set, anchored on the two REAL captured plans (the faithful
  one, and the `filters: []` one that silently dropped every constraint).
- `tests/test_harness_invariants.py` — render determinism, patch apply-then-invert, append-only
  versioning, fingerprint binding, placeholder/size guards, memorization lint, holdout isolation,
  plus (added for cross-model comparison) fingerprint-path collision-freedom and `report
  --compare`'s mismatch/protocol warnings.
- `tests/test_independence.py` — asserts on the prompts actually assembled at the litellm
  boundary: no case ids, no expectations, no expected results, no conversation history.
- `tests/test_runner_fake.py` — a fake litellm target for deterministic end-to-end runs.

## Known limitations (by design, not oversight)

- One instruction in, one result out — no multi-turn conversation, no session state.
- No rendering — the executor returns raw records, not a chart or table component.
- No aggregation (group-by/count/sort/range) — the validator rejects plans needing it
  (mosaic#96, open).
- `related_lookup` steps can only narrow by a client-side filter over each call's own small
  result — no server-side predicate on `relatedTo` exists yet (mosaic#148, filed).

## Known limitation (not by design — an open reliability gap)

Plan *faithfulness* to the NL instruction is not guaranteed, and isn't checked by anything in
this pipeline. The validator only checks that a plan is executable and safe against the live
schema/capabilities; it has no way to check "does this plan actually answer what was asked."
Observed directly with `ollama_chat/gemma4:12b`: a structurally-valid plan that silently dropped
a stated filter and an entire requested lookup step. A stronger model — `bedrock/global.
anthropic.claude-haiku-4-5-20251001-v1:0`, tried once a Bedrock credential became available —
does not have *that* problem (no dropped steps, correct op shapes), but the gap did not close:
it now produces a structurally-valid plan with the right filter *field* but the wrong *value*
(`sample_type="brain tissue"` instead of `"tissue"`), guessed from the instruction's phrasing
rather than the schema's real vocabulary — silently zero results instead of 26. Confirmed not a
one-off: the harness's full-suite run against the same model found the identical value-guessing
pattern on multiple other cases. Nothing here catches either shape of this yet — worth flagging
to a human reviewer (e.g., always print the plan for user approval before executing) rather than
assuming "validated" means "correct," and worth pursuing as the concrete next lever: grounding
the model in each filterable field's *actual* value vocabulary, not just its name.
