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
# provider's own API key env var (litellm infers which one from the model prefix):
export EXON_MODEL=anthropic/claude-opus-5-20251101   # default if unset
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
- **Not yet tried**: a real cloud-model run (Anthropic/OpenAI/Gemini) — no credentials were
  available in this environment for any of them. Given the local model's mixed results, a
  stronger model is the most likely next lever, not further prompt tuning against a 12B local
  model. The two bugs above are real fixes that benefit every provider equally; the
  faithfulness gap is a model-capability question this session couldn't resolve either way.

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
```

Defaults to report-and-stop; `--auto-refine` needs `EXON_REFINER_MODEL` and its credential.

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

### Test suite

Four files, 60 checks, no model calls required:

- `tests/test_grading.py` — the golden set, anchored on the two REAL captured plans (the faithful
  one, and the `filters: []` one that silently dropped every constraint).
- `tests/test_harness_invariants.py` — render determinism, patch apply-then-invert, append-only
  versioning, fingerprint binding, placeholder/size guards, memorization lint, holdout isolation.
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
Observed directly: `ollama_chat/gemma4:12b` producing a structurally-valid plan that silently
dropped a stated filter and an entire requested lookup step. A stronger model may not have this
problem as often, but nothing here catches it either way yet — worth flagging to a human
reviewer (e.g., always print the plan for user approval before executing) rather than assuming
"validated" means "correct."
