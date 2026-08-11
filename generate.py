#!/usr/bin/env python3
"""Generate the mosaic-demo-small synthetic data bundle.

Uses linkml-data-gen's Python API (not its CLI) so the per-class counts can
exceed the CLI's ``--count-for`` clamp of 1000. Builds the SchemaView by hand
with an explicit importmap so ``schemas/demo.yaml``'s ``imports: [hippo_core]``
resolves without going through Mosaic's own schema-loading path (see
generation_schema.yaml's header comment for why a separate, generation-only
tree_root schema is used instead of declaring one in schemas/demo.yaml).
"""

from __future__ import annotations

import argparse
import importlib.resources
import os
import sys
from datetime import datetime, timedelta

import yaml
from linkml_runtime import SchemaView

from linkml_data_gen import DataGenerator, GenerationConfig

HERE = os.path.dirname(os.path.abspath(__file__))
GENERATION_SCHEMA = os.path.join(HERE, "generation_schema.yaml")
DEMO_SCHEMA = os.path.join(HERE, "schemas", "demo.yaml")
HINTS_FILE = os.path.join(HERE, "hints.yaml")
DEFAULT_OUT = os.path.join(HERE, "data", "bundle.yaml")

COUNT_OVERRIDES = {"donors": 300, "samples": 900, "workflows": 1200, "datasets": 1200}

# Deliberately seeded keywords for the full-text-search acceptance scenario
# (Donor.notes / Dataset.description) — hints can only shape *probabilistic*
# text, not guarantee a specific keyword appears, so these are patched in
# after generation onto the first record of each pool.
SEEDED_DONOR_KEYWORD = "cohort-alpha:42"
SEEDED_DATASET_KEYWORD = "recall-freeze"


def _build_schema_view() -> SchemaView:
    hippo_core = str(
        importlib.resources.files("mosaic.schemas").joinpath("hippo_core")
    ).removesuffix(".yaml")
    importmap = {
        "hippo_core": hippo_core,
        "demo": DEMO_SCHEMA.removesuffix(".yaml"),
    }
    return SchemaView(GENERATION_SCHEMA, importmap=importmap)


def _load_hints() -> dict:
    with open(HINTS_FILE) as f:
        return yaml.safe_load(f)


def _seed_keywords(bundle: dict) -> None:
    donors = bundle.get("donors") or []
    if donors:
        base = donors[0].get("notes") or ""
        donors[0]["notes"] = f"{base} Enrolled under {SEEDED_DONOR_KEYWORD}.".strip()

    datasets = bundle.get("datasets") or []
    if datasets:
        base = datasets[0].get("description") or ""
        datasets[0]["description"] = (
            f"{base} Produced from the {SEEDED_DATASET_KEYWORD} pipeline run.".strip()
        )


def _fix_workflow_timestamps(bundle: dict) -> None:
    """Re-derive completed_at from started_at + duration_hours.

    started_at and completed_at are sampled independently (each from the
    same 2015-2025 default window), so roughly half of all workflows would
    otherwise show a completion date before their start date. Anchoring
    completed_at to started_at + duration keeps both fields (already
    individually realistic) mutually consistent.
    """
    for w in bundle.get("workflows", []):
        started = w.get("started_at")
        completed = w.get("completed_at")
        if not started or not completed:
            continue
        start_dt = datetime.fromisoformat(started)
        duration = w.get("duration_hours", 2.0)
        end_dt = start_dt + timedelta(hours=duration)
        w["completed_at"] = end_dt.isoformat()


def _check_referential_integrity(bundle: dict) -> None:
    donor_ids = {d["id"] for d in bundle.get("donors", [])}
    sample_ids = {s["id"] for s in bundle.get("samples", [])}
    workflow_ids = {w["id"] for w in bundle.get("workflows", [])}

    errors = []
    for s in bundle.get("samples", []):
        if s.get("donor") not in donor_ids:
            errors.append(f"Sample {s['id']} has dangling donor={s.get('donor')!r}")
    for w in bundle.get("workflows", []):
        for sid in w.get("input_samples") or []:
            if sid not in sample_ids:
                errors.append(f"Workflow {w['id']} has dangling input_sample={sid!r}")
    for d in bundle.get("datasets", []):
        if d.get("produced_by") not in workflow_ids:
            errors.append(f"Dataset {d['id']} has dangling produced_by={d.get('produced_by')!r}")

    if errors:
        print(f"REFERENTIAL INTEGRITY FAILURES ({len(errors)}):", file=sys.stderr)
        for e in errors[:20]:
            print(f"  - {e}", file=sys.stderr)
        raise SystemExit(1)

    print(
        "Referential integrity OK: "
        f"{len(donor_ids)} donors, {len(sample_ids)} samples, "
        f"{len(workflow_ids)} workflows, {len(bundle.get('datasets', []))} datasets."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output bundle YAML path")
    parser.add_argument("--seed", type=int, default=0, help="RNG seed (reproducible)")
    args = parser.parse_args()

    sv = _build_schema_view()
    hints = _load_hints()
    config = GenerationConfig(
        seed=args.seed,
        count_overrides=COUNT_OVERRIDES,
        max_count=1200,
        hints=hints,
    )
    gen = DataGenerator(sv, config)
    bundle = gen.generate(root_class="DemoBundle")

    _seed_keywords(bundle)
    _fix_workflow_timestamps(bundle)
    _check_referential_integrity(bundle)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        yaml.safe_dump(bundle, f, sort_keys=False)

    counts = {k: len(v) for k, v in bundle.items() if isinstance(v, list)}
    print(f"Wrote {args.out}: {counts}")


if __name__ == "__main__":
    main()
