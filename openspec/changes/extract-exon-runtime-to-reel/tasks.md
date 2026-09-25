## 1. Record the departure before acting on it

- [ ] 1.1 Amend `reel/proposals/exon-migration.md`: split Phase B into
      **B-runtime** and **B-harness**, with the import-graph evidence and the
      reasoning that P1's rationale is a claim about the harness
- [ ] 1.2 Refresh that runbook's section 0 "Current state" — it is dated
      2026-09-11 and says "No HTTP turn endpoint yet", which
      `exon/conversational_server.py` has since made false
- [ ] 1.3 Tick precondition **P2**: the turn endpoint exists and was exercised
      by Mosaic's relay end to end — Aperture chat panel → `converseQuerySpec`
      → Exon → proposal → executed, verified in a browser 2026-09-21
- [ ] 1.4 Confirm P3/P4 (ADR ratification status) or record an explicit decision
      to proceed with them still `Proposed`

## 2. Prepare Reel's landing site

- [ ] 2.1 Reel A4: `pyproject.toml` for `datahelix-reel` — `src/` layout,
      `litellm` + `mcp` client deps, `reel[harness]` extra declared but unused
      until B-harness
- [ ] 2.2 Reel A5: `.github/workflows/tests.yml` mirroring this repo's test
      invocation (`pytest tests/`, no model calls)
- [ ] 2.3 Reel A6: register the `REEL_EVAL_CASES=<path>` fixture seam so the
      harness can point at this repo's `evals/` without copying it

## 3. Carry the runtime (Phase B-runtime)

- [ ] 3.1 Create the `config` module holding `MAX_ATTEMPTS`, `MAX_TOKENS`,
      `MODEL`, `REQUEST_TIMEOUT`, `decode_kwargs_for` — the one place this is
      not a pure copy (design.md Decision 3)
- [ ] 3.2 Carry `spec_planner`, `conversational_planner`,
      `conversational_orchestrator`, `conversational_server`, `mosaic_mcp`,
      `schema`; repoint their `from .planner import …` at `config`
- [ ] 3.3 Decide and act on `query_router.py` — carry or leave (design.md Open
      Questions); it imports only `planner` constants and `spec_planner`, so
      either is mechanically clean
- [ ] 3.4 Carry the runtime's unit tests (`test_spec_planner`,
      `test_conversational_planner`, `test_conversational_orchestrator`,
      `test_conversational_server`); leave `test_grading`,
      `test_harness_invariants`, `test_independence`, `test_runner_fake`
- [ ] 3.5 Rename `EXON_*` env vars to `REEL_*`, keeping the wire shape
      byte-for-byte (ADR-0008: the shape does not change at migration)
- [ ] 3.6 Carry the OpenSpec spec deltas as Reel's first specs, renamed
      `exon-*` → `reel-*`
- [ ] 3.7 Verify against a live Mosaic that the carried runtime reproduces the
      same discovery → proposal → 50 donors path this repo produces today

## 4. Package and publish

- [ ] 4.1 Dockerfile for the planning service — the turn endpoint on a
      configurable port, no fixtures baked in
- [ ] 4.2 First tag and image (Phase C1), CI green
- [ ] 4.3 Record the pin this repo will depend on

## 5. Mount it in DataHelix `ide`

- [ ] 5.1 Add the planning-service slot to
      `datahelix/deploy/recipes/ide/docker-compose.yml`, named so Phase D is an
      image swap rather than a rename
- [ ] 5.2 Set `MOSAIC_EXON_URL` on both the `mosaic` and `mosaic-dev` services
      — without it Mosaic never registers `converseQuerySpec` and Aperture's
      panel silently does not appear
- [ ] 5.3 Add `--mcp` to both Mosaic service commands; the planner reads the
      capability manifest over MCP and neither command passes it today
- [ ] 5.4 Confirm no gateway change is needed — Aperture reaches the panel over
      the already-routed `/graphql`, and Mosaic↔planner traffic is
      container-internal
- [ ] 5.5 Verify `make dev` end to end in a browser on `:8080`, with
      `solo-solo-1` stopped so it is not answering on that port instead

## 6. Hand this repo over to the dependency

- [ ] 6.1 Phase C3: replace `exon/`'s runtime with a pointer and a pin; keep
      `schemas/`, `generate.py`, `evals/`, `hints.yaml`
- [ ] 6.2 Archive this repo's `exon-*` OpenSpec specs with forward pointers to
      Reel's
- [ ] 6.3 Update `README.md`, `DEMO.md` and `APERTURE_EXON_CONTRACT.md` to
      describe a consumed service rather than a hosted one

## 7. Not in this change, recorded so it is not lost

- [ ] 7.1 Task 2.5 (harness re-baseline on result equivalence), including the
      undecided facet/range routing question in 2.5c
- [ ] 7.2 Phase B-harness, once 2.5 lands
- [ ] 7.3 Task 2.4: delete `planner.py`, `ops.py`, `validator.py`,
      `executor.py` in place
- [ ] 7.4 Phase C2 (`MOSAIC_EXON_URL` → `MOSAIC_REEL_URL` with aliases) and
      Phase D2 (certified ledger, `solo`)
