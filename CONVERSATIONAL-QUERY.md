# The conversational query surface

Ask a LinkML-backed store what it holds, in plain language, and get a runnable query
back. Runs in Docker behind one port.

Updated 2026-09-22. Covers what it does, how it was built, how to run it, how it is
measured, and what is not done.

The demo schema grew from 4 entity classes to **15** on 2026-09-22 (§10). Every example
in §6 was re-run against the larger schema and the result recorded, so the numbers here
are measured rather than remembered.

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
> → **58 donors**, in a table, exportable.

The field is called `history_of_rhi`. The question contains none of those words.

It now does this across **15 collections and 146 slots**, not the 4 and 39 it was built
against.

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
to match a field name. The schema annotates every slot with a description — 39 of them at
the time, 146 now — and **none of it reached the model.**

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

**Every question below was run against the live stack and the result recorded** — the
anchor and criteria the planner actually proposed, and the row count that proposal
actually returns against the current 8,768-record dataset. Nothing here is
plausible-sounding invention.

Counts came from two places, both measured on 2026-09-22: field filters through GraphQL
exactly as the page runs them, and traversals computed from the bundle the database was
loaded from — a relationship criterion executes as a client-side semijoin, and
reproducing that in one GraphQL document would test my arithmetic rather than the data.

| Mark | Means |
| --- | --- |
| ✅ | Graded eval case, passed every run of all three measured runs |
| ⚠️ | Graded case, flaky — passed some runs and not others |
| ❌ | Graded case, failed every run of all three |
| ▣ | Not a graded case; run here and the result recorded |

The marks come from three separate n=3 runs of the same eleven cases (§10). Only `d11`
fails reliably; the other reds are flaky, and one of them (`d09`) has scored both 0/3 and
3/3 against an identical setup.

**The planner proposes; nothing executes until you click Run.**

---

### One field

The bread and butter: a plain-language phrase resolving to a field nobody named.

| Ask | Proposes | Rows | |
| --- | --- | --- | --- |
| **what do we have on donors about head injuries?** | names `history_of_rhi` | 58 | ✅ `d01` |
| **show me failed workflows** | `Workflow` · `status = failed` | **116** | ▣ |
| **datasets that are publicly released** | `Dataset` · `is_public = true` | **228** | ▣ |
| **which screens came back positive?** | `ToxicologyReport` · `is_positive = true` | **76** | ▣ |
| **which reagent lots have expired?** | `ReagentLot` · `is_expired = true` | **47** | ▣ |
| **which instruments have been retired?** | `Instrument` · `is_decommissioned = true` | **2** | ▣ |
| **show me open-access papers** | `Publication` · `is_open_access = true` | **19** | ▣ |
| **aliquots that have been used up** | `Aliquot` · `is_depleted = true` | **211** | ▣ |
| **which diagnoses were made with certainty?** | `Diagnosis` · `certainty = definite` | **199** | ▣ |
| **which storage locations are full?** | `StorageLocation` · `is_at_capacity = true` | **8** | ▣ |
| **run configurations that aren't reproducible** | `RunConfiguration` · `is_reproducible = false` | **274** | ▣ |
| **what part of the brain did these specimens come from?** | names `brain_region` | 271 tissue samples | ✅ `d05` |

### Several criteria at once

Nothing in these questions says "and", or names an operator.

| Ask | Proposes | Rows | |
| --- | --- | --- | --- |
| **female donors in the case cohort with a history of head impacts** | `sex = female` · `cohort = case` · `history_of_rhi = true` | **13** | ▣ |
| **frozen tissue samples from the hippocampus** | `sample_type = tissue` · `storage_condition = frozen` · `brain_region = hippocampus` | **11** | ▣ |
| **completed RNA-seq runs** | `workflow_type = rna_seq` · `status = completed` | **119** | ▣ |
| **show me the critical quality problems** | `severity = critical` · `is_resolved = false` | **23** | ▣ |
| **show me the baseline MMSE assessments** | `instrument_name = mmse` · `is_baseline = true` | **152** | ▣ |
| **definite CTE diagnoses with a Braak stage of 4 or more** | `certainty = definite` · `condition_name contains "CTE"` · `braak_stage ≥ 4` | **6** | ▣ |
| **donors over 60 who had repeated head impacts** | `age_at_death > 60` · `history_of_rhi = true` | **43** | ▣ |

**"show me the critical quality problems" is the one to demo.** Nothing in the question
says `severity`, `critical` or `resolved`. The planner picked the enum value *and*
inferred that a "problem" is one still open — a second criterion nobody asked for and
everybody meant.

### Numbers and dates

Comparison operators and date boundaries, from ordinary phrasing.

| Ask | Proposes | Rows | |
| --- | --- | --- | --- |
| **donors who died before 50** | `age_at_death < 50` | **17** | ▣ |
| **aliquots with less than 100 microlitres left** | `volume_ul < 100` | **34** | ▣ |
| **specimens thawed more than twice** | `thaw_count > 2` — on `Aliquot`, not `Sample` | **85** | ▣ |
| **runs that took more than a day** | `duration_hours > 24` | **23** | ▣ |
| **datasets bigger than 10 gigabytes** | `file_size_bytes > 10000000000` | **2** | ▣ |
| **samples collected since 2020** | `collected_at ≥ 2020-01-01` | **381** | ▣ |
| **toxicology screens reported before 2018** | `reported_at < 2018-01-01` | **46** | ▣ |
| **papers published since 2023** | `published_on ≥ 2023-01-01` | **8** | ▣ |

Two things worth noticing. *"More than a day"* became `> 24`, and *"10 gigabytes"* became
`10000000000` — unit conversion the question never spelled out. And *"specimens thawed
more than twice"* lands on `Aliquot`, because thaw counts are tracked per portion, not per
sample; "specimen" is the researcher's word for `Sample` everywhere else in this document.

### Traversals — constraining a *different* collection

The shape the whole thing exists for: you name one collection, the answer constrains
another. Each of these produces a **relationship criterion**, not a field filter.

| Ask | Proposes | Rows | |
| --- | --- | --- | --- |
| **samples from female donors** | `Sample` where related `donor` has `sex = female` | **434** | ▣ |
| **toxicology screens on donors in the case cohort** | `ToxicologyReport` → `donor.cohort = case` | **79** | ▣ |
| **aliquots stored in liquid nitrogen** | `Aliquot` → `location.facility_type = liquid_nitrogen` | **205** | ▣ |
| **datasets from workflows that failed** | `Dataset` → `produced_by.status = failed` | **113** | ▣ |
| **diagnoses for donors with repeated head impacts** | `Diagnosis` → `donor.history_of_rhi = true` | **101** | ▣ |
| **run configurations that used a decommissioned instrument** | `RunConfiguration` → `instrument.is_decommissioned = true` | **290** | ▣ |
| **papers that used publicly released datasets** | `Publication` → `datasets.is_public = true` | **9** | ▣ |
| **donors whose consent was withdrawn** | `Donor` → `ConsentRecord.scope = withdrawn` | **8** | ▣ |
| **unresolved critical flags on public datasets** | `severity = critical` · `is_resolved = false` · → `dataset.is_public = true` | **5** | ▣ |

**All nine were correct on the first attempt.** The last one mixes two field criteria and
a traversal in a single spec. None of this was demonstrable before the schema grew — with
four collections there was nothing a researcher would traverse *to* in these words.

### Full-text

| Ask | Proposes | Rows | |
| --- | --- | --- | --- |
| **find donors whose notes mention cohort-alpha** | `Donor` · `notes contains "cohort-alpha"` | **1** | ▣ |

`cohort-alpha:42` is a keyword `generate.py` seeds deliberately so a search scenario has a
known-present term (`_seed_keywords`). The equivalents on the newer collections are
`panel-echo:7` in a toxicology `findings_summary`, `lane-drift` in a QC flag `detail`, and
`consortium-nine` in a publication `abstract_text`.

**One full-text question fails, and it is instructive.** *"which quality flags mention
lane-drift?"* does **not** search — the planner answers that none of the five
`flag_code` values are "lane-drift" and stops. It reasoned about the enum and never
considered the free-text `detail` field, which is FTS5-indexed and does contain the term.
A correct-sounding refusal to a question that had an answer, which is the most expensive
kind.

### Refining over two turns

The second turn adds to the first rather than starting over.

| First | Then | Ends at | Rows | |
| --- | --- | --- | --- | --- |
| what do we have on donors about head injuries? | **yes, and only the case cohort** | `history_of_rhi = true` · `cohort = case` | **30** | ▣ |
| show me failed workflows | **just the RNA-seq ones** | `status = failed` · `workflow_type = rna_seq` | **21** | ▣ |
| which screens came back positive? | **only the ones on blood** | `is_positive = true` · `specimen_matrix = blood` | **39** | ▣ |

### About the metadata — these answer in the conversation, no query

| Ask | Answers with | |
| --- | --- | --- |
| **what fields are available on datasets?** | every Dataset field with its enum values | ⚠️ `d09` — 0/3 and 3/3 across runs; drops `produced_by` when it fails |
| **which fields only accept a fixed set of values?** | enums across the collections, with their values | ⚠️ `d10` — spans the newer collections but drops `cohort`/`sex`/`status` |
| **is there anything that tells us how a sample was kept before analysis?** | `storage_condition` | ✅ `d03` |
| **what do we record about how samples are stored?** | same answer, different words | ✅ `d08` |
| **which fields tell us whether a dataset can be shared outside the project?** | `access_level` **and** `is_public` | ✅ `d02` |
| **can we tell which donors were part of the main study group?** | asks back, without naming `cohort` | ⚠️ `d07` |
| **what kinds of things does this dataset hold, and how do they relate?** | a prose tour of the entities | ❌ `d11` — 0/3 in every run; names the entities, not the edges |
| **what do we have on donors about toxicology reports?** | the ToxicologyReport fields, and says demographics live on Donor | ⚠️ `d06` |
| **what can you tell me about toxicology reports?** | panel type, specimen matrix, detection, substances, date, summary | ▣ |
| **what do we record about cognitive assessments?** | the instrument (MMSE/MoCA/CDR/GDS/NPI), raw score, percentile, baseline flag | ▣ |
| **what information do we keep about where samples are physically stored?** | **traverses Sample → Aliquot → StorageLocation** and describes all three | ▣ |
| **what do we track about the papers that cite our data?** | title, abstract, journal, type, date, DOI, open access — *and the link to datasets* | ▣ |
| **is there anything about the hardware a pipeline ran on?** | names `RunConfiguration` as the link from a workflow to its instrument and reagent lots | ▣ |

**Two of these are better than the graded suite makes them look.** *"Where are samples
physically stored?"* requires noticing that samples are sub-divided into aliquots and that
the location hangs off the aliquot — two hops, correctly followed, unprompted. *"Papers
that cite our data"* volunteers the `datasets` edge without being asked, which is exactly
the thing `d09` and `d11` fail to do. The capability is there; it is not reliable.

**Read `d03` and `d08` together.** They are the same question in different words, and for
a while one passed and the other bounced back with a menu. Two phrasings behaving
differently is the characteristic risk of prompt-shaped behaviour, and the only defence is
one case per phrasing.

### When it asks back — and does it well

Three questions in the corpus produced a clarification rather than a query, and all three
were the right call. What makes them good is that each **names the fields while asking**,
so the user can answer in one word:

> **"assessments scoring under 20"** → *"Do you want assessments where the `raw_score` is
> under 20, or the `percentile_rank` is under 20? (Raw scores vary by instrument and
> aren't comparable across them.)"*

> **"how long did each processing run take?"** → *"wall-clock duration for each completed
> run, or CPU time consumed?"*

That second one is a question the schema growth *made* ambiguous, on purpose:
`Workflow.duration_hours` is wall-clock and `RunConfiguration.compute_hours` — added with
the new collections — is CPU time. It is graded `d04` and is the only question of
twenty-five in the first corpus that answered differently between two runs.

Compare with `d07`, which asks back **without** naming `cohort` and so leaves the user
nothing to put in a query. A clarification still has to hand over the data element.

### It doesn't invent fields — mostly

| Ask | Answers | |
| --- | --- | --- |
| **what imaging do we have on donors, MRI or CT scans?** | *"the schema doesn't record imaging data directly"* | ❌ `n11` — unreliable, see below |
| **do we have any genetic sequencing variants called on donors?** | names `workflow_type: variant_calling` and `dataset_type: vcf` as real, then says no individual variants are held | ▣ |
| **what medications were donors taking?** | no medication record either during life or in toxicology; offers the substances a screen detects | ▣ |
| **how much did each donor weigh?** | no weight field; lists what Donor *does* hold | ▣ |

The variant question is the best refusal in the set, because the honest answer is
"partly" — and it says which part, then offers the traversal that gets closest.

**But this is not reliable, and it is the headline finding of the schema growth.** Other
runs of the imaging question reached for `condition_name`, `instrument_name` and
`dataset_type` — fields with nothing to do with imaging. `n11` is a standing eval case and
it is failing. §10 has the detail.

### Choosing what comes back

After any query returns rows, the **Fields** button beside the exports narrows the table
to the columns you care about, and both exports follow it. That closes the loop from
*"which field holds this?"* to *"show me just that."*

Every field still crosses the wire — this is client-side projection, because the query
artifact cannot yet carry a field list ([mosaic#215](https://github.com/BU-Neuromics/mosaic/issues/215)).

### Two rough edges to know before demoing

- **"reagent lots expiring this year" resolves to 2025.** The planner is not told the
  current date, so it guessed — and the guess is a year stale. It builds a perfectly
  well-formed `expires_on` range; the range is just the wrong year. Say "expiring in 2026"
  and it is correct.
- **Full-text on the newer collections is not reached** (the `lane-drift` case above).
  Search works; the planner does not think to use it.

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
- **Discovery is graded** — 22 cases across two suites, sampled, on the slots a turn names.
- **The user picks which fields to read**, and exports honour the choice.
- **It holds up at 15 collections.** Verified in a browser on 2026-09-22: the nav lists
  all fifteen, the anchor picker offers all fifteen, the Fields panel renders the new
  collections with their real descriptions, enum values and reference targets, and a
  query on a new collection runs and returns rows. §6 has the measured results.
- **The panel follows the answer.** Ask about toxicology while the builder is anchored on
  something else and the panel presents `ToxicologyReport` — the named fields ranked to
  the top, *"5 relevant to your question"*, and a line saying why it moved with a **Return
  rows of Toxicology reports** button. Adopting changes the draft only: verified live that
  the URL stays `?view=query` and nothing runs, so Run remains the only execution gesture
  (ADR-0039). Scored on slots belonging to exactly one collection, so a shared `name` or
  `notes` never moves it.
- **The nav agrees with itself.** Exactly one entry is current, and it is the query entry
  while a query view is open.

### Doesn't

| | |
| --- | --- |
| **Reference fields go unnamed** | The most valuable thing left. `produced_by`, `donor`, `input_samples` are how a user learns a traversal is possible, and answers list the scalars and stop. `d11` fails on it in every run; `d09` fails on it in some. The capability exists — the metadata answers in §6 volunteer edges unprompted — it just is not reliable. |
| **The negative case regressed** | Pushing "name the fields" to fix one case made `d06` name plausible-but-wrong fields for an unmodelled topic. An explicit carve-out didn't hold. |
| **A clarification that withholds the field** | `d07` asks back about an ambiguous phrase — fine — without naming `cohort`, which leaves the user nothing to query. |
| **Field selection in the *spec*** | The user can choose columns; the planner cannot express that choice. `columns` is rejected at parse. [mosaic#215](https://github.com/BU-Neuromics/mosaic/issues/215). |
| **`make chat` from pinned images** | Needs a Mosaic newer than v0.13.0, for `--mcp` and the Host allow-list. `make chat-dev` works today. |
| **A certified deployment** | `ide` builds from source and is exempt from the deploy gate. `solo` needs a Mosaic release *and* a Reel release. |
| **The older reliability suite** | Still grading the *retired* query-plan emitter. |
| **`exon/` has forked** | The prompt work went to Reel only; this repo's copy is stale and Phase C3 hasn't happened. |
| **Answers describe fields instead of naming them** | *"whether a screen was run and came back positive"* is readable and correct, and a user cannot type it into a filter. This is one reason cases score lower than the answers read — see §10. |
| **A cold page still opens on whichever collection sorts first** | Partly fixed: the builder now takes its cold-start anchor from the nav's declared default instead of its own alphabetical index, so the two agree. But `buildNavView` itself falls back to `visible[0]` when no `defaultCollection` is configured, and this demo configures none — so it still lands on `Aliquot`, now for the nav's reason. Needs a `VITE_NAV` default, or task 7.3 (ask instead of defaulting). |

### Honest caveats about the evidence

- **The eval suite is a day old** and two of its own bugs surfaced on its first live run.
  5 of 11 is a starting line.
- **The UI has now been watched working**, which it had not been when this was first
  written. The composer, the Fields panel, the anchor picker and Run were driven in a
  browser on 2026-09-22 against the 15-collection schema. The earlier caveat said browser
  automation "couldn't reliably drive the composer" — that was a coordinate-frame error on
  my side, the same one that produced a wrongly-filed `aperture#64` (§11). Clicking by
  element reference and checking `document.activeElement` works every time.
- **Prompt behaviour is tuned, not proven**, and §10 argues it now needs a rewrite rather
  than another patch.
- **The examples in §6 are two samples each, not three.** Enough to catch a question that
  answers differently run to run — one did — and not enough to call any of them stable.
  The graded suites in §10 are the reliability claim; §6 is a tour.

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

### State at four collections — 5 of 11 stable (n=2–3)

*(This table is the four-collection schema. The scaling section below re-runs the same
eleven cases at fifteen and adds a second suite.)*

| Case | Asks | State |
| --- | --- | --- |
| `d01` | what do we have on donors about head injuries? | ✅ |
| `d02` | which fields tell us whether a dataset can be shared outside the project? | ✅ |
| `d03` | is there anything that tells us how a sample was kept before analysis? | ✅ |
| `d04` | how long did each processing run take? | ⚠️ flaky |
| `d05` | what part of the brain did these specimens come from? | ✅ |
| `d06` | what do we have on donors about toxicology reports? *(was the negative case — see the scaling section)* | ⚠️ |
| `d07` | can we tell which donors were part of the main study group? | ❌ |
| `d08` | what do we record about how samples are stored? | ✅ |
| `d09` | what fields are available on datasets? | ❌ |
| `d10` | which fields only accept a fixed set of values? | ✅ |
| `d11` | what kinds of things does this hold, and how do they relate? | ❌ |

### The failures, grouped by cause

**Reference fields go unnamed — `d11` always, `d09` sometimes.** Both fail the same way.
`produced_by`, `donor`, `input_samples` are how a user learns a **traversal** is possible,
and an answer that lists the scalar fields and stops has told them less than it appears
to. This is the **third** time reference slots have been the weak spot: the grounding
renderer originally skipped their descriptions entirely (fixed), and now the *answers*
skip them.

At fifteen collections the picture is less uniform than it was. `d09` has scored 3/3, and
several ungraded metadata questions in §6 — *"papers that cite our data"*, *"where samples
are physically stored"* — volunteer the edge without being asked. So this is no longer
"the planner cannot name references"; it is "the planner names them about half the time",
which is a different and more tractable problem.

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

### Scaling the schema: the 4 → 15 collection experiment

Every claim in this section was measured against **four** entity classes and about forty
slots. That is not a scale at which "put every class and slot description in the prompt"
can fail, so it has never told us whether the strategy works or merely hasn't been
stressed. `grow-demo-schema-collections` grows the schema to fifteen classes and re-runs
the *same eleven cases, same prompt, same model*, so the difference is attributable.

**Context is not the constraint.** The planner runs Haiku 4.5, whose window is 200K
tokens. The grounding block costs 2,332 of them at four classes. Even at fifteen it stays
an order of magnitude inside the window; what is expected to degrade first is
**field-selection accuracy**, because there are simply more near-miss slot names to choose
between.

#### Measuring grounding cost honestly

Not a character-count estimate and not a per-class average extrapolated from a different
schema size. Two otherwise-identical planning calls — one with the full grounding, one
with none — and the difference in **Bedrock's own `prompt_tokens`**:

```python
from reel.planner.boundary import fetch_capabilities
from reel.story.turn import request_turn

caps = fetch_capabilities()
full = request_turn("what fields are available on datasets?", caps).usage["prompt_tokens"]
bare = request_turn("what fields are available on datasets?", {}).usage["prompt_tokens"]
print(full - bare)          # grounding tokens
```

#### Baseline — four collections

Recorded before any schema edit, `bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0`:

| | |
| --- | --- |
| Entity types | 4 |
| Grounding block | 8,014 chars |
| `prompt_tokens` with grounding | 5,410 |
| `prompt_tokens` without | 3,078 |
| **Grounding tokens** | **2,332** (583/entity) |
| **d01–d11 @ n=3** | **5 / 11** |

Failing: d04 (2/3), d06 (0/3), d07 (0/3), d09 (2/3), d10 (0/3), d11 (0/3).
At fifteen collections the quoted run passes d01, d02, d03, d05, d08 and d09,
and fails d04 (1/3), d06 (1/3), d07 (1/3), d10 (2/3) and d11 (0/3).

**One case will change meaning, not degrade.** `d06` — *"what do we have on donors about
toxicology reports?"* — is the negative case, asserting the planner names nothing for a
topic the schema does not model. After this change the schema *does* model toxicology, so
d06's correct answer becomes a set of real slots. That is bookkeeping, not a regression,
and it is recorded as such rather than being quietly folded into either score.


#### Result — fifteen collections

Same prompt, same model, same eleven cases. `d06`'s assertion was corrected
first, for the reason below.

| | 4 collections | 15 collections |
| --- | --- | --- |
| Entity types | 4 | 15 |
| Grounding block | 8,014 chars | 28,391 chars |
| **Grounding tokens** | **2,332** | **8,361** |
| Tokens per entity | 583 | **557** |
| Share of Haiku's 200K window | 1.2% | 4.2% |
| **d01–d11 @ n=3** | **5 / 11** | **6 / 11** |

Both figures are a clean n=3 with no errored runs. An earlier
fifteen-collection run was throttled by Bedrock and decided `d04`, `d05` and
`d10` on two runs each; it is not the one quoted, and it scored 6/11 as well.

**Grounding cost grew sub-linearly.** Per-entity cost went *down*, because the
dimension classes are small — the naive `583 × 15` projection would have
overstated it by about 16%. At 557 tokens per entity, and leaving room for the
3,078-token prompt and an 8,192-token reply, the 200K window does not bind until
somewhere past **300 collections** — which is not the limit anyone hits first.

**The frozen arm did not degrade — and the individual cases are noisier than the
total.** Read 5 → 6 as "unchanged". Three separate fifteen-collection runs of the
same eleven cases, same prompt, same model, scored **6, 6 and 6** — and not the
same six:

| Case | run A | run B | run C |
| --- | --- | --- | --- |
| `d04` how long did each run take? | 2/3 | 2/2 | 1/3 |
| `d09` what fields are available on datasets? | 2/3 | 0/3 | **3/3** |
| `d10` which fields take fixed values? | 0/2 | 0/2 | 2/3 |
| `d06` toxicology | 0/3 † | 2/3 | 1/3 |

† scored against the pre-correction `expect_none`.

`d09` — the question this entire line of work started from — went 0/3 and 3/3
against an identical setup. The total is stable; which cases make it up is not.
**At n=3, anything under a two-case swing in the total is noise, and any single
case's mark is a snapshot rather than a property.** The §6 marks are labelled
accordingly: only `d11` fails reliably.

#### The degradation is real, and it showed up somewhere unexpected

Not on the known-good questions — on the planner's willingness to invent.

`n11` is the negative case: *"what imaging do we have on donors, MRI or CT
scans?"*, against a schema that models no imaging at all. At four collections
its predecessor refused cleanly. At fifteen it twice reached for things that
merely sound close — `condition_name`, `instrument_name`, `administered_by`,
`dataset_type` — none of which have anything to do with imaging.

That is the cost of a larger candidate set, and it is the opposite of what we
expected to measure. More collections did not make the planner worse at finding
the right field. It made it worse at saying there isn't one.

**With a correction, because a wider corpus run showed this is inconsistent rather
than uniform.** Asked the same imaging question twice more (§6), both runs opened
correctly — *"the schema doesn't record imaging data directly"* — and one then
offered `notes` as free text that might mention it. The suite's own earlier standard
called that **correct**: `d06`'s original framing was *"says so, then points at free
text that might mention it."* So part of `n11`'s graded failure is the grader
counting a legitimate free-text offer, and part is genuine invention. Both happen.
The defect is that you cannot predict which, and a refusal you cannot predict is not
a refusal you can demonstrate.

#### Discovering the new collections is harder — but not for the reason the number suggests

`discovery-new-collections.yaml` scores **3 / 11** across two runs. That is not
comparable to the frozen arm's 6/11, because those eleven cases were written to
be hard on purpose (design.md Decision 3): each targets a slot one hop further
out than the obvious class, or one with a deliberate homonym.

The failures are more useful than the score:

- **`n07` — "which machine was a run done on?"** 0/3. `Assessment.instrument_name`
  is a clinical questionnaire; `Instrument` is laboratory hardware. The planner
  matched the word. This homonym was introduced deliberately and it worked
  exactly as designed.
- **`n09` — "how did donors do on their cognitive tests?"** 0/3, and
  `instrument_name` is the right answer here. The same pair of names defeats the
  planner in both directions.
- **`n02`, `n03`, `n10` pass 3/3** — including `n03`, whose trap is that
  `storage_condition` (the right answer to d03 and d08) is *not* a temperature.
  So the planner can follow a relationship one hop out when the words do not
  collide.

The pattern across every failure is lexical collision, not schema size.

#### What this does and does not license

- It does **not** justify a grounding-cost optimisation. At 4% of the window
  there is nothing to save, and the ~500 tokens per entity of `id` /
  `is_available` boilerplate repeated fifteen times is ugly rather than
  expensive.
- It **does** support the prompt rewrite that section 10 already concluded was
  needed, and it sharpens the brief: the rewrite has to make refusal and
  homonym-discrimination work, not field-finding, which is already fine.
- The eval suite now has a negative case again (`n11`), and it is failing — which
  is the correct state for a case that has just identified a real defect.

#### The schema is frozen; the generated data is not

Worth stating plainly, because it reads like a contradiction otherwise. The four
original classes are unchanged byte-for-byte — but their **data** moved. `DemoBundle`
now fills fifteen pools from one seeded generator, so the random stream that reaches
`Donor` is not the stream it saw with four. Measured directly by generating both from
the same seed:

| | 4 pools | 15 pools |
| --- | --- | --- |
| donors with `history_of_rhi` | 50 | **58** |
| first donor | Michael Jones, case | Michelle Vega, case |
| donor id sequence | *identical* | *identical* |

Ids are assigned deterministically, so the rows line up; the values in them do not.
This does not touch the discovery comparison, which grades **which slots a turn named**
and never a row count. It does mean any row-level figure from before 2026-09-22 is
stale — including the *"50 donors"* this document opened with for a year.

#### The answers read better than they score

A recurring gap between what the planner says and what the grader credits. Asked about
toxicology in the browser, it replied:

> *"whether a screen was run and came back positive, which assay panel was used (basic,
> expanded, heavy metals, or targeted), what biological matrix was tested…"*

Accurate, readable, and it names **not one slot**. `is_positive`, `panel_type` and
`specimen_matrix` are all described rather than named. The grader credits a spoken
compound (*"storage condition"* → `storage_condition`) but *"came back positive"* is not
a spelling of `is_positive` — it is a paraphrase, and a user cannot type it into a filter.

The grader is right and the answer is good. What is missing is the last inch: having
found the field, say its name. That belongs in the prompt rewrite's brief alongside
refusal and homonyms.

#### One thing the small collections nearly broke

Every facetable field was checked for degeneracy rather than assumed, because
a nine-row collection can collapse a weighted boolean to a single value by
chance — `Instrument.is_decommissioned` is weighted 78/22, so nine rows come up
all-`false` about 11% of the time, which would fail the schema's own facet
requirement on a collection we shipped. It came out 7/2.

One facet did degenerate, for a different reason: `ReagentLot.is_expired` read
72/3 against a hint declaring 71/29, because `_fix_intervals` derives it from
`expires_on` and the receipt window stopped in 2024 — so nearly every lot had
expired by now. The hint was a statement that looked like a fact and was not.
Removed, with the receipt window moved to 2022–2026; it now reads 47/28.

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

### Already fixed upstream — I was reporting stale findings

Two of the three introspection gaps recorded earlier in this session **were already fixed**
by [#212](https://github.com/BU-Neuromics/mosaic/pull/212), which landed on `main` before
they were written down. Verified in the merged tree:

- ~~`slot_model_to_dict` omits `is_external_xref`~~ — `mcp/serialize.py` now emits both it
  and `has_default`. `mosaic://schema` carries all **13** of `SlotModel`'s attributes.
- ~~`MosaicSlotInfo` omits `is_external_xref` and `has_default`~~ — `graphql/resolvers.py`
  now declares and populates both. `hippoSchema` carries all **13**.

The lesson is the finding: this repo's mosaic checkout had drifted three commits behind
`origin/main`, so a claim that was true when first investigated had stopped being true and
nothing said so. **Check the merge base before reporting an upstream gap.** The branch has
since been merged up.

### Still open, verified against current `main`

- **The "mirrors REST `GET /schemas`" claims** (`resolvers.py:582` and two others) overstate
  the correspondence. REST is a separately-implemented projection off a *different* tap
  (`registry.induced_slots()` rather than `build_type_model()`), emitting five slot
  attributes and **no descriptions** — so GraphQL and MCP are strict supersets, not mirrors.
  Unfiled.

### Reverse traversal is native now, and this schema does not use it

[mosaic#204](https://github.com/BU-Neuromics/mosaic/issues/204) — *"QuerySpec has no
reverse-edge traversal"* — was **closed 2026-09-19** by
[#210](https://github.com/BU-Neuromics/mosaic/pull/210) (ADR-0011). Reverse references are
declared with LinkML's own `inverse` keyword and resolved as virtual fields, never
separately stored:

```yaml
Donor:
  attributes:
    samples: { range: Sample, multivalued: true, inverse: donor }
```

**What #210 fixed, precisely.** Before it, declaring an inverse produced a query that
*silently returned nothing*: the validator passed it, the manifest classified it as
filterable, the compiler emitted a to-many node — and the storage adapter resolved every
multivalued edge against the ADR-0002 `relationships` link table, which the reverse side of
an FK never writes. It ran and returned zero rows.

**It deliberately did not make reverse edges automatic**, for two reasons worth more than
the feature:

1. **One physical encoding per fact.** LinkML binds `inverse` to `owl:inverseOf` — the
   reverse is *entailed* by the forward slot, never asserted. Without the virtual treatment,
   ADR-0002 would treat `samples` as a *stored* multivalued reference, so a write carrying
   `samples: [...]` would materialise relationship rows: a second, independently writable
   encoding of the one fact `Sample.donor` already stores. Two encodings drift.
2. **Every transport derives from one type model.** If `Donor.samples` appears there,
   GraphQL grows a resolver, a `DonorFilter.samples` some/none input and a `samplesCount`;
   REST and the TUI list it; MCP advertises it. Auto-deriving a reverse for every FK would
   inflate every surface with edges nobody modelled.

So declaring `inverse:` is the schema author saying *"this direction is part of my model."*
It is the intended interface, not a workaround.

**`schemas/demo.yaml` declares none** — which is why `Donor` has zero forward references and
why traversal from it falls through to Aperture's capped client-side semijoin. That is not a
gap to patch; it is a capability this schema has not opted into. Whether it should is a
modelling question about the data, not a mechanical one.

*(ADR-0011 is `Status: Proposed`, deciders "labadorf (pending)" — implemented and merged,
not yet ratified. Same pattern as ADR-0010.)*

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
and breaking something else (§10). Patching has stopped converging. The 4 → 15 scaling
run sharpened the brief considerably — it is now **four** behaviours that must hold
simultaneously, and field-finding, the one everybody worries about, is not among them:

- **Name the field, don't describe it.** *"whether a screen came back positive"* is not
  `is_positive`, and a user cannot filter on a paraphrase.
- **Refuse predictably.** The same unmodelled topic gets a clean refusal on one run and
  an invented field on the next.
- **Tell homonyms apart.** `Assessment.instrument_name` is a questionnaire;
  `Instrument` is hardware. The planner fails this in both directions (`n07`, `n09`).
- **Name the edges, not just the entities.** Still the `d09`/`d11` cause, unchanged.

**2a. ~~Make the Fields panel follow the conversation.~~ Done 2026-09-22** —
`add-schema-field-panel` tasks 7.0a–7.0c, with the cold-start anchor only partly fixed
(§9). What remains of that change is the larger redesign: rename the surface to "Ask"
(7.1), make the anchor the page's heading (7.2), ask what to return rows of instead of
defaulting (7.3), group the panel by entity (8.x), and search it (9.x) — which matters
more now that it lists fifteen collections' worth of fields.

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
| `mosaic-demo-small` | `exon-conversational-turn-core` (schema growth + scaling measurement) |
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
- **`d07`, `d09` and `d11` should stay red** until the things they describe are fixed.
  They are the cheapest standing record that the goal is not fully delivered. (`d06` is
  no longer one of them — the schema grew a toxicology collection, so its assertion
  changed from "name nothing" to naming real fields; `n11` carries the negative case now.)
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
- **`evals/discovery.yaml` is frozen at eleven cases.** It is the comparison arm for the
  4 → 15 scaling measurement. New cases go in `evals/discovery-new-collections.yaml`.
  Adding a twelfth to the first file makes the two arms incomparable, which is the one
  thing that file exists to prevent.
- **Don't write schema descriptions for yourself.** Two field descriptions said things
  like *"deliberately shares a name with `Donor.notes`"* — notes about this schema's own
  test design, rendered to researchers in the Fields panel and fed to the planner as
  grounding. Caught by looking at the page. The name collisions are deliberate and they
  stay; narrating them in user-facing prose was the mistake.
- **Click by element reference, not screenshot coordinates.** Three different coordinate
  frames are in play (`window.innerWidth` 1511, the screenshot's 1400, the accessibility
  tree's 1679). Guessing between them is what produced the wrongly-filed `aperture#64`.
  Click by `ref` and confirm with `document.activeElement`.
