"""HTTP endpoint for the Aperture-Exon conversational contract (design.md
Decision 8's wire contract). Slice 3 of 3 -- see conversational_planner.py's
docstring for the full split.

This is a thin wrapper: it translates Decision 8's JSON request/response
shape to and from conversational_orchestrator.append_turn/edit_turn calls.
It has no planning logic and no turn-list bookkeeping of its own -- both
already exist and are already tested in isolation.

Capabilities are supplied at app-construction time (`create_conversational_app
(capabilities, ...)`), mirroring how `mosaic.mcp.server.create_mcp_server`
takes its schema-derived data as a constructor argument rather than
fetching it itself. How Exon's real deployment actually OBTAINS that
manifest (an MCP client fetching mosaic://capabilities from a configured
Mosaic URL once at startup, per design.md Decision 8's own text: "Exon's
own turn endpoint may call ... mosaic://capabilities as an MCP client") is
a separate, following increment -- this slice is fully testable with a
real HTTP client and a capabilities dict handed to it directly, without
that wiring existing yet.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .conversational_orchestrator import _current_query_spec, append_turn, edit_turn


class TurnModel(BaseModel):
    id: str
    utterance: str
    status: Literal["proposal", "clarification", "suspended"]
    query_spec: Optional[dict] = None
    message: str


class TurnRequest(BaseModel):
    utterance: str
    query_spec: Optional[dict] = None
    turns: list[TurnModel] = []
    edit_turn_id: Optional[str] = None


class TurnResponse(BaseModel):
    turn: TurnModel
    suspended_turn_ids: list[str] = []


def create_conversational_app(
    capabilities: dict, *, model: str = None, protocol: str = "tool_call"
) -> FastAPI:
    """Build the Exon conversational turn-taking service for one Mosaic
    deployment's capability manifest.

    `model`/`protocol` are threaded through to every request_turn call --
    a deployment-time choice (mirrors planner.py's EXON_MODEL env var),
    not something a caller sets per-request.
    """
    app = FastAPI(title="exon-conversational")

    @app.post("/turn", response_model=TurnResponse)
    def turn(req: TurnRequest) -> TurnResponse:
        turns = [t.model_dump() for t in req.turns]
        kw = {"model": model, "protocol": protocol}

        if req.edit_turn_id is not None:
            try:
                new_turns, redone, suspended = edit_turn(
                    turns, req.edit_turn_id, req.utterance, capabilities, **kw
                )
            except ValueError as exc:
                # A caller mistake (an edit_turn_id not present in the
                # turns it sent) -- 400, not 500: nothing on Exon's own
                # side is broken.
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except RuntimeError as exc:
                # A genuine system failure (API error, exhausted parse
                # retries) -- never folded into a conversational status,
                # per conversational_orchestrator.py's own rationale.
                # Mosaic's converse_query_spec (not this endpoint) is
                # responsible for turning an unreachable/failing Exon into
                # its own discriminated "error" turn status (Decision 8) --
                # from here, a loud transport-level failure is correct.
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            return TurnResponse(turn=TurnModel(**redone), suspended_turn_ids=suspended)

        # Plain append: Decision 9 -- for now, Aperture's point-and-click
        # QuerySpec builder is locked while a chat is active, so the
        # wire's stated `query_spec` and what `turns` alone would derive
        # must always agree. Asserting that (rather than silently trusting
        # either) means nothing quietly goes stale if that lock is ever
        # lifted without this endpoint being told -- see design.md
        # Decision 9 for the unlock path (pass `req.query_spec` through as
        # append_turn's `existing_query_spec` override instead of
        # asserting equality here; no other code needs to change).
        derived = _current_query_spec(turns)
        if req.query_spec != derived:
            raise HTTPException(
                status_code=400,
                detail=(
                    "'query_spec' does not match the state derived from 'turns' -- "
                    "Aperture's point-and-click builder is expected to be locked while "
                    "chatting (design.md Decision 9), so these should never disagree. "
                    f"given={req.query_spec!r} derived={derived!r}"
                ),
            )

        try:
            new_turns, new_turn = append_turn(turns, req.utterance, capabilities, **kw)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return TurnResponse(turn=TurnModel(**new_turn), suspended_turn_ids=[])

    return app
