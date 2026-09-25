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

---

## Amendment (2026-09-22): the surface is not a builder, and not a lens

Driven by using it. The fields panel landed and immediately exposed an information
architecture problem it did not create — the empty grid had been hiding it.

### What was wrong

**"Query builder" sits in the nav as a peer of Datasets / Donors / Samples / Workflows,
but it is not a peer.** `openQueryBuilder()` takes no argument: it opens with whatever
`collection` is in the URL, falling back to `anchored[0]`. So the page has an anchor, the
nav has a selection, and they are one piece of state wearing two hats. Both paths feel
wrong for the same reason:

- *collection → Query builder* is indirect: you already said "Donors", then had to go
  somewhere else to use it
- *Query builder cold* is arbitrary: it silently picks one for you

### The reading that was tried and rejected

**"The query surface is a lens on a collection"** — each collection offering Browse |
Query, the anchor always being the thing you clicked.

**Rejected, and the reason matters more than the rejection.** It breaks on exactly the
case the surface exists for. "Samples from female donors" is not a lens on Samples: it
needs Donor's fields too. Framing the page as *"you are in Donors"* fights cross-class
querying, which is the point of ADR-0035.

### The reading that holds

**The anchor is the shape of the answer, not a location.** A QuerySpec has exactly one
anchor — the type of rows returned — and criteria that traverse outward. "Rows of Samples,
constrained by something about their Donor." That is a property of *the query*, not of
navigation. Three things follow:

1. **Nav peerage is correct.** The surface is a place. It is not a mode of a collection.
2. **The page must state its subject where a heading goes.** Today the anchor is a
   `<select>` buried inside `.query-frame`, so nothing on screen says whether you are
   building rows of Donors or rows of Samples.
3. **Cold start asks the real question** — *what do you want rows of?* — rather than
   defaulting to `anchored[0]`.

### The name is the diagnosis

"Query builder" names the *form*, not the job, which is why it reads as a place, behaves as
a lens, and is neither. Renaming it around what it produces makes the rest follow.

**Recommended: "Ask."** It matches the composer's own verb ("Describe the query"), it
covers the discovery half — which is most of what the surface now does — and it is honest
for a user who does not yet know what they are looking for. *"Find"* is the alternative and
is better for retrieval, worse for discovery. *"Explore"* is unavailable: the results bar
already has "Explore as graph".

**Change the LABEL only.** `nav-query-builder` is a load-bearing testid across two vitest
suites and `e2e-smoke.mjs`; renaming both in one pass buys nothing and breaks the only
thing asserting arrangement — which cannot currently be run here (no Playwright browsers).

### Grouping the fields panel, and its real limit

The panel as built shows the **anchor's fields only**. Ask *"which samples came from female
donors?"* and it shows Sample's fields while the answer talks about `sex`, which is on
Donor. That breaks on the first cross-class question.

So it groups by entity: the anchor, then the entities reachable in **one hop**.

**One hop, and no further.** That is what a `RelatedCondition` can express. Showing two
hops would list fields the artifact cannot filter on — the same class of error as discovery
eval `d04`, where the planner reached for a field it could not project.

**Both directions — and the reverse story changed under us.**

`deriveEdges` returns forward edges (a reference the anchor holds) and reverse edges
(`rev:`, a reference something else holds back). Aperture resolves the reverse kind with a
capped client-side semijoin, which the results bar labels "semijoin tier".

**That compensation is no longer the only option.** Mosaic
[#204](https://github.com/BU-Neuromics/mosaic/issues/204) — *"QuerySpec has no reverse-edge
traversal"* — was **closed on 2026-09-19** by
[#210](https://github.com/BU-Neuromics/mosaic/pull/210), ADR-0011: reverse references are
now **native**, declared with LinkML's own `inverse` keyword and resolved as virtual fields
that are never separately stored.

```yaml
Donor:
  attributes:
    samples:
      range: Sample
      multivalued: true
      inverse: donor        # Sample.donor is the stored FK; this side is derived
```

**But this schema declares none**, which is why `Donor` measured **zero forward
references**. So today every traversal from Donor is a compensated semijoin — not because
Mosaic cannot do better, but because the schema has not asked it to.

Two consequences:

1. The panel marks a hop by **how it will actually run** — native reference vs compensated
   semijoin — rather than by direction. Once a schema declares `inverse`, the same hop
   silently becomes native and the mark disappears on its own.
2. **`schemas/demo.yaml` has not opted into this capability.** Declaring `inverse:` is
   the intended interface, not a workaround: #210 made reverse edges *work* (they used to
   validate, compile, run, and return zero rows, because the storage adapter looked in a
   link table the reverse side of an FK never writes) but deliberately did **not** make
   them automatic. LinkML binds `inverse` to `owl:inverseOf`, so the reverse is entailed
   rather than asserted — auto-deriving one per FK would both risk two writable encodings
   of one fact and inflate every transport with edges nobody modelled. Whether this schema
   *should* declare them is a modelling question about the data, not a mechanical one.

*(Verified: this repo's mosaic checkout sits 3 commits behind `origin/main` and predates
#210 — the feature is real, the local tree just has not caught up.)*

### Designing for a schema that gets much bigger

The measurement above is the **small** case: four entity types, ~20 cards at one hop. The
schemas this is heading for are substantially larger — many more collections, each with
more fields. A grouped list that works at four entities is unusable at forty.

So the panel is a **field finder**, not a field list:

- **Search is a primary control, not a nicety.** Match on field name, slot name, and
  description text — the description is the whole reason a user's vocabulary finds a field
  whose name shares none of its words, so it must be searchable, not merely displayed.
- **Only the anchor's group is expanded.** Reachable entities are named and collapsed, so
  the cost of a large schema is a longer list of *group headers*, not of cards.
- **The conversation stays the primary finder.** At scale, asking is faster than browsing,
  and the panel is the browsable fallback and the confirmation surface — not the main way
  in. That division is what keeps the page honest as the schema grows.

This also sets a hard boundary: the panel must never try to present *every* entity in the
deployment. It presents the anchor, and what the anchor can reach in one hop. Everything
else is reached by changing the anchor.

### Measured, because it decides the layout

Field counts on the demo schema — four entity types, the small case:

| Anchor | Own | One hop | Total cards |
| --- | --- | --- | --- |
| Dataset | 10 | Workflow | 19 |
| Sample | 11 | Donor | 20 |
| Workflow | 9 | Sample | 20 |
| Donor | 9 | Sample *(reverse)* | 20 |

**~20 cards on the smallest realistic schema**, on a page that must also hold results. So
grouping is **collapsed by default with the anchor expanded** — not all-open. A schema with
twenty entity types would otherwise make the panel unusable at exactly the scale where
discovery matters most.

### Constraints this must not relitigate

- `+ filter` writes the **draft**, never the URL. Pinned by a test.
- A related-field filter must produce a `RelatedCondition` with `edge` + nested `criteria`,
  **not** a flat condition. `e2e-smoke.mjs` asserts sub-conditions remain descendants of
  `query-related`.
- The `AppShell` slot contract and the 1100px breakpoint stay untouched.
