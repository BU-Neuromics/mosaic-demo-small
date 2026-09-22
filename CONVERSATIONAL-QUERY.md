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
11. [Open work](#11-open-work)

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

✅ = run against live data and confirmed. Everything else is expected but unverified.

Note the ✅ marks predate the last two prompt changes, so they are worth re-running
rather than trusted.

### About the data — these return rows

| Ask | Expect |
| --- | --- |
| ✅ **what do we have on donors about head injuries?** | Proposal on `history_of_rhi` → **50 donors** |
| **donors over 60 who had repeated head impacts** | Two criteria combined |
| **which samples came from the hippocampus?** | `brain_region` filter |
| **show me failed workflows** | `status` enum resolved from plain words |
| **datasets that are publicly released** | `is_public` |
| **samples from female donors** | A *traversal* — constrains the related Donor, not the Sample |

### About the metadata — these answer in the conversation

| Ask | Expect |
| --- | --- |
| ✅ **what fields are available on datasets?** | All ten fields, enum values inline, one short answer |
| ✅ **which fields are constrained to a fixed set of values?** | All five enums with their permitted values |
| ✅ **what entity types does this deployment describe?** | Four types, each with a one-line description |
| ✅ **what do we record about how samples are stored?** | `storage_condition` — again, no shared vocabulary |
| ✅ **which fields tell us whether a dataset can be shared outside the project?** | Two fields: `access_level` *and* `is_public` |
| **how are donors and samples connected?** | Tests whether *reference* descriptions surface the traversal |

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

The planner was a prototype living inside this demo repo. It has moved to **Reel**, which
is where this capability is designed to live.

That move was gated on a precondition requiring the older query-plan path to be retired
first. We found the gate **doesn't apply to the part that needed moving**: the turn-path
runtime imports nothing from the retired code — only the reliability harness does, through
a single function. So the migration phase was split:

- **now** — the runtime moves, packaged and containerized
- **later** — the harness moves, once it grades the path that actually ships

The turn contract is unchanged across the move by design, so this is a translation rather
than a rewrite, and the container slot is identical either way.

---

## 9. What works and what doesn't

### Working

- Discovery answering in a researcher's vocabulary, verified live against real data
- The full stack in Docker, one port, no host processes
- The planner packaged as its own image, carrying **no schema, no data, no fixtures** —
  the schema arrives at runtime, which is what lets one image serve any deployment
- **Discovery is graded**, on the slots a turn names — §10
- **The user picks which fields to read**, and exports honour the choice

### Not yet

| | |
| --- | --- |
| **Field selection in the *spec*** | The user can choose which fields to read; the **planner** cannot express that choice. `columns` is rejected at parse, which is why eval case `d04` stays red. |
| **`make chat` from pinned images** | Needs a Mosaic newer than v0.13.0, for `--mcp` and the Host allow-list. `make chat-dev` works today. |
| **A certified deployment** | `ide` builds from source and is exempt from the deploy gate. `solo` needs a Mosaic release *and* a Reel release. |
| **The older reliability suite** | Still grading the *retired* query-plan emitter. |

Each of these is expanded in [§11](#11-open-work).

---

## 10. Measuring it

The goal statement fixes what to assert, so this wasn't a judgement call:

> *"…identifying the specific data elements they wish to include in a query. The response
> is only useful for constructing a query spec that pulls back specific fields."*

The unit of success is therefore **which slots a turn named** — never prose quality,
never row counts, never a table of field metadata. An answer that reads beautifully and
names the wrong field has failed.

```bash
cd reel
MOSAIC_MCP_URL=http://localhost:8099/mcp \
REEL_EVAL_CASES=../mosaic-demo-small/evals/discovery.yaml \
    python -m reel.evals.run
```

Exit status is the number of failing cases, so it works as a gate without parsing
output. It is deliberately **not** part of `pytest tests/` — every case spends a model
call, and CI has to stay free and credential-less.

Three design choices worth stating:

- **Subset, not equality.** Offering `cause_of_death` alongside `history_of_rhi` is a
  better answer; an equality check would train the planner to be stingy.
- **A filter and a sentence both count.** The user learns the field either way.
- **A negative case.** `d06` asserts the turn names *no* slot for a topic the schema
  doesn't model. A planner that always finds something is only caught this way — no
  quantity of positive cases will do it.

**Current score: 5 of 7.** Both failures are kept failing, as findings:

| | |
| --- | --- |
| **d04** — *"how long did each processing run take?"* | The `columns` gap made measurable. The planner reaches for `completed_at` because the user is asking which **field** to look at, and a QuerySpec can only express which **rows** to return. `duration_hours` is already in the envelope; there's nothing to filter on. Filed as [mosaic#215](https://github.com/BU-Neuromics/mosaic/issues/215); the user-facing half is now closed (below). |
| **d07** — *"the main study group"* | A real weakness. The phrase is genuinely ambiguous so asking back is fine — asking back *without naming `cohort`* is not, because it leaves the user nothing to put in a query. |

The first run also found two bugs in the grader itself, both now tested: `donor`/`name`/
`notes` are slot names *and* ordinary words, so crediting the bare word scored prose as a
hit; and conversely "storage condition" communicates the field as well as
`storage_condition` does, so scoring only the underscored spelling marked correct answers
wrong.

---

## 11. Open work

Ordered by what blocks what, not by size.

**`columns` — field selection in the spec.** The goal's last clause is *"a query spec that
pulls back specific fields"*, and the spec cannot say it. `columns` is rejected at parse,
so the planner cannot emit it even speculatively. [mosaic#215](https://github.com/BU-Neuromics/mosaic/issues/215)
proposes an increment: accept a flat list of anchor-owned slots and project server-side,
leaving ADR-0035's harder to-many `aggregate`/`explode` choice for later. This is what
keeps `d04` red.

**Retiring the old query-plan path.** Dead code that the reliability suite still grades,
and the precondition the Reel migration is waiting on. It carries an undecided design
question of its own: how to route facet- and range-shaped questions, where the obvious
fix (a `result_shape` field on the spec tool) would leak into the conversational contract
and break its no-aggregation guarantee. Two options are written down; neither is chosen.

**Releases.** `make chat` from pinned images needs a Mosaic newer than v0.13.0, for both
`--mcp` and the Host allow-list. `solo` — the path real users would reach — needs that
*and* a Reel release to certify against.

**Nothing is on `main`.** Five branches:

| Repo | Branch |
| --- | --- |
| `reel` | `main` (the repo's own default; runtime, image, evals) |
| `mosaic` | `docs/ratify-adr-0010` |
| `mosaic-demo-small` | `exon-conversational-turn-core` |
| `aperture` | `fix/discovery-turn-chrome` |
| `datahelix` | `feat/ide-planning-service` |

They want reviewing as a set — several only make sense together.

---

## Notes for whoever picks this up

- **The grader is young.** Two of its bugs surfaced on its first live run. 5/7 is a
  starting line, not a score — and tuning the grader to make cases pass is how a suite
  stops measuring anything.
- **`d04` and `d07` should stay red** until the things they describe are fixed. They are
  the cheapest standing reminder that the goal is not fully delivered.
- **Prompt behaviour is tuned, not proven.** Three rounds of fixes came from watching
  someone use it, and each found something the previous round had not.
- **The planner grounds once, at startup.** Every schema change needs
  `make restart-planner`, and forgetting produces confidently stale answers rather than
  an error.
