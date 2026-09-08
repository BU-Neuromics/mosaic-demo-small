"""Exon's MCP client onto Mosaic's query boundary (`add-mosaic-mcp-boundary`
task 2.3).

This is the module that makes Exon a *client* of the boundary rather than a
second implementation of it. Three calls, each replacing something Exon used
to do locally:

  - `fetch_capabilities()`  replaces `schema.load_capability_manifest()` reading
    a hand-authored `evals/schema/capabilities.json`. The server generates the
    manifest from its own live `SchemaRegistry`, so it cannot drift from the
    deployment the query will actually run against -- which was the whole
    three-way-drift problem this migration exists to fix.
  - `validate_query_spec()` replaces `validator.validate_plan()`.
  - `execute_query_spec()`  replaces `executor.execute_plan()`.

Deliberately NOT included:

  - Any re-implementation of validation. A `valid: false` result is returned
    as-is, coded errors and all; interpreting them is the caller's business.
    Re-checking anything here would rebuild the duplication being removed.
  - The aggregation/search tools (`count_query_spec` etc.). They exist on the
    boundary and Exon will need them, but *deciding* which of them a given
    instruction wants is task 2.5c's open question ("teach the planner to
    route, or grade the class explicitly") -- an unmade decision, not a
    missing function. Wiring them in ahead of that choice would prejudge it,
    so this module exposes only what task 2.3 actually asks for. Adding them
    later is additive: same session plumbing, one more thin method each.

Sync-facing on purpose. The MCP SDK is async, but every caller here (`cli.py`,
the harness) is synchronous top-to-bottom, and one `asyncio.run` per call is
the honest cost of that -- there is no long-lived session to amortize, since
each Exon invocation is a one-shot process. A future long-running Exon service
would want a persistent session instead; that is a real change, flagged here
rather than pre-built.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

DEFAULT_MCP_URL = "http://localhost:8080/mcp"

#: Env var naming the Mosaic MCP endpoint. Mirrors `EXON_MODEL`'s
#: deployment-time-choice convention: a deployment detail, never a code change.
MCP_URL_ENV = "MOSAIC_MCP_URL"


def mcp_url() -> str:
    return os.environ.get(MCP_URL_ENV, "").strip() or DEFAULT_MCP_URL


class MosaicBoundaryError(RuntimeError):
    """Raised when the boundary itself is unreachable or answers
    unintelligibly -- NOT when it validly reports a QuerySpec invalid.

    That distinction is the point: an invalid QuerySpec is a normal,
    expected, information-carrying outcome that callers must handle, while
    "Mosaic isn't there" is an operational failure. Collapsing the two
    would make a stopped server look like a rejected query.
    """


async def _call(coro_name: str, *args, **kwargs) -> Any:
    """Open a session, run one operation, close. See the module docstring on
    why this is per-call rather than a held session."""
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise MosaicBoundaryError(
            "The MCP client requires the `mcp` package: pip install -r exon/requirements.txt"
        ) from exc

    url = mcp_url()
    try:
        # NOTE: mcp 2.1.1's streamable_http_client yields a 2-tuple. Older
        # snippets in the wild unpack three values (an extra session-id
        # callback); if this raises a ValueError on unpacking after an SDK
        # upgrade, that arity is why.
        async with streamable_http_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await getattr(session, coro_name)(*args, **kwargs)
    except MosaicBoundaryError:
        raise
    except Exception as exc:
        raise MosaicBoundaryError(
            f"Could not reach Mosaic's MCP boundary at {url}: {_root_cause(exc)}. Is the "
            f"server running with --mcp (mosaic serve --config mosaic.yaml --graphql "
            f"--mcp)? Set {MCP_URL_ENV} to point elsewhere."
        ) from exc


def _root_cause(exc: BaseException) -> str:
    """Flatten an ExceptionGroup down to its actual cause.

    The MCP SDK runs its transport in an anyio task group, so a plain
    connection refusal surfaces as "unhandled errors in a TaskGroup (1
    sub-exception)" -- which tells an operator nothing. This message exists
    to be actionable, so dig out the leaf: "[Errno 61] Connection refused"
    is the thing worth printing.
    """
    seen = 0
    while seen < 10:
        inner = getattr(exc, "exceptions", None)
        if not inner:
            break
        exc = inner[0]
        seen += 1
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


def _tool_payload(result: Any) -> dict:
    """Unwrap a tool result's single JSON content block."""
    content = getattr(result, "content", None) or []
    if not content:
        raise MosaicBoundaryError("Mosaic returned a tool result with no content block.")
    text = getattr(content[0], "text", None)
    if text is None:
        raise MosaicBoundaryError(
            f"Mosaic returned a non-text tool result ({type(content[0]).__name__})."
        )
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise MosaicBoundaryError(
            f"Mosaic returned a tool result that is not JSON: {text[:200]!r}"
        ) from exc


def fetch_capabilities() -> dict:
    """Read `mosaic://capabilities` -- the server-generated manifest, keyed by
    entity name, that `spec_planner`'s grounding renderers consume directly."""
    result = asyncio.run(_call("read_resource", "mosaic://capabilities"))
    contents = getattr(result, "contents", None) or []
    if not contents:
        raise MosaicBoundaryError("mosaic://capabilities returned no contents.")
    text = getattr(contents[0], "text", None)
    if text is None:
        raise MosaicBoundaryError("mosaic://capabilities returned no text content.")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise MosaicBoundaryError(
            f"mosaic://capabilities is not JSON: {text[:200]!r}"
        ) from exc


def validate_query_spec(spec: dict) -> dict:
    """`{valid, errors}`. A `valid: false` is a RESULT, not an exception --
    its coded per-criterion errors are exactly what a retry loop needs."""
    return _tool_payload(
        asyncio.run(_call("call_tool", "validate_query_spec", {"query_spec": spec}))
    )


def execute_query_spec(spec: dict, *, limit: int = 100, offset: int = 0) -> dict:
    """`{valid, errors, items, total}`. Validates server-side first,
    unconditionally, so a caller that skipped `validate_query_spec` still
    cannot execute an invalid spec -- the boundary's guarantee, not ours."""
    return _tool_payload(
        asyncio.run(
            _call(
                "call_tool",
                "execute_query_spec",
                {"query_spec": spec, "limit": limit, "offset": offset},
            )
        )
    )
