# Retire the host-serve workaround; verify parity on the certified solo container

## Why

This repo currently serves GraphQL from a **host-side `mosaic serve`** against an
editable `../mosaic` checkout, instead of the certified DataHelix `solo`
container. That was a workaround, not a preference: the certified container was
pinned to Mosaic `0.12.1`, which predates `ec59c90`, so booting it against this
repo's schema crash-looped on `Workflow.input_samples: required: true`
(mosaic#143 / mosaic#144). The caveat is documented in `README.md`'s
"Two Mosaic builds in play" section.

**The gate that section names has now cleared, on both halves:**

- Mosaic **v0.13.0** (2026-08-20) contains `ec59c90` — confirmed by
  `git tag --contains ec59c90`.
- mosaic#146's fix (PR #147, merge `3bda128`) is an ancestor of `v0.13.0` —
  confirmed by `git merge-base --is-ancestor`, not by the issue close date.
- DataHelix `main` pins `mosaic 0.13.0` in
  `certification/composition.lock.json` with a published digest
  (`sha256:ded2942…`, `status: published`), and
  `certification/compatibility.json` certifies it at 7 passing / 0 failing.

So the container should now boot against this project. That claim is worth
proving rather than assuming, because the last time we assumed, it crash-looped.

## What Changes

- Verify the certified solo container boots against this project via
  `PROJECT_DIR=… make up`, from DataHelix **`main`** (see Risk below).
- Re-audit the three `capability: blocked` questions against the *pinned*
  Mosaic version. Their blockers have since closed, so the markers may be stale:
  - `q34` (`blocked_by: mosaic#148`, relatedTo predicate) — #148 closed
    2026-08-20; release membership unresolved by commit search, so it must be
    settled empirically.
  - `q32`, `q33` (`blocked_by: mosaic#96`, sort / facet counts) — #96 closed
    2026-09-15, *after* the v0.13.0 tag, and the aggregation work traces to
    `63962ae`, which is **not** an ancestor of v0.13.0. These are expected to
    remain blocked at the pinned version, and that expectation is itself a
    finding to record rather than silently carry.
- Establish parity by **diffing a container run against
  `evals/expected-results.json`** — the verified per-question result sets —
  rather than by inspecting GraphiQL by hand. Note that `evals/baselines/` is
  *not* the right referent: those files are LLM eval runs (keyed `model`,
  `scores`, `wall_clock_s`), so diffing them across a serving-path change would
  measure model nondeterminism rather than Mosaic behaviour.
- Update `README.md`'s "Two Mosaic builds in play" section to reflect whichever
  outcome the verification actually produces.

## Non-Goals

- **The conversational track.** `converse_query_spec` exists only on Mosaic
  `main`, 34 commits past `v0.13.0`, so the certified container cannot serve
  `converseQuerySpec`. Work gated on mosaic#205 / mosaic#204 keeps the
  host-serve path and is out of scope here.
- **Aperture's chat panel.** The certified pair is mosaic 0.13.0 + aperture
  **0.4.0** — older than both this workspace's `feat/conversational-chat-panel`
  branch and Aperture `main`. This change validates the pre-chat-panel SPA only.
- Rebasing or retiring DataHelix's `fix-solo-recipe-schema-dir-imports` branch.
- Filing the two open upstream findings (stale `uv.lock` on Mosaic `main`;
  mosaic#204 complete-but-unmerged). Both are deliberately held.

## Risk

The local DataHelix checkout sits on `fix-solo-recipe-schema-dir-imports`,
**14 commits behind `main`**, and still pins `mosaic 0.12.1`
(verified via `git show HEAD:certification/composition.lock.json`). It also
lacks the recipe rewrites #78, #83, #85 and #68/#89. Running `make up` from that
checkout would reproduce the original crash-loop and look like a regression.
Verification therefore runs from DataHelix `main`, leaving that branch untouched.

A green benchmark run is **not** sufficient evidence on its own: if a stale
`blocked` marker causes a question to be skipped, the run can be green while
hiding a capability that should now pass. The re-audit gates the parity claim.

**The Docker daemon was not running when this change was written.** Track A is
not executable until it is started, so that is a pre-flight task rather than an
assumption. The recipe also builds locally (`build: .`) `FROM` digest-pinned
`ghcr.io` images, so it needs registry access — but it does **not** need
DataHelix's uninitialized `aperture`/`mosaic` submodules, which should be left
alone.
