# Change: Add a conversational, turn-taking planning capability to Exon for Aperture's chatbot MVP

## Why

Aperture's planned MVP is a chatbot-like interface that lets a user collaboratively define a set
of Mosaic entities in natural-language conversation, ultimately retrieving and displaying them as
a results view. `add-mosaic-mcp-boundary` already gives Exon a single-shot planning mode (one
instruction in, one validated `QuerySpec` out, via Mosaic's `validate_query_spec`/
`execute_query_spec`), but a single-shot call cannot support "collaboratively define" — there is
no way to say "only from donors over 60" as a follow-up to "show me hippocampus samples" without a
notion of turns, state, and correction.

This change adds that conversational capability to Exon, deliberately grounded in Aperture's own
already-accepted architecture rather than invented from scratch:

- Aperture's ADR-0035 states plainly that composing instances of `QuerySpec` across turns is
  **Reel's** job, not Aperture's or Exon's — but Reel has zero code today and this MVP is needed
  now. Rather than build a competing engine permanently or wait on an empty repository, this
  change has Exon host the capability now, **deliberately shaped in Reel's own vocabulary** (its
  `Instruction`/`Op`/`State` model, read directly from `instruction-path-model.md` and
  ADR-0001–0004, not from a secondhand summary) so a future handoff to Reel is a translation, not
  a rewrite.
- Aperture has no backend service of its own — verified directly: its `ScopedDataClient` is a thin
  GraphQL pass-through, and even its own persisted state rides on Mosaic as documents (ADR-0032),
  which explicitly rejects "a dedicated control-plane service" as against Aperture's architectural
  stance. So the browser must reach this new capability through Mosaic, never through a bespoke
  Exon-facing call — consistent with Aperture's `scopedClient.ts` principle that the browser should
  not own LLM credentials or orchestration.

Full rationale and the resolved design decisions are recorded in `APERTURE_EXON_CONTRACT.md` at
the repo root, produced by a dedicated design session; this proposal formalizes that document into
an OpenSpec change.

## What Changes

- **New `exon-conversational-planner` capability**: a stateless turn function —
  `(existing QuerySpec | null, prior turns, new utterance) → response` — layered on top of Exon's
  existing single-shot planning core, not a second, separate service. Each turn is validated
  against Mosaic's `validate_query_spec` before ever being returned; the LLM never decides to
  execute. Response is discriminated (`proposal` — an updated, validated `QuerySpec` plus a
  natural-language restatement — or `clarification` — a question back, no spec change). The MVP
  operation vocabulary is restricted to `filter` and `exists-related-filter` (Reel's own broader
  op catalog — `distinct-values`, `group-by+count`, `pivot-grain`, `set-op` — stays out of scope,
  consistent with `add-mosaic-mcp-boundary`'s refusal to grow the query language prematurely).
- Supports **rewind-and-edit of a specific earlier turn**: each turn carries an `id`; editing an
  earlier turn recomputes turns after it, and any later turn that no longer makes sense given the
  edit is flagged as suspended for the user to re-prompt — never silently dropped, matching Reel's
  own "recompute, don't discard" behavior (ADR-0004).
- **Anchor pivots** (switching which entity type a conversation is about) always re-run the new
  rule fresh against current data; they never lock onto a frozen prior result set.
- **No conversation persistence** in this MVP — a page refresh loses the transcript; the resulting
  `QuerySpec` still survives via Aperture's existing URL-based state mechanism.
- **Extends `mosaic-query-boundary-contract`** (the external-dependency contract capability from
  `add-mosaic-mcp-boundary`) with one more dependency: a `converse_query_spec` MCP tool, hosted by
  Mosaic, delegating server-to-server to Exon's planning core — the browser's only path to this
  capability.
- **No implementation in this change** — proposal, design, spec deltas, and tasks only, per the
  standing "create the OpenSpec only, then stop for review" instruction. Nothing in Mosaic's or
  Aperture's own repositories is implemented here.

## Impact

- **Affected specs (this repo)**: `exon-conversational-planner` (ADDED), `mosaic-query-boundary-
  contract` (ADDED requirement, extending the capability `add-mosaic-mcp-boundary` already
  introduces).
- **Affected code (this repo, blocked on Mosaic's `converse_query_spec` existing)**: a new
  turn-taking entry point into Exon's planning core, sitting alongside (not replacing) the
  single-shot planner from `add-mosaic-mcp-boundary`.
- **External dependencies, not implemented by this change**: Mosaic gaining a `converse_query_spec`
  MCP tool (extends the same Phase 1 surface as `BU-Neuromics/mosaic#177`, not yet filed as its own
  issue); Aperture building the chat UI that calls it — both owned by their own repos/teams.
- **Explicitly not required**: any change to Aperture's existing non-chat `QuerySpec` builder path,
  which continues to work unmodified.
