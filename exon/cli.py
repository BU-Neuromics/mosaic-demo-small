"""python -m exon "<instruction>" -- runs Exon end-to-end: plan -> validate -> execute -> report.

Requires the host-served Mosaic instance running WITH the MCP boundary
(`mosaic serve --config mosaic.yaml --graphql --mcp`) and the credential for
whatever `EXON_MODEL` names (see exon/README.md).

Migrated to Mosaic's MCP query boundary (`add-mosaic-mcp-boundary` task 2.3):
the model emits a `QuerySpec`, and Mosaic validates and executes it. Exon no
longer validates or executes anything itself.

Three things changed here, all of them the point of the migration:

  - Grounding comes from `mosaic://capabilities` (server-generated, from the
    live SchemaRegistry) instead of the hand-authored
    `evals/schema/capabilities.json`, which could and did drift from the
    deployment being queried.
  - `validator.validate_plan` -> Mosaic's `validate_query_spec`.
  - `executor.execute_plan` -> Mosaic's `execute_query_spec`.

`exon/planner.py`, `validator.py`, `executor.py` and `ops.py` (the QueryPlan
path) are deliberately still present and untouched: task 2.4 retires them only
once this path is confirmed end-to-end, and `harness/` still grades against
QueryPlan until task 2.5 re-baselines it.
"""
import json
import sys

from .mosaic_mcp import (
    MosaicBoundaryError,
    execute_query_spec,
    fetch_capabilities,
    mcp_url,
    validate_query_spec,
)
from .spec_planner import plan_query_spec

PAGE_LIMIT = 1000


def _print_errors(errors: list) -> None:
    for e in errors:
        code = e.get("code", "?")
        path = e.get("path", "?")
        print(f"  [{code}] {path}: {e.get('message', '')}", file=sys.stderr)


def main() -> None:
    if len(sys.argv) < 2:
        print('usage: python -m exon "<instruction>"', file=sys.stderr)
        sys.exit(1)
    instruction = sys.argv[1]

    try:
        print(f"Fetching capability grounding from {mcp_url()} ...", file=sys.stderr)
        capabilities = fetch_capabilities()

        spec = plan_query_spec(instruction, capabilities)
        print("=== QuerySpec ===")
        print(json.dumps(spec, indent=2, default=str))

        # Validate as its own step, even though execute_query_spec validates
        # again server-side regardless. The point is the REPORT: a rejected
        # spec should show the user precisely which criterion Mosaic refused
        # and why, rather than surfacing as an empty result set.
        verdict = validate_query_spec(spec)
        if not verdict.get("valid"):
            print("=== REJECTED by Mosaic's validator ===", file=sys.stderr)
            _print_errors(verdict.get("errors") or [])
            sys.exit(2)
        print("=== Validated OK (by Mosaic) ===", file=sys.stderr)

        result = execute_query_spec(spec, limit=PAGE_LIMIT)
    except MosaicBoundaryError as e:
        # The boundary being unreachable is an operational failure, distinct
        # from a query being rejected -- different exit code so a script can
        # tell "your question was refused" from "the server is down".
        print(f"=== BOUNDARY UNREACHABLE: {e} ===", file=sys.stderr)
        sys.exit(3)
    except RuntimeError as e:
        # plan_query_spec's own exhausted-retries/API-failure convention.
        print(f"=== PLANNING FAILED: {e} ===", file=sys.stderr)
        sys.exit(4)

    if not result.get("valid"):
        # Reachable only if the spec passed the standalone validate above and
        # was then refused at execute time -- a real inconsistency worth
        # showing loudly rather than smoothing over.
        print("=== REJECTED at execution ===", file=sys.stderr)
        _print_errors(result.get("errors") or [])
        sys.exit(2)

    total = result.get("total")
    items = result.get("items") or []
    print("=== Result ===")
    print(json.dumps({"total": total, "items": items}, indent=2, default=str))
    if total is not None and len(items) < total:
        print(
            f"(showing {len(items)} of {total}; raise PAGE_LIMIT or page with offset)",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
