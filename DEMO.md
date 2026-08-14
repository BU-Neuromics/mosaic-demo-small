# Exon — status and runnable demo

> **Run every command in this file from the repository root** (`mosaic-demo-small/`), which is
> where this file lives. Paths like `evals/schema/capabilities.json` are relative to it.

Last verified: 2026-08-14, against `../hippo@502991c` and `ollama_chat/gemma4:12b`.

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
- **66 automated checks** across 4 files, all passing, requiring **no model calls** and finishing
  in about 9 seconds.
- The context-tuning harness: probe → suite → runner → grader → triage → refiner → loop → CLI.

**What does not work yet — stated plainly**

No local 7–12B model reaches a usable pass rate on the harder half of the suite. Multi-constraint
and traversal questions currently drop a stated constraint or pick the wrong entity. Two specific
fixes are queued for that (below); neither is a mystery.

**Progress:** 36/40 tasks on the `add-exon-context-harness` OpenSpec change (validates `--strict`).
Remaining: re-run the truncation-withholding check; the closed refinement loop (blocked — needs a
refiner API credential); before/after reliability numbers (needs the former); and re-baselining
gemma4 now that reasoning mode is disabled automatically.

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

# Start the GraphQL server if it isn't already up (check: curl -s localhost:8080/graphql -X POST \
#   -H 'content-type: application/json' -d '{"query":"{__typename}"}')
mosaic serve --config mosaic.yaml --graphql --port 8080

export EXON_MODEL=ollama_chat/gemma4:12b
```

Requires `pip install -r exon/requirements.txt` (litellm) and Ollama running locally.

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

## 2. Ask a question in English — about 1 minute each

```bash
python3 -m exon "How many donors are in the case cohort?"
```

Prints the generated plan, then `=== Validated OK ===`, then the result. Expect **total: 104**.

```bash
python3 -m exon "Which samples did donor DNR-0068 contribute?"
python3 -m exon "How many samples are stored frozen?"
```

The flagship question — the one this project was built around. Expect it to be **less reliable**;
that honesty is part of the demo:

```bash
python3 -m exon "Bring me back all of the brain tissue samples that we have for the hippocampus region, with the donor's cohort, sex, and RHI history, and also possibly any rnaSeq data associated with them"
```

---

## 3. Watch it refuse rather than guess

```bash
python3 -c "
from exon.schema import fetch_hippo_schema, load_capability_manifest
from exon.ops import FieldFilter, FilterStep, QueryPlan
from exon.validator import validate_plan, ValidationError
hs=fetch_hippo_schema('http://localhost:8080/graphql')
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

## 5. The harness measuring reliability — slow, and deliberately unflattering

```bash
python3 -m exon.harness run --samples 2 --split train
```

Per-case pass rates plus a classified failure breakdown. **This will show failures.** That is the
pass condition, not a defect: the spec states that a clean seed run would mean *the harness is
wrong, not the planner*. Budget 20–40 minutes.

```bash
python3 -m exon.harness probe        # capability fingerprint, ~10 min; prints the isolated-vs-loaded table
python3 -m exon.harness loop --help  # the closed cycle (needs EXON_REFINER_MODEL + credential)
```

---

## What to expect, so nothing surprises you

- **Simple filter questions work.** Multi-constraint and traversal questions are where it drops a
  stated constraint or picks the wrong entity.
- **Every run takes minutes** on a local 12B model. The 9-second test suite is the demo that
  respects an audience's time.
- **If asked "is it reliable?"** — the accurate answer is: *not yet on a 7–12B local model, and we
  can now say exactly why and where. On a frontier model it is one environment variable to find
  out.*

### The two next changes, already named by the measurements

1. A `CONSTRAINT` block requiring every constraint stated in the question to appear as a filter —
   addresses q09/q35 silently dropping `sample_type='tissue'`.
2. Clearer reverse-lookup presentation — q21 queried `Donor` when asked which *samples* a donor
   contributed.

Both are one-block context changes, applied and measured one at a time so a score movement stays
attributable. Set `EXON_THINK=1` to re-enable reasoning mode and see the 19× difference directly.
