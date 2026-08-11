#!/usr/bin/env python3
"""Explore the ingested mosaic-demo-small store via the Mosaic SDK directly
(no running server needed) — a quick sanity check to run alongside (not
instead of) manual verification in Aperture.

Demonstrates: per-class counts, a facet tally, a single-valued-reference
filter query, full-text search on both hippo_search fields, and the full
Dataset -> Workflow -> Sample -> Donor traversal.
"""

from __future__ import annotations

import argparse
import collections
import os

import mosaic

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCHEMA = os.path.join(HERE, "schemas", "demo.yaml")
DEFAULT_DB = os.path.join(HERE, "data", "mosaic.db")


def facet_tally(client: "mosaic.MosaicClient", entity_type: str, field: str, sample: int = 2000) -> dict:
    items = client.query(entity_type, limit=sample).items
    return dict(collections.Counter(i["data"].get(field) for i in items).most_common())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default=DEFAULT_SCHEMA)
    parser.add_argument("--db", default=DEFAULT_DB)
    args = parser.parse_args()

    client = mosaic.client_for_schema(args.schema, database_url=args.db)

    print("=== Counts ===")
    for cls in ("Donor", "Sample", "Workflow", "Dataset"):
        print(f"  {cls}: {client.query(cls, limit=1).total}")

    print("\n=== Facets ===")
    print("  Donor.cohort:", facet_tally(client, "Donor", "cohort"))
    print("  Donor.sex:", facet_tally(client, "Donor", "sex"))
    print("  Sample.sample_type:", facet_tally(client, "Sample", "sample_type"))
    print("  Workflow.status:", facet_tally(client, "Workflow", "status"))
    print("  Dataset.access_level:", facet_tally(client, "Dataset", "access_level"))
    print("  Dataset.is_public:", facet_tally(client, "Dataset", "is_public"))

    print("\n=== Single-valued FK filter (bidirectionally queryable) ===")
    # Pick the donor with the most samples so the check is meaningful (not
    # just "returned >= 1") — verify the filter returns EXACTLY that donor's
    # samples, not merely a nonzero/under-returning result.
    all_samples = client.query("Sample", limit=2000).items
    by_donor = collections.Counter(s["data"]["donor"] for s in all_samples)
    donor_id, expected_count = by_donor.most_common(1)[0]
    result = client.query("Sample", filters=[{"field": "donor", "value": donor_id}])
    got_ids = sorted(i["id"] for i in result.items)
    expected_ids = sorted(s["id"] for s in all_samples if s["data"]["donor"] == donor_id)
    print(f"  Donor {donor_id}: expected {expected_count} samples, "
          f"filter returned {result.total} ({'exact match' if got_ids == expected_ids else 'MISMATCH'})")

    print("\n=== Full-text search ===")
    donor_hits = client.search("Donor", "cohortalpha42")
    print(f"  Donor.notes ~ 'cohortalpha42': {[h['id'] for h in donor_hits]}")
    dataset_hits = client.search("Dataset", "recalfreeze")
    print(f"  Dataset.description ~ 'recalfreeze': {[h['id'] for h in dataset_hits]}")

    print("\n=== Multi-hop traversal: Dataset -> Workflow -> Sample(s) -> Donor(s) ===")
    dataset = client.query("Dataset", limit=1).items[0]
    workflow = client.get("Workflow", dataset["data"]["produced_by"])
    sample_ids = workflow["data"]["input_samples"]
    donor_ids = {client.get("Sample", sid)["data"]["donor"] for sid in sample_ids}
    print(f"  Dataset {dataset['id']} -> Workflow {workflow['id']} "
          f"-> {len(sample_ids)} Sample(s) -> {len(donor_ids)} distinct Donor(s): {sorted(donor_ids)}")

    print("\n=== Reverse-query limitation (expected, per design) ===")
    print("  No GraphQL/SDK query field exists for 'workflows(inputSamples: <id>)' —")
    print("  the multivalued reference is forward-resolved only via the schema's")
    print("  generated API. (The lower-level client.relationships.find_relationships(")
    print("  target_id=...) *can* answer this off the shared relationships table, but")
    print("  that's an internal SDK escape hatch, not a schema-generated query field —")
    print("  Aperture's GraphQL layer never exposes it.)")


if __name__ == "__main__":
    main()
