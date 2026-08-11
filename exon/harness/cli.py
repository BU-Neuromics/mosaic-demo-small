"""Harness entry points.

    python -m exon.harness probe                       # [0] fingerprint the target
    python -m exon.harness run    [--samples K]        # [B]+[C] one pass, print the report
    python -m exon.harness loop   [--auto-refine]      # the whole cycle
    python -m exon.harness report --run <dir>          # re-render a finished run

`run` defaults to report-and-stop; the closed loop needs `--auto-refine` and a refiner credential.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from ..context.seed import seed_context
from ..context.template import ContextArtifact
from ..schema import fetch_hippo_schema, load_capability_manifest
from .cases import load_suite
from .loop import LoopConfig, RUNS_ROOT, new_run_dir, run_refinement_loop
from .probe import ModelFingerprint, probe_model
from .runner import run_suite
from .triage import build_bundle

DEFAULT_ENDPOINT = os.environ.get("EXON_ENDPOINT", "http://localhost:8080/graphql")
DEFAULT_MODEL = os.environ.get("EXON_MODEL", "ollama_chat/gemma4:12b")
FINGERPRINT_PATH = Path("evals/schema/fingerprint.json")
MANIFEST_PATH = "evals/schema/capabilities.json"


def _grounding_for_probe(hippo_schema, manifest):
    from ..planner import PLAN_TOOL, build_grounding_context

    return (
        build_grounding_context(hippo_schema, manifest),
        "bring me back all of the brain tissue samples for the hippocampus region, with the "
        "donor cohort, sex and RHI history, and any rnaSeq data associated with them",
        PLAN_TOOL,
    )


def _load_or_probe(model, hippo_schema, manifest, *, force=False, skip_load_check=False):
    """A stored fingerprint is reused only if it matches this model; otherwise re-probe. A context
    fitted to one local model tells you nothing about another."""
    if FINGERPRINT_PATH.exists() and not force:
        fp = ModelFingerprint.from_dict(json.loads(FINGERPRINT_PATH.read_text()))
        if fp.model == model:
            print(f"reusing fingerprint {fp.id} for {model} ({FINGERPRINT_PATH})")
            return fp
        print(f"stored fingerprint is for {fp.model!r}, not {model!r} -- re-probing")
    fp = probe_model(
        model,
        load_check=None if skip_load_check else _grounding_for_probe(hippo_schema, manifest),
    )
    FINGERPRINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    FINGERPRINT_PATH.write_text(json.dumps(fp.to_dict(), indent=2) + "\n")
    print(f"wrote {FINGERPRINT_PATH}")
    return fp


def _seed_or_latest(fp, contexts_dir: Path) -> ContextArtifact:
    existing = ContextArtifact.latest(contexts_dir) if contexts_dir.exists() else None
    if existing is not None:
        existing.assert_fingerprint(fp.id)   # refuses a context fitted to a different model
        print(f"resuming from context v{existing.version:03d}")
        return existing
    return seed_context(fp)


def cmd_probe(args):
    hs = fetch_hippo_schema(args.endpoint)
    m = load_capability_manifest(MANIFEST_PATH)
    fp = _load_or_probe(args.model, hs, m, force=True, skip_load_check=args.skip_load_check)
    art = seed_context(fp)
    print(f"\nseed context: protocol={art.protocol.value} "
          f"num_ctx={art.decode_params.num_ctx} blocks={len(art.blocks)}")
    return 0


def cmd_run(args):
    hs = fetch_hippo_schema(args.endpoint)
    m = load_capability_manifest(MANIFEST_PATH)
    cases = load_suite()
    fp = _load_or_probe(args.model, hs, m, skip_load_check=True)
    artifact = (
        ContextArtifact.load(args.context) if args.context else seed_context(fp)
    )

    report = run_suite(
        cases, artifact, hs, m,
        model=args.model,
        samples_per_case=args.samples,
        endpoint=args.endpoint,
        max_workers=args.workers,
        split=args.split,
        progress=True,
    )
    print()
    print(report.summary_line())
    print()
    for r in sorted(report.results, key=lambda r: r.pass_rate):
        flag = "FLAKY" if r.is_flaky else ("ok" if r.strict_pass else "FAIL")
        print(f"  {r.case_id:<5} {r.split:<8} {r.pass_rate:>4.0%}  {flag:<6} {r.outcome_counts()}")

    env = report.environment_failures()
    if env:
        print(f"\n{len(env)} environment/config failure(s) -- NOT context problems, withheld "
              f"from any refiner: {env[:5]}")

    train_only = [c for c in cases if c.split == "train"]
    from .loop import _train_only

    bundle = build_bundle(
        _train_only(report), train_only, artifact,
        determinism_ceiling=fp.determinism_at_temp_0,
    )
    out = Path(args.out) if args.out else new_run_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report.to_dict(), indent=2, default=str) + "\n")
    (out / "bundle.md").write_text(bundle.to_markdown())
    print(f"\nwrote {out}/report.json and {out}/bundle.md")
    return 0


def cmd_loop(args):
    hs = fetch_hippo_schema(args.endpoint)
    m = load_capability_manifest(MANIFEST_PATH)
    cases = load_suite()
    fp = _load_or_probe(args.model, hs, m, skip_load_check=args.skip_load_check)

    run_dir = Path(args.out) if args.out else new_run_dir()
    seed = _seed_or_latest(fp, run_dir / "contexts")
    (run_dir / "fingerprint.json").write_text(json.dumps(fp.to_dict(), indent=2) + "\n")

    cfg = LoopConfig(
        model=args.model,
        samples_per_case=args.samples,
        max_iterations=args.max_iter,
        reliability_threshold=args.threshold,
        endpoint=args.endpoint,
        max_workers=args.workers,
        auto_refine=args.auto_refine,
    )
    outcome = run_refinement_loop(
        cases, seed, hs, m, cfg, fingerprint=fp, run_dir=run_dir
    )
    print(f"\nstop reason: {outcome.stop_reason}")
    print(f"baseline holdout {outcome.baseline_holdout:.2f} -> best "
          f"{outcome.best_holdout:.2f} ({outcome.improvement():+.2f}) "
          f"at v{outcome.best_artifact.version:03d}")
    print(f"report: {outcome.run_dir}/report.md")
    return 0


def cmd_report(args):
    run = Path(args.run)
    md = run / "report.md"
    if md.exists():
        print(md.read_text())
        return 0
    its = sorted((run / "iterations").glob("iter*.json"))
    if not its:
        print(f"no report or iterations found under {run}", file=sys.stderr)
        return 1
    for p in its:
        d = json.loads(p.read_text())
        s = d["scores"]
        print(f"iter {d['iteration']:02d} v{d['context_version']:03d} "
              f"train={s['train']:.2f} holdout={s['holdout']:.2f} "
              f"strict={s['strict_train']} flaky={s['flaky']}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m exon.harness")
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe", help="fingerprint the target model")
    p.add_argument("--skip-load-check", action="store_true",
                   help="skip the under-load protocol verification (faster, but the isolated "
                        "ladder alone can be confidently wrong)")
    p.set_defaults(fn=cmd_probe)

    r = sub.add_parser("run", help="one pass over the suite")
    r.add_argument("--samples", type=int, default=5)
    r.add_argument("--split", choices=["train", "holdout"], default=None)
    r.add_argument("--context", default=None, help="path to a context vNNN.json")
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--out", default=None)
    r.set_defaults(fn=cmd_run)

    l = sub.add_parser("loop", help="the full measure -> refine -> re-measure cycle")
    l.add_argument("--samples", type=int, default=5)
    l.add_argument("--max-iter", type=int, default=10)
    l.add_argument("--threshold", type=float, default=0.8)
    l.add_argument("--workers", type=int, default=4)
    l.add_argument("--out", default=None)
    l.add_argument("--skip-load-check", action="store_true")
    l.add_argument("--auto-refine", action="store_true",
                   help="call the refiner model and apply patches; without it the run reports "
                        "and stops")
    l.set_defaults(fn=cmd_loop)

    rep = sub.add_parser("report", help="re-render a finished run")
    rep.add_argument("--run", required=True)
    rep.set_defaults(fn=cmd_report)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
