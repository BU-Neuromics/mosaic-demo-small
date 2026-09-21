# Ask the data what it holds

**A conversational query surface over a LinkML schema — running in Docker, one port.**

Updated 2026-09-21.

---

## Contents

1. [The result](#1-the-result)
2. [What we set out to do](#2-what-we-set-out-to-do)
3. [The wrong turn, and why it was wrong](#3-the-wrong-turn-and-why-it-was-wrong)
4. [What actually fixed it](#4-what-actually-fixed-it)
5. [Running it](#5-running-it)
6. [Queries to try](#6-queries-to-try)
7. [How the Docker stack was made to work](#7-how-the-docker-stack-was-made-to-work) ← *the part worth reading twice*
8. [Where the planner now lives](#8-where-the-planner-now-lives)
9. [Where we stand](#9-where-we-stand)
10. [Questions for the room](#10-questions-for-the-room)

---

## 1. The result

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

✅ = run against live data and confirmed. Everything else is expected-but-unverified —
worth a dry run before you present.

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

### The honesty case — worth doing live

> **what do we have on donors about toxicology reports?**

✅ There is no toxicology field in this schema. It **says so**, then point at `notes`
and `cause_of_death` as free text that might mention it — rather than inventing a field.

This is the most reassuring thing in the demo.

### The two-step, if you want to show the full loop

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

## 9. Where we stand

### Working

- Discovery answering in a researcher's vocabulary, verified live against real data
- The full stack in Docker, one port, no host processes
- The planner packaged as its own image, carrying **no schema, no data, no fixtures** —
  the schema arrives at runtime, which is what lets one image serve any deployment

### Not yet

| | |
| --- | --- |
| **`make chat` from pinned images** | Needs a Mosaic newer than v0.13.0 — for `--mcp` and the Host fix. `make chat-dev` works today. |
| **A certified deployment** | `ide` builds from source and is exempt from the deploy gate. Real users on `solo` need a Mosaic release *and* a Reel release to certify against. |
| **Harness coverage** | The reliability suite grades the *older* query-plan emitter, so it can neither confirm nor catch a regression in the conversational path. Verification so far is live runs — honest, but not CI. |
| **Prompt behaviour** | Tuned, not proven. The questions in §6 were verified against live data; a different phrasing may still surprise us. |

---

## 10. Questions for the room

1. **Certification path.** Reaching real users means cutting a Mosaic release and a Reel
   release. What's the appetite?
2. **Harness coverage.** The conversational path is ungraded. Worth building
   conversational cases, or is live verification enough for now?
3. **Cost exposure.** Every turn spends a model invocation, and the boundary has no
   authentication — anyone who can reach it can cause spend, with no attribution. This was
   **accepted deliberately** when ADR-0010 was ratified, with rate limiting deferred. It
   should be a decision the room has made, not one it inherits.
