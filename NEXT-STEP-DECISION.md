# Deploy to first users, or automate ingest first?

**Status:** 🔴 Open — for the next working session · **Raised:** 2026-09-29
**Related:** [`REFERENCED-CLASS-TRAVERSAL.md`](./REFERENCED-CLASS-TRAVERSAL.md) (what shipped),
`datahelix:platform/design/roadmap-1.0.md` §4 (the `[HUMAN]` escalation queue this belongs in)

The single-user stack became genuinely deployable this week. That makes the next move a real
fork rather than an ordering detail, and the platform convention is explicit about what to do
with one: *"Escalate [HUMAN] items — never resolve them by implication."* Left alone this gets
decided by whoever starts something first.

## What changed

`aperture 0.6.0 + mosaic 0.14.0` is certified against fixture 1.1.0 — ledger **10 passing /
0 failing** — and both deploy recipes boot. They had been **gated shut**: they pin component
images by digest and refuse to start when those drift from the certified lock, and they had
drifted two releases. A single container now serves Aperture at `/` and Mosaic at `/graphql`
same-origin. Verified running, not asserted.

Alongside that, referenced-class traversal shipped the whole way through, and a silent defect
came out with it: record identity was being chosen from an eight-column *display* budget, so two
of fifteen collections identified records by `name` — and the query planner returned zero rows
for them with no error at all.

## The fork

Both are cheap. Neither blocks the other. Each makes the other better-informed if it goes first,
which is precisely why it wants deciding rather than falling into.

| | **A — deploy to first users** | **B — automate the ingest** |
|---|---|---|
| Unlocks | people other than the maintainer using it; provenance recording who did what | the graph stays current instead of being a hand-loaded snapshot |
| Cost | **days** — mostly schema and data; the recipes already exist | **weeks** — one production connector, a trigger, an audit trail |
| Roadmap | not an epic at all | **P3.6**, which carries its own `[HUMAN]` adapter choice (REDCap vs CSV-batch) |
| Strongest case | every roadmap choice after it is currently a guess — there is no user feedback in the system at all | an explorer over stale data stops being opened, so adoption dies before feedback arrives |
| What it cannot do | everyone sees everything — access is **gated, not differentiated** | nothing about who may see what |

## The constraint that probably decides it

**Is the first real dataset identifiable?**

`AUTH_MODE=htpasswd|oidc` is already implemented in the `solo` recipe against a pinned
oauth2-proxy (platform ADR-0006), so gated multi-user access exists **today** — the deployment
can sit behind institutional sign-in and provenance names the real person. But that decides
*whether you may use this deployment*, never *which records you may see*. Per-record and
per-slot control belong to Bridge, which is unbuilt.

- **If yes** — option A is capped at a small trusted group, and Bridge (P3.1) moves up sharply.
- **If no** — de-identified or internal-only means A is genuinely unblocked and the cheaper
  sequence holds.

This is the one input that cannot be read out of any repo. Everything else above was verified
against a running system.

## Recommendation

**A, then reassess** — assuming de-identified data. Not because ingest doesn't matter, but
because roadmap decisions are currently being made with zero real users. Deploying is days, the
login story is already built, and a week of someone actually using this says more about what
comes next than any amount of reasoning about it.

Then most likely **B**, because stale data kills adoption faster than missing features do.

## Explicitly not on the table at this session

**Bridge (P3.1).** Per-record access control is a separate, much larger build, and designing
access rules before seeing how people use the system is the wrong order.

**The AI/agentic surface — the direction being targeted regardless.** A and B are about what
runs *alongside* it, not instead of it. One thing to know before working it: **P3.4 is stale.**
The roadmap already records that the MCP agent surface landed in Mosaic instead (ADR-0009/0010),
but the Aperture-side half — ratifying ADR-0018/0021 plus the P3.5 keystone probe — has never
been re-scoped. Expect to restate that row rather than treat it as current.
