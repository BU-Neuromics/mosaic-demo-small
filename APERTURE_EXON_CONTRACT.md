# Aperture ↔ Exon: the conversational query contract

**Status (2026-09-07): formalized and Exon's side implemented.** This document began as the
output of a design session (2026-08-2x) working out how Aperture's planned chatbot-style
interface should talk to Exon, now that Exon is no longer a safety-critical validator/executor
(that moves to Mosaic — see `openspec/changes/add-mosaic-mcp-boundary/`) but a harness and
reference conversational-planning service sitting between Aperture and Mosaic's new MCP
boundary. It was formalized into `openspec/changes/add-exon-conversational-contract/`
(`design.md` carries a ninth decision beyond the four below, resolved during implementation —
see "State ownership and the wire contract" further down). Of the three repos in the dependency
graph below, only Exon's turn-taking planning core (this repo) is built and tested end-to-end
over real HTTP: `exon/conversational_planner.py`, `exon/conversational_orchestrator.py`,
`exon/conversational_server.py` — see `exon/README.md`'s "Conversational mode" section for what
shipped and what's still deferred. Mosaic's `converse_query_spec` MCP tool (tracked upstream as
`BU-Neuromics/mosaic#186`) and Aperture's chat UI remain unbuilt, external to this repo.

## The MVP being designed for

A chatbot-like interface in Aperture that lets a user collaboratively define a set of Mosaic
entities in natural-language conversation with an LLM, and ultimately retrieve and display those
entities as a results view in Aperture — e.g. "show me hippocampus samples" → "only from donors
over 60" → a table of matching samples.

## How this relates to `add-mosaic-mcp-boundary`

That change already establishes: Mosaic hosts the MCP boundary (schema/capability resources,
`validate_query_spec`/`execute_query_spec` tools, a `construct-query-spec` Prompt, actionable
per-criterion validation errors); Exon becomes an MCP client of it; `QuerySpec` (Aperture's
ADR-0035 artifact) is the canonical typed query IR, replacing `QueryPlan`. This document builds on
that — it does not change any decision already recorded there — and adds one more capability on
top: **Mosaic also hosts a `converse_query_spec` MCP tool**, which delegates server-to-server to
Exon's planning core, giving Aperture a conversational way to build a `QuerySpec` instead of only
a single-shot or hand-built one.

## Is this Exon's job, or Reel's?

Aperture's own accepted ADR-0035 defines Reel's role in almost exactly these words: "Aperture owns
the noun [`QuerySpec`] and its execution; Reel composes instances of it." Reel's own (unbuilt)
design already sketches a richer version of this exact loop — typed `Instruction`s applied
turn-by-turn, with forking, branching, and historical watermark-pinning. This MVP is a genuine
subset of Reel's stated job, requested before Reel has any code.

**Resolution: Exon hosts this now, deliberately shaped so Reel can inherit it later — not a
permanent home, not built inside Reel.** Concretely, this means adopting Reel's own vocabulary for
the shape of a "turn" (see below) even though the implementation lives in Exon, so a future
migration is a translation, not a rewrite.

### Grounding in Reel's actual design (verified directly, not from a summary)

Reel's `instruction-path-model.md` and ADR-0001–0004 give a precise model:

```
Instruction {
  id
  parents: [state_id]                          # ≤1 in v1 — linear only
  source:  chat | ui_event | agent | replay
  raw:     <NL utterance | UI gesture payload>  # canonical, editable
  ops:     [Op]                                 # derived, inspectable, disposable
  status:  valid | invalid | suspended
}
```
A turn is "raw intent, elaborated by the LLM into one or more typed ops, then dry-run-validated
before it can apply" — which is Exon's own reject-don't-approximate discipline already, just named
in Reel's vocabulary.

Two corrections this made to our earlier assumptions:

- **`State` in Reel's model is broader than `QuerySpec`** — a generic typed subgraph spec
  (`focal_type`, `predicates`, `grain`), of which a `QuerySpec`-style cohort is one lens. Reel's
  own op catalog (`filter · exists-related-filter · distinct-values · group-by+count ·
  pivot-grain · set-op · render-as-primitive`) is broader than what `QuerySpec`'s current code
  supports.
- **For this MVP, `State` = `QuerySpec` concretely**, and the `ops` vocabulary is restricted to
  **`filter` and `exists-related-filter` only** (mapping directly to `QuerySpec`'s
  `FieldCondition`/`RelatedCondition`). `distinct-values`, `group-by+count`, `pivot-grain`, and
  `set-op` are explicitly deferred — consistent with `add-mosaic-mcp-boundary`'s existing refusal
  to grow the query language prematurely.

Reel's design also confirms an already-recorded non-goal: it names a **graph-level `asOf` query
resolver as a missing Mosaic capability**, needed for its own reproducibility story and not yet
built. This MVP inherits the same gap and makes no historical/reproducibility promise.

## Architecture

```
Aperture (browser, no backend of its own)
   │  calls Mosaic only — never Exon directly
   ▼
Mosaic — hosts `converse_query_spec` MCP tool
   │  delegates server-to-server
   ▼
Exon — planning core (turn-taking logic)
   │  validates via Mosaic's own validate_query_spec before returning anything
   ▼
Mosaic — the same MCP boundary, now validating/executing
```

**Why the browser talks only to Mosaic, never to Exon directly:** verified that Aperture has no
backend service of its own — the `web/` React SPA's `ScopedDataClient` is a thin pass-through to
Mosaic's GraphQL, and even its own persisted state (saved views, drafts) rides *on Mosaic* as
documents (`ADR-0032`), not a bespoke service — that ADR explicitly rejects "a dedicated
control-plane service" as against Aperture's own architectural stance. A `src/aperture/` Python
package exists but is a superseded early prototype (its own `pyproject.toml`: "the CLI is
superseded"), not a live service. Routing through Mosaic keeps the browser's call surface uniform
with how it already reaches everything else, and keeps LLM credentials and orchestration off the
browser entirely (`scopedClient.ts`'s own stated principle).

## State ownership and the wire contract

- **Aperture holds state; Exon's turn function is stateless.** Aperture already has a
  state-carrier for `QuerySpec` (`qs` rides the URL today) — no new session-holding service is
  needed in Exon. Each call is `(existing QuerySpec | null, prior turns, new utterance) →
  response`.
- **Wire shape stays simple now; the Reel mapping is documented, not literally implemented.**
  Exon's actual response is `QuerySpec` + a natural-language message + a status + a turn `id` —
  not Reel's full nested `Instruction{parents, ops, node_hash}` envelope. The correspondence is
  1:1 in spirit (this doc *is* that mapping), so migrating to Reel later is a translation layer,
  not a rewrite. The turn `id` is included because of the edit-semantics decision below —
  Aperture needs to be able to say "redo from this specific turn."
- **Response is discriminated: `proposal` vs. `clarification`.** Default to proposing a visible,
  correctable `QuerySpec` update; fall back to asking a clarifying question only on genuine
  ambiguity (contradictory constraints, an enum value that doesn't resolve).
- **Resolved during implementation: what the wire's `query_spec` field means when it could
  diverge from the turn history.** Since Aperture tracks the current draft independently (its
  URL) as well as sending it on the wire, the two could in principle disagree. As implemented:
  Aperture locks its point-and-click builder while a chat is active, so they shouldn't diverge —
  and Exon's endpoint asserts that invariant (400-level, naming both values, on disagreement)
  rather than silently trusting either side. The unlock path, if that lock is ever lifted, is a
  change to the HTTP layer alone (stop asserting equality, pass the wire value through as an
  override); the orchestrator already exposes that override and needs no change itself.

## Validation and execution

- **Design intent: Exon validates against Mosaic before ever returning to Aperture.** Every
  candidate `QuerySpec` was meant to be checked via Mosaic's `validate_query_spec` first, feeding
  a validation failure back into Exon's own retry loop (using the actionable per-criterion errors
  and the `construct-query-spec` Prompt already specified in `add-mosaic-mcp-boundary`) rather
  than surfacing a raw error to the user. **As shipped, this retry loop does not exist yet**
  (`add-exon-conversational-contract` task 2.3, deferred as its own increment) — Exon's endpoint
  today returns a `proposal` that is shape-conforming to its tool-call schema but not re-validated
  against live data. The authoritative check that actually guarantees "Aperture never receives an
  invalid `QuerySpec`" lives on Mosaic's side: `converse_query_spec` re-validates in-process before
  ever labeling a turn `proposal` (design.md Decision 8, task 1.2) — and that tool doesn't exist
  yet either (`BU-Neuromics/mosaic#186`, open). Until both pieces ship, nothing in this path
  actually enforces that guarantee end-to-end.
- **The LLM never decides to execute.** Exon's contract ends at "here's a validated `QuerySpec`."
  Fetching and rendering the results view is Aperture's own existing/planned execution path,
  triggered by an explicit user action — "model plans, deterministic code executes."

## Four resolved design decisions

1. **Edit semantics: rewind-and-edit a specific earlier turn**, not just linear accumulation. The
   user can go back to an earlier message, change it, and downstream turns recompute — if a later
   turn no longer makes sense given the edit, it's flagged for the user to re-prompt, never
   silently dropped (Reel's "suspend, don't discard" behavior, ADR-0004). This is why each turn
   needs an `id` in the wire contract above.
2. **Anchor pivots always re-run the rule fresh against current data.** If the user pivots to a
   different entity type mid-conversation ("show me the donors of those samples instead"), the new
   query re-derives the relationship as a filter rule ("donors who have a hippocampus sample")
   rather than locking onto the exact previously-matched result set. Simpler, no new hand-off
   plumbing, and matches current data rather than a frozen snapshot.
3. **No conversation persistence for MVP.** A page refresh loses the chat transcript. The thing
   that actually matters long-term — the resulting `QuerySpec` — still survives via Aperture's
   existing URL mechanism. Matches Aperture's own honest-degradation posture (ADR-0029) rather
   than adding a new persisted document kind before the core loop is proven.
4. **Wire contract stays simple, Reel-mapping stays in prose** (see above) — not a literal
   `Instruction`/`Op` envelope in Exon's actual API today.

## Explicit non-goals for this MVP

- No aggregation ops (`group-by+count`, `distinct-values`), no `pivot-grain`, no `set-op` — only
  `filter` and `exists-related-filter`.
- No multi-user/shared conversations — single user per conversation.
- No story branching/forking (Reel's tree/DAG topology) — linear only, matching Reel's own v1
  scoping.
- No historical/reproducibility pinning (`asOf`) — the graph-level resolver this would need
  doesn't exist in Mosaic yet (confirmed via Reel's own design, which flags the same gap).
- No auth model, no rate-limiting/cost guardrails on the conversational surface — real concerns,
  explicitly deferred, not designed here.
- No requirement that Aperture change its existing non-chat query-builder path — this is an
  additional way to populate a `QuerySpec`, not a replacement for the existing builder UI.

## Cross-repo dependency graph

```
Mosaic (hippo)         — needs `converse_query_spec` MCP tool
                          (extends add-mosaic-mcp-boundary Phase 1; tracked as mosaic#186 — open)
        │  blocks
        ▼
Exon (mosaic-demo-small) — turn-taking planning core — SHIPPED, tested standalone over real HTTP
                            (only the full Aperture → Mosaic → Exon path is blocked on mosaic#186)
        │  blocks
        ▼
Aperture                 — chat UI, calling Mosaic's converse_query_spec — not started
                            (blocked on mosaic#186 shipping, not on Exon: Exon's turn function
                            already exists and is reachable)
```

Three repos now, one more than `add-mosaic-mcp-boundary`'s two (Mosaic + Exon). Exon's own
planning core needed only what `add-mosaic-mcp-boundary` Phase 1 already shipped
(`mosaic://capabilities`, `validate_query_spec`) and didn't wait on mosaic#186 — see
`openspec/changes/add-exon-conversational-contract/tasks.md`'s Phase 2 header for the corrected
dependency reasoning. Only the full end-to-end path (a real Aperture chat calling a real Mosaic
`converse_query_spec` calling this repo's Exon) remains blocked on mosaic#186 shipping.

## Open questions not yet resolved

- Whether `QuerySpec`'s `columns`/`explode` mechanism can be scoped to match a
  `RelatedCondition`'s own sub-criteria on the same edge — still unresolved even in ADR-0035
  itself ("field-level schema lives with the implementation"), and directly relevant to any
  "distinguish not-checked from none-found" style question in a conversational flow.
- Exact UX for "suspended" turns (decision 1 above) — Reel's model specifies the *behavior*
  (flag, don't discard), not the UI treatment; Aperture would need to design that affordance.
- Whether Reel, once built, actually adopts this contract as designed, or arrives at something
  different once real implementation constraints are known — this document is a best-effort
  bridge, not a guarantee.
