# Tasks

## 1. Record the baseline before touching anything

- [ ] 1.1 Run `evals/discovery.yaml` (d01–d11) unmodified against the
      current 4-collection schema, `--samples 3`, and record the score,
      the per-case results, and the exact model string.
- [ ] 1.2 Measure the grounding block's token cost at 4 collections with
      `messages.count_tokens` against the assembled block — not an
      estimate from character count.
- [ ] 1.3 Commit both numbers before any schema edit, so the comparison
      arm cannot be retroactively adjusted.

## 2. Schema

- [ ] 2.1 Add 11 concrete classes to `schemas/demo.yaml`, each `is_a:
      Entity` with a `name` slot: `ToxicologyReport`, `Diagnosis`,
      `Assessment`, `ConsentRecord`, `Aliquot`, `StorageLocation`,
      `RunConfiguration`, `Instrument`, `ReagentLot`, `QcFlag`,
      `Publication`.
- [ ] 2.2 Confirm every new class is either `is_a: Entity` or explicitly
      a value object. A class that is neither — and that Mosaic's
      `INFRASTRUCTURE_CLASSES` does not exclude — becomes a permanently
      empty Aperture collection (the trap `demo.yaml`'s `ExternalID`
      override already documents).
- [ ] 2.3 Verify no slot, description or annotation on `Donor`, `Sample`,
      `Workflow` or `Dataset` changed: `git diff` on those blocks is
      empty.
- [ ] 2.4 Add the ~10 supporting enums with per-value descriptions where
      the value is not self-evident.
- [ ] 2.5 Give each new class at least one distinctive, unshared slot
      (design.md Decision 3) and at least two enum-backed facets.
- [ ] 2.6 Add `hippo_search: fts5` to the free-text slot on
      `ToxicologyReport`, `QcFlag` and `Publication`.
- [ ] 2.7 Add a multivalued reference (`RunConfiguration.reagent_lots →
      ReagentLot`) so the N:M storage path is exercised by more than one
      edge.

## 3. Generation

- [ ] 3.1 Mirror all 15 pools in `generation_schema.yaml`'s `DemoBundle`.
- [ ] 3.2 Add a parity check to `generate.py`, run before generation,
      that raises when a concrete entity class in `demo.yaml` has no
      `DemoBundle` pool.
- [ ] 3.3 Confirm `GenerationConfig.max_count=1200` is a per-pool
      ceiling, not a global one, before adding 11 pools. If it is
      global, raise it and say so.
- [ ] 3.4 Extend `COUNT_OVERRIDES` with the new pools; keep dimension
      tables small (9 instruments, 24 storage locations, 40
      publications, 75 reagent lots) and every pool non-empty.
- [ ] 3.5 Extend `hints.yaml` with faker providers, weighted choices and
      numeric distributions for the new slots — no uniform-random
      categoricals.
- [ ] 3.6 Extend `_check_referential_integrity` to cover every new edge:
      `ToxicologyReport.donor`, `Diagnosis.donor`, `Assessment.donor`,
      `ConsentRecord.donor`, `Aliquot.sample`, `Aliquot.location`,
      `RunConfiguration.workflow`, `RunConfiguration.instrument`,
      `RunConfiguration.reagent_lots[*]`, `QcFlag.dataset`,
      `Publication.datasets[*]`.
- [ ] 3.7 Generalise `_fix_workflow_timestamps` into an interval repair
      covering the new start/end pairs: `ConsentRecord.signed_at <
      withdrawn_at`, `QcFlag.raised_at < resolved_at`,
      `ReagentLot.received_on < expires_on`.
- [ ] 3.8 Seed searchable keywords into the new fts5 fields the way
      `_seed_keywords` already does, so search cases are gradeable.

## 4. Build and load

- [ ] 4.1 `python generate.py --seed 0` — parity check, integrity check
      and interval repair all pass.
- [ ] 4.2 `mosaic migrate --schema-dir schemas` on a fresh DB creates
      exactly 15 entity tables plus system tables, and no table for
      `QualityMetrics` or `ExternalID`.
- [ ] 4.3 `mosaic ingest --validate-schema schemas/demo.yaml` reports the
      expected created count per class and zero errors.
- [ ] 4.4 Bring up the Docker stack and confirm Aperture lists 15
      collections, each with at least one row.

## 5. Measure the scaling result

- [ ] 5.1 Re-run the **unmodified** d01–d11 against the 15-collection
      schema, same model, same prompt, `--samples 3`.
- [ ] 5.2 Re-measure grounding token cost at 15 collections the same way
      as 1.2, and record actual tokens-per-class rather than carrying
      forward the 4-class figure.
- [ ] 5.3 Classify every case whose result moved as either **regression**
      or **right answer changed** (design.md Decision 2). A case whose
      correct answer genuinely widened gets its `expect_slots` updated
      and is annotated as such.
- [ ] 5.4 Write new discovery cases for the new collections, scored
      separately from the headline — including the motivating question,
      *"what information do we have on donors about toxicology
      reports?"*, which must now name `substances_detected` and
      `panel_type`.

## 6. Record

- [ ] 6.1 Add the measured before/after — collection count, grounding
      tokens, d01–d11 score — to `CONVERSATIONAL-QUERY.md`. Extend the
      existing document; do not create a new summary markdown.
- [ ] 6.2 State plainly what the measurement showed, including if the
      answer is "no measurable degradation at 15" — that is a real and
      useful result, not a failed experiment.
- [ ] 6.3 If degradation is measurable, note it as the evidence that
      motivates the prompt rewrite, which remains a separate change.
