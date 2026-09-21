# Ask the data what it holds

**A conversational query surface over a LinkML schema, running in Docker.**

Updated 2026-09-21.

---

## The one-sentence version

A researcher can now ask, in their own words, what the data holds — and get either
a straight answer or a runnable query, without knowing a single field name.

> **"what do we have on donors about head injuries?"**
> → *Filtering to donors with a documented history of repetitive head impacts (RHI).*
> → **50 donors**, in a table, exportable.

The field is called `history_of_rhi`. The question contains none of those words.

---

## What made that possible

The planner reads each field's **description from the schema** — the prose a curator
already wrote — not just its name and type.

That sounds obvious. It wasn't happening. The grounding the planner received looked
like this:

```
tox_screen_result: string -- ops: eq, contains
history_of_rhi: boolean -- ops: eq, neq, is_null
```

Names, types, operators. No prose. So a question phrased in a researcher's vocabulary
could only be answered when the vocabulary happened to match a field name. The schema
annotates all 39 slots with a description; none of it reached the model.

It now looks like this:

```
history_of_rhi: boolean -- ops: eq, neq, is_null; orderable;
  "Whether this donor has a documented history of repetitive head impacts (RHI)."
```

That is the whole change. **Roughly ten lines**, in one function.

---

## The wrong turn we took first, and why it's worth mentioning

The first attempt answered a different question: *how do we show a user a table of
field metadata?* It described the schema **as data** — one row per entity type, one
row per field — so "what fields are on datasets?" became an ordinary query returning
an ordinary table.

It worked. It was also the wrong shape, for a reason that only becomes visible once
you state the goal precisely:

- The goal is **discovery in service of building a query**, not a metadata table.
- The conversational boundary **never executes**. So the planner could not read those
  rows while planning — the only path was to propose a query over `SchemaField`, make
  the user run it, read the table, and ask again.
- It was a **fifth copy** of facts four other surfaces already carried, and the only
  one materialized into storage — so the only one that could go stale.

The rows were a workaround for grounding that omitted the descriptions: they put the
prose into a searchable column so the planner could *retrieve* what it should simply
have been *shown*.

**Retired.** The record is kept as a superseded OpenSpec change, not deleted — the
reasoning is worth more than the code was.

---

## Demo script

Open **http://localhost:8080** → **Query builder** in the left sidebar.

### 1. Discovery that produces data

> **what do we have on donors about head injuries?**

Expect a **proposal** — one or two plain sentences, plus a filled-in query. Click
**Use in builder** → **50 donors**, with Export CSV / JSON.

The point to make out loud: `history_of_rhi` shares no word with "head injuries". It
is findable only because the schema's own description says *"repetitive head impacts
(RHI)"*.

### 2. Discovery that answers a listing question

> **what fields are available on datasets?**

Expect a short answer naming all ten fields with enum values inline. No table to run,
no follow-up needed.

This is the question that started the whole line of work. It used to be **refused** —
and refused self-contradictorily: the planner offered to list the fields, then declined
when taken up on it.

### 3. Honesty when the answer is "we don't have that"

> **what do we have on donors about toxicology reports?**

There is no toxicology field in this schema. Expect it to **say so**, then point at
`notes` and `cause_of_death` as free text that might mention it — rather than
inventing a field.

Worth doing live. It is the most reassuring thing in the demo.

### Others worth having ready

| Question | What it shows |
| --- | --- |
| **which fields tell us whether a dataset can be shared outside the project?** | Names two fields (`access_level`, `is_public`), neither matching the wording |
| **which fields are constrained to a fixed set of values?** | All five enums with their permitted values |
| **what entity types does this deployment describe?** | Four types, each with a one-line description |
| **what do we record about how samples are stored?** | `storage_condition` — again, no shared vocabulary |

---

## What's actually running

Four containers behind one port. No host processes.

```
localhost:8080  →  gateway (nginx)
                     ├── Aperture      the browser UI
                     ├── Mosaic        the query boundary: validates and executes
                     └── Reel          the planner: proposes, never executes
```

**Reel is untrusted by design.** It proposes a query; Mosaic re-validates every one
in-process before any caller sees it; nothing runs until a person clicks. That
separation is a ratified decision on both sides (Mosaic ADR-0010, Reel ADR-0007), not
an implementation detail.

The planner is **opt-in**. Without it, Mosaic never advertises the conversational
capability and the UI correctly hides the chat panel — the stack is still a complete
browsing environment.

---

## Running it

```bash
cd datahelix/deploy/recipes/ide
cp .env.example .env     # first time only — edit the paths if your layout differs
make chat-dev            # everything from source, planner included
open http://localhost:8080
```

| Command | What it does |
| --- | --- |
| `make chat-dev` | Everything from source, planner included |
| `make chat` | Same, from pinned images *(needs a Mosaic release — see Limitations)* |
| `make dev` | No planner — browsing only, chat panel hidden |
| `make logs-planner` | Follow the planner: grounding, model calls, failures |
| `make restart-planner` | Re-read the schema after a change |
| `make down` | Stop everything |

**One gotcha worth knowing:** the planner fetches its grounding **once, at startup**.
Change the schema or point at a different project and it keeps answering about the old
one until `make restart-planner`.

---

## Limitations, stated plainly

- **`make chat` against pinned images does not work yet.** It needs a Mosaic newer
  than v0.13.0 — the published image has no `--mcp` flag at all, and lacks the Host
  allow-list fix below. `make chat-dev` from source works today.
- **Not a certified deployment.** The `ide` recipe builds from source and is exempt
  from the deploy gate. Reaching real users on `solo` needs a Mosaic release and a
  Reel release to certify against.
- **The reliability harness does not yet cover this path.** It grades the older
  query-plan emitter, so it can neither confirm nor catch a regression in the
  conversational path. Verification so far is live runs, which is honest but not CI.
- **Prompt behaviour is tuned, not proven.** The three questions above were verified
  against live data today. A different phrasing may still surprise us.

---

## Things found along the way

Two were real bugs in shipped code, surfaced only by trying to package this properly:

**Mosaic's MCP boundary accepted only loopback callers.** Anything else got
`421 Invalid Host header`, with a client-side error that named no cause. Invisible
while everything runs as host processes on one machine; an absolute wall the moment
anything is containerized. Fixed, and filed as
[mosaic#214](https://github.com/BU-Neuromics/mosaic/issues/214) — *this is the single
reason "it works locally but not in Docker" was true.*

**An empty environment variable is not an unset one.** `KEY: ${KEY:-}` in a compose
file *sets* the variable to empty; `os.environ.get(name, default)` then returns `""`
rather than the default. That handed the model client an empty model string and
`boto3` a profile literally named empty. Fixed on both sides.

Also worth recording: **`git rm` did not remove a retired recipe.** An untracked
`__pycache__` kept the directory alive, and the server auto-discovers recipes — so it
went on serving classes whose every tracked file was deleted. Check the *served*
schema, not the file listing.

---

## Where the work landed

| Repo | What changed |
| --- | --- |
| **reel** | The planner itself — migrated out of the demo repo, packaged, containerized |
| **mosaic** | MCP Host allow-list; ADR-0010 ratified |
| **mosaic-demo-small** | Descriptions into the grounding; the retired approach superseded |
| **aperture** | Chat-panel chrome: the status label, and the builder lock |
| **datahelix** | The `ide` recipe now runs the planning service |

The planner moving into **Reel** is the substantive structural change: it was a
prototype living inside a demo repo, and Reel is where this capability is designed to
live. The turn contract is unchanged across the move by design, so the migration is a
translation rather than a rewrite.

---

## What I'd ask the room

1. **Certification path.** Getting this to real users means a Mosaic release and a
   Reel release. What's the appetite for cutting those?
2. **Harness coverage.** The conversational path is ungraded. Worth building
   conversational cases, or is live verification enough for now?
3. **Cost exposure.** Every turn spends a model invocation, and the boundary has no
   authentication. Accepted deliberately and recorded, with rate limiting deferred —
   but it should be a decision the room has made, not one it inherits.
