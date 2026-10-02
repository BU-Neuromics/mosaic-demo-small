"""`python -m exon.chat` -- an interactive terminal chat for the conversational
MVP. Stands in for Aperture's (unbuilt) chat UI so the path can be driven and
demonstrated by a person.

It deliberately talks to **Mosaic's `converse_query_spec` MCP tool**, never to
Exon directly. That is the whole point: this exercises the real MVP path
(client -> Mosaic -> Exon -> Mosaic re-validates -> client), so what you see
here is what Aperture will get, not a shortcut around the boundary.

It also plays Aperture's other role: **holding the conversation state**. Exon
is stateless by design, so the turn list lives here and is sent back in full on
every call -- exactly what Aperture will do with it.

Commands:
    <anything else>   send as the next conversational turn
    /run              execute the current QuerySpec and show matching records
    /spec             print the current QuerySpec
    /turns            list the conversation's turns, with their numbers
    /edit N <text>    rewind: redo turn N with new wording, recomputing later turns
    /help, /quit
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Optional

from .mosaic_mcp import mcp_url

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
GREEN, YELLOW, RED, CYAN = "\033[32m", "\033[33m", "\033[31m", "\033[36m"

STATUS_STYLE = {
    "proposal": (GREEN, "proposal"),
    "clarification": (YELLOW, "needs clarification"),
    "suspended": (YELLOW, "suspended"),
    "error": (RED, "error"),
}


def _c(text: str, colour: str) -> str:
    return f"{colour}{text}{RESET}"


def _print_turn(turn: dict, *, index: Optional[int] = None) -> None:
    colour, label = STATUS_STYLE.get(turn.get("status"), (DIM, turn.get("status", "?")))
    prefix = f"[{index}] " if index is not None else ""
    print(f"\n{prefix}{_c('you', DIM)}: {turn.get('utterance', '')}")
    print(f"{prefix}{_c('exon', CYAN)} ({_c(label, colour)}): {turn.get('message', '')}")


def _print_spec(spec: Optional[dict]) -> None:
    if not spec:
        print(_c("  (no QuerySpec yet)", DIM))
        return
    print(_c(json.dumps(spec, indent=2), DIM))


def _current_spec(turns: list) -> Optional[dict]:
    """The draft as of now: the most recent proposal's spec. Mirrors
    conversational_orchestrator._current_query_spec -- a clarification or a
    suspended turn changes nothing."""
    for t in reversed(turns):
        if t.get("status") == "proposal":
            return t.get("query_spec")
    return None


def _print_records(payload: dict) -> None:
    if not payload.get("valid"):
        print(_c("  Mosaic rejected this QuerySpec:", RED))
        for e in payload.get("errors") or []:
            print(f"    [{e.get('code')}] {e.get('path')}: {e.get('message')}")
        return

    items, total = payload.get("items") or [], payload.get("total")
    print(f"\n  {_c(str(total), BOLD)} matching record(s); showing {len(items)}.\n")
    if not items:
        return

    # Column set from the first record's own data -- the schema is arbitrary,
    # so nothing here hardcodes field names.
    cols = [k for k in (items[0].get("data") or {}) if k != "name"][:5]
    header = f"  {'id':<12} " + " ".join(f"{c[:14]:<15}" for c in cols)
    print(_c(header, BOLD))
    print(_c("  " + "-" * (len(header) - 2), DIM))
    for it in items:
        data = it.get("data") or {}
        row = f"  {str(it.get('id', ''))[:12]:<12} "
        row += " ".join(f"{str(data.get(c, ''))[:14]:<15}" for c in cols)
        print(row)


async def _converse(session: Any, **args) -> dict:
    result = await session.call_tool("converse_query_spec", args)
    (content,) = result.content
    return json.loads(content.text)


async def _execute(session: Any, spec: dict, limit: int = 10) -> dict:
    result = await session.call_tool(
        "execute_query_spec", {"query_spec": spec, "limit": limit}
    )
    (content,) = result.content
    return json.loads(content.text)


HELP = """
Type anything to send it as the next conversational turn. Commands:
  /run           execute the current QuerySpec and show matching records
  /spec          print the current QuerySpec
  /turns         list the conversation's turns with their numbers
  /edit N <text> redo turn N with new wording (later turns recompute)
  /help          this message
  /quit          exit
"""


async def _repl(session: Any) -> None:
    turns: list = []
    print(HELP)

    while True:
        try:
            line = (await asyncio.to_thread(input, f"\n{BOLD}>{RESET} ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue

        if line in ("/quit", "/exit"):
            return
        if line == "/help":
            print(HELP)
            continue
        if line == "/spec":
            _print_spec(_current_spec(turns))
            continue
        if line == "/turns":
            if not turns:
                print(_c("  (no turns yet)", DIM))
            for i, t in enumerate(turns, 1):
                _print_turn(t, index=i)
            continue

        if line == "/run":
            spec = _current_spec(turns)
            if not spec:
                print(_c("  Nothing to run yet -- ask for something first.", YELLOW))
                continue
            print(_c("  executing via Mosaic's execute_query_spec ...", DIM))
            _print_records(await _execute(session, spec))
            continue

        edit_turn_id = None
        utterance = line
        if line.startswith("/edit"):
            parts = line.split(maxsplit=2)
            if len(parts) < 3 or not parts[1].isdigit():
                print(_c("  usage: /edit N <new wording>", YELLOW))
                continue
            n = int(parts[1])
            if not 1 <= n <= len(turns):
                print(_c(f"  no turn {n}; there are {len(turns)}.", YELLOW))
                continue
            edit_turn_id, utterance = turns[n - 1]["id"], parts[2]
            print(_c(f"  rewinding to turn {n} and recomputing after it ...", DIM))
        else:
            print(_c("  thinking ...", DIM))

        payload = await _converse(
            session,
            utterance=utterance,
            query_spec=_current_spec(turns) if edit_turn_id is None else None,
            turns=turns,
            edit_turn_id=edit_turn_id,
        )
        turn = payload["turn"]
        suspended = payload.get("suspended_turn_ids") or []

        # Take the server's authoritative `turns` wholesale rather than
        # rebuilding locally. After an edit this is the only place the
        # recomputed later turns exist -- reconstructing from `turn` alone
        # would leave a stale draft and make /run execute a pre-edit query.
        # Absent `turns` means nothing was applied (an error turn), so the
        # existing list stays as-is.
        if payload.get("turns"):
            turns = payload["turns"]
        elif turn.get("status") != "error":
            turns = turns + [turn]

        _print_turn(turn)
        if turn.get("status") == "proposal":
            _print_spec(turn.get("query_spec"))
            print(_c("  /run to see matching records", DIM))
        if suspended:
            print(
                _c(
                    f"\n  {len(suspended)} later turn(s) no longer make sense after that "
                    f"edit and were suspended, not dropped -- /turns to see them, then "
                    f"re-word them.",
                    YELLOW,
                )
            )


async def _main() -> int:
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
    except ImportError:
        print("Needs the mcp package: pip install -r exon/requirements.txt", file=sys.stderr)
        return 1

    url = mcp_url()
    print(f"{BOLD}Exon conversational demo{RESET}  {DIM}(via Mosaic at {url}){RESET}")
    try:
        async with streamable_http_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                if "converse_query_spec" not in names:
                    print(
                        _c(
                            "\nMosaic is up, but converse_query_spec is not registered.\n"
                            "It only appears when Mosaic knows where Exon is. Restart it with:\n"
                            "  MOSAIC_EXON_URL=http://127.0.0.1:9100/turn \\\n"
                            "    mosaic serve --config mosaic.yaml --graphql --mcp --port 8080\n"
                            "and start Exon's turn service with:\n"
                            "  python -m exon.conversational_server",
                            RED,
                        ),
                        file=sys.stderr,
                    )
                    return 2
                await _repl(session)
    except Exception as exc:  # noqa: BLE001 - a demo should explain, not traceback
        print(
            _c(
                f"\nCould not talk to Mosaic's MCP boundary at {url}: "
                f"{type(exc).__name__}: {exc}\n"
                f"Is it running with --mcp? See DEMO.md section 6.",
                RED,
            ),
            file=sys.stderr,
        )
        return 3
    print("bye")
    return 0


def main() -> None:
    sys.exit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
