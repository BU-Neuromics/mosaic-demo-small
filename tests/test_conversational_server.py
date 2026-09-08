"""HTTP endpoint tests (design.md Decision 8's wire contract). Stubs
request_turn exactly as test_conversational_orchestrator.py does -- this
file asks a different question again: given the orchestration layer
works (already proven), does the HTTP translation match Decision 8's JSON
shape exactly, and does Decision 9's query_spec/turns-agreement check
actually fire when it should?
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from exon.conversational_planner import TurnAttempt
from exon.conversational_server import create_conversational_app

CAPS = {"Sample": {"fields": []}}

SPEC_A = {"v": 1, "anchor": "Sample", "mode": "AND", "criteria": [{"kind": "field", "slot": "a", "op": "eq", "value": 1}]}
SPEC_B = {"v": 1, "anchor": "Sample", "mode": "AND", "criteria": [{"kind": "field", "slot": "b", "op": "eq", "value": 2}]}
SPEC_C = {"v": 1, "anchor": "Sample", "mode": "AND", "criteria": [{"kind": "field", "slot": "c", "op": "eq", "value": 3}]}


def _proposal(spec, message="ok"):
    return TurnAttempt(protocol="tool_call", turn={"status": "proposal", "message": message, "query_spec": spec})


def _clarification(message="which one?"):
    return TurnAttempt(protocol="tool_call", turn={"status": "clarification", "message": message, "query_spec": None})


class _ScriptedModel:
    def __init__(self, *attempts):
        self.queue = list(attempts)

    def __call__(self, utterance, capabilities, *, existing_query_spec=None, prior_turns=(), **kw):
        return self.queue.pop(0)


@pytest.fixture
def client(monkeypatch):
    model = _ScriptedModel()
    monkeypatch.setattr("exon.conversational_orchestrator.request_turn", model)
    app = create_conversational_app(CAPS)
    tc = TestClient(app)
    tc.model = model  # stash for tests to queue responses onto
    return tc


class TestAppend:
    def test_first_turn_with_empty_history_and_null_spec(self, client):
        client.model.queue.append(_proposal(SPEC_A, "filtering to a=1"))
        r = client.post("/turn", json={"utterance": "hello", "query_spec": None, "turns": []})
        assert r.status_code == 200
        body = r.json()
        assert body["turn"]["status"] == "proposal"
        assert body["turn"]["query_spec"] == SPEC_A
        assert body["turn"]["message"] == "filtering to a=1"
        assert body["suspended_turn_ids"] == []
        assert body["turn"]["id"]  # assigned, non-empty

    def test_second_turn_with_matching_query_spec_succeeds(self, client):
        client.model.queue.append(_proposal(SPEC_A, "t1"))
        r1 = client.post("/turn", json={"utterance": "first", "query_spec": None, "turns": []})
        t1 = r1.json()["turn"]

        client.model.queue.append(_proposal(SPEC_B, "t2"))
        r2 = client.post("/turn", json={
            "utterance": "second", "query_spec": SPEC_A, "turns": [t1],
        })
        assert r2.status_code == 200
        assert r2.json()["turn"]["query_spec"] == SPEC_B

    def test_mismatched_query_spec_is_rejected_400(self, client):
        # Decision 9: for now, this must never legitimately happen (the
        # point-and-click builder is locked while chatting) -- a mismatch
        # here means a bug on the caller's side, not a real divergence to
        # resolve.
        client.model.queue.append(_proposal(SPEC_A, "t1"))
        r1 = client.post("/turn", json={"utterance": "first", "query_spec": None, "turns": []})
        t1 = r1.json()["turn"]

        r2 = client.post("/turn", json={
            "utterance": "second", "query_spec": SPEC_C, "turns": [t1],  # wrong -- should be SPEC_A
        })
        assert r2.status_code == 400
        assert "does not match" in r2.json()["detail"]

    def test_a_system_failure_is_a_502_not_a_conversational_status(self, client, monkeypatch):
        monkeypatch.setattr("exon.conversational_orchestrator.MAX_ATTEMPTS", 1)
        client.model.queue.append(TurnAttempt(protocol="tool_call", error="provider down"))
        r = client.post("/turn", json={"utterance": "hello", "query_spec": None, "turns": []})
        assert r.status_code == 502
        assert "provider down" in r.json()["detail"]

    def test_malformed_request_body_is_a_422(self, client):
        r = client.post("/turn", json={"query_spec": None, "turns": []})  # missing 'utterance'
        assert r.status_code == 422

    def test_unknown_turn_status_in_history_is_rejected_by_schema(self, client):
        r = client.post("/turn", json={
            "utterance": "x", "query_spec": None,
            "turns": [{"id": "a", "utterance": "y", "status": "not-a-real-status", "message": "z"}],
        })
        assert r.status_code == 422


class TestEdit:
    def test_editing_a_turn_returns_the_redone_turn_with_the_same_id(self, client):
        client.model.queue.append(_proposal(SPEC_A, "t1"))
        r1 = client.post("/turn", json={"utterance": "first", "query_spec": None, "turns": []})
        t1 = r1.json()["turn"]

        client.model.queue.append(_proposal(SPEC_B, "t1 revised"))
        r2 = client.post("/turn", json={
            "utterance": "first, revised", "query_spec": SPEC_A, "turns": [t1], "edit_turn_id": t1["id"],
        })
        assert r2.status_code == 200
        body = r2.json()
        assert body["turn"]["id"] == t1["id"]
        assert body["turn"]["query_spec"] == SPEC_B
        assert body["suspended_turn_ids"] == []

    def test_editing_recomputes_and_suspends_a_later_turn(self, client):
        client.model.queue.append(_proposal(SPEC_A, "t1"))
        r1 = client.post("/turn", json={"utterance": "first", "query_spec": None, "turns": []})
        t1 = r1.json()["turn"]

        client.model.queue.append(_proposal(SPEC_B, "t2"))
        r2 = client.post("/turn", json={"utterance": "second", "query_spec": SPEC_A, "turns": [t1]})
        t2 = r2.json()["turn"]

        client.model.queue.append(_proposal(SPEC_C, "t1 redone"))
        client.model.queue.append(_clarification("t2 no longer applies"))
        r3 = client.post("/turn", json={
            "utterance": "pivot", "query_spec": SPEC_A, "turns": [t1, t2], "edit_turn_id": t1["id"],
        })
        assert r3.status_code == 200
        body = r3.json()
        assert body["suspended_turn_ids"] == [t2["id"]]
        assert body["turn"]["query_spec"] == SPEC_C

    def test_editing_an_unknown_turn_id_is_a_400(self, client):
        r = client.post("/turn", json={
            "utterance": "edit", "query_spec": None,
            "turns": [{"id": "a", "utterance": "x", "status": "proposal", "query_spec": SPEC_A, "message": "y"}],
            "edit_turn_id": "no-such-id",
        })
        assert r.status_code == 400
        assert "no turn" in r.json()["detail"]

    def test_edit_does_not_require_query_spec_to_match_current_state(self, client):
        # Decision 9's equality check is append-only: an edit's redo step
        # rewinds to a PAST point (turns[:idx]), which the wire's
        # current-state field is never the relevant input for.
        client.model.queue.append(_proposal(SPEC_A, "t1"))
        r1 = client.post("/turn", json={"utterance": "first", "query_spec": None, "turns": []})
        t1 = r1.json()["turn"]

        client.model.queue.append(_proposal(SPEC_B, "t1 redone"))
        r2 = client.post("/turn", json={
            # Deliberately wrong/stale top-level query_spec -- must not matter for an edit.
            "utterance": "revise", "query_spec": SPEC_C, "turns": [t1], "edit_turn_id": t1["id"],
        })
        assert r2.status_code == 200


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
