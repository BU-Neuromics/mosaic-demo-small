# Design: Aperture chat panel over `converse_query_spec`

## Context

Three repos are load-bearing here: this repo (Exon's planning core + the demo's Mosaic instance),
`../mosaic` (`BU-Neuromics/mosaic`, hosts the MCP boundary), and `../aperture-spike`/`aperture`
(`BU-Neuromics/aperture`, the SPA). `APERTURE_EXON_CONTRACT.md` already resolved nine design
decisions for the wire contract between Exon and Mosaic; this document does not revisit those. It
covers the *next* layer: how a browser actually reaches that contract, and how it looks and feels
once it does.

Two facts changed the shape of this design relative to a naive reading of the contract doc:

1. **`converse_query_spec` already shipped** (`mosaic` PR #199, `bc1a688`/`6eabb45`) — the
   contract doc's own "blocked on mosaic#186" framing is stale.
2. **Aperture already has a working, shipped `QuerySpec` builder** (`web/src/query/`:
   `QueryBuilderView.tsx`, `querySpec.ts`, `planner.ts`, `GraphView.tsx` — v0.4.0+ on
   `origin/main`) that executes specs and renders/exports results. This is not a "build the UI"
   problem; it is "add chat next to a UI that already works."

The near-term goal is narrower than the eventual one: a **local** demo (this repo's synthetic
data) polished for a national meeting, not yet the VA/AWS production deployment a researcher will
eventually use. That later transition is real and already discussed, but is explicitly a
follow-on (see Non-Goals).

## Goals / Non-Goals

**Goals**
- A browser-based chat panel in Aperture, at full behavioral parity with `exon/chat.py`, reachable
  without an MCP client in the browser.
- One local command that boots Mosaic + Exon + Aperture together for the demo.
- Close the two real correctness gaps between Exon's and Aperture's `QuerySpec` shape and edge
  vocabulary before either side builds against the other.

**Non-Goals (explicit follow-ons, not addressed by this change)**
- VA/AWS production deployment: Bedrock governance/approval for routing researcher data through
  it, IAM credential ownership, packaging Exon as a real deployable (`pyproject.toml`, an image),
  and the `datahelix` solo-recipe wiring to run it there. All confirmed as a later, separate phase.
- Migrating Exon's turn-taking core into `BU-Neuromics/reel`. Checked directly: Reel is
  design-only (one commit, "seed," no code), part of a larger "BASS platform" joined via a
  `drylims` integration repo not present locally. `APERTURE_EXON_CONTRACT.md` already asked "is
  this Exon's job or Reel's" and answered "Exon now, Reel-shaped so a later migration is a
  translation, not a rewrite" — unchanged here. Worth remembering for later, not actioned now.
- Cost/abuse guardrails on the conversational surface, and conversation-as-provenance (a
  chat-produced saved view keeps the resulting `QuerySpec` but loses the conversation that
  produced it) — both already named as deferred in the original contract doc; still deferred.

## Decisions

### 1. Transport: a GraphQL mutation over the same handler, not browser-side MCP

Mosaic exposes `converseQuerySpec` as a mutation on its generated `Mutation` root, delegating to
the identical in-process handler `converse_query_spec` (the MCP tool) already calls. Precedent:
`hippoSchema`, an existing hand-written meta field on the generated `Query` root
(`mosaic/src/mosaic/graphql/resolvers.py`) — this is the same move one root over.

**Alternatives considered:**
- *Browser speaks MCP directly to `/mcp`.* Rejected: verified `datahelix`'s solo-recipe
  `nginx.conf` proxies only `/graphql`, `/health`, `/docs`, `/openapi.json` — no `/mcp` — and
  verified no CORS handling exists anywhere in Mosaic today. This path would need a new nginx
  location, SSE buffering configuration, CORS for local dev, and an MCP client added to the SPA
  bundle, to preserve a "one boundary protocol" purity Aperture's own ADR-0017 doesn't actually
  require ("one active data-plane endpoint," not "one wire protocol").
- *A dedicated BFF.* Rejected outright — Aperture's own ADR-0016 already rejects a BFF role
  ("Bridge" is the deferred name for that), and Aperture's SPA is architecturally a thin GraphQL
  pass-through by design (verified: `ScopedDataClient`/`scopedClient.ts`).

### 2. `QuerySpec` spelling: Aperture canonicalizes on Exon's (LinkML) spelling

Exon's spec (`anchor: "Sample"`, `edge: "donor"` — a plain slot name, forward-only today) and
Aperture's spec (`anchor: "samples"` — a collection id, `edge: "fwd:donor"`/`"rev:samples.donor"`
— a derived composite key) currently disagree. Aperture changes to store LinkML type + slot names
and resolve to its `CollectionModel`/`QueryEdge` internally at render time. Ships as `v2` with a
tolerant `v1` read for existing saved views (control-plane documents, ADR-0032).

**Rationale:** Aperture's own ADR-0035 states the artifact "must not fork by spelling." The
collection-id/derived-key spelling is a client-side introspection artifact — correct as internal
UI state, wrong as the shape of a shared, persisted, cross-system artifact. Exon's spelling is
also what Mosaic's `validate_query_spec`/`execute_query_spec` actually accept, so canonicizing
there means the URL-persisted `qs` is the same string the server takes, with no translation layer
anywhere.

**Alternatives considered:** Exon adopts Aperture's spelling (rejected — leaks client-derivation
artifacts into a server contract, and Exon's LLM grounding would have to teach a spelling the
server itself rejects); a translation shim inside the new mutation (rejected — introduces a third
spelling authority, and the saved `qs` in the URL still wouldn't match what `execute_query_spec`
takes).

### 3. Reverse edges: extend Exon's grounding, FK-backed only

`exon/spec_planner.py`'s `render_traversable_edges` currently offers only forward edges (fields
the anchor entity itself holds). Extend it to also offer single-valued FK-backed reverse edges —
mirroring what Aperture's own `planner.ts`'s `deriveEdges` already does client-side for the
manual builder.

**Rationale:** the contract document's own flagship conversational example — "show me the donors
of those samples instead" — is a reverse edge from a `Sample` anchor. Forward-only chat cannot
express the example the contract was written around.

**Explicitly excluded:** multivalued, relationships-table-backed reverse lookups (e.g.
`Workflow.input_samples`). This repo's own README already documents this as a real, deliberate
platform limitation — there is no GraphQL query to compensate against such a lookup, so offering
it as a chat edge would produce a spec that fails at validation or execution, not one that works.

### 4. Placement: a new `inspector`-slot layout, not a mode inside the query view

Add a `headerNavMainInspector` layout to Aperture's layout registry; the chat panel lives in the
declared `inspector` slot (ADR-0031), not welded into `QueryBuilderView`'s `main` content.

**Rationale:** ADR-0031 already declares the `inspector` slot and explicitly sanctions growing the
layout library ("a new hard-coded, tested template + a catalog entry"). Keeping chat at the shell
level, rather than inside one view, matches ADR-0021's stated eventual direction (in-app chat
editing config from inside Aperture generally) — a seam that's cheap to add now and expensive to
relocate later.

**Alternatives considered:** a mode toggle inside `QueryBuilderView` (rejected — welds an
app-level surface into one view, the opposite direction from ADR-0021's stated end state); a
separate `Ask` nav route (rejected — best short-term build cost, but hides the spec the chat is
producing behind a disclosure, and creates two query surfaces to reconcile).

### 5. Feature bar: full parity with `chat.py`

Turn-by-turn history, viewing/editing the live `QuerySpec`, rewind-and-edit a past turn via
`edit_turn_id` (later turns recompute or suspend, never silently dropped — ADR-0025 / contract
Decision 1), then running the resulting spec through Aperture's **existing** execution/render/
export path. No new execution logic — `QueryBuilderView`/`planner.ts` already do this.

**Rationale:** `conversational_orchestrator.py` already implements and tests the turn-list/
rewind/suspend bookkeeping. The panel is a client for existing, tested logic, not new logic — a
lighter, linear-only chatbox would mean building *less* than what's already shipped and proven.

### 6. Branch base: fresh off Aperture's `origin/main`

Not the locally-checked-out `spike/nl-graphql-query-explore` branch. Confirmed via `git show
--stat` that branch's only unique commit adds two non-code docs files (172 lines total,
`docs/nl-graphql-query-spike.md` + `docs/nl_graphql_spike_query.py`) — cherry-pick those onto the
new branch; nothing else needs preserving. Starting fresh inherits the entire shipped query
surface (builder, graph view, export, saved views, sort, identity) the spike branch predates.

### 7. Local launcher: extend `run-chat-demo.sh`, don't build a new one

Add Aperture's web dev server as a third service in this repo's existing script, reusing its
hardened preflight (`require_free_port` port-conflict detection naming the offending PID/argv,
`wait_for` with owner-PID verification, a cleanup trap on exit).

**Rationale:** verified the script has no other hardcoded sibling-repo path — it calls `mosaic`
off `PATH` — so the only new cross-repo assumption is one path/env var to Aperture's `web/`
checkout, no worse than what already exists. A new script inside Aperture's repo would either
duplicate this hardening or shell back into this one anyway; manual multi-terminal steps
reintroduce exactly the CLI fragility this whole effort exists to remove.

### 8. Run mode: `vite dev` now, a build/preview rehearsal before the meeting

**Rationale:** dev mode is the fastest iteration loop while the panel is still being built. But
dev mode bypasses the runtime-config overlay (`window.__APERTURE_CONFIG__`, set by the real
deployment's image entrypoint) that production depends on — at least one full `npm run build &&
npm run preview` run is required before the actual presentation so that path is exercised at
least once before it matters live.

### 9. Suspended-turn UI: inline + a glanceable banner

The affected turn gets an inline treatment (reusing `chat.py`'s own yellow "suspended" status
color) naming what it depended on, with re-word/dismiss actions, plus one small summary banner
above the input whenever any suspended turns exist, so a scrolled-past one is never missed.

**Rejected:** relocating suspended turns into a separate "needs attention" tray — weakens
ADR-0025's "flag, don't discard" into "flag, then relocate," and divorces the turn's original
wording from where the break happened.

### 10. In-flight waiting UI: typing indicator + real elapsed timer + cancel

A turn can legitimately take up to 60s (`MOSAIC_EXON_TIMEOUT` default). Show a typing indicator, a
**real** elapsed-time counter (not fabricated progress-stage text — Exon's call is one opaque HTTP
round trip with no real intermediate signal to report), and a cancel button. Input stays disabled
while a turn is in flight, since turns are strictly ordered and the server derives current state
from the full list — a race would corrupt it. Cancel-and-retry is explicitly sanctioned by
Mosaic's own timeout error message ("retrying the same utterance is safe").

**Rejected:** a bare typing indicator with no timer/cancel (a long silent wait reads as frozen,
worse live in front of a room); simulated staged progress text (fabricates internal state that
doesn't exist and can visibly desync from reality — e.g. still say "drafting" after the call has
already failed server-side).

### 11. Builder lock UI: greyed-out form + explicit reset

Once the first chat turn is sent, the manual criteria form greys out (stays visible, becomes
read-only) with an explanatory note, plus a "Clear conversation & edit manually" button that drops
the turn history and unlocks it.

**Rationale:** Mosaic's `converse_query_spec` endpoint asserts the wire `query_spec` agrees with
what it derives from `turns` and 400s on disagreement (contract Decision 9) — the lock is not
optional, only its presentation is. Since no conversation persistence exists regardless (contract
Decision 3 — a refresh already loses the transcript), resetting on exit loses nothing that
wouldn't already vanish.

**Rejected:** read-only with no reset (no in-app path back to manual editing — frustrating for a
live demo where hand-tweaking one thing is likely); "don't lock, last edit wins" (reopens exactly
the wire/turn divergence problem Decision 9 was written to prevent).

## Risks / Trade-offs

- **Two-repo release coordination.** The mutation (Mosaic) and the reverse-edge grounding (Exon,
  this repo) are independent and can land in parallel; Aperture's canonicalization must land
  before its own panel work, but neither blocks this repo's tasks. See `tasks.md` for the explicit
  ordering.
- **Aperture's `QuerySpec` v1→v2 migration touches saved views** (control-plane documents,
  ADR-0032). Owned entirely by Aperture's own repo/process — named here so it isn't lost, not
  designed here.
- **This proposal's Exon-side changes (reverse edges) change model behavior** that the harness
  should measure before/after, per decision in `tasks.md` Phase 2 — treated as a required task,
  not an afterthought, so "it works" is measured, not assumed.

## Migration Plan

1. Mosaic: add the `converseQuerySpec` mutation (external repo, tracked as an issue there).
2. This repo, in parallel: Exon reverse-edge grounding + harness multi-turn coverage.
3. This repo: extend `run-chat-demo.sh` for the local three-service launcher.
4. Aperture (external, sequenced): `QuerySpec` v2 canonicalization, then the inspector layout, then
   the panel itself (turn state, lock, suspended-turn and in-flight UI).
5. Doc fixups: `APERTURE_EXON_CONTRACT.md`'s two stale lines, at implementation time.

No rollback complexity: every piece here is additive (a new mutation alongside the existing MCP
tool; a new edge kind alongside forward edges; a new layout alongside the existing one; a new
script step alongside the existing two) — nothing existing is removed or made backward-
incompatible except Aperture's own `QuerySpec` v1→v2 migration, which carries its own tolerant read.

## Open Questions

- Exact wording/placement of the inspector-slot chat entry point relative to Aperture's existing
  nav (left to Aperture's own implementation, informational here).
- Whether Aperture's `QuerySpec` v2 migration needs an explicit one-time rewrite of existing saved
  views, or a permanent tolerant-read shim — Aperture's own call, not resolved here.
- Timing of the VA/AWS transition relative to this local milestone is not yet scheduled;
  deliberately left open per the user's own framing ("locally here THEN we will transition").
