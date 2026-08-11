## Context

This change consolidates a full validation pass over a supplied
architecture plan for building a natural-language-to-GraphQL query layer on
Aperture (source plan, with corrections applied throughout this document:
`/Users/christianlandaverde/.claude/plans/aperture-natural-language-graphql-fancy-biscuit.md`).
The original plan's own background section made several claims about the
current Mosaic/Aperture codebases; these were checked against real source
and live upstream state rather than taken at face value. Everything found
is captured here so it stays attached to the work, not scattered across
chat history.

## Goals / Non-Goals

- Goals: refresh the Mosaic dependency to latest upstream; make a
  realistic complex query (the tissue-request example) literally runnable
  end-to-end; produce an honest capability manifest and benchmark that
  distinguishes "supported today" from "blocked, tracked upstream."
- Non-Goals: this change does not build the query-plan compiler, the LLM
  planner service, or any Aperture UI — that's `datahelix`/`aperture`-repo
  work, preserved below as tracked follow-on scope, not implemented here.
  The tissue-request schema fields are an explicit spike, not a permanent
  schema commitment (open question below).

## Decisions

### Upstream freshness (Mosaic)

The local `../hippo` checkout (origin `github.com/BU-Neuromics/hippo`) was
found **10 commits / two releases behind** `origin/main` when checked.
Confirmed via `git diff`/`git show` on the clone and live GitHub API
queries against `BU-Neuromics/mosaic`:

- **mosaic#143 and #144 are already fixed upstream** (commit `ec59c90`,
  both closed on GitHub) — exactly the two bugs this demo's README
  documents as "filed, worked around" (migrate-idempotency crash on
  multivalued reference slots; unescaped FTS5 MATCH crash). Action: pull,
  re-verify against this demo's data, then remove both workarounds
  (`Workflow.input_samples` artificial non-required-ness; alphanumeric-only
  seeded search keywords) and update the README.
- **ADR-0005 "edge-only reference emission" already shipped** (commit
  `153b9bc`, merged before v0.12.0, breaking). Raw `*_id`/`*_ids` output
  scalars are removed entirely from generated GraphQL types; a reference
  slot renders as exactly one field — the resolved relationship object.
  This doesn't fix Aperture's own "reference selections return only an ID"
  query-builder limitation (that was always an Aperture choice, not a
  Mosaic constraint — nested selection into the resolved object already
  worked pre-ADR-0005), but it means **any Aperture code still selecting a
  raw `*_id` scalar field will now fail** against upstream Mosaic. Check
  for this when the `aperture` submodule/clone is inspected.
- **mosaic#96** (aggregation/facets/sort/range) confirmed **still open**
  upstream — no change to the original plan's treatment of it.
- **mosaic#132** (open): "Multivalued reference cardinality: cheap count
  without resolving the list (deferred from ADR-0005)" — adjacent to but
  distinct from the reverse-lookup gap below (it's about a cheap count on
  the *forward* direction).
- Searched for an existing tracker matching the reverse-lookup gap below
  (checked #45, a stale pre-ADR-0005 REST/GraphQL parity map, and #132) —
  **neither covers it**; a new issue is not a duplicate.
- `c263e8b` (merged, v0.12.x): filter-op validation now correctly rejects
  unsupported ops (previously `gt`/`lt`/`ne`/`contains` silently degraded
  to `eq`, returning wrong-but-plausible results) and `limit=0` now
  actually returns zero rows.

### Second genuine gap found during execution: certified container lags the fix it was supposed to pick up

Task 1.2 assumed that pulling `../hippo` to latest and restarting the
`datahelix` solo container would let the same fix reach both. It doesn't.
The commit that fixes #143/#144 (`ec59c90`) landed on `main` **after**
`v0.12.1` was tagged; no release has been cut past it, so no new digest
exists. The solo recipe's Dockerfile builds `FROM` a **digest-pinned,
published** `ghcr.io/bu-neuromics/mosaic` image (`v0.12.1`,
`sha256:2ac3e3c1…`, per `datahelix/certification/composition.lock.json`) —
by explicit design ("Never build components from source in this recipe"),
it cannot pick up an unreleased fix from `main`.

Confirmed empirically: restarting the running solo container after setting
`Workflow.input_samples: required: true` reproduced #143's exact
`ALTER TABLE error: Cannot add a NOT NULL column with default value NULL`
crash-loop, even though the same schema change against the host's editable
`../hippo` checkout (three consecutive `mosaic migrate` passes) was clean.
The container's Mosaic build simply doesn't have the fix — the earlier
"upstream freshness" section's `../hippo` pull only ever affected the host
checkout, never the certified container's independently-pinned image.

**Decision (user-directed)**: rather than either (a) keeping the
workarounds permanently — which would falsely claim the two filed bugs are
still unfixed — or (b) rebuilding the solo image locally from `main` —
which defeats the digest-pinned certification model the Dockerfile and
`composition.lock.json` explicitly commit to — this change's spike and
benchmark (tasks 3 and 5) run against a **host-side
`mosaic serve --config mosaic.yaml --graphql`** (the fixed `../hippo`
checkout) bound to the same port the container would otherwise use. This
is explicitly *not* "the certified solo container" and every `evals/`
snapshot notes which build actually served it, so nothing claims to
certify a deployment surface that can't yet exist.

**Follow-on, not part of this change**: `datahelix`'s certified-frontier
pin for `mosaic` needs to move past `v0.12.1` once BU-Neuromics/mosaic cuts
a release containing `ec59c90`, at which point the solo container will
regain parity with the host checkout and the caveat above can be dropped.
This is `datahelix` repo work (`composition.lock.json` + the bump-bot
process), tracked here for continuity, not implemented by this change.

### ADR-0005 raw-id-scalar check on the `aperture` clone (task 1.4) — negative result

Checked whether `../aperture-spike` (`e9b197b`, the tip of `main` at clone
time) selects any raw `*_id`/`*_ids` GraphQL scalar that ADR-0005 removed
upstream. It does not: `web/src/data/hippoSource.ts`'s `selectionFor`
already selects `ref`/`refList` columns as the nested resolved object
(`${column.field} { ${column.targetIdField} }`, e.g. `donor { id }`), not
a raw id scalar, and `ColumnModel`s are derived live from GraphQL
introspection rather than hardcoded — a schema that never publishes a raw
`*_id` field (as any current Mosaic instance now does, post-ADR-0005)
simply never produces a `column.kind === 'id'` entry for it. The one
`authorId` occurrence in the repo (`web/src/data/testing/realIntrospection.json`)
is a cached introspection fixture for an unrelated Book/Author test
domain, not part of the live query-building path. No action needed.

### Reverse relationship traversal (central finding)

The original plan's background implied relationship traversal is
generally bidirectional. In reality there are two distinct cases,
confirmed directly in `mosaic/graphql/schema_builder.py:379-504` and
`resolvers.py:283-311, 829-870`:

1. **Single-valued FK reference** (`Sample.donor`, `Dataset.produced_by`):
   forward resolution only. The target type gets **no nested reverse
   field** (no `donor.samples { ... }`) — but reverse lookup *is* possible
   via a **root-level equality/IN-filtered query** on the child type:
   `samples(filters: [{field: "donor", value: $donorId}])`. Any future
   query-plan/compiler design needs a "fetch children via filter" node
   distinct from "traverse via forward reference field," or it can't
   represent "show me this donor's samples."
2. **Multivalued reference stored in the shared `relationships` table**
   (`Workflow.input_samples`, ADR-0002): **no GraphQL-exposed reverse
   lookup at all** — no root query wraps `RelationshipManager.find_relationships`.
   The only reverse path is the SDK escape hatch
   (`client.relationships.find_relationships(target_id=...)`), never
   exposed through Aperture/GraphQL. Matches this demo's own README
   callout; a genuine Mosaic API gap, not a bug in this demo.

**Concrete impact**: two of the original plan's own benchmark examples
("starting from a donor, find the donor's samples and the datasets
containing those samples"; "show the workflow used to process each dataset
associated with a particular donor") are **not achievable today** — both
require the blocked multivalued reverse. They must be marked
`capability: blocked` in the benchmark, not answered via an unfiltered
forward scan + client-side match (that violates the plan's own
no-incomplete-page-approximation rule). Add one more benchmark question
that *is* achievable using only the donor→sample filtered-query leg, so
Phase 2 still has a working relationship-traversal example.

**Resolution — file it upstream, don't quietly downgrade the plan**:
- **Draft issue title**: "GraphQL API: no reverse-lookup query for
  relationships-table-backed multivalued references"
- **Draft issue body outline**: describe `Workflow.input_samples` as the
  concrete repro case; contrast with the existing single-valued-FK reverse
  pattern (`samples(filters:[{field:"donor", ...}])`); request either (a) a
  symmetric filter argument on the referencing entity exposed from the
  referenced entity's list query, or (b) a dedicated
  `relatedTo(entityType, id)` root query backed by
  `RelationshipManager.find_relationships`.
- Until it lands, affected benchmark questions get `blocked_by:
  [mosaic#146]`, the same pattern already used for `mosaic#96`.

### Tissue-request spike (why these 3 fields, this way)

The user's real-world motivating example: *"today we got a tissue request
today where the requester asked for 8 brain sample one from 4 regions all
of whom had hx of rhi. Bring me back all of the brain tissue samples that
we have for the brain regions selected and requested with the donor
attributes as specified and also possibly any RNASeq data for them to
send data to them rather than tissue."* This maps more naturally to
`brainbank-hippo-performance/hippo-benchmark`'s schema (it already has
real anatomical-region classes), but the user chose to extend this repo's
small demo schema instead, to keep the spike fast and self-contained.

- **Reuse the existing `WorkflowTypeEnum`** for `rna_seq` rather than a
  separate `assay_type` field/class — smaller diff; `workflow_type` is
  already the "what kind of pipeline run is this" facet.
- **`brain_region` is sparse/optional** — most samples
  (`blood`/`csf`/`urine`/`saliva`) have no meaningful brain region;
  `hints.yaml` has no conditional-on-another-field mechanism, so a small
  fraction of non-tissue samples may incidentally get a `brain_region`
  value. Acceptable for a spike.
- **`history_of_rhi` is required** (always populated, ~18% true) — a
  clean boolean facet, matching the existing pattern for
  `Dataset.is_public`.
- **The RNA-seq leg exercises the exact reverse-traversal gap above**:
  "does any RNA-seq dataset exist for these particular samples/donors"
  cannot be answered with one server-side query. The only route is
  `workflows(filters:[{field:"workflowType", value:"rna_seq"}])` with
  nested `inputSamples { id, donor { id } }`, then match ids **client-side**
  — which the plan explicitly forbids treating as a supported query
  pattern. The spike must present this leg as blocked/capability-dependent,
  demonstrating the client-side match only for illustration, never
  packaging it as a working query.

### Mechanical corrections to the source plan (text corruption, not substantive)

The original plan document had dropped characters throughout (e.g. "the
estion" for "the question", "relathips" for "relationships") and two
concrete defects worth fixing wherever this plan is referenced:
- The `QueryPlan` JSON example's `filters` key was malformed
  (`]": [` instead of `"filters": [`). Corrected form:
  ```json
  {
    "root_entity": "Dataset",
    "fields": [
      "id", "name",
      { "field": "sample", "selections": ["id", "tissueType", { "field": "donor", "selections": ["id", "sex"] }] },
      { "field": "workflow", "selections": ["id", "name"] }
    ],
    "filters": [{ "field": "assayType", "operator": "eq", "value": "RNA-seq" }],
    "limit": 50, "offset": 0
  }
  ```
- Milestone 3's last bullet was missing its subject: should read "No
  mutation operation can pass through the policy layer."
- The suggested `VITE_HIPPO_GRAPHQL_URL=http:localhost:8080/graphql` is
  both malformed (`http:` needs `//`) and contrary to the solo recipe's
  own relative-path default (`/graphql`, deliberately avoiding CORS) — use
  the relative default unless Aperture and Mosaic are on different
  origins.

## Work That Belongs In Each Repository (carried forward in full, out of scope here)

**This repo (`mosaic-demo-small`)** — everything in this change's
`tasks.md`: schema fields, data regeneration, the query spike, the
capability manifest, the benchmark.

**`../hippo` (Mosaic)** — pull to latest only; no code changes. Roadmap
dependencies tracked upstream, not implemented anywhere in this
initiative: sorting, range filters, facet/group-by counts, relationship
counts (mosaic#96, mosaic#132), cursor pagination, explicit schema
versioning/fingerprint exposure, query-cost controls beyond relationship
depth, and — newly identified by this change — reverse-lookup support for
relationships-table-backed multivalued references (new issue, drafted
above).

**`datahelix`/`aperture`** — the full remaining architecture from the
original plan, none of it implemented by this change:
- **Phase 3 (query model)**: recursive `Selection` type (forward nested +
  the "fetch children via filter" reverse case identified above); a
  generic read-query compiler; GraphQL-variable-based value binding;
  validation against live introspection; a developer query workbench.
- **Phase 4 (read-only LLM service)**: server-side agent
  (`src/aperture/agent/{app,models,schema_registry,semantic_catalog,planner,compiler,validator,policy,executor,answerer}.py`)
  — schema registry with fingerprint-based cache invalidation; semantic
  catalog compact enough for an LLM prompt; intent planner returning only
  a validated `QueryPlan`, never raw GraphQL; deterministic compiler;
  policy layer (query-only, no mutations/subscriptions, row/depth/timeout
  limits, field denylist); executor against the scoped/bridge
  architecture; result answerer that always shows the generated GraphQL.
- **Phase 5 (validation and bounded repair)**: the 9-step
  plan/entity/relationship/operator/compile/parse/policy/execute/response
  validation pipeline, with exactly one bounded repair attempt on
  structured validation errors — never an open-ended retry loop.
- **Phase 6 (Aperture UI integration)**: "Ask Aperture" conversational
  panel showing interpretation, result summary, table, GraphQL, variables,
  and limitations; actions to open results as a collection, apply filters,
  pivot entities, save views, export, copy the GraphQL.
- **Evaluation strategy**: query validity, semantic correctness,
  capability honesty (no aggregation from an incomplete page; distinguish
  "no records matched" from "not representable today"), safety (read-only,
  limits enforced, no leaked credentials, prompt-injection resistant), and
  transparency (GraphQL always inspectable) — proposed initial targets:
  ≥90% of supported benchmark questions compile+execute, ≥85% produce the
  expected result, 100% of unsupported questions correctly identified as
  such, zero mutations executed.
- **ADR to record**: "Aperture's natural-language layer will generate a
  typed, schema-derived query plan. Application code will compile,
  validate, authorize, and execute GraphQL. The LLM will not directly
  execute arbitrary GraphQL."
- **Milestones** (unchanged from the original plan): M1 GraphQL contract +
  benchmark; M2 general query engine; M3 read-only NL prototype; M4
  evaluation and hardening; M5 Aperture UI integration.

## Migration Plan

1. Pull `../hippo` to latest; re-run `make migrate && make ingest` in this
   repo; confirm mosaic#143/#144 stay fixed against this demo's own data
   before removing the workarounds.
2. Add the 3 schema fields + `hints.yaml` entries; regenerate/migrate/
   ingest; confirm the already-running `localhost:8080` instance reflects
   the new fields (restart the solo recipe if it doesn't pick them up
   live).
3. Clone `../aperture-spike`, branch `spike/nl-graphql-query-explore`;
   hand-write and run the example query; capture the result (including
   the documented RNA-seq-leg limitation).
4. Capture the `evals/schema/*.json` snapshots; write the benchmark.
5. File the upstream issue, with the user's explicit go-ahead at that
   point in execution.

No rollback complexity: additive-only changes to an already-synthetic,
regeneratable demo dataset; the Aperture clone lives entirely outside this
repo and is never pushed.

## Open Questions

- Should the 3 tissue-request fields be kept permanently in
  `schemas/demo.yaml`, or reverted after the spike's findings are captured?
  Decide once the spike's query results are in hand.
- **Resolved**: `evals/` lives in this repo, not `datahelix`.
  `expected-results.json` hardcodes ids (`SMPL-0001`, `DNR-0068`,
  `WRKF-0245`, `DTST-0001`, accession `SMP604876`) that are only stable
  under this repo's own `generate.py --seed 0` default — moving the
  benchmark to `datahelix` would decouple it from the generator that makes
  it reproducible.
