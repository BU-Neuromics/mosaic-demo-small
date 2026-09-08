"""Turn-list state management for the Aperture-Exon conversational contract
(design.md Decision 5: rewind-and-edit with recompute-and-suspend).

Slice 2 of 3 (see conversational_planner.py's own docstring for the split):
this module owns the `list[Turn]` a conversation accumulates -- assigning
turn ids, deciding what "the current draft" is, and recomputing/suspending
turns after an edit. It has no network surface either; the HTTP endpoint
(Decision 8) is slice 3, a thin wrapper calling `append_turn`/`edit_turn`.

Two judgment calls made here, stated explicitly because neither is handed
down by design.md in this much detail:

1. **What "no longer makes sense" (Decision 5) means, mechanically.** No
   heuristic is invented beyond what request_turn already tells us: an old
   turn is recomputed by re-running its ORIGINAL utterance against the new
   state, and it is marked `suspended` exactly when that recompute comes
   back `status="clarification"` -- i.e. the model itself can no longer
   confidently resolve it. That clarification's own message becomes the
   suspended turn's message, since Decision 5 already says a suspended turn
   is "surfaced to the user to re-prompt" -- the model's own question IS
   the re-prompt, not a separately synthesized one.

2. **A genuine call failure is never folded into "suspended."** Ambiguity
   (`status="clarification"`) is a SUCCESSFUL call -- the model did its job
   and reported it can't resolve this. An API error or exhausted parse
   retries is a system failure, unrelated to conversational ambiguity, and
   is raised loudly (matches spec_planner.plan_query_spec's own
   RuntimeError convention) rather than silently presented to the user as
   "this turn is suspended," which would hide an operational problem behind
   a normal-looking conversational outcome.

Once a turn is marked suspended, everything after it cascades to suspended
without further model calls -- there is no coherent base state left to
reinterpret them against once the chain of drafts breaks.
"""
from __future__ import annotations

import uuid

from .conversational_planner import request_turn
from .planner import MAX_ATTEMPTS, MODEL


def _new_turn_id() -> str:
    return uuid.uuid4().hex


def _current_query_spec(turns: list[dict]) -> dict | None:
    """The draft as of the end of `turns`: the most recent `proposal`
    turn's query_spec, skipping back past any trailing clarification (the
    user hasn't resolved it yet, so it changed nothing) or suspended
    (invalidated, carries no spec) turns."""
    for turn in reversed(turns):
        if turn["status"] == "proposal":
            return turn["query_spec"]
    return None


def _prior_turns_view(turns: list[dict]) -> tuple:
    """The (utterance, message) pairs request_turn's grounding needs --
    every turn, including clarifications and suspended ones: the model
    benefits from seeing the full back-and-forth, not just the resolved
    steps."""
    return tuple({"utterance": t["utterance"], "message": t["message"]} for t in turns)


def _find_turn_index(turns: list[dict], turn_id: str) -> int:
    for i, t in enumerate(turns):
        if t["id"] == turn_id:
            return i
    raise ValueError(f"no turn with id {turn_id!r} in this conversation")


def _request_turn_with_retry(
    utterance: str,
    capabilities: dict,
    *,
    existing_query_spec: dict | None,
    prior_turns: tuple,
    model: str = None,
    context: tuple = None,
    protocol: str = "tool_call",
) -> dict:
    """Bounded retry facade, mirrors spec_planner.plan_query_spec exactly.
    Raises RuntimeError only on a real system failure -- see this module's
    docstring, point 2, for why that's never converted into a
    conversational status."""
    last = None
    for _ in range(MAX_ATTEMPTS):
        last = request_turn(
            utterance, capabilities, existing_query_spec=existing_query_spec,
            prior_turns=prior_turns, model=model, context=context, protocol=protocol,
        )
        if last.error:
            raise RuntimeError(
                f"Call to model {model or MODEL!r} failed -- check the provider's API key "
                f"env var is set and the model string is valid for that provider. "
                f"Original error: {last.error}"
            )
        if last.turn is not None:
            return last.turn

    detail = last.parse_error or f"content: {(last.raw_content or '')[:400]!r}"
    if last.truncated:
        detail = f"response truncated (finish_reason=length) before producing a turn; {detail}"
    raise RuntimeError(
        f"Model {model or MODEL!r} produced no usable turn in {MAX_ATTEMPTS} attempt(s) -- {detail}"
    )


_UNSET = object()  # distinguishes "no override given" from an explicit None


def append_turn(
    turns: list[dict], utterance: str, capabilities: dict,
    *, existing_query_spec=_UNSET, **kw
) -> tuple[list[dict], dict]:
    """Add a new turn to the end of the conversation. Returns
    (new_turns_list, the_new_turn) -- `turns` itself is never mutated.

    `existing_query_spec`, when given, OVERRIDES the turns-derived current
    draft -- see design.md Decision 9. This exists for a caller (the HTTP
    endpoint) that has its own independently-tracked notion of "the
    current state" and needs it to win; when omitted (every caller in this
    codebase today), behavior is unchanged from before this parameter
    existed. `edit_turn`'s redo step has no equivalent override: it always
    rewinds to a past point (`turns[:idx]`), which an override representing
    the *current* moment was never the right input for."""
    if existing_query_spec is _UNSET:
        existing_query_spec = _current_query_spec(turns)
    result = _request_turn_with_retry(
        utterance, capabilities,
        existing_query_spec=existing_query_spec,
        prior_turns=_prior_turns_view(turns),
        **kw,
    )
    new_turn = {"id": _new_turn_id(), "utterance": utterance, **result}
    return turns + [new_turn], new_turn


def edit_turn(
    turns: list[dict], edit_turn_id: str, new_utterance: str, capabilities: dict, **kw
) -> tuple[list[dict], dict, list[str]]:
    """Redo the turn named by `edit_turn_id` with `new_utterance`, then
    recompute every turn after it against the edited state. Returns
    (new_turns_list, the_redone_turn, suspended_turn_ids). `turns` itself
    is never mutated; the redone turn keeps its original id (same
    conversational slot, new content) -- everything after it is a NEW
    Turn object even when unchanged in content, since its position in a
    freshly-built list is what `turns` fully replaces here.
    """
    idx = _find_turn_index(turns, edit_turn_id)
    base = turns[:idx]

    result = _request_turn_with_retry(
        new_utterance, capabilities,
        existing_query_spec=_current_query_spec(base),
        prior_turns=_prior_turns_view(base),
        **kw,
    )
    redone = {"id": edit_turn_id, "utterance": new_utterance, **result}

    new_turns = base + [redone]
    suspended_ids: list[str] = []
    cascading = False

    for old in turns[idx + 1:]:
        if cascading:
            new_turns.append({
                "id": old["id"], "utterance": old["utterance"],
                "status": "suspended", "query_spec": None,
                "message": (
                    "This turn was suspended because an earlier turn it depended on "
                    "was also suspended by the edit above -- resolve that one first."
                ),
            })
            suspended_ids.append(old["id"])
            continue

        recompute = _request_turn_with_retry(
            old["utterance"], capabilities,
            existing_query_spec=_current_query_spec(new_turns),
            prior_turns=_prior_turns_view(new_turns),
            **kw,
        )
        if recompute["status"] == "clarification":
            new_turns.append({
                "id": old["id"], "utterance": old["utterance"],
                "status": "suspended", "query_spec": None,
                "message": recompute["message"],
            })
            suspended_ids.append(old["id"])
            cascading = True
        else:
            new_turns.append({"id": old["id"], "utterance": old["utterance"], **recompute})

    return new_turns, redone, suspended_ids
