# Exon — the conversational layer, and how to run it

> Run every command from the repository root (`mosaic-demo-small/`).

**Updated: 2026-09-18.**

---

## What this is

This repo is the demo dataset and the **planning service** behind conversational query in the
platform. It is not an application you run by itself.

The product is the browser:

```
Aperture (the UI)  →  Mosaic (the runtime + MCP boundary)  →  Exon (this repo, the planner)
         all three packaged and shipped by DataHelix's Docker recipes
```

You type a question in Aperture. Exon turns it into a structured query. **Mosaic re-checks that
query before anything runs.** If the question needs something the platform can't do, you get a
clear refusal instead of wrong rows.

That last part is the point. A confident wrong answer is worse than a refusal.

---

## Where it stands today

**Working**

- **Docker is the normal path again.** The packaged container used to crash on this schema, so we
  ran a server by hand as a stopgap. That was fixed and released in Mosaic 0.13.0; the container
  was verified against this project on 2026-09-17 and serves all 3,600 records, UI included.
- **The chat panel works in a real browser.** Until today it had only ever been driven against a
  fake backend. It now runs against the real MCP-backed path end to end.
- **You can ask what the data holds, in your own words.** "What do we have on donors about head
  injuries?" now resolves to `history_of_rhi` — a field whose name shares no word with the
  question. The planner reads each field's description from the schema, so discovery is answered
  in the conversation and leads straight into the query, instead of being refused as "a reference
  lookup rather than a query refinement."
- **The benchmark is current.** 31 of 35 executable questions verified against live data, no
  regressions. Two previously marked impossible turned out to work once we tried them. Three
  further schema-discovery questions (q36–q38) assert on the planner's reply rather than on rows.

**Not working yet**

- **"Show me the donors of those samples."** Reversing a relationship — samples → donors rather
  than donors → samples — doesn't work. It fails *safely*: rejected before execution, so you never
  see wrong rows. Two changes are needed, one in Mosaic (pull request open) and one line in this
  repo's schema. We only discovered the second half by running it.
- **Answer faithfulness.** The planner sometimes invents a plausible value instead of the real one
  — "brain tissue" where the data says "tissue" — and returns zero rows rather than an error.
  Measured, not guessed: see "Reliability" below.

**Not yet exercised**

Multi-turn refinement, editing an earlier question, and cancel have not been driven through the
browser. The last two have no automated tests at all.

---

## Run the product

### The packaged stack — one command

This is what ships: Aperture, Mosaic and this project's data in a single container.

```bash
cd ../datahelix/deploy/recipes/solo
PROJECT_DIR=/abs/path/to/mosaic-demo-small make up     # -> http://localhost:8080
```

Open **http://localhost:8080** for the full UI. Verified working 2026-09-17.

**What the container does not have.** It runs the last *release*, and conversational query is
newer than that. So the chat panel is absent here — correctly, because the UI only shows features
the backend actually advertises. For chat you need the stack below until the next release.

### The conversational stack — until the next release

```
browser :5173  →  Mosaic :8099  →  Exon :8091
 Aperture UI       re-checks         plans
```

```bash
# 1. Mosaic from the ../mosaic checkout (unreleased code — not the container).
MOSAIC_EXON_URL=http://127.0.0.1:8091/turn \
  mosaic serve --config mosaic.yaml --graphql --mcp --port 8099

# 2. Exon, the planning service. Reads the schema from Mosaic's MCP endpoint once at
#    startup, so Mosaic must be up first.
EXON_TURN_PORT=8091 MOSAIC_MCP_URL=http://127.0.0.1:8099/mcp \
  python3 -m exon.conversational_server

# 3. Aperture.
cd ../aperture/web
VITE_HIPPO_GRAPHQL_URL=/graphql npm run dev -- --config vite.proxy.config.ts --port 5173
```

**Two silent failures, both of which cost us time:**

- Miss `MOSAIC_EXON_URL` and the chat feature is never registered. The panel just doesn't appear —
  no error anywhere.
- Miss `VITE_HIPPO_GRAPHQL_URL` and the page loads but shows "configure the endpoint" instead of
  the app.

Once a release carries conversational query, this collapses back into the single container above.

---

## What we verified in the browser, 2026-09-17

| | |
|---|---|
| Plain English → a real query | ✅ "tissue samples from the hippocampus" |
| Refuses rather than guessing | ✅ a counting question got an explanation, not a fake answer |
| Asks when the question is ambiguous | ✅ twice, unprompted |
| Rejects what it can't do safely | ✅ see below |

On the reverse-relationship question, the planner proposed something and Mosaic rejected it
**before anything ran**:

```
'Donor' has no relationship 'donor'. Known relationships: []. Nothing was applied.
```

"Nothing was applied" is the good outcome. The alternative — a query that runs and quietly returns
the wrong rows — is exactly what this design exists to prevent.

---

## The data, if you want to check answers by hand

```bash
# 104 donors in the case cohort
curl -s localhost:8080/graphql -H 'content-type: application/json' \
  -d '{"query":"{ donors(filters:[{field:\"cohort\",value:\"case\"}]){ total } }"}'

# 26 hippocampus tissue samples, each donor's details resolved in the same call
curl -s localhost:8080/graphql -H 'content-type: application/json' \
  -d '{"query":"{ samples(filters:[{field:\"sample_type\",value:\"tissue\"},{field:\"brain_region\",value:\"hippocampus\"}],filterMode:AND){ total items{ id brainRegion donor{ cohort sex historyOfRhi } } } }"}'
```

These are the numbers the benchmark checks against, so they are the ones to trust.

### Ask what the data holds

Verified live 2026-09-21 against `mosaic serve` on this repo's schema, with
`bedrock/global.anthropic.claude-haiku-4-5`.

In the chat panel, try:

> what do we have on donors about head injuries?

Expect an answer, not a query: the panel names `history_of_rhi` and says what it holds, then
offers to put it in the query. Say yes and the next turn is an ordinary proposal filtered on that
field.

The point is the field's NAME shares no word with the question. `history_of_rhi` is findable only
because the schema's own description — "a documented history of repetitive head impacts (RHI)" —
is now part of what the planner reads. Two more worth trying:

> which fields tell us whether a dataset can be shared outside the project?

> is there anything that tells us how a sample was kept before analysis?

The first names both `access_level` and `is_public`; the second, `storage_condition`. On the
2026-09-21 run all three resolved correctly, and the follow-up turn for the first produced
`history_of_rhi eq true` — which Mosaic validated and executed to 50 donors, the same number
q05 has carried since August.

**Nothing is stored to make this work.** The descriptions come from `schemas/demo.yaml`, reach the
planner through the live capability manifest, and are rendered into its grounding. There are no
schema-describing rows to regenerate, and nothing that can go stale: edit a description in the
schema, restart the server, and the next answer reflects it.

**A discovery answer does not derail the conversation.** It is a clarification that *answered*, so
editing an earlier turn recomputes it without suspending the turns that follow — unlike a
clarification that is genuinely waiting on you.

---

## Reliability

Kept because it's honest, not flattering. Measured 2026-08-18 and unchanged — today's work was
plumbing, not model quality.

Moving from a local model to a hosted one (Claude Haiku 4.5) fixed *reliability* — no more dropped
filters or ignored instructions — but not **faithfulness**. The planner still sometimes answers a
slightly different question than the one asked.

| Model | Train | Holdout | Strict |
|---|---|---|---|
| Haiku 4.5 | 0.33 | 0.50 | 7/21 |
| Sonnet 5 | 0.38 | 0.50 | 8/21 |

Automatic prompt tuning raised Haiku's training score (0.33 → 0.43) but **holdout didn't move at
all** — it learned the examples, not the task. The same tuning on Sonnet 5 did move holdout
(0.50 → 0.67), which suggests the ceiling is the model, not the prompt.

Three recurring failure shapes: guessing values that sound right but aren't in the data, picking
the wrong entity on a reverse lookup, and failing to refuse when a question can't be answered.

**Next thing to fix:** value guessing — give the planner the actual allowed values per field
rather than hoping it infers them.

---

## Tests

Development tooling, not part of the product. No model calls, about nine seconds.

```bash
python3 tests/test_grading.py            # 23 checks
python3 tests/test_harness_invariants.py # 28 checks
python3 tests/test_independence.py       #  9 checks
python3 tests/test_runner_fake.py        #  6 checks

python3 -m pytest tests/test_spec_planner.py tests/test_conversational_planner.py \
  tests/test_conversational_orchestrator.py tests/test_conversational_server.py   # 72 checks
```

The first four are scripts, not pytest files — running them under `pytest` fails with a collection
error. Run them directly.

The one worth watching is in `test_grading.py`:

```
PASS  dropped-filter plan is PLAN_UNFAITHFUL
```

That query was structurally valid and would have run fine, but it had silently dropped every
condition the question asked for. "Is this safe to run" and "does this answer the question" are
different questions, and only the second one catches it.
