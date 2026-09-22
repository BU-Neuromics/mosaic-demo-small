# The conversational query surface

Ask a LinkML-backed store what it holds, in plain language, and get a runnable query
back. Runs in Docker behind one port.

Updated 2026-09-21. Covers what it does, how it was built, how to run it, how it is
measured, and what is not done.

---

## Contents

1. [What it does](#1-what-it-does)
2. [What we set out to do](#2-what-we-set-out-to-do)
3. [The wrong turn, and why it was wrong](#3-the-wrong-turn-and-why-it-was-wrong)
4. [What actually fixed it](#4-what-actually-fixed-it)
5. [Running it](#5-running-it)
6. [Queries to try](#6-queries-to-try)
7. [How the Docker stack was made to work](#7-how-the-docker-stack-was-made-to-work) ← *the part worth reading twice*
8. [Where the planner now lives](#8-where-the-planner-now-lives)
9. [What works and what doesn't](#9-what-works-and-what-doesnt)
10. [Measuring it](#10-measuring-it)
11. [Upstream — filed, fixed, and still open](#11-upstream--filed-fixed-and-still-open)
12. [Open work](#12-open-work)

---

## 1. What it does

A researcher asks, in their own words, what the data holds — and gets either a straight
answer or a runnable query, without knowing a single field name.

> **"what do we have on donors about head injuries?"**
> → *Filtering to donors with a documented history of repetitive head impacts (RHI).*
> → **50 donors**, in a table, exportable.

The field is called `history_of_rhi`. The question contains none of those words.

---

## 2. What we set out to do

The original question was narrower: **"what fields are available on datasets?"** — and
the system used to *refuse* it, self-contradictorily. It would offer to list the fields,
then decline when taken up on the offer.

Stating the goal precisely is what unlocked everything else:

> Let a user ask about the classes and slots available, **for the purpose of identifying
> the specific data elements they want in a query.**

Two things follow from that wording, and both turned out to matter:

- The point is **discovery in service of querying**. Not a metadata browser.
- The answer's job is to get the user to a query — so a rendered table of field
  metadata is not the deliverable, even though it looks like one.

---

## 3. The wrong turn, and why it was wrong

The first attempt answered a different question — *how do we show a user a table of field
metadata?* — by describing the schema **as data**: one row per entity type, one row per
field, generated from the live schema and ingested. "What fields are on datasets?" then
became an ordinary query returning an ordinary table.

**It worked.** It was still the wrong shape, for three reasons that only become visible
once the goal is stated precisely:

| | |
| --- | --- |
| **It couldn't serve the goal** | The conversational boundary **never executes**. So the planner could not read those rows while planning. The only path was: propose a query over `SchemaField` → make the user run it → read the table → ask again. It *mandated* the unwanted table as a required step. |
| **It was a fifth copy** | Four surfaces already described the schema (`__schema`, `hippoSchema`, `mosaic://schema`, `mosaic://capabilities`). The rows were the only copy materialized into storage — so the only one that could go stale. |
| **It was a workaround** | It put the schema's prose into a searchable column so the planner could *retrieve* what it should simply have been *shown*. |

**Retired.** The record is kept as a superseded OpenSpec change rather than deleted — the
reasoning is worth more than the code was.

---

## 4. What actually fixed it

The planner reads each field's **description from the schema** — prose a curator already
wrote — not just its name and type.

Before, the grounding handed to the model looked like this:

```
history_of_rhi: boolean -- ops: eq, neq, is_null
cause_of_death: string  -- ops: eq, contains, is_null
```

Names, types, operators. A question could only be answered when its vocabulary happened
to match a field name. This schema annotates all 39 slots with a description; **none of
it reached the model.**

Now:

```
history_of_rhi: boolean -- ops: eq, neq, is_null; orderable;
  "Whether this donor has a documented history of repetitive head impacts (RHI)."
```

That is the whole change — **roughly ten lines, in one function.**

Three smaller pieces went with it:

- **Descriptions on reference fields too.** The renderer used to skip them, which would
  have omitted exactly the fields that name where *related* information lives.
- **Discovery answers in the conversation**, rather than as a query to run.
- **An edit no longer suspends the conversation.** Editing an earlier turn used to
  cascade-suspend everything after a discovery turn. Now only a genuinely blocking
  question does.

### Then making the answer readable

The first working version was correct and unusable. Asked about head injuries, it
listed three fields, quoted each schema description verbatim — trailing `(facet)` and
all — said *"On the Donor entity:"*, and closed with a four-option menu. Meanwhile the
builder sat locked and empty and the results pane read *"Nothing run yet"*.

Three rounds of fixes, each from watching someone use it:

| Symptom | Fix |
| --- | --- |
| A wall of text and no data | **Prefer a proposal.** When one field clearly answers, filter on it and say so in a sentence. A second turn to reach rows is worse than a first turn that shows them. |
| Schema vocabulary leaking to a researcher | **Write for the reader.** No verbatim description text, no `(facet)`, no "entity", no headers, no menus, at most one follow-up question. |
| *"What fields are available on datasets?"* bounced back as *"do you mean schema discovery or records?"* | **Separate the two shapes.** "What exists?" → just answer it. "What do we have about X?" → build the query. And never ask the user to choose between those two — that is the question restated as a menu. |
| A locked builder showing the *previous* anchor, beside a proposal it claimed to own | **Adopt the proposal into the builder's draft** the moment it arrives. |
| *"Use in builder"* | Renamed **"Run this query"** — because that is what it does. Writing the spec to the URL *is* execution here; the old label undersold it. |

### And closing the last mile

The goal ends in *"the specific data elements they wish to include"* — and until now the
results table returned **every** column of every row. Discovery could identify exactly
the right field and the user still got everything back.

The results table now has a **Fields** control: pick which columns to read, and both
exports honour the choice. It reads *"Fields (3 of 9)"* once a selection is active, so a
narrowed table never looks like missing data.

This is the remedy the upstream rejection itself prescribes — *"request full envelopes
and project client-side"* — so it is a workaround, not a fix. Every field still crosses
the wire, and the **planner** still cannot express the user's choice, because
`columns` is rejected at parse. Filed as
[mosaic#215](https://github.com/BU-Neuromics/mosaic/issues/215).

One thing deliberately **not** done: auto-running the proposal. The first attempt wrote
the spec straight to the URL, which this builder treats as already-executed — so a model
proposal would have run with no human gesture at all. ADR-0039 exists to prevent exactly
that. The proposal is now *visible* immediately and still *runs* only when you say so.

---

## 5. Running it

```bash
cd datahelix/deploy/recipes/ide
cp .env.example .env     # first time only — edit paths if your layout differs
make chat-dev
open http://localhost:8080
```

Then click **Query builder** in the left sidebar.

| Command | What it does |
| --- | --- |
| `make chat-dev` | Everything from source, planner included |
| `make chat` | Same, from pinned images — *needs a Mosaic release, see §9* |
| `make dev` | No planner: browsing only, chat panel correctly hidden |
| `make logs-planner` | Follow the planner — grounding, model calls, failures |
| `make restart-planner` | Re-read the schema after changing it |
| `make down` | Stop everything |

**The one gotcha:** the planner fetches its grounding **once, at startup**. Change the
schema, or point at a different project, and it keeps answering about the old one until
`make restart-planner`.

---

## 6. Queries to try

The eval suite (§10) is the source of truth for what reliably works. These marks come
from it:

- **✅ stable** — passes every run of the graded case
- **⚠️ flaky** — passes some runs
- **❌ known failure** — fails reliably; see §10 for why
- **unmarked** — plausible, never graded

### About the data — these return rows

| Ask | Expect | |
| --- | --- | --- |
| **what do we have on donors about head injuries?** | Proposal on `history_of_rhi` → **50 donors** | ✅ `d01` |
| **how long did each processing run take?** | Should name `duration_hours` | ⚠️ `d04` |
| **what part of the brain did these specimens come from?** | `brain_region` | ✅ `d05` |
| **donors over 60 who had repeated head impacts** | Two criteria combined | — |
| **show me failed workflows** | `status` enum resolved from plain words | — |
| **datasets that are publicly released** | `is_public` | — |
| **samples from female donors** | A *traversal* — constrains the related Donor, not the Sample | — |

### About the metadata — these answer in the conversation

| Ask | Expect | |
| --- | --- | --- |
| **which fields only accept a fixed set of values?** | Every enum, across all four entity types | ✅ `d10` |
| **is there anything that tells us how a sample was kept before analysis?** | `storage_condition` | ✅ `d03` |
| **what do we record about how samples are stored?** | `storage_condition` — the same question, different words | ✅ `d08` |
| **which fields tell us whether a dataset can be shared outside the project?** | `access_level` **and** `is_public` | ✅ `d02` |
| **what fields are available on datasets?** | All ten Dataset fields | ❌ `d09` — drops `produced_by` |
| **what kinds of things does this hold, and how do they relate?** | The reference fields, which is what makes traversal visible | ❌ `d11` |
| **can we tell which donors were part of the main study group?** | `cohort` | ❌ `d07` |

**Read `d03` and `d08` together.** They are the same question in different words, and for
a while one passed and the other bounced back with a menu. Two phrasings behaving
differently is the characteristic risk of prompt-shaped behaviour, and the only defence is
one case per phrasing.

### It doesn't invent fields

> **what do we have on donors about toxicology reports?**

✅ This schema models nothing about toxicology, so it **says so**, then points at free
text that might mention it — rather than reaching for the nearest plausible field.

The point is a refusal to invent, not a gap in the data. A planner that always finds
*something* reads as confident and is occasionally wrong. This is now a standing eval
case (`d06`) rather than something checked by hand.

### Choosing what comes back

After any query returns rows, the **Fields** button beside the exports narrows the table
to the columns you care about, and both exports follow it. That closes the loop from
*"which field holds this?"* to *"show me just that."*

Every field still crosses the wire — this is client-side projection, because the query
artifact cannot yet carry a field list.

### Two-turn refinement

> **what do we have on donors about head injuries?** → then → **yes, and only the case cohort**

The second turn refines the first rather than starting over.

---

## 7. How the Docker stack was made to work

**Read this section before trying to reproduce any of it.** Every item below cost real
time to find, and none of it is guessable from the symptom.

### What's running

```
localhost:8080  →  gateway (nginx)
                     ├── Aperture      the browser UI
                     ├── Mosaic        the query boundary: validates and executes
                     └── Reel          the planner: proposes, never executes
```

Four containers, one port, no host processes. The gateway makes everything same-origin,
which is why **CORS never enters the picture** — worth knowing, because Mosaic's CORS
support is unreleased and it would otherwise be a blocker.

**Reel is untrusted by design.** It proposes; Mosaic re-validates every proposal
in-process before any caller sees it; nothing executes until a person clicks. That
separation is a ratified decision on both sides (Mosaic ADR-0010, Reel ADR-0007).

The planner is **opt-in**: `make dev` omits it, Mosaic then never advertises the
conversational capability, and the UI correctly hides the chat panel.

### The blocker that explains "it works locally but not in Docker"

> **Mosaic's MCP boundary accepted only loopback callers.**

`mcp/router.py` called `streamable_http_app()` passing neither `transport_security` nor
`host`. The SDK defaults `host="127.0.0.1"`, turns that into the **entire** allow-list,
and has DNS-rebinding protection on by default. So the boundary answered `127.0.0.1` and
nothing else.

Invisible for months — every caller was a host process addressing it as `localhost`. An
absolute wall the moment anything crosses a container boundary:

- sibling container → `http://mosaic:8001/mcp` sends `Host: mosaic:8001` → **rejected**
- Docker-host client → `Host: host.docker.internal:8099` → **rejected**

And the diagnosis was harder than it should be: the Python MCP client reports it as
`MCPError: Server returned an error response`. The real status (**421**) and body
(**`Invalid Host header`**) only appear if you `curl` the endpoint raw.

**Fixed** in Mosaic: `MOSAIC_MCP_ALLOWED_HOSTS`, *added to* the loopback defaults rather
than replacing them — an operator who configures a container name must not thereby lose
the ability to debug locally. `*` disables the check for a deployment that treats its own
network as the boundary. An empty value is deliberately **not** read as `*`, because
failing open on a typo would kill a security control silently.
Filed as [mosaic#214](https://github.com/BU-Neuromics/mosaic/issues/214).

### The other five, each found by running it

**1. `KEY: ${KEY:-}` sets a variable to empty — which is not unset.**
`os.environ.get(name, default)` then returns `""`, not the default. This handed litellm an
empty model string (its error named no provider at all, just a link to its docs) and gave
`boto3` a profile literally named empty. Fixed on **both** sides: compose uses the
pass-through list form for optional variables, and the planner's config treats empty as
unset for all five reads.

**2. The published Mosaic v0.13.0 image has no `--mcp` flag at all.** The `mcp` extra
postdates the tag. The `mosaic-dev` service now installs it on first run — mirroring the
`node_modules` pattern `aperture-dev` already uses. **This comes out the moment an image
ships with the extra.**

**3. That image's `ENTRYPOINT` is `mosaic`.** A `command:` of `sh` arrives as `mosaic sh`
→ *"No such command 'sh'"*. The entrypoint is now cleared explicitly.

**4. In the source profile the service is `mosaic-dev`, not `mosaic`.** Compose service
names *are* the DNS names, so the planner pointing at `mosaic` got *"Name or service not
known"* and restarted forever.

**5. Deliberately no `depends_on`.** It would have to name `mosaic` or `mosaic-dev`
depending on the active profile, and compose **rejects a dependency on a service whose
profile is off** — breaking every plain `docker compose` command, `make restart-planner`
included. The planner's own retry plus `restart: unless-stopped` covers the startup race,
and its log says exactly what it is waiting for.

### And one that wasn't Docker's fault

**`git rm` did not remove a retired recipe.** An untracked `__pycache__` kept the
directory alive, and Mosaic auto-discovers `recipes/` next to the config — so the server
went on serving classes whose every tracked file was deleted. Visible in `GET /schemas`
with no corresponding tables in the database.

> **Check the *served* schema, not the file listing.**

### Why `.env` exists

Running against a real project meant four path overrides on every command line. Compose
already reads `.env` from the recipe directory — that's the mechanism for exactly this.
`cp .env.example .env`, edit once, done.

The example points at **sibling clones** (`../../../../`) rather than datahelix's own
submodules (`../../../`), because the submodules are uninitialized in a fresh checkout and
the defaults then resolve to empty directories — which fails confusingly as
*"No such option: --mcp"*, since the image's own CLI runs instead of the mounted source.

---

## 8. Where the planner now lives

The planner was a prototype living inside this demo repo, under the name **Exon**. It has
moved to **Reel**, which is where the capability is designed to live. Exon's name is
retired at migration; the wire contract is not.

### Why the gate didn't apply

The move was gated on precondition **P1**: the older query-plan path retired and the
reliability harness re-based. That work is real and unfinished — it contains an undecided
design question of its own.

But P1's stated rationale is *"migrating an in-flight refactor across repos mid-stream
loses the before/after the harness exists to provide"* — **a claim about the harness.**
Phase B being one atomic step is what extended it to the runtime too.

The import graph shows the two halves were already separable. The turn-path runtime
imports **nothing** from the retired code; its only tie was five configuration constants:

| Module | Sibling imports |
| --- | --- |
| `spec_planner` | `planner` (`MAX_ATTEMPTS`, `MAX_TOKENS`, `MODEL`, `REQUEST_TIMEOUT`, `decode_kwargs_for`) |
| `conversational_planner` | `planner` (same), `spec_planner` |
| `conversational_orchestrator` | `conversational_planner`, `planner` (constants) |
| `conversational_server` | `conversational_orchestrator` |
| `query_router` | `planner` (constants), `spec_planner` |
| `mosaic_mcp`, `schema` | none |

`harness/grading.py` is the **sole** module coupled to the retired path, through
`validator.resolve_field` — the same dependency the retirement task already names as
blocking its own deletion. That dependency times the harness's move, and nothing times the
runtime's.

So Phase B split into **B-runtime** (done) and **B-harness** (still gated). Every
rationale P1 states is still honoured.

### What moved, and the one thing that isn't a copy

```
exon/spec_planner.py                -> reel/planner/spec_planner.py
exon/schema.py                      -> reel/planner/capabilities.py
exon/mosaic_mcp.py                  -> reel/planner/boundary.py
exon/conversational_planner.py      -> reel/story/turn.py
exon/conversational_orchestrator.py -> reel/story/conversation.py
exon/conversational_server.py       -> reel/serve/http.py
(new)                               -> reel/config.py
```

`config.py` is the exception. Those five constants lived in the **retired** emitter, and
copying that file across to satisfy five imports would have dragged the whole QueryPlan
path into Reel and undone the split. Values unchanged; only the env prefix moves,
`EXON_*` → `REEL_*`.

Two corrections the carry surfaced, both now fixed in the runbook:

- **`context/` was filed under the planner** in the original map. Nothing in the turn path
  imports it — only the harness does — and it imports the retired module itself. Moved to
  the B-harness list.
- **Domain-bound tests came with it.** The `TestAgainstMosaicItself` classes read
  `schemas/demo.yaml`, a fixture the carry rules keep in the demo repo. Rather than drop
  them they now read a schema by path from `REEL_TEST_SCHEMA` and skip when it's unset —
  the same seam registered for eval cases. **76 pass standalone, 85 with the seam
  pointed at this repo's schema**, which is the proof the seam works rather than merely
  skipping.

### The ADRs, and how they were ratified

B-runtime was blocked on **P3** — three Reel ADRs and one Mosaic ADR still `Proposed`.
All four were ratified, in the order P3 requires (Mosaic first, because Reel ADR-0007
records the Reel side of that arrangement and must not lead it).

**This is worth stating precisely, because the gate was released rather than satisfied.**
Mosaic ADR-0010's own note said its terms — client-visible failures naming a *role* not an
*address*, the wire contract not being Mosaic's to change, and the cost-amplification
consequence — *"were settled during review of that PR and have not been ratified in a
design session."*

**No design session was held.** What changed was the evidence: the relay has now been
driven end to end through a browser, exercising most of those terms directly. The ADR
records that it was ratified on that basis, by name, without a session.

**The cost exposure is accepted, not mitigated.** Rate limiting stays deferred, and anyone
who can reach a configured Mosaic can still cause spend at a third party with no
attribution. Ratifying settled the boundary's *shape*; it did not close that.

### Packaging

- `pyproject.toml` for `datahelix-reel` — hatchling, `src/` layout, bare `import reel`
- CI across Python 3.11–3.13, mirroring this repo's invocation, **no model calls**
- A `Dockerfile` — non-root, writes nothing, and carries **no schema, no data, no eval
  cases**. The schema arrives at runtime from the capability manifest, which is what lets
  one image serve any deployment.
- Two seams registered before they were consumed: `REEL_EVAL_CASES`, `REEL_TEST_SCHEMA`

### What still points backwards

`exon/` still exists in this repo as source, and has **forked** — the prompt work of the
last few hours went to Reel only. Phase C3 (replace it with a pointer and a pin) has not
happened. Anything grading or running `exon/` is grading a copy nobody executes.

---

## 9. What works and what doesn't

### Works

- **Discovery in a researcher's vocabulary.** A question containing none of a field's
  words resolves to it, through the schema's own description.
- **Metadata listing.** Field lists with types and enum values, entity types with
  descriptions, every enum across the schema — verified live.
- **It doesn't invent fields** *(when it behaves — see below)*. A topic the schema
  doesn't model gets said so rather than a plausible substitute.
- **The full stack in Docker**, one port, no host processes.
- **The planner as its own image**, carrying no schema, data or fixtures.
- **Discovery is graded** — 11 cases, sampled, on the slots a turn names.
- **The user picks which fields to read**, and exports honour the choice.

### Doesn't

| | |
| --- | --- |
| **Reference fields go unnamed** | The most valuable thing left. `produced_by`, `donor`, `input_samples` are how a user learns a traversal is possible, and answers list the scalars and stop. One cause behind two failing metadata cases (`d09`, `d11`). |
| **The negative case regressed** | Pushing "name the fields" to fix one case made `d06` name plausible-but-wrong fields for an unmodelled topic. An explicit carve-out didn't hold. |
| **A clarification that withholds the field** | `d07` asks back about an ambiguous phrase — fine — without naming `cohort`, which leaves the user nothing to query. |
| **Field selection in the *spec*** | The user can choose columns; the planner cannot express that choice. `columns` is rejected at parse. [mosaic#215](https://github.com/BU-Neuromics/mosaic/issues/215). |
| **`make chat` from pinned images** | Needs a Mosaic newer than v0.13.0, for `--mcp` and the Host allow-list. `make chat-dev` works today. |
| **A certified deployment** | `ide` builds from source and is exempt from the deploy gate. `solo` needs a Mosaic release *and* a Reel release. |
| **The older reliability suite** | Still grading the *retired* query-plan emitter. |
| **`exon/` has forked** | The prompt work went to Reel only; this repo's copy is stale and Phase C3 hasn't happened. |

### Honest caveats about the evidence

- **The eval suite is a day old** and two of its own bugs surfaced on its first live run.
  5 of 11 is a starting line.
- **Some UI work is test-verified, not seen.** The builder-draft adoption, the renamed Run
  button and the Fields picker all pass tests and typecheck; browser automation couldn't
  reliably drive the composer, so they have not been watched working.
- **Prompt behaviour is tuned, not proven**, and §10 argues it now needs a rewrite rather
  than another patch.

## 10. Measuring it

### What is asserted, and why it wasn't a judgement call

The goal statement fixes the unit of success:

> *"…identifying the specific data elements they wish to include in a query. The response
> is only useful for constructing a query spec that pulls back specific fields."*

So a turn is graded on **which slots it named** — never prose quality, never row counts,
never a table of field metadata. An answer that reads beautifully and names the wrong
field has failed; a terse one that names the right field has not.

A slot counts as named whether the turn **filters on it** or **says it**. Both tell the
user what to include.

```bash
cd reel
MOSAIC_MCP_URL=http://localhost:8099/mcp \
REEL_EVAL_CASES=../mosaic-demo-small/evals/discovery.yaml \
    python -m reel.evals.run -n 3
```

Exit status is the number of unreliable cases, so it gates without parsing output. It is
deliberately **not** in `pytest tests/` — every case spends a model call, and CI has to
stay free and credential-less. The unit suite proves the grader; the runner proves the
planner.

### Three design choices

- **Subset, not equality.** Offering `cause_of_death` alongside `history_of_rhi` is a
  better answer. Equality would train the planner to be stingy.
- **A negative case.** `d06` asserts the turn names *no* slot for a topic the schema
  doesn't model. A planner that always finds *something* reads as confident and is
  occasionally wrong; no quantity of positive cases catches that.
- **Every run must pass.** A case passing 2 of 3 is a coin flip the next prompt edit may
  tip, and calling it green hides that.

### Sampling, and why the first numbers were wrong

The runner originally took **one sample per case**. That cannot distinguish a broken
prompt from an unlucky one — and this repo's own harness spec already said so:

> *"Reliability is measured as a distribution, not a single pass or fail."*

Adding `--samples` (default 3) immediately reclassified several cases that had been
reported as passing. **Any single-run score in an earlier version of this document is
unreliable.** The honest figure is below.

### Current state — 5 of 11 stable (n=2–3)

| Case | Asks | State |
| --- | --- | --- |
| `d01` | what do we have on donors about head injuries? | ✅ |
| `d02` | which fields tell us whether a dataset can be shared outside the project? | ✅ |
| `d03` | is there anything that tells us how a sample was kept before analysis? | ✅ |
| `d04` | how long did each processing run take? | ⚠️ flaky |
| `d05` | what part of the brain did these specimens come from? | ✅ |
| `d06` | what do we have on donors about toxicology reports? *(negative)* | ❌ |
| `d07` | can we tell which donors were part of the main study group? | ❌ |
| `d08` | what do we record about how samples are stored? | ✅ |
| `d09` | what fields are available on datasets? | ❌ |
| `d10` | which fields only accept a fixed set of values? | ✅ |
| `d11` | what kinds of things does this hold, and how do they relate? | ❌ |

### The failures, grouped by cause

**Reference fields go unnamed — `d09`, `d11`.** Both fail the same way. `produced_by`,
`donor`, `input_samples` are how a user learns a **traversal** is possible, and an answer
that lists the scalar fields and stops has told them less than it appears to. This is the
**third** time reference slots have been the weak spot: the grounding renderer originally
skipped their descriptions entirely (fixed), and now the *answers* skip them.

**This is the most valuable single thing left to fix** — one cause behind two failing
metadata cases.

**A regression introduced while fixing something else — `d06`.** Pushing *"name the
relevant fields"* hard enough to fix `d08` made the negative case start naming
plausible-but-wrong fields for a topic the schema doesn't model. An explicit carve-out
("if the schema holds nothing, name none") did not hold it. **Not fixed.**

**A clarification that doesn't hand over the field — `d07`.** *"The main study group"* is
genuinely ambiguous, so asking back is defensible. Asking back **without naming
`cohort`** is not: it leaves the user nothing to put in a query. A clarification still has
to hand over the data element.

**`d04` is flaky, and it used to mean something else.** It was written as *the `columns`
gap made measurable* — the planner reaching for a date field because a QuerySpec can say
which **rows** but not which **fields**. Once the prompt started naming fields in prose it
began passing intermittently. **It no longer measures the projection gap**; that gap is
still entirely real and is tracked at
[mosaic#215](https://github.com/BU-Neuromics/mosaic/issues/215).

### Two grader bugs the first live run found

Both now covered by unit tests:

- **`donor`, `name`, `notes` are slot names *and* ordinary words.** Crediting the bare word
  scored *"the donor's free-text notes"* as naming two slots, turning the negative case
  into a false failure. A name without an underscore is now credited from prose only when
  written as a field reference (backticks, bold, quotes); from the spec it always counts.
- **Conversely, "storage condition" communicates the field as well as
  `storage_condition`.** Scoring only the underscored spelling marked correct, readable
  answers wrong. The spoken form now counts for compound names.

### The prompt is oscillating, and that is the real finding

Four rounds of prompt changes, each driven by a real failure, each trading against
another case:

| Round | Fix | What it cost |
| --- | --- | --- |
| 1 | Prefer a proposal, keep it short | — |
| 2 | Separate "what exists" from "what do we have about X" | Created a classification the model couldn't make |
| 3 | Remove the classification; always name the fields | Broke the negative case (`d06`) |
| 4 | Carve out "name nothing when nothing matches" | Didn't hold |

Round 2's failure is worth stating plainly, because it was self-inflicted: the prompt told
the model to decide whether a question was *about the data* or *about what exists*, and
**"what do we record about how samples are stored?" is honestly both.** A model that
cannot classify asks which — and a flat *"never ask"* sitting beside *"you must pick a
branch"* loses. It produced exactly the bounce-back the whole contract exists to prevent:

> *"Are you asking what fields we track about sample storage (schema discovery), or do you
> want to retrieve samples filtered by how they're stored?"*

The pattern across all four rounds says the prompt now needs a **considered rewrite**
rather than another patch. Patching has stopped converging.

## 11. Upstream — filed, fixed, and still open

### Filed and fixed

**[mosaic#214](https://github.com/BU-Neuromics/mosaic/issues/214) — the MCP boundary
accepted only loopback callers.** The single reason "it works locally but not in Docker"
was true. Fixed in the same branch as the ADR ratification: `MOSAIC_MCP_ALLOWED_HOSTS`,
added to the loopback defaults rather than replacing them, with `*` to disable and an
empty value deliberately **not** read as `*`. Full detail in §7.

### Filed, open

**[mosaic#215](https://github.com/BU-Neuromics/mosaic/issues/215) — `QuerySpec` cannot
express field selection.** The goal's last clause is *"a query spec that pulls back
specific fields"* and the artifact has no way to carry it. `columns` is rejected at
**parse**, so a planner cannot emit it even speculatively — the boundary re-validates
every proposal and the whole turn would fail.

The issue proposes an increment: accept a flat list of anchor-owned slots and project
server-side, leaving the harder to-many `aggregate`/`explode` choice for later. That alone
would let the planner answer "which fields" questions correctly.

### Found, not yet filed

Three findings from mapping the introspection surfaces, all still unfiled because the
GitHub MCP server failed to connect for most of this session (`Authorization header is
badly formatted`); `gh` was used instead for the two above.

- **`slot_model_to_dict` omits `is_external_xref`**, so `mosaic://schema` carries 12 of
  `SlotModel`'s 13 attributes.
- **`MosaicSlotInfo` omits `is_external_xref` *and* `has_default`**, so `hippoSchema`
  carries 11 of 13.
- **The "mirrors REST `GET /schemas`" claims** in three docstrings overstate the
  correspondence. REST is a separately-implemented projection off a *different* tap
  (`registry.induced_slots()` rather than `build_type_model()`), emitting five slot
  attributes and **no descriptions** — so GraphQL and MCP are strict supersets, not
  mirrors.

### A note on one issue that was filed wrongly

`aperture#64` was opened claiming the chat composer silently dropped the first message
after a page load, with a confident argument that a deterministic pattern ruled out tooling
error. **It was tooling error** — a screenshot coordinate frame (840px) that didn't match
the real viewport (984px), so clicks landed short of the textarea. Confirmed by reading
`document.activeElement` directly, which showed focus never left `BODY`.

Closed with the correction. Recorded here because the reasoning that produced it sounded
rigorous and was wrong: "deterministic, therefore not flaky tooling" ignored that a fixed
coordinate offset is also deterministic.

---

## 12. Open work

Ordered by what I would do next, not by size.

**1. Reference fields in answers.** One cause behind two failing metadata cases. Answers
list scalar fields and stop, so a user never learns that `produced_by` or `input_samples`
exist and that traversal is possible. This is the third time reference slots have been the
weak spot — the grounding renderer originally skipped their descriptions too.

**2. Rewrite the discovery prompt.** Four rounds of patches, each fixing a real failure
and breaking something else (§10). Patching has stopped converging. A rewrite should start
from the three behaviours that must hold simultaneously — name the fields, name *only*
relevant ones, never hand the question back as a menu — rather than adding a fifth rule.

**3. `columns` upstream.** [mosaic#215](https://github.com/BU-Neuromics/mosaic/issues/215).
The goal's last clause, unexpressible in the artifact. The flat-list increment would be
enough for the conversational path.

**4. Phase C3.** Replace this repo's `exon/` with a pointer and a pin. It has forked; the
longer it sits, the more expensive the reconciliation.

**5. Retiring the old query-plan path.** Dead code the reliability suite still grades, and
the precondition B-harness waits on. It carries an undecided design question: how to route
facet- and range-shaped questions, where the obvious fix would leak into the conversational
contract and break its no-aggregation guarantee. Two options written down, neither chosen.

**6. Releases.** `make chat` from pinned images needs a Mosaic release. `solo` needs that
and a Reel release to certify against.

### Nothing is on `main`

| Repo | Branch |
| --- | --- |
| `reel` | `main` (its own default — runtime, image, evals) |
| `mosaic` | `docs/ratify-adr-0010` |
| `mosaic-demo-small` | `exon-conversational-turn-core` |
| `aperture` | `fix/discovery-turn-chrome` |
| `datahelix` | `feat/ide-planning-service` |

They want reviewing as a set — several only make sense together.

---

## Notes for whoever picks this up

Things that will rot if nobody owns them:

- **Don't tune the grader to make cases pass.** Two of its bugs surfaced on its first live
  run and both were real, but the line between *fixing a grader* and *fitting it to the
  answers* is thin. The rule used so far: a grader change has to be defensible from the
  goal statement alone, independent of which cases it flips.
- **`d06`, `d07`, `d09` and `d11` should stay red** until the things they describe are
  fixed. They are the cheapest standing record that the goal is not fully delivered.
- **The planner grounds once, at startup.** Every schema change needs
  `make restart-planner`. Forgetting produces confidently stale answers rather than an
  error — which is how a demo shows the wrong entity types for ten minutes before anyone
  notices.
- **Check the *served* schema, not the file listing.** A retired recipe kept serving
  classes whose every tracked file had been deleted, because an untracked `__pycache__`
  kept its directory alive and the server auto-discovers recipes.
- **Use port 8099, or the gateway on 8080.** A stale `solo-solo-1` container also answers
  on 8080 and serves an older schema — including the retired `SchemaField` classes. Two
  separate confusions this session traced back to hitting it by accident.
- **`REEL_*`, not `EXON_*`.** The env prefix changed with the move. `MOSAIC_EXON_URL` is
  the exception: it is *Mosaic's* variable and is renamed later, with the old name kept as
  an alias.
