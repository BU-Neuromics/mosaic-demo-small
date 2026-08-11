## 1. Refresh this repo's capability manifest

- [x] 1.1 Pull `../hippo` to `origin/main` (done: `ec59c90` → `3bda128`, includes `relatedTo`).
      Confirmed the `mosaic` CLI/package on `PATH` is the editable install resolving to this
      checkout, not a stale pip release.
- [x] 1.2 Start the host-served Mosaic instance (`mosaic serve --config mosaic.yaml --graphql`)
      against this repo's existing `data/mosaic.db`. (Found and stopped a 5-day-stale process
      pre-dating the pull that was holding port 8080; restarted clean; currently running on
      `localhost:8080`.)
- [x] 1.3 Verified live: `Query.relatedTo` takes exactly `id: ID!, relationshipType: String` —
      no predicate argument. Verified live: `filters[].field` requires the snake_case slot name
      (`sample_type`, `brain_region`, `workflow_type`, `history_of_rhi`); the camelCase GraphQL
      field name silently returns an empty result. Regenerated
      `evals/schema/{introspection,mosaic-domain-schema,capabilities}.json` against this live
      instance (`capabilities.json`'s own pre-existing `_meta.known_gotcha` already documented
      the field-casing footgun — confirmed it, updated `_meta.captured_against` to `3bda128`,
      and added the `relatedTo`/mosaic#148/#149 details to the `Sample` reverse-relationship
      entry).

## 2. Correct this repo's specs to match verified reality

- [x] 2.1 `small-demo-schema` spec delta (in this change's `specs/`) already reflects the
      live-verified finding.
- [x] 2.2 Reclassified q24/q25 in `evals/questions.yaml` from `blocked` to `traversal`; verified
      live against DNR-0001 (q24: 3 samples → 3 bounded `relatedTo` calls → 9 workflows → 6
      datasets) and the full 115-sample tissue-request set (q25: 115 bounded calls, 45/115
      samples matched an `rna_seq` workflow — cross-validates the prior full-scan workaround's
      own reported 45/115). `evals/expected-results.json` updated with both real results.
- [x] 2.3 Added `q34`, scoped to the single-sample predicate-filtered case mosaic#148 actually
      blocks, with `blocked_by: [mosaic#148]`.
- [ ] 2.4 **Still pending user decision**: whether to also patch the already-archived
      `small-demo-schema` spec's stale camelCase filter examples — not done, out of scope until
      confirmed.

## 3. Implement Exon v1 in this repo

- [x] 3.1 Scaffolded `exon/` (`schema.py`, `ops.py`, `validator.py`, `executor.py`,
      `planner.py`, `cli.py`/`__main__.py`) — no framework, single-purpose modules.
- [x] 3.2 Schema-grounding implemented and verified live against the running instance.
- [x] 3.3 LLM planner implemented (forced structured output via `tool_choice`). **Revised to
      use `litellm.completion()` instead of the `anthropic` SDK directly** (design.md Decision
      7 addendum) so the provider is configurable via `EXON_MODEL` (a `litellm` model string)
      rather than hardcoded. Verified live (no real credentials needed): switching `EXON_MODEL`
      across `anthropic/...`, `openai/...`, `gemini/...` correctly routes to each provider's own
      missing-credentials error — confirming the provider genuinely changes. Caught and fixed a
      real gap in the same pass: `litellm` maps different providers' missing-credentials errors
      to *different* exception subclasses (`AuthenticationError` for Anthropic,
      `InternalServerError` for OpenAI) — catching only the former let the latter fall through
      as a raw traceback; fixed by catching the shared `openai.APIError` base instead. **Still
      could not be exercised end-to-end (a real model call)** — no provider API key is set in
      this environment. Fails loudly with a clear `RuntimeError`, not a silent fallback; a real,
      stated limitation of this build, not a design shortcut. See `exon/README.md`.
- [x] 3.4 Dry-run validator implemented and unit-verified: rejects a camelCase filter field, an
      unsupported filter op (`GT`), an unscoped `related_lookup`, and (added after a second
      review pass) a bogus `select_fields`/`forward_relation.select_fields` entry — each with a
      specific reason; accepts a correctly-shaped plan.
- [x] 3.5 Executor implemented against the host-served endpoint. A second review pass caught
      three real bugs, all fixed and re-verified: (a) snake_case applied to GraphQL output
      *selection* instead of camelCase, conflating it with the filter vocabulary — the exact
      mosaic#149 distinction this project is about; (b) pages returned without checking
      `items` vs `total`, so a result exceeding `limit` (default 100; full set is 115) would
      have silently truncated — now paginates until complete; (c) the GraphQL accessor name was
      guessed instead of read from `hippoSchema.accessor_name`. See `exon/README.md`.
- [x] 3.6 Ran the driving example end-to-end twice with a hand-built `QueryPlan` (standing in
      for the LLM step): once per-region (26 hippocampus tissue samples, 9 with an `rna_seq`-
      referencing workflow) and once after the pagination fix, default `limit=100`, across all
      4 regions — correctly retrieved all 115 samples and found 45/115 with an `rna_seq` match,
      matching the prior full-scan workaround's figure exactly. **Then ran it for real** against
      `ollama_chat/gemma4:12b` (local, no cloud credentials available) — found and fixed two real
      bugs (Ollama's `num_ctx` default silently truncating before any tool call; the grounding
      context feeding the model manifest-key labels instead of real `relationship_type` values),
      then observed the model's forced-tool-call reliability is genuinely low even after both
      fixes, and that a structurally-valid plan it did produce silently dropped the stated
      filter and the RNA-seq lookup — a faithfulness gap the validator has no way to catch. See
      `exon/README.md`'s "What actually happened" for the full account; not glossed over.
- [x] 3.7 Documented in `exon/README.md`: architecture, how to run it, what actually happened,
      the bug found and fixed, and known limitations.

## 4. File the two upstream issues

- [x] 4.1 Filed: [mosaic#148](https://github.com/BU-Neuromics/mosaic/issues/148) — "GraphQL
      API: `relatedTo` has no predicate/filter on the referenced entity" (design.md Decision 4).
- [x] 4.2 Filed: [mosaic#149](https://github.com/BU-Neuromics/mosaic/issues/149) — "GraphQL list
      filters silently return empty results when field uses the GraphQL field name instead of the
      underlying LinkML slot name" (design.md Decision 5).
- [ ] 4.3 Update task 2.3's benchmark question with mosaic#148 (done above; carry into
      `evals/questions.yaml` when task 2.3 is implemented).

## 5. Validate and wrap up

- [x] 5.1 `openspec validate add-exon-query-planner --strict` — passes.
- [x] 5.2 Reported: validator/executor fully proven (see 3.6). Planner now run for real against
      a local Ollama model — two real bugs found and fixed (`num_ctx` truncation, manifest-label
      confusion), but forced-tool-call reliability and instruction-faithfulness are both low
      with this specific 12B local model; a cloud-model run (Anthropic/OpenAI/Gemini) was never
      attempted (no credentials available). Not yet archived — holding until either a stronger
      model is tried, or the faithfulness gap is explicitly accepted as a known limitation
      (`exon/README.md`'s "Known limitation" section), and until 2.4 is resolved.
