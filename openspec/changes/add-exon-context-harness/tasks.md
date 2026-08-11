## 0. Prerequisite: reconcile with post-#150 upstream (scores are meaningless until this is done)

- [x] 0.1 Pulled `../hippo` to `origin/main` — landed on `502991c` (one commit past the expected
      `7669fac`; #152 was a CI-only fix). Restarted the served instance and verified all three new
      behaviours live: `field: "sampleType"` → 278 (resolves), `field: "sample_type"` → 278
      (unchanged), unknown field → `UNKNOWN_FILTER_FIELD` listing the valid slots.
- [x] 0.2 Fixed `exon/validator.py`: resolves either spelling through `hippoSchema` via a
      slot index built from the live schema (never a guessed transformation); still rejects unknown
      names with the valid-slot list; newly rejects filters on multivalued reference slots (→ use
      `related_lookup`) and on computed provenance fields (→ use `asOf`), plus multivalued
      `forward_relation`. Verified with 10 assertions: 3 now-valid camelCase cases accepted, 7
      invalid cases rejected with specific reasons.
- [x] 0.3 Regenerated `evals/schema/{introspection,mosaic-domain-schema}.json` against the
      restarted instance. Replaced `capabilities.json`'s stale `known_gotcha` with
      `filter_field_vocabulary` (records #149 RESOLVED and what now happens instead) and
      `unfilterable_fields` (the two new `UNFILTERABLE_FIELD` classes); `known_gotcha` now carries
      only the still-open mosaic#148.
- [x] 0.4 Corrected stale `#149`-as-open prose in `exon/{ops,schema,executor,planner}.py`, added an
      "Upstream status" section to `exon/README.md`, and fixed the two `add-exon-query-planner`
      spec-delta scenarios that asserted camelCase silently returns zero. Also relaxed the
      over-strict field-name instruction the planner feeds the model. Both changes re-validate
      `--strict`.
- [x] 0.5 Re-verified the benchmark against the updated server: q05 = 50, q20 = 115, q24 =
      3 samples → 9 workflows → 6 datasets (same 6 ids), q25 = 115 bounded calls → 45 samples with
      an `rna_seq` workflow. **All match expected-results.json exactly — no regression.**

## 1. Capability probe

- [x] 1.1 `exon/harness/probe.py`: system-role adherence, protocol ladder, stop sequences,
      determinism at temp 0, preamble tendency, context window. 5 calls each, unanimous-only to
      qualify.
- [x] 1.2 `ModelFingerprint` persisted with raw evidence; `exon/context/seed.py` derives v000
      (protocol, decode params, corrective blocks) from it. Note it correctly produced ZERO blocks
      for gemma4:12b — the probe found no preamble tendency and perfect determinism, so seeding
      corrective blocks would be wasted tokens.
- [x] 1.3 `ContextArtifact.assert_fingerprint` refuses a context fitted to a different model; the
      CLI re-probes instead of reusing one.
- [x] 1.4 Ran against `ollama_chat/gemma4:12b`. **The probe immediately contradicted itself, which
      is the most useful finding so far**: every protocol passed 5/5, determinism read 100%, and
      preamble tendency 0% — yet the intermittent tool-call failures that motivated this change are
      real. The isolated ladder uses a trivial prompt; the real failures happen on ~1800 grounding
      tokens with 6-8k tokens of reasoning. An isolated-only probe would have told the loop
      "protocol is fine, must be a prose problem" and sent the refiner to reword instructions that
      were never the cause.
- [x] 1.5 **(added)** `_check_protocol_under_load` re-verifies the chosen protocol on a realistically
      sized request and demotes it if it does not hold. Both ctxtune's spec and the original
      version of this one specified only the trivial check; this is a correction to both.
      Also capped seed `num_ctx` at a working 32768 rather than the advertised 262144, which would
      allocate an enormous KV cache for a 2k prompt.

## 2. Context artifact

- [x] 2.1 `exon/context/template.py`: typed blocks, `DecodeParams`, `OutputProtocol`,
      `ContextArtifact` with version/parent/changelog, `render`, `apply_patch`, `validate`
      (placeholders + size cap), append-only `save`. Dataclasses rather than pydantic, matching
      `exon/ops.py` — the validation that matters here is custom anyway, and one idiom per package
      beats two.
- [x] 2.2 `planner.py`'s grounding split into `render_schema_slots` / `render_relationship_types` /
      `render_limitations` placeholder renderers; `DEFAULT_GROUNDING_BODY` is the same template the
      harness tunes, so a tuning gain reaches `python -m exon` unchanged.
- [x] 2.3 `plan_query` gained an injected `context` parameter, and `request_plan` was split out as
      the single stateless no-retry call for measurement. The retry stays only on the product
      surface: a retry is right for a user asking a question and wrong for measuring reliability.
      `python -m exon` still works unchanged.

## 3. Test suite

- [x] 3.1 `evals/plan-expectations.yaml` keyed to existing question ids. 29 in scope.
- [x] 3.2 `exon/harness/cases.py` with `load_suite` and a hard drift guard (an expectation naming an
      unknown question raises); matching is semantics-based, resolving spellings via `hippoSchema`.
- [x] 3.3 Split 21 train / 8 holdout, stratified so holdout covers filter, traversal and blocked.
- [x] 3.4 **(added)** Found that q20/q25 were UNSCORABLE and would have corrupted the tuning: both
      say "the tissue-request example", a reference to *other questions*, which a stateless planner
      cannot resolve. Demanding those regions tested mind-reading, and the refiner would have kept
      trying to fix an unfixable case — most likely by writing the regions into the context, exactly
      the answer-key memorization the lint exists to prevent. Added `q35`, the project's driving
      question verbatim and fully self-contained (verified live: 26 hippocampus tissue samples, 9
      with an `rna_seq` workflow); q20/q25 remain valid benchmark questions but are excluded from
      the harness suite with the reason recorded.

## 4. Run and grade

- [x] 4.1 `exon/harness/runner.py`: k samples/case, concurrent, stateless single-turn calls, no
      generation retries; transport errors retried then recorded separately.
- [x] 4.2 `exon/harness/grading.py`: the tier ladder, with execution only for tagged cases.
- [x] 4.3 Mean pass rate, strict k-of-k count and flake rate reported separately.
- [x] 4.4 Grader golden set (`tests/test_grading.py`, 23 checks) anchored on the two REAL captured
      plans — the faithful one passes, the `filters: []` one is `PLAN_UNFAITHFUL` and the detail
      names the specific missing filter. Also covers: over-filtering is unfaithful too; spelling and
      IN-list order do not matter; the manifest-label-as-relationship_type bug is caught; for blocked
      questions a rejected plan is the PASS and an accepted one is `MISSING_REJECTION`.
- [x] 4.5 **(added)** Fixed a real bug in `_compare_expected`: for a two-step plan the LAST step is
      the reverse lookup, so it compared 9 matches against the 26-sample total and failed a
      completely correct plan. Each stage is now compared against the figure that describes it.

## 5. Triage and refine

- [x] 5.1 `exon/harness/triage.py`: taxonomy, dedup, ≤3 examples per class, and the enabled blocks
      that were supposed to prevent each failure ("ALREADY TRIED"). `build_bundle` raises on any
      non-train grade rather than trusting the caller.
- [x] 5.2 `exon/harness/refine.py`: patch-shaped forced tool call via litellm, ≤3 block changes or
      one decode/protocol change, required `changelog` and `hypothesis`, and an explicit preference
      order that puts protocol/decode changes ahead of prose for format and determinism failures.
- [x] 5.3 Memorization lint (case ids, ≥8-word verbatim spans) + size cap + exemplar cap, all
      enforced on the candidate before it can be applied.
- [x] 5.4 Refiner is instructed to propose removing any block that did not reduce its target code,
      and the bundle gives it the evidence to judge that.

## 6. Loop

- [x] 6.1 `exon/harness/loop.py`: stops on threshold met, max iterations, plateau, regression
      (train up + holdout down ×2), or SIGINT with clean state flush.
- [x] 6.2 Returns the best **holdout**-scoring version, not the last, and rolls back any revision
      that regresses holdout. `report.md` carries the per-iteration table.
- [x] 6.3 Per-iteration artifacts under `runs/<ts>/` (context, report, bundle, patch + rationale) so
      a regression stays diffable; `runs/` is gitignored.
- [x] 6.4 `exon/harness/cli.py` + `__main__.py`: `probe | run | loop | report`, defaulting to
      report-and-stop (`--auto-refine` opts into the closed cycle).

## 7. Test the harness itself

- [x] 7.1 Fake litellm target (`tests/test_runner_fake.py`) — deterministic end-to-end runs with
      zero model calls, which matters when a real local-model run takes about an hour.
- [x] 7.2 Grader golden set — see 4.4 (23 checks, includes formatting-divergent-but-equivalent
      pairs that must pass).
- [x] 7.3 Holdout isolation asserted against the serialized bundle string, plus `build_bundle`
      refusing holdout grades outright.
- [x] 7.4 Patch apply-then-invert restores a byte-identical render; append-only versioning,
      fingerprint binding, placeholder and size guards all covered.
      (`tests/test_harness_invariants.py`, 28 checks.)

## 8. Verify

- [ ] 8.1 Baseline run on the seed context — **must reproduce the known dropped-filter failure**. A
      clean seed run means the harness is wrong, not the planner.
- [ ] 8.2 Force `EXON_OLLAMA_NUM_CTX=4096` and confirm `TRUNCATED` is reported but never appears in
      the refiner bundle. (Running; queued behind the loaded probe on the single Ollama instance.)
- [x] 8.3 Planner independence proven against the ACTUAL assembled prompts at the litellm boundary
      (`tests/test_independence.py`, 9 checks): every call is (system, user) with no assistant
      turns; no case id, expectation structure, rejection reason, or expected-results content
      appears; repeated samples send byte-identical prompts; `num_ctx` is correctly withheld from a
      non-ollama provider.
- [ ] 8.4 `loop --max-iter 2` end-to-end — blocked: no refiner credential in this environment.
      `--no-auto-refine` (report and stop) is exercised and works.
- [ ] 8.5 Report the before/after reliability numbers plainly.
- [x] 8.6 `openspec validate add-exon-context-harness --strict` passes.
