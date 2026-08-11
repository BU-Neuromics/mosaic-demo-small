"""python -m exon "<instruction>" -- runs Exon end-to-end: plan -> validate -> execute -> report.

Requires the host-served Mosaic instance running (mosaic serve --config mosaic.yaml --graphql)
and ANTHROPIC_API_KEY set for the planner step.
"""
import dataclasses
import json
import sys

from .executor import execute_plan
from .planner import plan_query
from .schema import fetch_hippo_schema, load_capability_manifest
from .validator import ValidationError, validate_plan

ENDPOINT = "http://localhost:8080/graphql"
MANIFEST_PATH = "evals/schema/capabilities.json"


def main() -> None:
    if len(sys.argv) < 2:
        print('usage: python -m exon "<instruction>"', file=sys.stderr)
        sys.exit(1)
    instruction = sys.argv[1]

    print("Fetching live schema grounding...", file=sys.stderr)
    hippo_schema = fetch_hippo_schema(ENDPOINT)
    capability_manifest = load_capability_manifest(MANIFEST_PATH)

    plan = plan_query(instruction, hippo_schema, capability_manifest)
    print("=== Plan ===")
    print(json.dumps([dataclasses.asdict(s) for s in plan.steps], indent=2, default=str))

    try:
        validate_plan(plan, hippo_schema, capability_manifest)
    except ValidationError as e:
        print(f"=== REJECTED: {e} ===", file=sys.stderr)
        sys.exit(2)
    print("=== Validated OK ===", file=sys.stderr)

    result = execute_plan(plan, ENDPOINT, hippo_schema)
    print("=== Result ===")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
