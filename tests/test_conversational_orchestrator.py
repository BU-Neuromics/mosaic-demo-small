"""Turn-list orchestration tests (Decision 5: rewind-and-edit,
recompute-and-suspend). All calls to the model are stubbed here -- the
orchestration logic (turn-id assignment, which spec is "current", the
recompute-and-cascade state machine) is pure bookkeeping around
request_turn, and should be verified deterministically and fast, not by
re-proving spec_planner's own LLM-facing behavior on every run.

test_conversational_planner.py already ground-truths the planning core
itself; this file assumes request_turn works and asks a different
question: given a SEQUENCE of its outputs, does the turn list end up in
the right shape?
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from exon.conversational_orchestrator import (
    _current_query_spec,
    _find_turn_index,
    append_turn,
    edit_turn,
)
from exon.conversational_planner import TurnAttempt

CAPS = {"Sample": {"fields": []}}  # opaque to these tests -- request_turn is stubbed out


def _proposal(spec: dict, message: str = "ok") -> TurnAttempt:
    return TurnAttempt(protocol="tool_call", turn={"status": "proposal", "message": message, "query_spec": spec})


def _clarification(message: str = "which one?") -> TurnAttempt:
    return TurnAttempt(protocol="tool_call", turn={"status": "clarification", "message": message, "query_spec": None})


class _ScriptedModel:
    """Stub for conversational_planner.request_turn: returns queued
    TurnAttempts in order, and records every call's kwargs for assertions
    about what grounding each call actually received."""

    def __init__(self, *attempts: TurnAttempt):
        self.queue = list(attempts)
        self.calls: list[dict] = []

    def __call__(self, utterance, capabilities, *, existing_query_spec=None, prior_turns=(), **kw):
        self.calls.append({
            "utterance": utterance,
            "existing_query_spec": existing_query_spec,
            "prior_turns": prior_turns,
        })
        return self.queue.pop(0)


SPEC_A = {"v": 1, "anchor": "Sample", "mode": "AND", "criteria": [{"kind": "field", "slot": "a", "op": "eq", "value": 1}]}
SPEC_B = {"v": 1, "anchor": "Sample", "mode": "AND", "criteria": [{"kind": "field", "slot": "b", "op": "eq", "value": 2}]}
SPEC_C = {"v": 1, "anchor": "Sample", "mode": "AND", "criteria": [{"kind": "field", "slot": "c", "op": "eq", "value": 3}]}


class TestAppendTurn:
    def test_first_turn_gets_no_existing_spec_or_history(self, monkeypatch):
        model = _ScriptedModel(_proposal(SPEC_A))
        monkeypatch.setattr("exon.conversational_orchestrator.request_turn", model)
        turns, new_turn = append_turn([], "first", CAPS)
        assert model.calls[0]["existing_query_spec"] is None
        assert model.calls[0]["prior_turns"] == ()
        assert new_turn["query_spec"] == SPEC_A
        assert "id" in new_turn and new_turn["id"]

    def test_second_turn_sees_the_first_as_current_spec_and_history(self, monkeypatch):
        model = _ScriptedModel(_proposal(SPEC_A, "first done"), _proposal(SPEC_B, "second done"))
        monkeypatch.setattr("exon.conversational_orchestrator.request_turn", model)
        turns, _ = append_turn([], "first", CAPS)
        turns, _ = append_turn(turns, "second", CAPS)
        assert model.calls[1]["existing_query_spec"] == SPEC_A
        assert model.calls[1]["prior_turns"] == ({"utterance": "first", "message": "first done"},)
        assert len(turns) == 2

    def test_a_clarification_does_not_become_the_current_spec(self, monkeypatch):
        model = _ScriptedModel(_proposal(SPEC_A), _clarification("which one?"), _proposal(SPEC_B))
        monkeypatch.setattr("exon.conversational_orchestrator.request_turn", model)
        turns, _ = append_turn([], "first", CAPS)
        turns, _ = append_turn(turns, "ambiguous", CAPS)
        assert turns[-1]["status"] == "clarification"
        turns, _ = append_turn(turns, "resolved", CAPS)
        # The third call must have seen SPEC_A (from turn 1), not None --
        # the intervening clarification changed nothing.
        assert model.calls[2]["existing_query_spec"] == SPEC_A

    def test_does_not_mutate_the_input_list(self, monkeypatch):
        model = _ScriptedModel(_proposal(SPEC_A))
        monkeypatch.setattr("exon.conversational_orchestrator.request_turn", model)
        original = []
        turns, _ = append_turn(original, "first", CAPS)
        assert original == []
        assert len(turns) == 1

    def test_a_real_call_failure_raises_not_silently_absorbed(self, monkeypatch):
        model = _ScriptedModel(TurnAttempt(protocol="tool_call", error="boom"))
        monkeypatch.setattr("exon.conversational_orchestrator.request_turn", model)
        monkeypatch.setattr("exon.conversational_orchestrator.MAX_ATTEMPTS", 1)
        with pytest.raises(RuntimeError, match="boom"):
            append_turn([], "first", CAPS)


class TestCurrentQuerySpec:
    def test_empty_history_has_no_spec(self):
        assert _current_query_spec([]) is None

    def test_skips_trailing_clarification(self):
        turns = [
            {"status": "proposal", "query_spec": SPEC_A},
            {"status": "clarification", "query_spec": None},
        ]
        assert _current_query_spec(turns) == SPEC_A

    def test_skips_trailing_suspended(self):
        turns = [
            {"status": "proposal", "query_spec": SPEC_A},
            {"status": "suspended", "query_spec": None},
        ]
        assert _current_query_spec(turns) == SPEC_A


class TestFindTurnIndex:
    def test_finds_the_right_index(self):
        turns = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        assert _find_turn_index(turns, "b") == 1

    def test_missing_id_raises(self):
        with pytest.raises(ValueError, match="no turn"):
            _find_turn_index([{"id": "a"}], "nope")


class TestEditTurn:
    def test_redoing_the_last_turn_keeps_its_id(self, monkeypatch):
        model = _ScriptedModel(_proposal(SPEC_A))
        monkeypatch.setattr("exon.conversational_orchestrator.request_turn", model)
        turns, first = append_turn([], "first", CAPS)

        model.queue.append(_proposal(SPEC_B, "redone"))
        turns, redone, suspended = edit_turn(turns, first["id"], "first, revised", CAPS)
        assert redone["id"] == first["id"]
        assert redone["query_spec"] == SPEC_B
        assert suspended == []
        assert len(turns) == 1

    def test_editing_an_earlier_turn_recomputes_what_follows(self, monkeypatch):
        model = _ScriptedModel(_proposal(SPEC_A, "t1"), _proposal(SPEC_B, "t2"))
        monkeypatch.setattr("exon.conversational_orchestrator.request_turn", model)
        turns, t1 = append_turn([], "first", CAPS)
        turns, t2 = append_turn(turns, "second", CAPS)

        # Editing t1: redo t1, then recompute t2's ORIGINAL utterance against the new base.
        model.queue.append(_proposal(SPEC_C, "t1 revised"))
        model.queue.append(_proposal(SPEC_B, "t2 still applies"))
        new_turns, redone, suspended = edit_turn(turns, t1["id"], "first, revised", CAPS)

        assert suspended == []
        assert new_turns[0]["query_spec"] == SPEC_C
        assert new_turns[1]["utterance"] == "second"  # original utterance preserved
        assert new_turns[1]["id"] == t2["id"]  # same conversational slot
        assert new_turns[1]["query_spec"] == SPEC_B
        # The recompute call must have been grounded in the NEW t1 state, not the old one.
        recompute_call = model.calls[-1]
        assert recompute_call["existing_query_spec"] == SPEC_C

    def test_a_turn_invalidated_by_the_edit_is_suspended_not_dropped(self, monkeypatch):
        model = _ScriptedModel(_proposal(SPEC_A, "t1"), _proposal(SPEC_B, "t2"))
        monkeypatch.setattr("exon.conversational_orchestrator.request_turn", model)
        turns, t1 = append_turn([], "first", CAPS)
        turns, t2 = append_turn(turns, "second", CAPS)

        model.queue.append(_proposal(SPEC_C, "t1 revised"))
        model.queue.append(_clarification("that no longer makes sense here"))
        new_turns, redone, suspended = edit_turn(turns, t1["id"], "pivot to something else", CAPS)

        assert suspended == [t2["id"]]
        assert new_turns[1]["status"] == "suspended"
        assert new_turns[1]["query_spec"] is None
        assert new_turns[1]["utterance"] == "second"  # original utterance preserved for re-prompting
        assert new_turns[1]["message"] == "that no longer makes sense here"

    def test_suspension_cascades_without_further_model_calls(self, monkeypatch):
        model = _ScriptedModel(_proposal(SPEC_A, "t1"), _proposal(SPEC_B, "t2"), _proposal(SPEC_C, "t3"))
        monkeypatch.setattr("exon.conversational_orchestrator.request_turn", model)
        turns, t1 = append_turn([], "first", CAPS)
        turns, t2 = append_turn(turns, "second", CAPS)
        turns, t3 = append_turn(turns, "third", CAPS)

        model.queue.append(_proposal(SPEC_C, "t1 revised"))
        model.queue.append(_clarification("t2 no longer applies"))
        calls_before = len(model.calls)
        new_turns, redone, suspended = edit_turn(turns, t1["id"], "pivot", CAPS)

        assert suspended == [t2["id"], t3["id"]]
        assert new_turns[1]["status"] == new_turns[2]["status"] == "suspended"
        assert new_turns[2]["utterance"] == "third"
        # Exactly two NEW calls happened (redo t1, recompute t2) -- t3 was
        # never sent to the model at all once the cascade started.
        assert len(model.calls) == calls_before + 2

    def test_editing_the_first_turn_of_a_two_turn_conversation(self, monkeypatch):
        # Base for the redo must be empty, not the pre-edit conversation.
        model = _ScriptedModel(_proposal(SPEC_A, "t1"))
        monkeypatch.setattr("exon.conversational_orchestrator.request_turn", model)
        turns, t1 = append_turn([], "first", CAPS)

        model.queue.append(_proposal(SPEC_B, "t1 redone"))
        edit_turn(turns, t1["id"], "totally different", CAPS)
        redo_call = model.calls[-1]
        assert redo_call["existing_query_spec"] is None
        assert redo_call["prior_turns"] == ()

    def test_editing_an_unknown_turn_id_raises(self, monkeypatch):
        model = _ScriptedModel()
        monkeypatch.setattr("exon.conversational_orchestrator.request_turn", model)
        with pytest.raises(ValueError, match="no turn"):
            edit_turn([{"id": "a", "status": "proposal", "query_spec": SPEC_A, "utterance": "x", "message": "y"}],
                      "nope", "edit", CAPS)

    def test_does_not_mutate_the_input_list(self, monkeypatch):
        model = _ScriptedModel(_proposal(SPEC_A, "t1"))
        monkeypatch.setattr("exon.conversational_orchestrator.request_turn", model)
        turns, t1 = append_turn([], "first", CAPS)
        original = list(turns)

        model.queue.append(_proposal(SPEC_B, "redone"))
        edit_turn(turns, t1["id"], "revised", CAPS)
        assert turns == original


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
