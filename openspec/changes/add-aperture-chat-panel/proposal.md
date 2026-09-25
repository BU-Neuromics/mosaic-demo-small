# Change: Add a conversational chat panel to Aperture, wired to Mosaic's `converse_query_spec`

## Why

Exon's conversational planning core (`add-exon-conversational-contract`) and Mosaic's
`converse_query_spec` MCP tool (`BU-Neuromics/mosaic#186`, shipped) already implement the whole
turn-taking loop end to end — but the only client that exists is a terminal chat
(`exon/chat.py`/`run-chat-demo.sh`), because Mosaic exposes the capability over MCP, which
Aperture's browser SPA cannot reach without new transport plumbing, and Aperture's own
`QuerySpec` artifact spells `anchor`/edge names differently than Exon's does. The goal driving
this change is concrete: a researcher opening Aperture in a browser and chatting a query the way
`chat.py` already lets you do on the command line, polished enough to demo at a national meeting
— locally, against this repo's own synthetic Mosaic instance, not yet the eventual VA/AWS
production deployment.

This proposal formalizes a long design discussion (session log available on request) into the
concrete decisions needed to close that gap, split across what this repo owns directly (Exon's
grounding, the local launcher, harness coverage) and what two external repos (Mosaic, Aperture)
need to do to meet it — tracked here as dependency contracts and informational tasks, the same
pattern `add-exon-conversational-contract` already used for its own Phase 1/Phase 3.

## What Changes

**Owned by this repo:**
- Extend Exon's turn-taking grounding (`exon/spec_planner.py`'s `render_traversable_edges`) to
  offer FK-backed single-valued **reverse** relationship edges, not just forward ones — needed to
  express the contract's own flagship example ("show me the donors of those samples instead").
  Multivalued, relationships-table-backed reverse lookups (e.g. `Workflow.input_samples`) stay
  unoffered — no GraphQL exposure exists to compensate against them.
- Extend the eval harness to measure **multi-turn conversational sequences** (including a
  rewind-and-edit/suspend fixture), not only independent single-shot calls, and require a
  before/after fingerprint run across the reverse-edge grounding change above.
- Extend `run-chat-demo.sh` to start and supervise **Aperture's web client** as a third managed
  service alongside Mosaic and Exon, reusing its existing preflight/cleanup hardening, so the
  local demo is one command.
- Fix `APERTURE_EXON_CONTRACT.md`'s two stale claims (mosaic#186 called "open"; the end-to-end
  validation guarantee called "unenforced") — both shipped.

**Tracked as an external dependency contract (Mosaic, `../mosaic`):**
- Mosaic exposes the same in-process `converse_query_spec` handler as a GraphQL mutation
  (`converseQuerySpec`), registered under the same `MOSAIC_EXON_URL`-configured condition as the
  existing MCP tool — so Aperture's browser can reach it over the `/graphql` endpoint it already
  uses, with no MCP client, SSE handling, or new CORS configuration.

**Informational only, owned by Aperture's own repo/ADR process (`BU-Neuromics/aperture`), not
implemented or spec'd by this change:**
- Canonicalize `QuerySpec`'s `anchor`/`edge` spelling onto Exon's LinkML type/slot names (v1→v2,
  tolerant read for saved views).
- Add an `inspector`-slot layout (`headerNavMainInspector`) hosting the chat panel, built on a
  fresh branch off `origin/main` (not the stale `spike/nl-graphql-query-explore` checkout).
- Build the panel itself to full parity with `chat.py`: turn history, spec view, rewind-and-edit,
  run; plus three UI-feel decisions (suspended-turn inline+banner treatment, in-flight
  typing-indicator+timer+cancel, and the builder-lock/reset affordance) — see `design.md`.
- Run mode: `vite dev` during active build-out, with a required `npm run build && npm run
  preview` rehearsal before the actual presentation.

## Impact

- **Affected specs (this repo):** `exon-conversational-planner` (ADDED — reverse-edge grounding),
  `mosaic-query-boundary-contract` (ADDED — GraphQL mutation transport; external dependency,
  extends the capability `add-exon-conversational-contract` already introduced there),
  `exon-context-harness` (ADDED — multi-turn conversational coverage), `conversational-demo-
  launcher` (ADDED, new capability — the three-service local launcher).
- **Affected code (this repo):** `exon/spec_planner.py`, `run-chat-demo.sh`,
  `evals/questions.yaml`/harness fixtures, `APERTURE_EXON_CONTRACT.md`.
- **Dependency:** this change extends capabilities `add-exon-conversational-contract` introduced,
  which is itself still open (11/17 tasks; its own task 2.9 — writing the archived spec files —
  is not yet done). Sequencing note in `tasks.md`.
- **External, not implemented here:** Mosaic (`../mosaic`) gaining the `converseQuerySpec`
  mutation; Aperture (`BU-Neuromics/aperture`) building the chat panel, canonicalizing `QuerySpec`,
  and adding the inspector layout — tracked via Aperture's own ADR + GitHub issue process, per its
  existing convention (no `openspec/` directory there).
- **Explicitly out of scope, named rather than silently dropped:** the VA/AWS production
  transition (Bedrock governance approval, IAM credential ownership, packaging Exon as a proper
  deployable rather than a bare directory, the `datahelix` solo-recipe wiring for a real
  deployment) and migrating Exon's turn-taking core into `BU-Neuromics/reel` (design-only today,
  no code; `APERTURE_EXON_CONTRACT.md`'s existing "Exon now, Reel-shaped for later" answer to
  "whose job is this" stands unchanged by this proposal). Also named, not owned here: Aperture's
  own consumer-driven GraphQL contract test (`contracts/hippo-graphql-contract.json`) needs a new
  assertion for the mutation — that's Aperture's repo's own follow-up.
