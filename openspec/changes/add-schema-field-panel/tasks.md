## 1. Carry the enrichment onto the models

- [x] 1.1 Add `HIPPO_SCHEMA_QUERY` and its result types to `web/src/data/introspection.ts`,
      beside `INTROSPECTION_QUERY`
- [x] 1.2 Issue it once in `connectHippoSource` (`web/src/data/hippoSource.ts`), gated on
      the `hippoSchema` presence check that already sets
      `capabilities.schemaIntrospection`; degrade silently to `undefined` on error or
      absence
- [x] 1.3 Add optional `description`, `range`, `kind`, `required`, `enumName` to
      `ColumnModel`; keep every existing property unchanged so the collections table,
      facets and detail view are untouched
- [x] 1.4 Join on SLOT name, not field name — `ColumnModel.field` is camelCase
      (`historyOfRhi`), `hippoSchema` is snake_case (`history_of_rhi`). Reuse `slotName()`;
      `specProse.tsx` already solves this exact mismatch
- [x] 1.5 Add `description` to `CollectionModel` from the entity description `__schema`
      already returns and `deriveCollections` currently discards
- [x] 1.6 Test: descriptions arrive and join correctly; an endpoint without `hippoSchema`
      yields models identical to today

## 2. The Fields panel

- [x] 2.1 `web/src/query/FieldsPanel.tsx` — one row per field: label, slot name, type,
      description, permitted values, required, reference target
- [x] 2.2 Replace `.query-blank` in `QueryBuilderView.tsx` with the panel
- [x] 2.3 Results replace the panel once a query has run; the Fields control brings it back
- [x] 2.4 Style on REAL tokens only — no invented names, no `var()` fallbacks (see design.md
      defect 1). Reuse `typeColorStyle()` for the entity accent, as nav and graph do
- [x] 2.5 Degrade: with `schemaIntrospection: 'graphql'` the panel renders from
      `ColumnModel` alone and nothing errors or blanks

## 3. Make the fields actionable

- [x] 3.1 `+ filter` appends a `FieldCondition` to the builder DRAFT
- [x] 3.2 Assert by test that it does NOT set `qs` and does NOT execute — a URL spec is an
      executed query here, and ADR-0039 makes Run the only execution gesture
- [x] 3.3 Column toggle reuses the existing `hiddenFields` state
- [x] 3.4 Retire the standalone `.query-fieldpicker` and its styles

## 4. Highlight what the conversation named

- [x] 4.1 `web/src/query/namedSlots.ts` — extract slot names from a turn's message
- [x] 4.2 Handle the common-word trap: a name with `_` counts bare; a single common word
      (`notes`, `name`, `donor`) counts only as a field reference; spec criteria always
      count. Reel's grader has this logic and the tests that prove it
- [x] 4.3 Order named fields first, then filterable, then the rest
- [x] 4.4 Test that a miss only fails to emphasise — the panel still lists every field

## 5. Chrome and defects

- [x] 5.1 Demote the lock banner to a caption. NOT inside the frame as originally
      planned: `fieldset[disabled]` disables every descendant, so moving it in disabled
      its own "Clear conversation" escape hatch. Caught by ChatPanel.test.tsx. It stays
      outside the fieldset, styled down
- [x] 5.2 Fix the phantom tokens (design.md defect 1)
- [x] 5.3 Fix `.cell-right` — either emit `.align-right` as `CollectionTable` does, or give
      `.cell-right` a rule (defect 2)
- [x] 5.4 Rename the inner `aria-label="Query composer"` so two nested landmarks do not
      share one name (defect 3)

## 6. Verify

- [x] 6.1 `npx vitest run` — 336 currently pass; none may break
- [x] 6.2 Preserve every load-bearing testid: `chat-panel`, `chat-turn`, `spec-prose`,
      `query-builder`, `query-anchor`, `query-condition`, `query-related`, `query-run`,
      `query-results`, `query-notes`, `nav-query-builder`
- [ ] 6.3 `node e2e-smoke.mjs` unmodified — it asserts ARRANGEMENT, not just presence
      (sub-conditions must stay descendants of `query-related`). NOT RUN: Playwright
      browsers are not installed in this environment (`npx playwright install`). The
      structure it pins is untouched — `query-related` and its nested `query-condition`
      markup was not edited — but that is reasoning, not a passing run
- [x] 6.4 Live in a browser: first load shows fields, not "Nothing run yet"; a discovery
      question highlights the field it named; `+ filter` adds a condition without running;
      Run replaces the panel with results
- [x] 6.5 Confirm no metadata question leaves a screen that is mostly empty grid

## 7. The surface is a place, and says what it is (amendment)

- [x] 7.0a **The panel follows the answer, not the anchor.** Found by driving
      the page at 15 collections: ask about toxicology, read a correct
      toxicology answer beside a panel showing `Aliquot`. Pick the subject
      from slots belonging to exactly ONE collection — `name`/`id`/`notes`
      identify nothing — and offer "use as anchor" rather than adopting
      silently. Presentational only: no URL write, no run.
- [x] 7.0b **Exactly one nav entry is current.** `CollectionsNav.tsx:43`
      marks a collection current whenever no workflow is open, including
      while the query surface is showing, and the query entry carries no
      `aria-current` at all. Switching the anchor then leaves the nav
      contradicting the anchor control.
- [x] 7.0c **Cold start uses the deployment's declared default anchor**
      (`navView.defaultId`) instead of `anchored[0]`, which is alphabetical
      — it is why a fresh page lands on `Aliquot`. Narrower than 7.3, which
      wants the question asked rather than answered; this removes the
      arbitrariness without blocking on that redesign.
      **Partial, and say so.** The builder and the nav now agree, which they
      previously need not have. But `buildNavView` falls back to
      `visible[0]` when no `defaultCollection` is configured, and this demo
      configures none — so the demo still opens on `Aliquot`, now for the
      nav's reason rather than the builder's own. The visible symptom needs
      either a `VITE_NAV` default for the deployment or 7.3.
- [ ] 7.1 Rename the nav LABEL "Query builder" → "Ask". Leave `data-testid`
      `nav-query-builder` alone — it is load-bearing in two vitest suites and
      `e2e-smoke.mjs`, and renaming both in one pass breaks the only arrangement
      assertion for no benefit
- [ ] 7.2 Make the anchor the page's identity: "Rows of **Samples**" as the heading,
      replacing the bare "Query" title and demoting the `<select>` inside `.query-frame`
      to a change-affordance on that heading
- [ ] 7.3 Cold start asks *what do you want rows of?* instead of silently defaulting to
      `anchored[0]`. Arriving from a collection keeps that collection as the answer —
      the question is already answered, so do not ask it again

## 8. Group the fields panel by entity (amendment)

- [ ] 8.1 Group: the anchor's own fields, then each entity reachable in ONE hop via
      `deriveEdges`. No second hop — a `RelatedCondition` cannot express it, and showing
      fields that cannot be filtered on repeats discovery eval `d04`'s mistake
- [ ] 8.2 **Collapsed by default, anchor expanded.** Measured on the demo schema: every
      anchor reaches ~20 cards at one hop with only four entity types
- [ ] 8.3 Mark a hop by HOW IT WILL RUN — native reference vs compensated semijoin — not
      by direction. Mosaic #204 was closed by #210 (ADR-0011): reverse references are
      native when a schema declares LinkML `inverse`. This schema declares none, which is
      why Donor measures ZERO forward references. Once it does, the same hop becomes
      native and the mark disappears on its own
- [ ] 8.4 `+ filter` on a RELATED field appends a `RelatedCondition` (`edge` + nested
      `criteria`), never a flat one — and still writes the DRAFT, never the URL
- [ ] 8.5 Test that a related filter nests: the sub-condition must be a DESCENDANT of the
      `query-related` block, which `e2e-smoke.mjs` asserts
- [ ] 8.6 Highlighting spans groups — a turn naming `sex` on Donor while anchored on
      Sample must emphasise it in the Donor group, and expand that group

## 9. Scale, because the schema is about to get much bigger (amendment)

The ~20-card measurement is the FOUR-entity case. A grouped list that works there is
unusable at forty collections, which is where this is heading.

- [ ] 9.1 Search as a primary control on the panel — matching field name, slot name AND
      description text. The description is the whole reason a user's vocabulary finds a
      field whose name shares none of its words, so it has to be searchable, not just
      displayed
- [ ] 9.2 Only the anchor's group expands; reachable entities are named and collapsed, so
      a bigger schema costs a longer list of group HEADERS, not of cards
- [ ] 9.3 The panel never presents every entity in the deployment — only the anchor and
      what it reaches in one hop. Everything else is reached by changing the anchor
- [ ] 9.4 Re-measure against a large schema (hippo-benchmark is ~90 tables) before calling
      this done. Four entity types proves nothing about forty

## 10. Follow-on, not in this change

- [ ] 10.1 DECIDE whether `schemas/demo.yaml` should declare `inverse` slots. Not a
      workaround — declaring is the intended interface, and #210 deliberately did not make
      reverse edges automatic (one physical encoding per fact; every transport derives from
      one type model). So this is a modelling question: is "a donor's samples" part of the
      model, or only "a sample's donor"? If yes, it makes the flagship cross-class example
      run natively instead of through Aperture's capped semijoin
- [ ] 10.2 Bump this repo's mosaic checkout past #210 so the inverse support is actually
      present locally (currently 3 commits behind origin/main)
