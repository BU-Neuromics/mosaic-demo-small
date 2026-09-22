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
