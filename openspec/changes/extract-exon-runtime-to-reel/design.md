## Context

Five repos hold pieces of this: `mosaic-demo-small` (Exon's source today),
`reel` (design only — two commits, no `src/`, no `pyproject.toml`, no CI),
`mosaic` (the relay that delegates to a planner), `aperture` (the chat panel),
`datahelix` (the deployment recipes).

The conversational path currently runs as three host processes — Mosaic, Exon,
and a vite dev server — wired by hand. That works and was verified end to end in
a browser, but it is not something a user on another machine can start.

## Goals / Non-Goals

**Goals**
- The planning service is an artifact: a package, an image, a pin.
- It lands where it is going to live, so the packaging work is done once.
- The demo repo keeps what is genuinely its own: the schema, the generator, the
  eval fixtures, and the harness that grades against them.

**Non-Goals**
- Finishing Exon Phase 2. This change is deliberately arranged so it does not
  have to.
- A certified `solo` deployment. See the proposal's out-of-scope list.
- Any change to the wire contract. ADR-0008 is explicit that the shape does not
  change at migration.

## Decisions

### Decision 1: The destination is Reel, not a new standalone Exon repo

Reel already exists, its ADR-0008 authorizes this exact move, and its A4 says
the `pyproject.toml` skeleton should land "only when the migration is
scheduled" — scheduling it is what this change does.

**Alternative considered: extract Exon to its own repo first, migrate to Reel
later.** Rejected. ADR-0008 retires the Exon name at migration, so the package,
the image, the CI and the pin would all be built twice, and the second build
would delete the first. The only thing it buys is avoiding a decision that
ADR-0008 has already made.

### Decision 2: Phase B splits into B-runtime and B-harness

The runbook's P1 rationale is that migrating an in-flight refactor "loses the
before/after the harness exists to provide." That is a claim about the harness,
and it is correct about the harness. Phase B being one atomic step is what
extends it to the runtime.

The import graph in the proposal shows the two halves are already separable: the
runtime touches none of the QueryPlan code, and `harness/grading.py` is the sole
module that does. Splitting the phase honors every stated rationale — the
harness still does not move until task 2.5 re-baselines it against the path that
actually ships.

This departs from a written runbook, so it is recorded as an amendment there
rather than executed silently. The runbook is Reel's file; this change is the
authority for the edit, not the edit itself.

### Decision 3: The five constants become a `config` module, not a carried `planner.py`

`MAX_ATTEMPTS`, `MAX_TOKENS`, `MODEL`, `REQUEST_TIMEOUT` and `decode_kwargs_for`
live in `planner.py`, which is retired and must not be carried. Carrying the
file to satisfy five imports would drag the entire QueryPlan emitter into Reel
and undo the point of the split.

They move to a small module of their own. This is the one place the migration is
not a pure copy, and it is worth stating so the diff is not mistaken for drift.

### Decision 4: The demo repo keeps the fixtures, and gains a pin

Phase B step 4 already says `schemas/`, `generate.py` and `evals/` stay — they
are domain-bearing. What changes here is that `exon/` stops being a source tree
and becomes a pointer plus a version pin (Phase C3). Reel A6 registers
`REEL_EVAL_CASES=<path>` as the seam, so the harness can point at this repo's
`evals/` without copying it.

### Decision 5: `ide` is the deployment target, not `solo`

`ide` mounts components from source, puts nginx in front (so same-origin makes
Mosaic's missing CORS irrelevant), and is "exempt from the ADR-0001 deploy gate
… nothing it produces is a certified artifact." That is exactly this change's
situation.

`solo` is the certified path users would reach on other systems, and it cannot
carry a planner yet: Mosaic only registers `converseQuerySpec` when
`MOSAIC_EXON_URL` is set, `solo` does not set it, and Reel migration D2 requires
"a release and a Mosaic pair to certify against." Both are future work, and
neither is blocked by doing `ide` first — the compose slot is identical.

## Risks / Trade-offs

- **A repo with a runtime and no reliability suite, for a while.** Between
  B-runtime and B-harness, Reel ships code whose grading lives elsewhere. The
  mitigation is that the runtime's own unit tests carry with it, and the demo
  repo's harness keeps grading the same wire contract across the boundary.
- **Two sources of truth for the turn contract during the window.** Mitigated by
  ADR-0008's guarantee that the shape does not change, and by C3's pin — the
  demo repo depends on a version rather than a copy.
- **The runbook's section 0 is already stale** (dated 2026-09-11; it says "No
  HTTP turn endpoint yet", which is no longer true). Acting on a stale runbook
  is a real risk; updating section 0 and ticking P2 is a task here.

## Migration Plan

Ordered so nothing is carried twice and the demo keeps working throughout:

1. `add-schema-discovery-for-query-building` lands (its changes are in the
   carry-set).
2. Reel A4/A5: `pyproject.toml`, CI.
3. B-runtime: carry the modules, add the `config` module, rename `EXON_*` →
   `REEL_*`, keep the wire shape byte-for-byte.
4. Dockerfile and first tag (C1).
5. `ide` gains the planning-service slot; `MOSAIC_EXON_URL` and `--mcp` on the
   Mosaic services.
6. C3: `exon/` here becomes a pointer plus a pin.
7. Later, unblocked by none of the above: task 2.5, then B-harness, then 2.4
   deletes the QueryPlan modules in place.

Rollback: until step 6, this repo still has a working `exon/`, so any step can be
abandoned without the demo losing the capability.

## Open Questions

- Does the harness move at B-harness, or stay here permanently and point at
  Reel via `REEL_EVAL_CASES`? Phase B step 3 says it carries; A6's seam would
  also let it stay. Settle at B-harness, not now.
- Whether `query_router.py` is runtime or demo surface. It imports only
  `planner` constants and `spec_planner`, so it *can* carry; whether it *should*
  depends on whether the single-shot router is Reel's concern or the demo's.
