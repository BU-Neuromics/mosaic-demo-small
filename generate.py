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
import random
from datetime import date, datetime, timedelta

import yaml
from linkml_runtime import SchemaView

from linkml_data_gen import DataGenerator, GenerationConfig
from mosaic.core.schema_typing import INFRASTRUCTURE_CLASSES
from mosaic.linkml_bridge import class_accessor_name

HERE = os.path.dirname(os.path.abspath(__file__))
GENERATION_SCHEMA = os.path.join(HERE, "generation_schema.yaml")
DEMO_SCHEMA = os.path.join(HERE, "schemas", "demo.yaml")
HINTS_FILE = os.path.join(HERE, "hints.yaml")
DEFAULT_OUT = os.path.join(HERE, "data", "bundle.yaml")

COUNT_OVERRIDES = {
    # Fact collections — the original four, unchanged.
    "donors": 300,
    "samples": 900,
    "workflows": 1200,
    "datasets": 1200,
    # Fact collections added by grow-demo-schema-collections.
    "toxicology_reports": 200,   # sparser than donors: screens are ordered selectively
    "diagnoses": 450,
    "assessments": 1050,
    "consent_records": 300,      # one per donor
    "aliquots": 1200,
    "run_configurations": 1200,  # one per workflow
    "qc_flags": 620,
    # Dimension collections — deliberately SMALL, never empty. The point of the
    # growth is a bigger grounding surface, not a bigger database: many facts
    # share few dimensions, so load time stays flat while the planner's
    # candidate set grows. A zero here would be a defect, not a saving — no
    # query against an empty collection returns anything, so no discovery eval
    # case could be graded on it.
    "storage_locations": 24,
    "instruments": 9,
    "reagent_lots": 75,
    "publications": 40,
}

# Deliberately seeded keywords for the full-text-search acceptance scenario
# (Donor.notes / Dataset.description) — hints can only shape *probabilistic*
# text, not guarantee a specific keyword appears, so these are patched in
# after generation onto the first record of each pool.
SEEDED_DONOR_KEYWORD = "cohort-alpha:42"
SEEDED_DATASET_KEYWORD = "recall-freeze"
SEEDED_TOXICOLOGY_KEYWORD = "panel-echo:7"
SEEDED_QCFLAG_KEYWORD = "lane-drift"
SEEDED_PUBLICATION_KEYWORD = "consortium-nine"


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


def _check_generation_pools(sv: SchemaView) -> None:
    """Fail loudly when an entity class has no pool in ``DemoBundle``.

    ``generation_schema.yaml`` hand-mirrors one multivalued slot per entity
    class. Its failure mode is silent: a class with no pool simply generates
    nothing, ingests nothing, and shows up in Aperture as a collection that
    opens to an empty table — no error anywhere. At four classes that was a
    latent hazard; at fifteen it is a live one, so the mirror is checked
    rather than remembered.
    """
    # ``induced_slot``, not ``get_slot``: the pools are class *attributes*, which
    # never reach the schema's global slot registry, so ``get_slot`` resolves
    # some of them to unrelated same-named slots and the rest to None. The first
    # version of this check reported Dataset and ReagentLot as missing while
    # they were sitting in DemoBundle.
    pooled = {
        sv.induced_slot(name, "DemoBundle").range
        for name in sv.class_slots("DemoBundle")
    }
    # Mosaic's own exclusion list, imported rather than restated: these classes
    # come from hippo_core, get no table, and so must get no pool. A local copy
    # would silently drift the day Mosaic changes it.
    missing = sorted(
        name
        for name, cls in sv.all_classes().items()
        if cls.is_a == "Entity"
        and not cls.abstract
        and name not in INFRASTRUCTURE_CLASSES
        and name not in pooled
    )
    if missing:
        raise SystemExit(
            "generation_schema.yaml is out of sync with schemas/demo.yaml — "
            f"no DemoBundle pool for: {', '.join(missing)}. Add a multivalued, "
            "inlined_as_list slot per missing class, or it will generate an "
            "empty collection with no error."
        )

    # A pool that exists under the wrong NAME is the subtler half of the same
    # hazard. Mosaic ignores our tree_root and synthesizes its own from the
    # domain classes, deriving each pool name as snake_case(ClassName) + "s"
    # (overridable per class with `hippo_accessor`). A DemoBundle slot that
    # disagrees generates fine and then fails at ingest with "Additional
    # properties are not allowed" — which names the pool but not the rule it
    # broke. `Diagnosis` -> `diagnosiss` found this the hard way.
    mismatched = []
    for slot_name in sv.class_slots("DemoBundle"):
        target = sv.induced_slot(slot_name, "DemoBundle").range
        cls = sv.get_class(target)
        if cls is None:
            continue
        expected = class_accessor_name(target, cls)
        if expected != slot_name:
            mismatched.append(f"{target}: DemoBundle says {slot_name!r}, Mosaic expects {expected!r}")
    if mismatched:
        raise SystemExit(
            "DemoBundle pool names disagree with Mosaic's synthesized tree root "
            "— ingest would reject the bundle:\n  "
            + "\n  ".join(mismatched)
            + "\nRename the DemoBundle slot, or set the class's `hippo_accessor` "
            "annotation to the name you want."
        )


def _order_interval(record: dict, start_key: str, end_key: str, min_days: int, max_days: int,
                    rng: random.Random) -> None:
    """Re-derive an end date/datetime as start + a positive offset.

    Both ends are sampled independently from the same window, so roughly half
    of every pair would otherwise end before it began. Same defect
    ``_fix_workflow_timestamps`` already corrects for workflows; these pairs
    are dates rather than durations, so the offset is drawn rather than read
    off another slot.
    """
    start, end = record.get(start_key), record.get(end_key)
    if not start or not end:
        return
    parse = datetime.fromisoformat
    start_dt = parse(start)
    end_dt = start_dt + timedelta(days=rng.randint(min_days, max_days))
    record[end_key] = end_dt.isoformat() if isinstance(record[start_key], str) and "T" in start else end_dt.date().isoformat()


def _fix_intervals(bundle: dict, seed: int) -> None:
    """Order every start/end pair the new collections introduced.

    Also aligns the boolean that restates each interval, so the demo does not
    show a consent that is simultaneously withdrawn and active. These are
    presentational coherence, not enforced domain rules — the same
    approximation ``Workflow.completed_at`` already makes.
    """
    rng = random.Random(seed)

    for c in bundle.get("consent_records", []):
        _order_interval(c, "signed_at", "withdrawn_at", 30, 2500, rng)
        if "is_active" in c:
            c["is_active"] = c.get("withdrawn_at") is None

    for f in bundle.get("qc_flags", []):
        _order_interval(f, "raised_at", "resolved_at", 1, 90, rng)
        if "is_resolved" in f:
            f["is_resolved"] = f.get("resolved_at") is not None

    for lot in bundle.get("reagent_lots", []):
        # expires_on is required, so unlike the pairs above it is always reset
        # rather than repaired-when-present.
        received = lot.get("received_on")
        if received:
            expiry = datetime.fromisoformat(received) + timedelta(days=rng.randint(90, 1095))
            lot["expires_on"] = expiry.date().isoformat()
            if "is_expired" in lot:
                lot["is_expired"] = expiry.date() < date.today()


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

    # The three fts5 fields the new collections add. Same reason as above:
    # hints shape probabilistic text, they cannot guarantee a keyword, and a
    # search scenario with no known-present term is untestable.
    reports = bundle.get("toxicology_reports") or []
    if reports:
        base = reports[0].get("findings_summary") or ""
        reports[0]["findings_summary"] = (
            f"{base} Confirmed against {SEEDED_TOXICOLOGY_KEYWORD}.".strip()
        )

    flags = bundle.get("qc_flags") or []
    if flags:
        base = flags[0].get("detail") or ""
        flags[0]["detail"] = f"{base} Consistent with {SEEDED_QCFLAG_KEYWORD}.".strip()

    publications = bundle.get("publications") or []
    if publications:
        base = publications[0].get("abstract_text") or ""
        publications[0]["abstract_text"] = (
            f"{base} Conducted by the {SEEDED_PUBLICATION_KEYWORD} group.".strip()
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


#: Every reference edge in the schema, as ``(pool, field, target pool, multivalued)``.
#: Table-driven rather than hand-written per edge: at fifteen classes the
#: hand-written form was already four edges out of date each time a class was
#: added, and a missed edge here means dangling ids reach ingest.
REFERENCE_EDGES = [
    ("samples", "donor", "donors", False),
    ("workflows", "input_samples", "samples", True),
    ("datasets", "produced_by", "workflows", False),
    ("toxicology_reports", "donor", "donors", False),
    ("diagnoses", "donor", "donors", False),
    ("assessments", "donor", "donors", False),
    ("consent_records", "donor", "donors", False),
    ("aliquots", "sample", "samples", False),
    ("aliquots", "location", "storage_locations", False),
    ("run_configurations", "workflow", "workflows", False),
    ("run_configurations", "instrument", "instruments", False),
    ("run_configurations", "reagent_lots", "reagent_lots", True),
    ("qc_flags", "dataset", "datasets", False),
    ("publications", "datasets", "datasets", True),
]


def _check_referential_integrity(bundle: dict) -> None:
    ids = {pool: {r["id"] for r in records} for pool, records in bundle.items()}

    errors = []
    for pool, field, target, multivalued in REFERENCE_EDGES:
        known = ids.get(target, set())
        for record in bundle.get(pool, []):
            value = record.get(field)
            refs = (value or []) if multivalued else ([value] if value is not None else [])
            for ref in refs:
                if ref not in known:
                    errors.append(
                        f"{pool}/{record['id']} has dangling {field}={ref!r} "
                        f"(no such {target})"
                    )

    empty = sorted(pool for pool, records in bundle.items() if not records)
    for pool in empty:
        errors.append(
            f"collection {pool!r} generated zero records — an empty collection "
            "renders as a dead entry in Aperture and cannot be graded by any "
            "eval case"
        )

    if errors:
        print(f"REFERENTIAL INTEGRITY FAILURES ({len(errors)}):", file=sys.stderr)
        for e in errors[:20]:
            print(f"  - {e}", file=sys.stderr)
        raise SystemExit(1)

    counts = ", ".join(f"{len(v)} {k}" for k, v in sorted(bundle.items()))
    print(f"Referential integrity OK across {len(bundle)} collections: {counts}.")
    print(f"Total records: {sum(len(v) for v in bundle.values())}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output bundle YAML path")
    parser.add_argument("--seed", type=int, default=0, help="RNG seed (reproducible)")
    args = parser.parse_args()

    sv = _build_schema_view()
    _check_generation_pools(sv)
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
    _fix_intervals(bundle, args.seed)
    _check_referential_integrity(bundle)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        yaml.safe_dump(bundle, f, sort_keys=False)

    counts = {k: len(v) for k, v in bundle.items() if isinstance(v, list)}
    print(f"Wrote {args.out}: {counts}")


if __name__ == "__main__":
    main()
