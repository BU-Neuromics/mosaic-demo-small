## 0. Prerequisite: reconcile with post-#150 upstream (scores are meaningless until this is done)

- [ ] 0.1 Pull `../hippo` to `origin/main` (`3bda128` → `7669fac`); restart the served instance and
      confirm live: `field: "sampleType"` now resolves, and an unknown field raises
      `UNKNOWN_FILTER_FIELD` instead of returning `total: 0`.
- [ ] 0.2 Fix `exon/validator.py`: accept either field-name spelling (resolved via `hippoSchema`),
      still reject unknown names, newly reject filters on multivalued reference slots and on
      computed/temporal fields.
- [ ] 0.3 Refresh `evals/schema/*.json`; rewrite `capabilities.json`'s `known_gotcha` (#149 fixed),
      keep `known_gotcha_2` (#148 open).
- [ ] 0.4 Correct stale `#149`-as-open language in `exon/README.md` and in the open
      `add-exon-query-planner` change, including its `small-demo-schema` scenario asserting
      camelCase silently returns zero.
- [ ] 0.5 Re-run the q24/q25 verifications to confirm no benchmark regression under the new
      filter-resolution behaviour.

## 1. Capability probe

- [ ] 1.1 `exon/harness/probe.py`: system-role adherence, protocol ladder (5/5 to qualify), stop
      sequences, determinism at temp 0, preamble tendency, context window. 5 calls each.
- [ ] 1.2 Persist `ModelFingerprint` including raw evidence; derive the seed context (v000) —
      protocol, decode params, initial OUTPUT_CONTRACT blocks — from it.
- [ ] 1.3 Refuse to reuse a stored context whose `fingerprint_id` doesn't match the current target.
- [ ] 1.4 Run the probe against `ollama_chat/gemma4:12b` and record the baseline — especially the
      determinism figure and which protocol tier actually qualifies.

## 2. Context artifact

- [ ] 2.1 `exon/context/template.py`: typed blocks, `DecodeParams`, `OutputProtocol`,
      `ContextArtifact` with `version`/`parent_version`/`changelog`; `render`, `apply_patch`,
      `validate` (required placeholders, size cap).
- [ ] 2.2 Refactor `planner.py`'s `build_grounding_context` / `_related_lookup_grounding` /
      `_manifest_limitations` into placeholder renderers — reuse, don't rewrite.
- [ ] 2.3 Add the injected-`context` parameter to `plan_query`; confirm `python -m exon "<question>"`
      still works unchanged.

## 3. Test suite

- [ ] 3.1 Author `evals/plan-expectations.yaml` keyed by existing `evals/questions.yaml` ids — no
      new NL questions. Include the driving example, the `capability: blocked` cases, and the
      failures already observed. Expectations describe required operations, not one query string.
- [ ] 3.2 `exon/harness/cases.py` with `load_suite` and an id-drift guard; semantics-based matching
      (spelling-insensitive via `hippoSchema`).
- [ ] 3.3 Assign train/holdout ~70/30, stratified by `capability`.

## 4. Run and grade

- [ ] 4.1 `exon/harness/runner.py`: k samples/case, concurrent (default 4), stateless single-turn
      calls, no in-runner generation retries; transport errors retried and recorded separately.
- [ ] 4.2 `exon/harness/grading.py`: the tier ladder; tier 3 execution only for tagged cases.
- [ ] 4.3 Report mean pass rate, strict k-of-k count, and flake rate separately.
- [ ] 4.4 Unit-test grading against the two real plans captured this session — the dropped-filter
      one must fail tier 2; the correct one must pass. No LLM call; this is the fast regression test.

## 5. Triage and refine

- [ ] 5.1 `exon/harness/triage.py`: failure taxonomy, dedup, ≤3 verbatim examples per code, plus the
      enabled blocks that were meant to prevent it. Accepts train-split grades only — raise
      otherwise.
- [ ] 5.2 `exon/harness/refine.py`: patch-shaped structured output via litellm; ≤3 block changes or
      1 decode/protocol change per iteration; required `changelog` and `hypothesis`.
- [ ] 5.3 Memorization lint + size cap; reject patches embedding a case id or ≥8-word verbatim span
      of a test question; reject exemplars copied from train cases.
- [ ] 5.4 Propose removal of any block that didn't reduce its target failure code.

## 6. Loop

- [ ] 6.1 `exon/harness/loop.py`: terminate on threshold met, max iterations, patience (no holdout
      improvement ×3), regression stop (train up + holdout down ×2), or SIGINT.
- [ ] 6.2 Return the **best holdout-scoring** version, not the last; print the v0→best diff and a
      per-iteration `train | holdout | strict | tokens` table.
- [ ] 6.3 Persist per-iteration artifacts under `runs/<ts>/`; implement `resume` from those files
      alone.
- [ ] 6.4 `exon/harness/cli.py`: `run | loop | report | resume`, defaulting to `--no-auto-refine`.

## 7. Test the harness itself

- [ ] 7.1 Fake litellm target returning scripted responses; end-to-end loop tests with zero model
      calls.
- [ ] 7.2 Grader golden set covering every failure code, including ≥10 formatting-divergent but
      semantically identical pairs that must pass.
- [ ] 7.3 Holdout isolation test asserting no holdout text appears in a serialized refiner bundle.
- [ ] 7.4 Patch algebra: apply-then-invert restores the prior artifact. Render determinism: same
      artifact → byte-identical prompt.

## 8. Verify

- [ ] 8.1 Baseline run on the seed context — **must reproduce the known dropped-filter failure**. A
      clean seed run means the harness is wrong, not the planner.
- [ ] 8.2 Confirm `TRANSPORT_ERROR` and truncation never appear in the refiner bundle (force with
      `EXON_OLLAMA_NUM_CTX=4096`).
- [ ] 8.3 Confirm planner independence by inspection: no history, prior plans, expectations, or case
      ids reachable from the planner prompt path.
- [ ] 8.4 `loop --max-iter 2` end-to-end once a refiner credential exists; verify rollback on
      regression and diffable run artifacts.
- [ ] 8.5 Report the before/after reliability numbers plainly — mean pass rate, strict count, and
      what remains failing.
- [ ] 8.6 `openspec validate add-exon-context-harness --strict`.
