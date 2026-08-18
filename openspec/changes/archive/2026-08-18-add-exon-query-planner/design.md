## Context

The user's own framing (see proposal.md's Why) sets the bar: Exon takes one verbatim NL request
and must return a correct, validated result — never a plausible-looking wrong one. Two things,
verified live against this repo's running instance during this session (not assumed from a diff
or from memory), determine what's achievable today:

1. `relatedTo(id, relationshipType)` (mosaic#146/PR#147) exists and works, but accepts no
   predicate on the referenced entity's own fields (confirmed via live introspection of
   `Query.relatedTo`'s args: exactly `id: ID!, relationshipType: String`). A live call
   (`relatedTo(id:"SMPL-0001")`) returned the referencing workflow's envelope with
   `data.workflow_type` (snake_case), no way to filter it server-side.
2. **List filters require the snake_case LinkML slot name in `field`, not the GraphQL field
   name.** Reproduced live on four fields: `samples(filters:[{field:"sampleType",...}])` →
   `total: 0` (wrong); `samples(filters:[{field:"sample_type",...}])` → `total: 278` (correct,
   matches a plain listing). Same pattern for `brainRegion`/`brain_region`,
   `workflowType`/`workflow_type`, and `historyOfRhi`/`history_of_rhi` — the last one **contradicts
   this repo's own already-archived spec's prose example** ("Filtering donors by RHI history"
   shows the camelCase form). Not a regression, though: this repo's own executable benchmark
   question q05 already uses the correct `history_of_rhi` form and is verified working
   (`expected-results.json`: `total: 50`); the spec's illustrative prose example, by contrast, was
   apparently never run in the camelCase form it shows — a documentation error in the archived
   spec's prose, distinct from the benchmark's own (correct) executable questions, not evidence
   platform behavior changed. Single-word fields (`sex`, `cohort`, `donor`) "work" either way only
   because snake_case and camelCase are spelled identically for one word — not evidence the
   camelCase form is honored. `hippoSchema`
   already exposes the correct (snake_case) names per entity, so a caller has a source of truth
   to build correct filters from — but nothing signals that ordinary `__type` introspection
   (camelCase) is the wrong vocabulary to use for the `field` argument. Checked for a duplicate:
   not #129 (unvalidated `op` values, not `field` names — closed, unrelated), not mentioned in
   #45's parity map.

Both findings matter because Exon's core discipline (below) is "reject, don't approximate" — and
finding 2 is a failure mode that ordinary schema-conformance validation *cannot* catch: the
camelCase field name is genuinely valid on the GraphQL type, it's just the wrong vocabulary for
`filters[].field`. The planner and validator must be built with this known from day one, not
discovered the way this session discovered it.

## Goals

- Take one NL instruction (the project's driving example) and produce a typed query plan grounded
  in live schema introspection — never in assumed field names or casing.
- Dry-run validate the plan against a live capability manifest before executing anything.
- Execute against this repo's live GraphQL endpoint and return a correct, verified raw result.
- Bring this repo's specs and benchmark up to date with the now-fixed (but still partial)
  `relatedTo` capability.
- Surface both live-verified platform gaps upstream, precisely scoped.

## Non-Goals

- Multi-turn conversation, session state, rewind/edit, or reproducibility-over-time (as-of
  watermarks) — v1 is one instruction in, one result out.
- Any rendering layer / visual output contract — the planner returns a raw, typed result (a list
  of records), not a chart or table component.
- Aggregation (group-by/count/sort/range/facets) — unsupported upstream (mosaic#96, open); the
  validator rejects plans needing it.
- Anything involving another repo or component. Exon's code, spec, and tests all live in this
  repo.

## Decisions

### 1. Where this lives: entirely inside `mosaic-demo-small`

No external repo, no upstream component dependency. A new `exon/` package here: a small,
single-purpose planner + validator + executor, following this repo's existing "simplicity first"
convention (openspec/AGENTS.md) — boring, proven patterns, no framework.

### 2. Op catalog (only what the driving example needs)

| Op | Backing query | Status |
|---|---|---|
| `filter` (equality/`IN`, using the **slot name from `hippoSchema`**, never the GraphQL field name) | `<entities>(filters:[...], filterMode:...)` | ✅ supported |
| `related-filter` (forward, single-valued FK) | nested selection or root filter (`samples(filters:[{field:"donor",...}])`) | ✅ supported |
| `related-filter` (reverse, multivalued/relationships-table) | `relatedTo(id, relationshipType)` **+ bounded client-side filter**, one call per already-identified id | ⚠️ partial — Decision 4 |
| `return-result` | n/a | returns the raw validated record set — no rendering |

Out of scope for v1 (not needed by the driving example and/or blocked): `distinct-values`,
`group-by+count` (mosaic#96), `pivot`, `set-op`.

### 3. Dry-run validator: reject, don't approximate

Before executing anything, the validator checks each op against:
- **The live capability manifest** — an op needing group-by/count/sort/range is rejected.
- **The live `hippoSchema`** — every `filter`/`related-filter` field name must resolve to an
  actual slot in `hippoSchema` for that entity type. A plan using a GraphQL-camelCase name that
  doesn't independently appear in `hippoSchema`'s slot list is rejected before execution, not
  silently sent as a filter that will return an empty result (Decision 5's finding, made
  structural here rather than left as a footgun).
- **Reverse relationship existence-with-predicate** — allowed only as one `relatedTo(id,
  relationship_type)` call per already-identified id, each filtered client-side over that call's
  own small result; never an unfiltered scan across an entire entity table. Holds for any number
  of already-identified ids, not just one.
- Anything else unrecognized → rejected with a reason, never guessed.

### 4. The `relatedTo` predicate gap (mosaic#148, filed)

Verified live (Context, finding 1): `relatedTo` takes `id` + optional `relationship_type` only.
"Workflows of type `rna_seq` that reference sample X" is answerable (one `relatedTo` call + a
small client-side filter) but not a single composed, server-side-filtered query.

Filed:
- **Title**: "GraphQL API: `relatedTo` has no predicate/filter on the referenced entity"
- **Body**: contrast with the existing root-level equality-filter pattern on forward FKs
  (`samples(filters:[{field:"donor", value:$id}])`); request either (a) an optional `filters`
  argument on `relatedTo` applied to the resolved entities before return, or (b) documented
  existence-only-by-design with fan-out size guidance.
- **Contrast with #146**: #146 was "no reverse lookup at all" (existence); this is "the lookup
  exists but can't carry a predicate" (join-filter) — distinct, narrower.

### 5. The filter field-name-casing gap (mosaic#149, filed, higher severity)

Verified live (Context, finding 2): `filters[].field` requires the snake_case slot name; the
camelCase GraphQL field name silently produces an empty result, not an error.

Filed:
- **Title**: "GraphQL list filters silently return empty results when `field` uses the GraphQL
  field name instead of the underlying LinkML slot name"
- **Body**: repro across `sampleType`/`sample_type`, `brainRegion`/`brain_region`,
  `workflowType`/`workflow_type`, `historyOfRhi`/`history_of_rhi`; note `hippoSchema` already
  exposes the correct names, so the fix is either (a) accept both forms (resolve camelCase to the
  underlying slot before filtering), or (b) reject an unrecognized `field` value with an error
  instead of silently matching nothing. (b) alone would already convert this from a silent-wrong-
  answer bug into a loud, safe one.
- **Severity note**: flag as higher priority than mosaic#148 — a valid-shaped empty result is
  indistinguishable from "no matching data," which is far more dangerous for any automated
  client (including Exon) than a capability that's merely unavailable.

### 6. Execution target: host-served Mosaic, not the solo container

Per this repo's existing README, the `datahelix` solo container is pinned to a published image
predating `relatedTo`. Exon talks to `mosaic serve --config mosaic.yaml --graphql` (the host-side,
freshly-pulled `../hippo` checkout) — already running for this session on `localhost:8080`
(replaced a 5-day-stale process that predated the pull).

### 7. LLM planner: schema-grounded, structured output, validated before execution

The planner takes the NL instruction + live `hippoSchema` + the capability manifest as context and
emits typed ops via structured/forced output (never free-text GraphQL), so the validator
(Decision 3) has something to check before anything runs. Model/token strategy (e.g. caching the
schema-grounding context rather than resending it every call) is an implementation detail, not
pinned here — the hard requirement is that grounding always comes from live introspection.

**Provider-agnostic via `litellm`** (revised after initial implementation, which called the
`anthropic` SDK directly): the planner calls `litellm.completion()` instead, using OpenAI-style
`tools`/forced `tool_choice`, which `litellm` translates to whichever provider the configured
model string names. `EXON_MODEL` is now a `litellm` model string (e.g.
`anthropic/claude-opus-5-20251101`, `openai/gpt-4o`, `gemini/gemini-1.5-pro`,
`ollama/llama3`) — the provider is a deployment-time choice, not a code change. Credentials
follow `litellm`'s standard per-provider env var convention (`ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`, etc., inferred from the model string's prefix), so the validator/executor's
"never guess, always read from the live grounding" discipline extends to provider selection
too — Exon doesn't hardcode an assumption about which LLM vendor is available. The op catalog,
validator, and executor are unaffected; only `planner.py`'s call surface changed.

Verified live (no real credentials needed to prove this): switching `EXON_MODEL` between
`anthropic/...`, `openai/...`, and `gemini/...` correctly routed to each provider's own
missing-credentials error, confirming the provider genuinely changes, not just the model name
under one hardcoded vendor. One thing this surfaced: `litellm` normalizes every provider's
errors onto `openai`'s exception hierarchy, but *which* subclass it uses isn't consistent
across providers for the same underlying problem (Anthropic's missing-key case raises
`AuthenticationError`; OpenAI's raises `InternalServerError`) — catching only
`AuthenticationError` (the first attempt) let the OpenAI case fall through as a raw traceback.
Fixed by catching the shared base, `openai.APIError`, instead of guessing which subclass a
given provider uses.

### 8. Reclassifying q24/q25 (mosaic#146, their old `blocked_by`, is now closed)

- **q24** ("donor → samples → workflows-that-consumed-them → datasets"): donor→samples is one
  filtered query; samples→workflows is one bounded `relatedTo` call per sample in that (small)
  set; workflow→datasets is a root filter. **Reclassify to its ordinary traversal capability.**
- **q25** ("does an rna_seq dataset exist for the tissue-request sample set"): one bounded
  `relatedTo` call per sample in that set (115, per the existing note), filtered client-side by
  `workflow_type == "rna_seq"` — no longer "fetch all 186 rna_seq workflows and match
  client-side." **Reclassify to its ordinary traversal capability**, noting the call count and
  citing mosaic#148 (Decision 4) as the reason it isn't one composed query, not as a reason it's
  unanswerable.
- Add one **new**, narrower benchmark question that mosaic#148 *does* block: a single already-known
  sample id, asking for its `rna_seq`-typed referencing workflow(s) as one composed query.

## Risks / Trade-offs

- **LLM plan-generation is the least-proven part of this** — mitigated by the dry-run validator;
  a wrong plan is rejected, not silently executed. If the driving example can't be made to pass
  reliably, that's a real result worth reporting, not something to hide.
- **The filter-casing bug (Decision 5) could exist elsewhere in ways not yet found** — this
  change only verified four fields; worth a broader sweep before fully trusting the manifest, but
  not a blocker to building the validator defensively (Decision 3 already resolves names against
  `hippoSchema` rather than trusting either vocabulary blindly).
- **`relatedTo` fan-out could be large for some entities** — not this driving example's case, but
  worth naming explicitly in mosaic#148's request.

## Migration Plan

No data migration. Sequence: regenerate capability manifest → correct specs → implement `exon/` →
run the driving example → file both issues (done: mosaic#148, mosaic#149) → report results. Fully reversible;
nothing pushed anywhere, nothing touching another repo.

## Open Questions

- Exact typed-op/JSON-schema shape for the planner's structured output — an implementation detail
  to settle while coding.
- Whether to patch the already-archived `small-demo-schema` spec's stale camelCase filter
  examples as part of this change or as a separate, smaller follow-up — raised for the approval
  conversation, not resolved here.
