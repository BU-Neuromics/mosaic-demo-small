# Tasks

## 1. Record the baseline before touching anything

- [x] 1.1 Run `evals/discovery.yaml` (d01–d11) unmodified against the
      current 4-collection schema, `--samples 3`, and record the score,
      the per-case results, and the exact model string.
- [x] 1.2 Measure the grounding block's token cost at 4 collections with
      `messages.count_tokens` against the assembled block — not an
      estimate from character count.
- [x] 1.3 Commit both numbers before any schema edit, so the comparison
      arm cannot be retroactively adjusted.

## 2. Schema

- [x] 2.1 Add 11 concrete classes to `schemas/demo.yaml`, each `is_a:
      Entity` with a `name` slot: `ToxicologyReport`, `Diagnosis`,
      `Assessment`, `ConsentRecord`, `Aliquot`, `StorageLocation`,
      `RunConfiguration`, `Instrument`, `ReagentLot`, `QcFlag`,
      `Publication`.
- [x] 2.2 Confirm every new class is either `is_a: Entity` or explicitly
      a value object. A class that is neither — and that Mosaic's
      `INFRASTRUCTURE_CLASSES` does not exclude — becomes a permanently
      empty Aperture collection (the trap `demo.yaml`'s `ExternalID`
      override already documents).
- [x] 2.3 Verify no slot, description or annotation on `Donor`, `Sample`,
      `Workflow` or `Dataset` changed: `git diff` on those blocks is
      empty.
- [x] 2.4 Add the ~10 supporting enums with per-value descriptions where
      the value is not self-evident.
- [x] 2.5 Give each new class at least one distinctive, unshared slot
      (design.md Decision 3) and at least two enum-backed facets.
- [x] 2.6 Add `hippo_search: fts5` to the free-text slot on
      `ToxicologyReport`, `QcFlag` and `Publication`.
- [x] 2.7 Add a multivalued reference (`RunConfiguration.reagent_lots →
      ReagentLot`) so the N:M storage path is exercised by more than one
      edge.

## 3. Generation

- [x] 3.1 Mirror all 15 pools in `generation_schema.yaml`'s `DemoBundle`.
- [x] 3.2 Add a parity check to `generate.py`, run before generation,
      that raises when a concrete entity class in `demo.yaml` has no
      `DemoBundle` pool. **Extended beyond the plan**: it also checks the
      pool's NAME against Mosaic's synthesized tree root, which caught
      `Diagnosis` → `diagnosiss` (fixed with a `hippo_accessor`
      annotation — the framework's own override for awkward plurals).
      Its only other symptom was an ingest error naming the pool but not
      the rule it broke.
- [x] 3.3 Confirm `GenerationConfig.max_count=1200` is a per-pool
      ceiling, not a global one, before adding 11 pools. **Confirmed
      per-pool** from its docstring ("how many instances to put in each
      top-level collection … and how to clamp it"); no change needed,
      and the four 1,200-row pools all sit at it.
- [x] 3.4 Extend `COUNT_OVERRIDES` with the new pools; keep dimension
      tables small (9 instruments, 24 storage locations, 40
      publications, 75 reagent lots) and every pool non-empty.
- [x] 3.5 Extend `hints.yaml` with faker providers, weighted choices and
      numeric distributions for the new slots — no uniform-random
      categoricals. **A hint whose slot is later derived is a lie**:
      `is_expired` is set by `_fix_intervals` from `expires_on`, so its
      `choices` weight was silently overwritten. Hint removed, receipt
      window moved to 2022–2026 so the derived value is non-degenerate.
- [x] 3.6 Extend `_check_referential_integrity` to cover every new edge:
      `ToxicologyReport.donor`, `Diagnosis.donor`, `Assessment.donor`,
      `ConsentRecord.donor`, `Aliquot.sample`, `Aliquot.location`,
      `RunConfiguration.workflow`, `RunConfiguration.instrument`,
      `RunConfiguration.reagent_lots[*]`, `QcFlag.dataset`,
      `Publication.datasets[*]`.
- [x] 3.7 Generalise `_fix_workflow_timestamps` into an interval repair
      covering the new start/end pairs: `ConsentRecord.signed_at <
      withdrawn_at`, `QcFlag.raised_at < resolved_at`,
      `ReagentLot.received_on < expires_on`.
- [x] 3.8 Seed searchable keywords into the new fts5 fields the way
      `_seed_keywords` already does, so search cases are gradeable.

## 4. Build and load

- [x] 4.1 `python generate.py --seed 0` — parity check, integrity check
      and interval repair all pass.
- [x] 4.2 `mosaic migrate --schema-dir schemas` on a fresh DB creates
      exactly 15 entity tables plus system tables, and no table for
      `QualityMetrics` or `ExternalID`.
- [x] 4.3 `mosaic ingest --validate-schema schemas/demo.yaml` reports the
      expected created count per class and zero errors.
- [x] 4.4 Bring up the Docker stack and confirm Aperture lists 15
      collections, each with at least one row.
- [x] 4.5 **Not in the plan, and the one scenario nothing else covered**:
      check every facetable field for degeneracy, not just that facets
      exist. A nine-row collection can collapse a weighted boolean to one
      value by chance. All 24 new facets carry more than one value;
      `ReagentLot.is_expired` came back 72/3 against a hint claiming
      71/29 and was fixed at the source (see 3.5).

## 5. Measure the scaling result

- [x] 5.1 Re-run the **unmodified** d01–d11 against the 15-collection
      schema, same model, same prompt, `--samples 3`.
- [x] 5.2 Re-measure grounding token cost at 15 collections the same way
      as 1.2, and record actual tokens-per-class rather than carrying
      forward the 4-class figure.
- [x] 5.3 Classify every case whose result moved as either **regression**
      or **right answer changed** (design.md Decision 2). **One case
      moved: `d06`**, the negative case, whose topic the change made
      real — converted to `expect_slots: [panel_type, specimen_matrix]`
      and annotated. No case regressed; per-case rates moved ±1 run in
      both directions, which `d04` (1/3, 2/3, 2/2 across three identical
      runs) shows is noise at n=3.
- [x] 5.4 Write new discovery cases for the new collections, scored
      separately from the headline, in `evals/discovery-new-collections.yaml`
      (n01–n11). The motivating question stayed in the frozen arm as the
      converted `d06` and now passes 2/3; `n01` asks it from the result
      side and fails 0/3.
- [x] 5.5 **Not in the plan, and necessary**: replace the negative case.
      Converting `d06` would otherwise have deleted the suite's only
      check that the planner refuses to invent — removed by a schema
      change rather than a decision. `n11` carries it, pointed at
      imaging, which this schema still does not model.

## 6. Record

- [x] 6.1 Add the measured before/after — collection count, grounding
      tokens, d01–d11 score — to `CONVERSATIONAL-QUERY.md`. Extend the
      existing document; do not create a new summary markdown.
- [x] 6.2 State plainly what the measurement showed, including if the
      answer is "no measurable degradation at 15" — that is a real and
      useful result, not a failed experiment.
- [x] 6.4 **Not in the plan, and it was the right thing to ask for**: drive the
      query builder page in a browser against the 15-collection schema, and
      re-run every example in the document rather than carrying forward
      remembered ones. Found three things nothing else would have:
      the Fields panel renders whatever the anchor is rather than what the
      answer was about; the left nav desyncs from the anchor picker; and two
      field descriptions narrated this schema's own test design at the
      researcher (fixed — the name collisions stay, the commentary goes).
- [x] 6.5 Re-run all 25 example questions and record measured anchors,
      criteria and row counts. 24 of 25 stable across two samples; `d04`
      is the exception and the reason is `RunConfiguration.compute_hours`
      making "how long did each run take?" genuinely ambiguous against
      `Workflow.duration_hours` — a right-answer change, not a regression.
- [x] 6.6 Record that the four original classes are frozen but their
      **generated data is not**: fifteen pools consume the seeded RNG
      differently, so `history_of_rhi` moved 50 → 58 and every donor value
      shifted, while ids stayed identical. Does not affect the discovery
      comparison, which grades slot names and never row counts.

- [x] 6.3 If degradation is measurable, note it as the evidence that
      motivates the prompt rewrite, which remains a separate change.
      **It is, and it is not where we expected.** Field-finding on the
      frozen arm held; what degraded is refusal — `n11` twice named
      `condition_name` / `instrument_name` / `dataset_type` for a topic
      with no imaging in it. The rewrite's brief is refusal and
      homonym-discrimination, not discovery.
