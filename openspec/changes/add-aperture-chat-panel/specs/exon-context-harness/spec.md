## ADDED Requirements

### Requirement: The harness evaluates multi-turn conversational sequences, not only independent single-shot calls

The harness SHALL support fixtures that exercise Exon's turn-taking planning core
(`conversational_planner.py`/`conversational_orchestrator.py`) as ordered sequences of turns
against a shared, evolving `QuerySpec` — including at least one rewind-and-edit sequence that
exercises the suspend-on-invalid-recompute path — rather than only evaluating every question as an
independent single-shot planner call.

#### Scenario: A multi-turn fixture measures the whole sequence, not each turn in isolation

- **WHEN** a fixture defines an ordered list of utterances meant to compose (e.g. "hippocampus
  samples" then "only from donors over 60")
- **THEN** the harness runs them as a single conversation, feeding each turn's response forward as
  the next turn's input state, and reports pass/fail for the sequence's final `QuerySpec` — not as
  N independent, context-free single-shot evaluations

#### Scenario: A rewind-and-edit fixture measures suspend-on-invalid-recompute, not just linear turns

- **WHEN** a fixture edits an earlier turn in a way that should invalidate a later turn already in
  the sequence
- **THEN** the harness asserts the later turn's status becomes `suspended` (never silently dropped
  or silently reinterpreted) as part of what "pass" means for that fixture

#### Scenario: A grounding change gets a before/after measurement, not just a shipped diff

- **WHEN** Exon's turn-taking grounding changes (e.g. adding reverse-edge traversal)
- **THEN** the harness's existing model-comparison/fingerprint tooling
  (`add-exon-harness-model-comparison`) is run against the multi-turn fixture set both before and
  after the change, so the change's effect on conversational reliability is measured, not assumed
