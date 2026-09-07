## ADDED Requirements

### Requirement: Turn-taking is a stateless function over caller-supplied state

Exon SHALL expose a turn-taking planning entry point that is a pure function of its inputs — the
existing `QuerySpec` (or none), the prior turns, and the new natural-language utterance — and
SHALL NOT persist conversation state between calls. The caller is responsible for holding and
resupplying state on every call.

#### Scenario: Two independent calls with the same inputs produce equivalent results

- **WHEN** the turn-taking entry point is called twice with identical existing `QuerySpec`, prior
  turns, and utterance, with no shared process state between the calls
- **THEN** both calls produce an equivalent response, demonstrating no hidden server-side session
  state influenced either call

#### Scenario: Exon stores nothing it wasn't given

- **WHEN** a turn-taking call completes
- **THEN** nothing about that turn is retained by Exon for use in a future call unless the caller
  explicitly resupplies it as part of that future call's prior-turns input

### Requirement: Every turn is validated against Mosaic before being returned

Exon SHALL validate every candidate `QuerySpec` produced during a turn against Mosaic's
`validate_query_spec` tool before returning it to the caller. A validation failure SHALL feed back
into Exon's own retry loop rather than being surfaced to the caller as a raw or unvalidated result.

#### Scenario: A turn's proposed QuerySpec is always pre-validated

- **WHEN** a turn-taking call returns a `proposal` response
- **THEN** the `QuerySpec` it contains has already passed Mosaic's `validate_query_spec`, and the
  caller never receives an unvalidated `QuerySpec` from this entry point

### Requirement: Response is discriminated between a proposal and a clarification

Exon SHALL return one of two response shapes for a turn: a `proposal` (an updated, validated
`QuerySpec` plus a natural-language restatement of the current interpretation) or a `clarification`
(no `QuerySpec` change, a natural-language question back to the user). Exon SHALL default to
`proposal` whenever a reasonable, visible, correctable interpretation of the utterance exists, and
SHALL use `clarification` only when the utterance is genuinely ambiguous.

#### Scenario: An unambiguous refinement produces a proposal

- **WHEN** a new utterance narrows or extends the existing `QuerySpec` without contradiction or
  unresolved ambiguity
- **THEN** Exon returns a `proposal` response with the updated `QuerySpec`, never a clarifying
  question for something it could reasonably interpret

#### Scenario: A genuinely ambiguous utterance produces a clarification, not a guess

- **WHEN** a new utterance conflicts with the existing `QuerySpec` in a way that cannot be resolved
  without more information, or names a value that does not resolve even after a validation-driven
  retry
- **THEN** Exon returns a `clarification` response with no `QuerySpec` change, rather than guessing
  and returning a `proposal` the user must notice and correct

### Requirement: The MVP operation vocabulary is restricted to filter and exists-related-filter

Exon's turn-taking entry point SHALL restrict every op it produces to `FieldCondition` (Reel's
`filter`) or `RelatedCondition` (Reel's `exists-related-filter`). It SHALL NOT produce ops
corresponding to Reel's broader catalog — `distinct-values`, `group-by+count`, `pivot-grain`, or
`set-op`.

#### Scenario: A request needing an out-of-scope op is refused, not approximated

- **WHEN** a user's utterance would require a `group-by+count`, `distinct-values`, `pivot-grain`,
  or `set-op` style operation to satisfy
- **THEN** Exon returns a `clarification` (or an explicit statement of the limitation) rather than
  approximating the request with `filter`/`exists-related-filter` ops that don't actually express
  what was asked

### Requirement: Each turn is individually addressable and editable

Exon SHALL assign each turn an identifier, and SHALL support the caller requesting a redo from a
specific prior turn with a replacement utterance. When an earlier turn is edited, Exon SHALL
recompute turns after it against the edited state, and SHALL mark any recomputed turn that no
longer validates or no longer makes sense given the edit as `suspended` rather than silently
dropping or silently reinterpreting it.

#### Scenario: Editing an earlier turn recomputes what follows it

- **WHEN** the caller requests a redo from turn N with a new utterance, where turns after N already
  existed
- **THEN** Exon recomputes the turns after N against the new state at N, using each turn's original
  utterance as input to that recomputation

#### Scenario: A turn invalidated by an earlier edit is flagged, not discarded

- **WHEN** recomputation after an edit produces a turn whose original utterance no longer resolves
  against the new state (e.g. it depended on a constraint the edit removed)
- **THEN** that turn's status is set to `suspended` and it remains visible to the caller for
  re-prompting, rather than being silently dropped from the turn sequence or silently
  reinterpreted without the user's input

### Requirement: Anchor pivots always re-run fresh against current data

Exon SHALL re-derive any relationship to a prior anchor as a filter rule evaluated against current
data whenever a turn changes the `QuerySpec`'s anchor (the entity type the conversation is about).
Exon SHALL NOT scope the new `QuerySpec` to the exact, frozen set of records the prior anchor had
previously matched.

#### Scenario: A pivot re-derives the relationship as a live rule

- **WHEN** a turn asks to switch from the current anchor to a related entity type (e.g. "show me
  the donors of those samples instead")
- **THEN** the resulting `QuerySpec`'s anchor changes, and the relationship to the prior anchor is
  expressed as a `RelatedCondition` filter rule, not as a reference to the specific set of records
  the prior `QuerySpec` had matched at the time of the pivot

### Requirement: The turn-taking entry point is reachable over HTTP using the design's wire shape

Exon SHALL expose its turn-taking entry point as an HTTP endpoint accepting the request shape
`{utterance, query_spec, turns, edit_turn_id}` and returning `{turn, suspended_turn_ids}`, with
`turn` shaped as `{id, utterance, status, query_spec, message}` (`status` one of `proposal`,
`clarification`, `suspended`, or `error`), per `design.md` Decision 8. This is the only network path
into this capability; Exon SHALL NOT require or advertise a browser-reachable endpoint of its own
(see `mosaic-query-boundary-contract`'s transport requirement).

#### Scenario: The endpoint accepts and returns the specified shapes

- **WHEN** Mosaic's `converse_query_spec` tool calls Exon's configured turn endpoint with a request
  body matching `{utterance, query_spec, turns, edit_turn_id}`
- **THEN** Exon's response matches `{turn, suspended_turn_ids}`, and every field Mosaic's tool
  relies on (`turn.status`, `turn.query_spec`, `turn.message`) is present with the specified meaning

### Requirement: The turn-taking planner never decides to execute

Exon's turn-taking entry point SHALL return, at most, a validated `QuerySpec` and SHALL NOT itself
call `execute_query_spec` or otherwise fetch entity data as part of producing a turn response.

#### Scenario: A turn response never contains fetched entity data

- **WHEN** any turn-taking call completes, whether it returns a `proposal` or a `clarification`
- **THEN** the response contains no fetched entity records — only a `QuerySpec` (for `proposal`)
  and/or a natural-language message, leaving the decision to fetch and display results entirely to
  the caller
