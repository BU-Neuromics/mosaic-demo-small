# Tasks

## 0. Pre-flight (none of this boots anything)

- [x] 0.1 Confirm the Docker daemon is running. It was **not** running when this
      change was written (`Cannot connect to the Docker daemon`), so this is a
      hard prerequisite, not a formality.
- [x] 0.2 Confirm `ghcr.io` is reachable and the certified base images are
      pullable. The solo recipe builds locally (`build: .`) `FROM` digest-pinned
      published images; it does **not** pull a prebuilt `datahelix-solo` image.
- [x] 0.3 Confirm no submodule initialization is needed. DataHelix's `aperture`
      and `mosaic` submodules are uninitialized, and the solo Dockerfile does not
      use them — it consumes `ghcr.io` images by digest. Do not init them.

## 1. Establish the certified serving path

- [x] 1.1 Confirm the DataHelix working checkout is clean, then check out
      `main` in place (leaving `fix-solo-recipe-schema-dir-imports` unmerged
      and unmodified). Record the branch it came from so it can be restored.
- [x] 1.2 Confirm the pin at that checkout — the evidence is the solo
      `Dockerfile`'s `ARG MOSAIC_IMAGE` digest, which must match
      `certification/composition.lock.json`'s mosaic entry
      (`sha256:ded2942…`, v0.13.0). On the local branch that ARG is
      `sha256:2ac3e3c…` (v0.12.1) — the crash-loop digest. The digest, not the
      branch name or the lockfile alone, is what decides whether the boot is
      meaningful.
- [x] 1.3 Boot the recipe:
      `cd deploy/recipes/solo && PROJECT_DIR=<abs path>/mosaic-demo-small make up`.
      Capture the container logs for the first 60s.
- [x] 1.4 Assert the specific historical failure is gone: no crash-loop, and no
      `Workflow.input_samples: required: true` error in the logs.
- [x] 1.5 Confirm the endpoint answers — GraphQL reachable, and the Aperture SPA
      loads at the recipe's published port.

## 2. Re-audit the stale capability markers

- [x] 2.1 For `q34` (`blocked_by: mosaic#148`): run its query against the
      *running container* and record whether `relatedTo` now accepts a
      predicate. Empirical, because commit search did not resolve whether #148
      shipped in v0.13.0.
- [x] 2.2 For `q32` / `q33` (`blocked_by: mosaic#96`): confirm the expectation
      that they remain blocked at v0.13.0 (aggregation work `63962ae` is not an
      ancestor of the tag). If they unexpectedly pass, that contradicts the
      ancestry evidence and must be reconciled before proceeding, not
      explained away.
- [x] 2.3 Update each marker to reflect the pinned version, recording *which
      Mosaic version* the block applies to rather than leaving an unscoped
      `blocked`. Any question that flips to passing gets a verified entry in
      `evals/expected-results.json`, per the existing
      "Supported question has a verified expected result" requirement.

## 3. Prove parity against the verified per-question results

The invariant is `evals/expected-results.json` — the per-question result sets
(`q01`…) that the existing spec already requires to have been produced by
running real queries against live data. The files in `evals/baselines/` are
**not** suitable here: they are LLM eval runs (keyed `model`, `scores`,
`wall_clock_s`, `fingerprint_id`), so diffing them across a serving-path change
would measure model nondeterminism, not Mosaic behaviour.

- [x] 3.1 Confirm the fixture is seed-stable (`generate.py --seed 0`) before
      running — `expected-results.json`'s ids are only valid under that seed.
- [x] 3.2 Execute each question's GraphQL query against the container endpoint.
- [x] 3.3 Diff the results against `evals/expected-results.json`, classifying
      every divergence as: expected-improvement (a stale marker that correctly
      flipped), expected-parity, or regression.
- [x] 3.4 Any regression blocks the change — report it rather than adjusting
      `expected-results.json` to match.
- [x] 3.5 Separately, note whether the Exon LLM harness still runs against the
      container. It is not the parity evidence, but a hard failure there is
      worth surfacing rather than discovering later.

## 4. Retire the workaround in the docs

- [x] 4.1 Rewrite `README.md`'s "Two Mosaic builds in play" section to match the
      verified outcome, keeping the host-serve command documented for the
      conversational track (which the container still cannot serve).
- [x] 4.2 State explicitly which Mosaic version the container path provides
      (0.13.0) versus what `main` carries, so the next reader does not assume
      the container has `converseQuerySpec`.
- [x] 4.3 Restore the DataHelix checkout to its original branch.

---

## Verified findings (2026-09-17, container = mosaic 0.13.0, digest `ded2942…`)

**Boot:** healthy, `RestartCount: 0`, no `input_samples: required: true`.
SPA/docs HTTP 200, GraphQL answers, data intact (300 donors / 900 samples /
1200 workflows). The workaround's original cause is gone.

**Parity vs `evals/expected-results.json` (35 questions) — zero regressions:**

| Outcome | Count | Detail |
|---|---|---|
| Exact parity | 26 | byte-identical responses |
| Parity after a contract change | 3 | q26/q27/q28 — see below |
| Multi-step, not a single query | 3 | q24/q25/q35 |
| Newly unblocked | 2 | q32, q33 |
| Still blocked | 1 | q34 |

**Contract change (not a regression):** 0.13.0 returns search results as a page
envelope (`{items,total,limit,offset}`); the baseline captured a bare list. The
stored queries `{ searchDonors(q:…) { id name } }` are now invalid. Adapted to
`{ … { total items { id name } } }` they return **identical data** — q26
`DNR-0001 / Michael Jones`, q27 `DTST-0001 / Proactive bandwidth-monitored
intranet`, q28 empty. `evals/questions.yaml` and `expected-results.json` need
updating to the envelope shape; that is a benchmark debt, not a platform defect.

**q32 / q33 are UNBLOCKED, contradicting this change's written expectation.**
The proposal predicted they would stay blocked because mosaic#96's work traced
to `63962ae`, which is not an ancestor of v0.13.0. That commit is the **MCP**
aggregation surface (#195); the **GraphQL list surface** aggregation (#156,
ADR-0007) closed 2026-08-19, one day *before* the v0.13.0 tag, and is in.
Verified live: `donors(orderBy: AGE_AT_DEATH, orderDir: DESC, filters:[{field:
"age_at_death", value:65, op:GT}])` → 174, correctly sorted (99, 96, 95, 95,
95); `donorsFacetCounts(field:"cohort")` → control 125 / case 104 / at_risk 71.
This is exactly the outcome the "empirical re-audit" requirement exists to
catch — issue-state inference was wrong, the live check was right.

**q34 is genuinely STILL BLOCKED at 0.13.0.** `relatedTo` still takes only
`(id, relationshipType)` — no predicate argument — so mosaic#148's fix is *not*
in the release despite the issue closing 2026-08-20. Its `blocked` marker is
correct and must be scoped to 0.13.0 rather than cleared.

**Traversal primitives intact:** `relatedTo(id:"SMPL-0032",
relationshipType:"input_samples")` → 4 workflows; q35's bounded step-1 returns
`total: 26`, matching its expected response exactly.

**Closeout (2026-09-17):** README's "Two Mosaic builds in play" rewritten —
container is now the documented default, with a capability table naming what
v0.13.0 lacks (`converseQuerySpec`, CORS, `relatedTo` predicate) and pointing
the conversational track at `datahelix/deploy/recipes/ide/`. Four other stale
claims in README fixed. DataHelix restored to
`fix-solo-recipe-schema-dir-imports`. Tasks 2.3 and 3.5 remain open: the
`capability: blocked` markers still need version-scoping with verified results
for q32/q33, the search questions need the page-envelope shape, and the Exon
LLM harness has not been run against the container.

**Tasks 2.3 / 3.5 closed 2026-09-17.**

- `evals/questions.yaml` + `evals/expected-results.json`: q26/q27/q28 reshaped to 0.13.0's
  page envelope (`{total, items{...}}`); q32 flipped `blocked` → `filter` and q33
  `blocked` → `aggregation`, both with results verified live against the certified
  container (174 donors ordered 99/96/95/95/95; control 125 / case 104 / at_risk 71).
  q34 stays `blocked` but now carries `blocked_at_version: mosaic 0.13.0` plus a note
  that mosaic#148 closed 2026-08-20 yet is **not** in the v0.13.0 tag — so the marker is
  re-audited per release rather than inferred from issue state.
- `_meta.captured_against` now states the mixed provenance per entry rather than claiming
  a single capture, and records the envelope shape change.
- Parity re-run after the fixes: **31 PARITY, 4 multi-step, 0 regressions, 0
  blocked-but-passing** (was 26 parity / 3 stale-blocked / 3 shape failures).
- 3.5: Exon's own suites are green — 72 via pytest
  (`test_spec_planner`, `test_conversational_planner`, `test_conversational_orchestrator`,
  `test_conversational_server`) plus the 4 script-style harness checks
  (`test_harness_invariants`, `test_grading`, `test_independence`, `test_runner_fake`),
  which are NOT pytest-collectable — they `sys.exit()` at module level and must be run as
  `python -m tests.<name>`.

Current state is documented in `DEMO.md` §7.
