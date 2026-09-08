# Exon — status and runnable demo

> **Run every command in this file from the repository root** (`mosaic-demo-small/`), which is
> where this file lives. Paths like `evals/schema/capabilities.json` are relative to it.

Last verified: 2026-08-18, against `../mosaic@502991c` (then named `../hippo`), the default `bedrock/global.anthropic.
claude-haiku-4-5-20251001-v1:0`, and (for comparison) `bedrock/global.anthropic.claude-sonnet-5`
(the default moved off local Ollama this session, once a Bedrock credential became available —
see "What does not work yet" below for what changed and what didn't).

---

## Status

**What Exon is.** Ask a question in plain English, get real data back. The model never writes
GraphQL: it emits a typed `QueryPlan`, a validator checks every field and capability against the
*live* schema before anything runs, and only then does the executor compile and run it.
Unsupported requests are refused with a reason rather than approximated.

**What works today**

- The full pipeline, end to end, on straightforward questions. Verified:
  `python3 -m exon "How many donors are in the case cohort?"` → **104**, matching the
  independently verified benchmark answer.
- The query layer against real data: 26 hippocampus tissue samples (9 with an RNA-seq workflow);
  the 115-sample tissue-request set (45 with RNA-seq); q24's donor chain resolving 3 samples → 9
  workflows → 6 datasets with reproducible ids.
- **77 automated checks** across 4 files, all passing, requiring **no model calls** and finishing
  in about 9 seconds.
- The context-tuning harness: probe → suite → runner → grader → triage → refiner → loop → CLI,
  plus (new) `report --compare` to line up two models' finished runs side by side at zero token
  cost, and a fingerprint path keyed per exact model string so probing one model never clobbers
  another's measured capabilities.

**What does not work yet — stated plainly**

Switching off local Ollama and onto a real hosted model (Bedrock Claude Haiku 4.5) fixed the
reliability half of the problem — no more dropped filters, no more ignored tool calls — but not
the faithfulness half. First full-suite baseline against the new default: **train=0.33,
holdout=0.50, strict=7/21**, across three distinct failure shapes (value-vocabulary guessing,
wrong entity on a reverse lookup, missing rejection on capability-gap questions). The closed
refinement loop (4 iterations) raised train (0.33 → 0.43) but **holdout stayed flat at
+0.00** — prose/block tuning alone didn't move the metric that matters.

Compared against a second model, `bedrock/global.anthropic.claude-sonnet-5`: same-sampling
baseline **train=0.38, holdout=0.50, strict=8/21**, and this time the refine loop *did* move
holdout — **0.50 → 0.67 (+0.17)** — before correctly hitting and rolling back from an unrelated
provider constraint (this model rejects `temperature=0`, caught the same way the harness catches
everything: measure, don't assume).

Full narrative (exact example values, the temperature-detection fix, the shared `select_fields`
bug across both models, per-model failure breakdowns) lives in `exon/README.md`'s "Findings from
the first full-suite run" and "Haiku vs Sonnet 5" sections — this file stays the short version.
Full comparison numbers: `evals/baselines/2026-08-18-compare-haiku-vs-sonnet-5.md` (see §5 below
for the command that produced it).

**Progress:** both `add-exon-context-harness` and `add-exon-harness-model-comparison` OpenSpec
changes are complete and archived, the latter with one deviation stated on its own terms: the
original truncation-withholding check (8.2, `add-exon-context-harness`) doesn't reproduce
anymore, because the auto-disable-reasoning fix (below) removed the condition that caused it.

### What the harness found in its first afternoon

Each of these came from a classified failure report, not from guessing at prompt wording.

| Finding | Evidence |
|---|---|
| Reasoning mode was the bug, not the prompt | 2631 completion tokens with **no** tool call → **135 tokens with one**. 19×, one parameter. |
| A grounding ambiguity was **our** bug | Two unrelated models — different vendors, different protocols — produced character-identical `unknown entity 'samples'` errors. When that happens the defect is ours. |
| Models disagree on output protocol | qwen2.5-coder: `tool_call` **0/5**, `json_schema` 5/5. The planner had *hardcoded* `tool_call`; unprobed, qwen would have failed 100% and looked useless. |
| Toy capability tests lie | Every protocol passed **5/5 in isolation** and **0/3 under real load** — three independent times. |

The last one is the transferable methodological point: **capability measured on a trivial prompt
does not predict capability under real load.** Both this project's original spec and the
alternative `ctxtune` spec called only for the trivial check.

Two bugs in our *own* diagnostics were also caught by data: the truncation message first named the
wrong ceiling (`num_ctx` when `max_tokens` bound), then gave advice that would have wasted time
(raise the budget — when doubling it merely doubled consumption, i.e. runaway generation).

---

## Prerequisites

```bash
cd ~/Documents/schemas/mosaic-demo-small          # all commands run from here

# Start the server if it isn't already up. --mcp is REQUIRED: `python -m exon` now reaches
# Mosaic's MCP boundary for capability grounding, validation, and execution.
# Check BOTH are up, not just GraphQL:
#   curl -s localhost:8080/graphql -X POST -H 'content-type: application/json' \
#     -d '{"query":"{__typename}"}'                     # -> {"data":{"__typename":"Query"}}
#   curl -s -o /dev/null -w '%{http_code}\n' localhost:8080/mcp   # -> 307 (404 means no --mcp)
mosaic serve --config mosaic.yaml --graphql --mcp --port 8080

export EXON_MODEL=bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0   # default if unset
```

Requires `pip install -r exon/requirements.txt` (litellm) and a Bedrock credential (an
`AWS_BEARER_TOKEN_BEDROCK` bearer token, or standard AWS credentials via `aws configure`/env
vars) — or set `EXON_MODEL`/`EXON_REFINER_MODEL` to any other `litellm`-supported provider
(`anthropic/...`, `openai/...`, `ollama_chat/...` with Ollama running locally, etc.) with that
provider's own credential.

---

## 1. The core demo — 9 seconds, no model, deterministic

Start here. It cannot fail on stage and it shows the whole thesis.

```bash
python3 tests/test_grading.py
```

23 checks. The two that matter are anchored on **real plans captured from the model**:

```
PASS  faithful driving-example plan passes
PASS  dropped-filter plan is PLAN_UNFAITHFUL
```

That second line is the point of the project. The plan was *structurally valid* — the validator
accepted it — and it had silently dropped every constraint the question stated. A schema
validator cannot catch that, because "is this safe to run" and "does this answer the question"
are different questions. Tier 3 of the grader catches it.

```bash
python3 tests/test_harness_invariants.py   # 28 checks: holdout isolation, patch algebra, memorization lint
python3 tests/test_independence.py         #  9 checks: no answer-key leakage into the model's prompt
python3 tests/test_runner_fake.py          #  6 checks: full loop with a fake model, zero real calls
```

---

## 2. Ask a question in English — a few seconds each against the default hosted model

```bash
python3 -m exon "How many donors are in the case cohort?"
```

Prints the generated plan, then `=== Validated OK ===`, then the result. Expect **total: 104**.

```bash
python3 -m exon "Which samples did donor DNR-0068 contribute?"
python3 -m exon "How many samples are stored frozen?"
```

The flagship question — the one this project was built around. Expect it to run to completion
with a structurally faithful plan (every filter, the donor lookup, and the RNA-seq check all
present) but to return **`total: 0`, not 26** — the model currently fills `sample_type` with
`"brain tissue"` (paraphrased from the question) instead of the schema's real value `"tissue"`.
That silent-wrong-answer, not a crash or a dropped step, is exactly the failure mode this project
exists to catch and surface, and it's the concrete next thing to fix (see the harness findings):

```bash
python3 -m exon "Bring me back all of the brain tissue samples that we have for the hippocampus region, with the donor's cohort, sex, and RHI history, and also possibly any rnaSeq data associated with them"
```

---

## 3. Watch it refuse rather than guess

```bash
python3 -c "
from exon.schema import fetch_mosaic_schema, load_capability_manifest
from exon.ops import FieldFilter, FilterStep, QueryPlan
from exon.validator import validate_plan, ValidationError
hs=fetch_mosaic_schema('http://localhost:8080/graphql')
m=load_capability_manifest('evals/schema/capabilities.json')
for label, plan in [
  ('range filter (mosaic#96, open)', QueryPlan('x',[FilterStep(entity='Donor', filters=[FieldFilter('age_at_death',65,'GT')])])),
  ('filter a relationship-table slot', QueryPlan('x',[FilterStep(entity='Workflow', filters=[FieldFilter('input_samples','SMPL-0001')])])),
  ('filter a computed provenance field', QueryPlan('x',[FilterStep(entity='Sample', filters=[FieldFilter('created_at','2024-01-01')])])),
  ('a camelCase field name (valid since mosaic#149)', QueryPlan('x',[FilterStep(entity='Sample', filters=[FieldFilter('sampleType','tissue')])])),
]:
    try: validate_plan(plan, hs, m); print('ACCEPTED:', label)
    except ValidationError as e: print('REFUSED :', label, '->', str(e)[:95])
"
```

Three refusals with actionable reasons, one acceptance. It declines rather than returning a
confident wrong answer — and it does **not** over-refuse a spelling that is genuinely valid.

---

## 4. The verified data results — instant, no model

```bash
# 104 donors in the case cohort (benchmark q01)
curl -s localhost:8080/graphql -H 'content-type: application/json' \
  -d '{"query":"{ donors(filters:[{field:\"cohort\",value:\"case\"}]){ total } }"}'

# 50 donors with a documented history of repetitive head impacts (q05)
curl -s localhost:8080/graphql -H 'content-type: application/json' \
  -d '{"query":"{ donors(filters:[{field:\"history_of_rhi\",value:true}]){ total } }"}'

# 115 tissue samples across the four brain regions (the tissue-request set)
curl -s localhost:8080/graphql -H 'content-type: application/json' \
  -d '{"query":"{ samples(filters:[{field:\"sample_type\",value:\"tissue\"},{field:\"brain_region\",value:[\"hippocampus\",\"frontal_cortex\",\"cerebellum\",\"brainstem\"],op:IN}],filterMode:AND){ total } }"}'

# 26 hippocampus tissue samples, with donor attributes resolved in the same call
curl -s localhost:8080/graphql -H 'content-type: application/json' \
  -d '{"query":"{ samples(filters:[{field:\"sample_type\",value:\"tissue\"},{field:\"brain_region\",value:\"hippocampus\"}],filterMode:AND){ total items{ id brainRegion donor{ cohort sex historyOfRhi } } } }"}'

# the reverse lookup that was IMPOSSIBLE before mosaic#146 shipped
curl -s localhost:8080/graphql -H 'content-type: application/json' \
  -d '{"query":"{ relatedTo(id:\"SMPL-0032\", relationshipType:\"input_samples\"){ entityId entityType data } }"}'
```

Both field-name spellings now work (mosaic#149, fixed upstream) — an unknown name raises
`UNKNOWN_FILTER_FIELD` instead of silently returning zero rows:

```bash
curl -s localhost:8080/graphql -H 'content-type: application/json' \
  -d '{"query":"{ samples(filters:[{field:\"sampleType\",value:\"tissue\"}]){ total } }"}'   # 278
curl -s localhost:8080/graphql -H 'content-type: application/json' \
  -d '{"query":"{ samples(filters:[{field:\"nonsense\",value:\"x\"}]){ total } }"}'          # loud error
```

---

## 5. The harness measuring reliability — deliberately unflattering, fast against the hosted default

```bash
python3 -m exon.harness run --samples 3
```

Per-case pass rates plus a classified failure breakdown. **This will show failures.** That is the
pass condition, not a defect: a clean seed run would mean *the harness is wrong, not the
planner*. Against the hosted default this is a few minutes for the full 29-case suite (it was
20–40 minutes per partial pass on a local 12B model; budget for that instead if you point
`EXON_MODEL`/`--model` at Ollama).

```bash
python3 -m exon.harness probe                                  # capability fingerprint, ~1 min against the hosted default
python3 -m exon.harness loop --auto-refine --max-iter 4         # the closed cycle -- EXON_REFINER_MODEL defaults to the same reachable model
```

Compare two models' already-finished runs, no new model calls, using the real saved baselines
from this session:

```bash
python3 -m exon.harness report --compare \
  evals/baselines/2026-08-18-bedrock-haiku-4-5-seed-v000.json \
  evals/baselines/2026-08-18-bedrock-sonnet-5-seed-v000.json
```

Prints both models' scores side by side plus the delta; warns explicitly if the two runs used
different sampling, and notes if they used different output protocols.

---

## 6. The conversational MVP — one command, then just type

This is the headline demo: build a query by **talking**, refine it across turns, go back and
change your mind, then see the records.

```bash
./run-chat-demo.sh
```

That starts everything and wires it together:

```
you (chat client)  ->  Mosaic :8080  ->  Exon :9100  ->  Mosaic re-validates
   stands in for            converse_query_spec        the turn-taking planner
   Aperture's UI            (the real MCP boundary)
```

The chat client deliberately talks **only to Mosaic**, never to Exon directly — so what you see
is the actual path Aperture will use, not a shortcut around it. It also holds the conversation
state, which is Aperture's job: Exon is stateless and gets the whole turn list on every call.

A demo that shows off everything worth showing, in about six lines of typing:

```
> show me tissue samples from the hippocampus
  exon (proposal): Filtering to tissue samples collected from the hippocampus.

> only from donors over 60
  exon (proposal): ...from the hippocampus, collected from donors over 60 years old.
                   (note the related criterion on donor.age_at_death — it traversed the edge)

> /run
  20 matching record(s)                      <- real rows from the live graph

> /edit 1 show me cerebellum samples instead
  exon (proposal): Filtering to samples from the cerebellum brain region.
                   turn 2 recomputes automatically against the new anchor

> /turns
  [2] exon (proposal): ...cerebellum..., where the donor is over 60 years old.

> /run
  58 matching record(s)                      <- the EDIT propagated; not the stale 20
```

Commands: `/run` execute, `/spec` show the QuerySpec, `/turns` list turns, `/edit N <text>`
rewind and redo turn N, `/help`, `/quit`.

**The two things to point at.** First, the model never writes GraphQL or SQL — every turn emits a
typed `QuerySpec` that **Mosaic validates before anything runs**, and Mosaic re-validates it again
on the way back even though Exon already grounded it. Second, `/edit` is the feature that is
easy to get wrong: turns after the edited one are *recomputed*, and any that no longer make sense
are marked **suspended** rather than silently dropped, for the user to re-word. That 20 -> 58 is
worth showing deliberately: it is the edit actually propagating.

Needs a model credential (same as §2 — `EXON_MODEL` plus that provider's key). Each turn is one
LLM call, so expect a couple of seconds per message. `Ctrl-C` or `/quit` stops both services.

If you would rather run the pieces by hand, in three terminals:

```bash
# 1
MOSAIC_EXON_URL=http://127.0.0.1:9100/turn \
  mosaic serve --config mosaic.yaml --graphql --mcp --port 8080
# 2
python3 -m exon.conversational_server
# 3
python3 -m exon.chat
```

`converse_query_spec` only appears on the MCP boundary when `MOSAIC_EXON_URL` is set — an
unconfigured deployment does not advertise a tool it cannot serve, so if the chat client reports
the tool missing, that env var on terminal 1 is why.

---

## What to expect, so nothing surprises you

- **Simple filter questions work, fast, against the hosted default.** Multi-constraint and
  traversal questions are where it currently guesses a filter *value* wrong, picks the wrong
  entity on a reverse lookup, or (rarely, 3/29 questions) accepts a plan it should refuse.
- **Every run against the hosted default finishes in seconds to low minutes**, not the 20–40
  minutes a local 12B model needed. The 9-second test suite is still the demo that respects an
  audience's time when you don't want to spend even that.
- **If asked "is it reliable?"** — the accurate answer is: *a real hosted model (Bedrock Claude
  Haiku 4.5) fixed the tool-call-compliance and dropped-filter problems the original local-model
  run had. It did not fix instruction-faithfulness: it now gets the right field but sometimes the
  wrong value, guessed from wording instead of the schema's real data. Measured, not assumed:
  train 0.33/holdout 0.50 on the full suite, and 4 iterations of context tuning alone didn't move
  holdout.*

### The next change, named by the measurements

Ground filter **values**, not just field names, in the live schema — the grounding context lists
field names today but never the values a field actually takes, so the model fills one in from the
question's own wording when it doesn't know better. A one-block context change (an enum-values
glossary derived from `hippoSchema`), applied and measured on its own so a score movement stays
attributable — exactly what 4 iterations of *other* prose changes didn't touch. Full detail
(exact example values, the two smaller already-diagnosed items, the gemma4-specific reasoning-mode
finding) lives in `exon/README.md`'s "Known limitation" and harness-findings sections.
