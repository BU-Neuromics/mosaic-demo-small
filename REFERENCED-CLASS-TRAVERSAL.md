# Referenced-class values in result tables — delivery record

**Status:** 🟢 Waves 0–1 complete and certified; Wave 2 in review · **Updated:** 2026-09-25
**Decision of record:** [Aperture ADR-0041](https://github.com/BU-Neuromics/aperture/blob/main/design/decisions/ADR-0041-referenced-class-slots-projection-vs-presentation.md)
**Umbrella:** [datahelix#93](https://github.com/BU-Neuromics/datahelix/issues/93)

> Kept here rather than in the integration repo because this is where the schema under
> discussion lives, and because this repo already carries the cross-component bridge
> documents (`APERTURE_EXON_CONTRACT.md`, `CONVERSATIONAL-QUERY.md`). Same genre, same shelf.

The ask was one sentence: *the results table should show slot values from referenced
classes, joined into one table, repeating anchor values where a reference is to-many, with
a user-controlled include set.* Delivering it touched five repositories, and this is the
record of what changed and why.

## 1. The premise was wrong, and the correction set the scope

The feature was framed as *"the QuerySpec already returns the data; the client can't display
it."* Neither half held:

1. **`QuerySpec` cannot express column selection at all.** Mosaic hard-rejects `columns`
   with `COLUMNS_NOT_SUPPORTED` (`core/query_spec.py`), whose message prescribes the
   remedy — *"request full envelopes and project client-side."* The conversational path
   round-trips every spec through that same parser, so adding the key would have broken the
   chat panel.
2. **Referenced values never crossed the wire.** `selectionFor` emitted `field { id }` and
   nothing else, so the renderer could only ever print a UUID. Mosaic's references are
   edge-only (its ADR-0005): there is no foreign-key scalar to fall back on.

So this was a data-layer, planner, and UI change — not a rendering change.

## 2. The decision: one name, two decisions

ADR-0035 reserved a `columns` field in 2026-08 and it sat unbuilt for a year. The reason was
that the field conflates two decisions with different owners, separated by one test:

> **Does changing it change the row set?**

| | Test | Home |
|---|---|---|
| Traversal + grain (`explode`) | 128 workflows → 342 rows | `QuerySpec.columns` — validated, server-compilable |
| Visibility, order, labelling | nothing | view-side state that never reaches a server |

Bound together, the first half needed a server compiler and the second needed nothing, so
neither shipped. Split, the forward directions ship now in the shape they keep when the
compiler lands.

## 3. What shipped

### Wave 0 — correcting the record (5 PRs, all merged)

Three repositories were planning against facts that had stopped being true.

| Repo | Change |
|---|---|
| aperture | ADR-0041 recorded; ADR-0035 amended with a forward pointer **and** a correction |
| mosaic | **ADR-0011 ratified** — its code had merged and been tested while the status stayed `Proposed` |
| reel | ADR-0006's `pivot-grain` row corrected — it was recorded as blocked on a dependency that had shipped |
| datahelix | roadmap records the unreleased backlog; `view-contract.md` gains `ColumnView` as its first concrete instance |
| mosaic-demo-small | the explode-scoping open question answered |

The stale sentence that mattered most was in ADR-0035: *"which Mosaic ADR-0011 adds and which
has not merged."* It had merged. Three repos were reasoning off it.

### Wave 1 — making the capability reachable

| Step | Outcome |
|---|---|
| mosaic **v0.14.0** cut | 40 commits were stranded on `main` with no tag — the MCP boundary, `converseQuerySpec`, and reverse edges |
| certification **fixture 1.1.0** | gains a multivalued reference (`Book.co_authors`) and an `inverse:`-declared reverse edge (`Author.books`) |
| aperture **v0.5.0** cut | carries the `idColumn` fix that gates the schema work below |
| pin bumped + certified | `fixture 1.1.0 · aperture0.5.0+mosaic0.14.0 · fail=None` — **the first ledger entry ever to cover 1.1.0** |
| `demo.yaml` declares four `inverse:` slots | `Donor.samples`, `Donor.diagnoses`, `Sample.aliquots`, `Workflow.datasets` |

### Wave 2 — the feature ([aperture#70](https://github.com/BU-Neuromics/aperture/pull/70), in review)

Edge derivation extended to to-many references with declared-over-inferred precedence; a
path-aware selection compiler that merges siblings; a flattener with `explode`/`count`/
`joinIds` and composite row keys; the typed `where:` compiler and planner rewiring; the
picker, grain banner and path-addressed export. 413 tests.

## 4. Four things found by looking rather than assuming

Each of these was recorded as true somewhere, and wasn't.

**`idColumn` was picked from the table budget.** A presentation constant — eight columns —
was deciding what identifies a record. Two of fifteen demo collections already identified
records by `name` while their detail paths took an `ID!`. The quiet case was the planner's
semijoin building an `IN` over names: matching nothing, reporting no error.
→ [aperture#67](https://github.com/BU-Neuromics/aperture/issues/67)

**mosaic#204 had merged but was carried by no tag.** Reverse-edge traversal was described as
blocked engineering in two repos. It was neither blocked nor engineering — it was a release.

**Mosaic's typed filter contract was complete in the certified pin and entirely unused.**
Aperture still compiled to the flat `filters:` list and ran every relationship criterion
through a capped client-side semijoin.

**Fixture 1.1.0 had never been certified.** All eight passing ledger entries recorded fixture
1.0.0, because the workflow appends a ledger tag on a push that changes
`composition.lock.json`, and the fixture bump touched `fixtures/**` only. The gate could not
have caught it: it matches on component versions and digests, not `fixture_version`.

## 5. Claims that were tested rather than asserted

- **Generated GraphQL is valid.** Emitted selections were parsed and validated against the
  real v0.14.0 schema, including the two-hop `workflows → inputSamples → donor`; compiled
  `where:` inputs were coerced through the real input types, including the `none` anti-join.
- **Inverse slots need no re-ingest.** mosaic v0.14.0 served an `inverse:`-declared schema
  against an **untouched copy** of the existing database and resolved every edge —
  `DNR-0002 → 3 samples`, `SMPL-0024 → 8 aliquots`, `WRKF-0001 → 2 datasets` — plus reverse
  predicates (`123` donors with a primary diagnosis). The claim was plausible from the ADR;
  it is now observed.
- **The feature works in a browser.** Driven in Chromium against a real Mosaic, which found a
  bug 413 passing tests did not: Run wrote the draft spec to the URL and the executing effect
  was keyed on that spec, so ticking a column produced a header with no data behind it. Every
  layer was correct in isolation; only the assembled app showed it.

## 6. Two constraints worth carrying forward

**Mixing a typed filter with a client compensation is legal only under AND.** The server
composes `filters` with `where` **by AND** — its own documented contract — so ANDing a
compensation onto an OR-mode typed filter would run a query that is not the one the spec
describes. A partially-compilable OR spec falls back entirely and says so.

**`none` keeps no fallback.** An anti-join cannot be compensated by a semijoin, which
collects the ids that *do* match and filters with `in`. Where no server predicate exists it
stays an error, because degrading would mean silently returning the wrong answer.

## 7. Outstanding

- **aperture#70** in review — the feature itself.
- **This branch** ([#3](https://github.com/BU-Neuromics/mosaic-demo-small/pull/3), 59 commits)
  carries the 15-collection schema *and* the four `inverse:` declarations. Until it lands,
  `main` has four entity classes and reverse traversal is exercised only by DataHelix's
  certification fixture.
- **Wave 3** — Mosaic's server-side `columns` compiler. The artifact does not change when it
  lands; only the planner does, which is ADR-0035's server-independence payoff being cashed.
- **Wave 4** — the View Contract's `table` primitive, where `ColumnView` stops being Aperture's
  interim state.
- Possible follow-up: `gate.py` matches on versions and digests but not `fixture_version`,
  which is why §4's fourth finding went unnoticed.
