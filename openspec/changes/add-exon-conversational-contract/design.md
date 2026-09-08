## Context

Aperture's planned chatbot MVP needs a way to collaboratively build a `QuerySpec` across
conversational turns. `add-mosaic-mcp-boundary` gives Exon a single-shot planning mode but no
notion of turns or state. A dedicated design session (recorded in full at
`APERTURE_EXON_CONTRACT.md`, repo root) worked out the contract; this document formalizes that
session's decisions into OpenSpec form. Two questions drove the session: whose job this actually
is (Exon's or Reel's), and how the browser should reach it given Aperture has no backend of its
own — both resolved with direct verification rather than assumption, detailed below.

## Goals / Non-Goals

**Goals**
- Let a user refine a `QuerySpec` conversationally, with every intermediate state visible and
  correctable, never silently guessed and left unverified.
- Ground the design in Aperture's and Reel's own already-accepted architecture rather than invent
  a competing model — a chat turn is exactly Reel's `Instruction` concept, elaborated by an LLM
  into typed ops and dry-run validated, whether or not Reel itself exists yet.
- Keep Exon's planning core a single core with two entry points (single-shot, from
  `add-mosaic-mcp-boundary`; turn-mode, from this change) rather than two competing services.
- Preserve every safety property `add-mosaic-mcp-boundary` already established: Mosaic validates
  before anything executes, the LLM never decides to execute, no write/mutation path.

**Non-Goals**
- **Building this in Reel.** Reel has zero code today; waiting on it blocks a needed MVP
  indefinitely. This change explicitly does not resolve whether Reel eventually inherits this
  contract as designed or arrives at something different once real implementation constraints are
  known (see Open Questions).
- **Growing the query language.** Reel's own op catalog (`filter · exists-related-filter ·
  distinct-values · group-by+count · pivot-grain · set-op · render-as-primitive`) is broader than
  what this MVP needs or what `QuerySpec`'s current code supports. Only `filter` and
  `exists-related-filter` are in scope; the rest stay deferred, consistent with
  `add-mosaic-mcp-boundary`'s own refusal to grow aggregation capability prematurely.
- **Historical/reproducibility pinning.** Reel's own design independently confirms Mosaic lacks the
  graph-level `asOf` query resolver a story-level watermark would need — this MVP inherits that gap
  rather than solving it.
- **Conversation persistence, auth, rate-limiting/cost guardrails, multi-user conversations.** Real
  concerns, explicitly out of scope for this MVP (see proposal.md's "What Changes").
- **Implementing anything inside `hippo` (Mosaic) or `aperture`.** This repo's OpenSpec authority
  stops at this repo's boundary; `mosaic-query-boundary-contract` states what this repo depends on,
  not what Mosaic's or Aperture's teams must build or when.
- **Designing the "suspended turn" UI affordance.** Reel's model specifies the *behavior* (flag,
  don't discard); the actual UI treatment is Aperture's to design.

## Decisions

### 1. Whose job this is: Exon hosts it now, shaped for Reel to inherit later

Aperture's accepted ADR-0035 states Reel's role almost verbatim: "Aperture owns the noun
[`QuerySpec`] and its execution; Reel composes instances of it." This MVP is a genuine subset of
that job. Rather than build it permanently into Exon (risking the same duplication this whole
architectural effort has been eliminating at every other layer) or block on Reel (zero code
today), Exon hosts the capability now using Reel's own vocabulary for a turn — read directly from
`instruction-path-model.md` and ADR-0001–0004:

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

Two things this direct read corrected versus an earlier, secondhand assumption: Reel's `State` is
a generic typed subgraph spec, broader than `QuerySpec`; and Reel's op catalog is broader than
`QuerySpec`'s current code. For this MVP, `State` concretely **is** `QuerySpec`, and the `ops`
vocabulary is restricted to `filter`/`exists-related-filter` only (Non-Goals). This is deliberate
narrowing in the same spirit Reel's own ADR-0003 prescribes for itself: general vocabulary, narrow
v1 implementation, so growth later is additive.

### 2. Transport: through Mosaic, never a direct browser-to-Exon call

Verified directly (not assumed): Aperture's `web/` React SPA has no backend of its own.
`ScopedDataClient` is a thin pass-through to Mosaic's GraphQL; even Aperture's own persisted state
(saved views, drafts) rides on Mosaic as `{kind, name, payload}` documents (ADR-0032), whose own
"Alternatives considered" section explicitly rejects "a dedicated control-plane service" as against
Aperture's architectural stance. A `src/aperture/` Python package exists but is a superseded early
prototype (its own `pyproject.toml`: "the CLI is superseded"), not a live service.

So this capability is reached exclusively through a new `converse_query_spec` MCP tool hosted by
Mosaic (extending `mosaic-query-boundary-contract`), which delegates server-to-server to Exon's
planning core. The browser's call surface stays uniform with how it already reaches everything
else, and LLM credentials/orchestration never touch the browser — consistent with
`scopedClient.ts`'s own stated principle.

### 3. State ownership: Aperture holds it, Exon's turn function is stateless

Aperture already has a state-carrier for `QuerySpec` — it rides the URL (`qs`) today. No new
session-holding service is needed in Exon. Each call is a pure function:
`(existing QuerySpec | null, prior turns, new utterance) → response`. This preserves the harness's
reproducibility methodology (`add-mosaic-mcp-boundary`'s Decision 7 rationale for keeping Exon's
planning core scriptable) and avoids Exon growing storage/session infrastructure it doesn't
otherwise need.

### 4. Wire contract: simple now, Reel-mapping in prose

Exon's actual response is `QuerySpec` + a natural-language message + a status + a turn `id` — not
Reel's full nested `Instruction{parents, ops, node_hash}` envelope. The correspondence to Reel's
model is documented (Decision 1) rather than implemented, so a future migration is a translation
layer, not a rewrite, without building infrastructure for a consumer (Reel) that cannot yet
validate the shape is right. The turn `id` is included specifically because of Decision 5
(rewind-and-edit) — Aperture needs to address a specific prior turn when asking Exon to redo from
it.

Response is discriminated: `proposal` (an updated, already-validated `QuerySpec` plus a
natural-language restatement of the current interpretation) or `clarification` (no spec change, a
question back). Default to `proposal` whenever a reasonable, visible, correctable interpretation
exists; use `clarification` only for genuine ambiguity — a contradictory constraint, or an enum
value that doesn't resolve even after Mosaic's validation-error-driven retry.

### 5. Edit semantics: rewind-and-edit a specific earlier turn, with recompute-and-suspend

The user can go back to an earlier turn, change it, and turns after it recompute against the
edited state. A later turn that no longer makes sense given the edit is marked `suspended` and
surfaced to the user to re-prompt — never silently dropped or silently reinterpreted. This mirrors
Reel's own ADR-0004 ("recompute-with-suspend, not discard") exactly, chosen deliberately over
simpler linear-only accumulation because the richer behavior was judged worth the added scope for
this MVP.

### 6. Anchor pivots always re-run fresh, never lock onto a frozen result set

If a turn changes which entity type the conversation is about (e.g. pivoting from Sample to
Donor), the new `QuerySpec` re-derives the relationship as a filter rule against current data,
never as a reference to the exact previously-matched record set. Simpler, requires no new
hand-off/pinning mechanism, and reflects current data rather than a stale snapshot from earlier in
the conversation.

### 7. No conversation persistence for this MVP

A page refresh loses the chat transcript; only the resulting `QuerySpec` survives, via Aperture's
existing URL mechanism. Matches Aperture's own honest-degradation posture (ADR-0029) rather than
introducing a new persisted document kind before the core conversational loop is proven.

### 8. Server-to-server wire contract: Exon exposes an HTTP endpoint; Mosaic validates the final candidate itself

Decision 2 says `converse_query_spec` "delegates server-to-server to Exon's planning core" but
doesn't say how. Three shapes were possible: Exon exposes its own HTTP endpoint that Mosaic calls;
Mosaic imports Exon's Python planning code directly; Mosaic shells out to it as a subprocess. The
latter two would put a specific consumer's planning code — and `litellm`, and provider credentials
— inside `datahelix-mosaic`, a generic runtime published for any LinkML schema with transport
extras opted into per deployment. That's the same three-way capability duplication ADR-0009 exists
to eliminate, just pointed the other direction; the subprocess option has the same coupling problem
plus a worse operational story. So: **Exon runs its own lightweight HTTP endpoint; Mosaic's
`converse_query_spec` tool is configured with its URL and calls out over plain HTTP.**

**Config surface.** `MOSAIC_EXON_URL` (unset by default). When unset, `converse_query_spec` is not
registered on Mosaic's MCP server at all — a deployment with no Exon configured shouldn't advertise
a tool it can't serve, exactly like `--mcp`/`MOSAIC_SERVE_MCP` already being conditional on the
`mcp` extra. A CLI flag threading through to this env var (mirroring `--mcp`) is left to whoever
implements Phase 1; only the env var name and the "absent → tool absent" behavior are part of this
contract.

**Request** (`POST` to the configured URL, one endpoint, JSON body):
```
{
  "utterance":    "<new NL turn text>",
  "query_spec":   <QuerySpec | null>,   # current state; null on the first turn
  "turns":        [<Turn>, ...],        # full prior turn history, oldest first
  "edit_turn_id": "<id> | null"         # set only when redoing an earlier turn (Decision 5);
}                                        # null = append a new turn after the last one
```

**Turn** (used both in the request's history and as the response's payload):
```
{
  "id":         "<stable turn id>",
  "utterance":  "<the NL input for this turn>",
  "status":     "proposal" | "clarification" | "suspended",
  "query_spec": <QuerySpec | null>,     # null when status is clarification or suspended
  "message":    "<NL restatement or clarifying question>"
}
```

**Response:**
```
{
  "turn":               <Turn>,         # this call's result (a new turn, or the redone one)
  "suspended_turn_ids": ["<id>", ...]   # turns invalidated by an edit; [] when not editing
}
```

This is the concrete shape Decision 3 (pure-function signature) and Decision 4 (discriminated
`proposal`/`clarification`) describe only in prose — #186's implementer needs field names, not just
intent.

**Validation stays authoritative in Mosaic, and this does not create a call cycle.** Exon's own
turn endpoint may call Mosaic's `validate_query_spec`/`mosaic://capabilities` as an MCP client
during its own generation retry loop — exactly the relationship the single-shot planner
(`add-mosaic-mcp-boundary`) already has with Mosaic, unchanged. Separately, `converse_query_spec`
validates whatever `QuerySpec` Exon's HTTP response carries **in-process** — calling the validator
function directly, not over MCP, since it's the same Mosaic process that already hosts it — before
ever labeling a turn `proposal`. This is defense-in-depth, not busywork: it's what keeps "Mosaic
validates before anything executes" true even if Exon's own check is stale, buggy, or bypassed, and
it never calls back into `converse_query_spec` itself, so there's no cycle. This also makes
explicit what Decision 4 only implied: `converse_query_spec` never calls `execute_query_spec` — a
`proposal` is always handed back for a separate, explicit `execute_query_spec` call once a human
confirms it, preserving "the LLM never decides to execute" (Goals) for this tool too.

**Failure semantics.** Exon unreachable, a timed-out request, or a response that still fails
Mosaic's re-validation after Exon's own retry loop already ran: `converse_query_spec` returns a
third top-level turn status, `"error"`, with `query_spec: null` and a `message` describing the
failure — kept inside the same discriminated envelope Aperture already has to branch on, rather
than a bare protocol-level tool exception. Mosaic's HTTP call to Exon should carry its own request
timeout (suggest ~60s), sized for the hosted-model latency this MVP actually targets (Bedrock
Haiku, per this session's earlier migration off local Ollama) — not `planner.py`'s existing
`REQUEST_TIMEOUT`, which is tuned far higher for slow local/Ollama generation and would make a chat
turn feel broken if reused here as-is.

### 9. What "existing QuerySpec" means when the wire's `query_spec` and the turn history could diverge

Decision 8's request carries `query_spec` as its own top-level field, separate from `turns` — and
Decision 3's rationale for that (Aperture already tracks the current draft independently, via its
URL) implies they are not always guaranteed to agree: Aperture's own point-and-click `QuerySpec`
builder (pre-existing, unrelated to chat) could in principle edit the same URL state a chat
conversation is also building, with no corresponding turn recording it.

**Whether that can actually happen is Aperture's own UI call, not this repo's** (Non-Goals already
name "designing the suspended-turn UI affordance" as Aperture's; this is the same kind of decision,
one level earlier). The direction, as of this design pass: **for now, Aperture locks its
point-and-click panel once a chat conversation begins** — pick one input method per conversation,
not both at once. Unlocking that later (letting both edit the same draft concurrently) is an
explicitly named possibility, not a closed door.

Given that, Exon's endpoint does not need to *resolve* a genuine divergence today — the lock means
one shouldn't exist. But "assume it can't happen and ignore the field" would silently rot: nothing
would notice if Aperture's lock is ever loosened without Exon being told, and the wire's own
`query_spec` field would sit unused and untested indefinitely. Instead: the endpoint computes the
current draft from `turns` (unchanged from `conversational_orchestrator.append_turn`'s existing
behavior) **and asserts it equals the wire's stated `query_spec`**, rejecting the request (400-level,
naming both values) if they disagree. This is a checked invariant standing in for the lock, not a
duplicate implementation of it — Exon has no notion of "UI panels" and never will; it only knows
whether the two numbers it was given agree.

**The unlock hook**: `conversational_orchestrator.append_turn` takes an optional
`existing_query_spec` override (falling back to today's turns-derivation when omitted, so every
already-shipped test and behavior is unchanged). The day Aperture's lock is lifted, the only change
needed is in the HTTP layer: stop asserting equality, and pass the wire's `query_spec` through as
the override instead. No change to `conversational_orchestrator.py` itself, no wire-contract change
(the field was always there), no change to `edit_turn` (its redo step rewinds to a past point,
`turns[:idx]`, which the wire's *current*-state field was never the right input for regardless).

## Risks / Trade-offs

- **Exon absorbing a role Aperture's own architecture assigns to Reel** is a real, named
  divergence from the ADR-0035 seam, not a neutral technical choice — mitigated by shaping the
  contract in Reel's own vocabulary (Decision 1), but that mitigation is a design intention, not a
  guarantee; nothing forces a future migration to actually happen.
- **Rewind-and-edit (Decision 5) is more scope than a simpler linear-accumulation MVP would need**
  — chosen deliberately, but it means Aperture must design a real UI affordance for editing a
  specific turn and surfacing suspended turns, which this change does not specify (Non-Goals).
- **`converse_query_spec` is a new dependency on Mosaic** beyond what `BU-Neuromics/mosaic#177`
  already describes — tracked as `BU-Neuromics/mosaic#186` (filed alongside the #177 split, after
  this proposal's earlier draft). Decision 8 now specifies its wire contract; posting it to #186 is
  the remaining handoff, not a filing step.

## Migration Plan

Additive only, and blocked in the same direction `add-mosaic-mcp-boundary` already established:
Mosaic's `converse_query_spec` must exist before Exon's turn-mode entry point can be implemented,
which must exist before Aperture's chat UI can be built. No data migration. Implementation proceeds
only after this proposal is reviewed and approved, per the standing instruction for this session.

## Open Questions

1. **Whether `QuerySpec`'s `columns`/`explode` mechanism can be scoped to match a
   `RelatedCondition`'s own sub-criteria on the same edge** — still unresolved even in ADR-0035
   itself ("field-level schema lives with the implementation"). Directly relevant to any
   "distinguish not-checked from none-found" style question arising conversationally. Owned by
   whoever implements `ColumnSpec` server-side (Mosaic) and client-side (Aperture); not resolved
   here.
2. **Exact UX for suspended turns** — Reel's model specifies the behavior (flag, don't discard),
   not the UI treatment. Aperture's own team's call.
3. **Whether Reel, once built, actually adopts this contract** as designed, or arrives at something
   different once real implementation constraints are known. This proposal is a best-effort bridge,
   not a guarantee of future compatibility.
4. ~~Where the Mosaic-side `converse_query_spec` work gets tracked~~ — **resolved**: tracked as
   `BU-Neuromics/mosaic#186` (filed alongside the #177 split, after this open question was first
   written). Decision 8 now specifies the wire contract (request/response shape, `MOSAIC_EXON_URL`
   config, validation ownership, failure semantics) that #186's implementer needs — posting it as a
   comment on #186 is the remaining handoff.
