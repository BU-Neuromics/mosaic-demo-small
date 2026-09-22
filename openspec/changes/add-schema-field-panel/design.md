## Context

Aperture's query page is a three-track CSS grid: `232px | 400px | minmax(0,1fr)` — nav,
conversational composer, main panel. The main panel only ever holds content when a
**query** exists, because that is all the page could produce when it was laid out.

`add-schema-discovery-for-query-building` gave it a second outcome — an answer that names
fields and produces no query — and that outcome has nowhere to go.

## Goals / Non-Goals

**Goals**
- A metadata answer produces a screen that looks like it did something.
- A user can act on a named field without typing another turn.
- Nothing is stored, generated, or capable of drifting.

**Non-Goals**
- Any change to the shell, nav, visual system, or collections browsing.
- Reintroducing a queryable representation of the schema in any form.
- Server-side field projection (mosaic#215).

## Decisions

### Decision 1: The empty state becomes the schema

`.query-blank` — a decorative CSS schematic reading "Nothing run yet" — is replaced by the
anchor entity's fields.

The claim behind it: **"nothing to show" was never true.** The page always knows the
schema; it was rendering a drawing of a graph instead of the graph. A user who has not yet
asked anything is exactly the user who most needs to see what is available.

**Alternative considered: let the composer expand to full width when there is no spec.**
Rejected — it gives prose more room to be prose. The answer is still only text, and the
user still cannot act on it.

**Alternative considered: a persistent Answer region above Results.** Rejected — it spends
vertical space on a region that is usually empty and makes the results area permanently
shorter.

### Decision 2: Read `hippoSchema`, because `__schema` does not carry what is needed

Verified against the live endpoint: `__schema` returns a **type** description and
`description: null` on **every** field. `hippoEntityType` returns per-slot `description`,
`kind`, `range`, `role`, `required`, `multivalued`, `identifier`, `targetEntityType`,
`enumName` and `enumValues`.

The app already detects `hippoSchema` and sets `capabilities.schemaIntrospection`, which
nothing reads. `introspection.ts` records that enrichment was deferred pending confirmation
of the query shape against a live server. That confirmation is now done.

**Degradation is not optional.** An endpoint advertising no `hippoSchema` must render the
panel from `ColumnModel` alone — labels, kinds, enum values, no descriptions — and error
nowhere (ADR-0029).

### Decision 3: `+ filter` writes the draft, never the URL

In this builder a spec in the URL **is an executed query** (`executed = urlState.querySpec`,
run by an effect). An affordance that set it would run the query with no deliberate
gesture, which is what ADR-0039 forbids ("the user must then explicitly run, exactly like a
spec they built by hand").

So the row action appends to the builder's **draft**. Run remains the only execution.

This is the same distinction that was got wrong and corrected once already in the chat
panel, where auto-applying a proposal to the URL silently removed the user's run.

### Decision 4: Highlighting is presentational and heuristic, and says so

The turn's message names fields in prose. To highlight them, extract slot names by matching
against the known slot list — the technique Reel's discovery grader already uses, including
its hard-won handling of the trap that `notes`, `name` and `donor` are **ordinary English
words** as well as slot names:

- a name containing `_` counts when it appears bare
- a single common word counts only when written as a field reference
- anything in the proposal's `criteria` always counts

**Getting this wrong dims a row. It never withholds data**, because the panel shows every
field regardless — extraction only reorders and emphasises.

### Decision 5: The standalone field picker is absorbed

"Which fields exist" and "which fields do I want to see" are the same question asked twice.
The picker added earlier (`.query-fieldpicker`) becomes the column toggle on each panel row.

## Risks / Trade-offs

- **It resembles the retired approach.** Addressed head-on in the proposal. The one-line
  version: that stored the schema to display it; this displays the schema.
- **One more query at connect time.** Gated on detection, issued once per session, and
  silently skipped when unsupported.
- **Extraction is heuristic.** Bounded by Decision 4 — worst case is a row not emphasised.
- **`ColumnModel` grows.** It is consumed by the collections table, facets and detail view;
  the new properties are optional and additive, so those paths are untouched.

## Migration Plan

Each step ships independently and leaves the page working.

1. Data layer only — fetch and join the enrichment, no UI change. Provable by test.
2. Fields panel replacing `.query-blank`, read-only. **This alone resolves the complaint.**
3. Row actions; retire the standalone picker.
4. Conversation highlighting.
5. Chrome: demote the lock banner, fix the defects below.

Rollback is per-step; nothing persists and no data migrates.

## Defects to fix in passing

1. **Phantom CSS tokens.** `.query-fieldpicker` references `--border-subtle`,
   `--surface-subtle`, `--text-xs`, `--text-muted`, `--text-sm` — none exist, all silently
   render hardcoded fallbacks, contradicting the file's own header rule ("no inline var()
   fallbacks"). Introduced by the picker this change absorbs.
2. **`.cell-right` has no rule anywhere.** The query results table emits it; the real rule
   is `.collection-table .align-right`. Numeric right-alignment is **inert** in query
   results while working in the collections table.
3. **Duplicate accessible name** — `<aside aria-label="Query composer">` wraps
   `<section aria-label="Query composer">`.

## Open Questions

- Whether the entity-level description (available from `__schema` today, currently
  discarded) belongs in the panel header or the page header. Settle when building it.
