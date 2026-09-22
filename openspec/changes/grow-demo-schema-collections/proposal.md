# Grow the demo schema from 4 collections to 15

## Why

The demo schema has four entity classes. Every claim we make about
schema discovery — that the planner can find the right field from a
natural-language question — has only ever been tested against four
classes and ~40 slots. That is not a scale at which the approach can
fail, so it has told us nothing about whether the approach *works* or
merely hasn't been stressed yet.

The grounding strategy is "put every class and slot description in the
prompt." That strategy has a breaking point. We do not know where it is,
and we will not find out by reasoning about it. The only way to learn it
is to grow the schema and re-run the discovery eval unchanged.

Context is not the constraint. The planning model is Haiku 4.5
(`config.py:MODEL`), whose window is 200K tokens; the measured grounding
cost today is roughly 2.3k tokens for four classes. Even a pessimistic
per-class projection puts fifteen classes an order of magnitude inside
the window. What is expected to degrade first is **field-selection
accuracy** — more near-miss slot names to choose between, more plausible
date fields, more classes that could each plausibly answer the same
question. That is a quality failure, not a capacity failure, and it is
invisible until the candidate set is large enough to confuse.

A second, concrete motivation: the question that started this work —
*"what information do we have on donors about toxicology reports?"* — has
no answer in the current schema, because there is no toxicology of any
kind. The running example cannot be demonstrated. After this change it
can.

## What Changes

- **Add 11 concrete entity classes** to `schemas/demo.yaml`, taking the
  total from 4 to 15, spanning clinical, governance, specimen-handling,
  instrumentation and publication concerns:
  `ToxicologyReport`, `Diagnosis`, `Assessment`, `ConsentRecord`,
  `Aliquot`, `StorageLocation`, `RunConfiguration`, `Instrument`,
  `ReagentLot`, `QcFlag`, `Publication`.
- **Leave the four existing classes byte-for-byte unchanged.** Every new
  foreign key points from a new class at an old one, never the reverse.
  This is deliberate: it makes the discovery eval a controlled
  experiment, where the only variable is the number of candidates in the
  grounding block.
- **Add the supporting enums** (~10) and mirror each new class in
  `generation_schema.yaml`'s `DemoBundle` root.
- **Generate modest row counts for the new classes** — roughly 5,400 new
  records against 3,600 existing, with several deliberately small
  dimension tables (9 instruments, 24 storage locations, 40
  publications). Collections are small, never empty; an empty collection
  cannot be graded by any eval case.
- **Extend `generate.py`**: referential-integrity checks for every new
  edge, date-interval repair for the new start/end pairs, and a
  **parity check** that fails loudly when a concrete entity class in
  `demo.yaml` has no corresponding pool in `DemoBundle`.
- **Measure and record the scaling result**: run the *existing,
  unmodified* `evals/discovery.yaml` (d01–d11) against both the
  4-collection and 15-collection schemas, and record measured grounding
  token cost at both sizes.

## Impact

- Affected specs: `small-demo-schema` (4 requirements MODIFIED, 2 ADDED)
- Affected code: `schemas/demo.yaml`, `generation_schema.yaml`,
  `hints.yaml`, `generate.py`, `data/bundle.yaml`, `data/mosaic.db`
- Affected docs: `CONVERSATIONAL-QUERY.md` (record the measured result)

### Explicitly out of scope

Named here because each is real work this change makes more urgent, and
folding any of it in would destroy the measurement:

- The planner **prompt rewrite**. The whole point is to run the current
  prompt against a larger schema. Changing both at once measures nothing.
- The **d09/d11 reference-field failures** and the d06 negative-case
  regression. These are known, open, and are part of the baseline.
- `add-schema-field-panel` **tasks 7–10**. Task 10 (panel scale/search)
  goes from nice-to-have to necessary at 15 collections — a 15-entity
  nav list and an unsearchable field panel are a different problem, and
  they get their own change.
