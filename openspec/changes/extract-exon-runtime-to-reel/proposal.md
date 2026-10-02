# Change: Extract Exon's runtime into Reel, packaged and containerized

## Why

Exon is a prototype of a capability Reel is meant to own. Reel ADR-0008 settles
that: *"Exon seeds Reel's implementation — migrate the prototype, do not
rewrite; its turn contract is the v1 wire form of `Instruction`."* Exon's name
is retired at migration.

Two things force the question now rather than later:

1. **Exon is not deployable.** It lives inside this demo repo with no
   `pyproject.toml`, no Dockerfile, no image, no pin. DataHelix's `ide` recipe
   cannot mount a planning service because there is nothing to mount, so the
   conversational path can only be run as loose host processes. That is not how
   users reach it.
2. **The migration runbook blocks on a gate that does not apply to the part we
   need.** `reel/proposals/exon-migration.md` precondition P1 requires Exon
   Phase 2 complete — the QueryPlan path retired and the harness re-baselined
   (`add-mosaic-mcp-boundary` tasks 2.4–2.7, with an undecided design question
   inside 2.5c). Its rationale is that migrating an in-flight refactor loses the
   before/after the harness exists to provide.

**That rationale is about the harness.** The runbook treats Phase B as one
atomic carry, so the gate is applied to everything. It does not have to be.

## The seam, verified

The turn-path runtime imports nothing from the QueryPlan code. Its only tie to
`planner.py` is five constants and one helper:

| Module | Imports from siblings |
| --- | --- |
| `spec_planner.py` | `planner` (`MAX_ATTEMPTS`, `MAX_TOKENS`, `MODEL`, `REQUEST_TIMEOUT`, `decode_kwargs_for`) |
| `conversational_planner.py` | `planner` (same constants), `spec_planner` |
| `conversational_orchestrator.py` | `conversational_planner`, `planner` (constants) |
| `conversational_server.py` | `conversational_orchestrator` |
| `query_router.py` | `planner` (constants), `spec_planner` |
| `mosaic_mcp.py`, `schema.py` | nothing |

No `validator`, no `executor`, no `ops`. The **only** module coupled to the dead
path is `harness/grading.py`, which imports `validator.resolve_field` — the same
dependency task 2.4 already names as blocking its own deletion.

The runtime is also fixture-free: the only `evals/` references in those modules
are docstrings describing what the MCP capability manifest replaced. Nothing
reads `schemas/` or `evals/` at runtime.

So P1 gates the **harness** carry. It does not gate the **runtime** carry.

## What Changes

- **Split Phase B** of `reel/proposals/exon-migration.md` into **B-runtime**
  (now) and **B-harness** (after task 2.5), recording the reasoning above. This
  change is the authority for that amendment; the runbook edit is Reel's to make.
- **Carry the runtime to Reel**: `spec_planner`, `conversational_planner`,
  `conversational_orchestrator`, `conversational_server`, `query_router`,
  `mosaic_mcp`, `schema`, plus a small `config` module holding the five
  constants currently imported from `planner.py`.
- **Package it** — Reel A4 (`pyproject.toml` for `datahelix-reel`), A5 (CI), and
  a Dockerfile, then a first tag (Phase C1).
- **Leave behind, deliberately**: `harness/`, `context/` (blocked on 2.5);
  `schemas/`, `generate.py`, `evals/`, `hints.yaml` (domain fixtures, which
  Phase B step 4 already says stay); `planner.py`, `ops.py`, `validator.py`,
  `executor.py` (retired in place by task 2.4, never carried).
- **This repo consumes the planner as a dependency** rather than hosting it —
  `exon/` becomes a pointer plus a pin, which is Phase C3.
- **Mount it in DataHelix's `ide` recipe** as the planning service Mosaic
  delegates to.

## Impact

- **Affected specs:** `exon-query-planner` (ADDED), `exon-context-harness` (ADDED)
- **Affected code:** `exon/` (runtime modules leave; harness and fixtures stay)
- **Other repos, not owned here:** `reel` (Phase A4/A5/B-runtime/C1 and the
  runbook amendment), `datahelix` (the `ide` compose slot), `mosaic` (Phase C2's
  `MOSAIC_EXON_URL` → `MOSAIC_REEL_URL` aliasing, later)
- **Depends on:** `add-schema-discovery-for-query-building` landing first — its
  changes are in the carry-set, and carrying a stale copy would strand them
- **Does NOT depend on:** `add-mosaic-mcp-boundary` tasks 2.4–2.7 (P1), for the
  reason set out above

## Explicitly out of scope

- Task 2.5's harness re-baseline, including the undecided facet/range routing
  question in 2.5c. Naming it here is not scheduling it.
- Certifying the planner for the `solo` recipe. Reel migration Phase D2 puts
  Reel on the certified ledger "once it has a release and a Mosaic pair to
  certify against"; neither exists yet, and `ide` is explicitly exempt from the
  ADR-0001 deploy gate.
- Retiring the Exon name at the Mosaic boundary (Phase C2).
