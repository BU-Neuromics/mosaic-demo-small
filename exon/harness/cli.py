"""Harness entry points.

    python -m exon.harness probe                       # [0] fingerprint the target
    python -m exon.harness run    [--samples K]        # [B]+[C] one pass, print the report
    python -m exon.harness loop   [--auto-refine]      # the whole cycle
    python -m exon.harness report --run <dir>          # re-render a finished run
    python -m exon.harness report --compare <a> <b>... # compare 2+ finished runs, no new calls

`run` defaults to report-and-stop; the closed loop needs `--auto-refine` and a refiner credential.
"""
import argparse
import json
import os
import re
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
DEFAULT_MODEL = os.environ.get("EXON_MODEL", "bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0")
MANIFEST_PATH = "evals/schema/capabilities.json"


def _model_slug(model: str) -> str:
    """Mechanical, collision-free -- no alias table, no stripping version suffixes (two
    versions of the same model must never resolve to the same fingerprint path)."""
    return re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")


def _fingerprint_path(model: str) -> Path:
    """One path per exact model string, so probing model B never overwrites or is mistaken
    for model A's measured capabilities (the shared evals/schema/fingerprint.json this replaced
    required a manual copy-and-rename to avoid exactly that)."""
    return Path(f"evals/schema/fingerprint-{_model_slug(model)}.json")


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
    fitted to one local model tells you nothing about another. Each model gets its own on-disk
    path (see _fingerprint_path), so probing model B never touches model A's file."""
    fingerprint_path = _fingerprint_path(model)
    if fingerprint_path.exists() and not force:
        fp = ModelFingerprint.from_dict(json.loads(fingerprint_path.read_text()))
        if fp.model == model:
            print(f"reusing fingerprint {fp.id} for {model} ({fingerprint_path})")
            return fp
        print(f"stored fingerprint at {fingerprint_path} is for {fp.model!r}, not {model!r} "
              f"-- re-probing")
    fp = probe_model(
        model,
        load_check=None if skip_load_check else _grounding_for_probe(hippo_schema, manifest),
    )
    fingerprint_path.parent.mkdir(parents=True, exist_ok=True)
    fingerprint_path.write_text(json.dumps(fp.to_dict(), indent=2) + "\n")
    print(f"wrote {fingerprint_path}")
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

    # new_run_dir() creates run_dir/{contexts,iterations}; an explicit --out never hit that path
    # and had no test/run exercising it end-to-end until the first real --auto-refine run (task
    # 8.4, previously blocked on a refiner credential) -- surfaced immediately as a crash on the
    # very first write.
    run_dir = Path(args.out) if args.out else new_run_dir()
    (run_dir / "contexts").mkdir(parents=True, exist_ok=True)
    (run_dir / "iterations").mkdir(parents=True, exist_ok=True)
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
    if args.compare and args.run:
        print("pass exactly one of --run/--compare", file=sys.stderr)
        return 1
    if args.compare:
        return _cmd_compare(args)
    if not args.run:
        print("pass exactly one of --run/--compare", file=sys.stderr)
        return 1
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


def _load_report_dict(path_str: str) -> dict:
    """A directory resolves to <dir>/report.json (a `run` output dir). Anything else is read
    directly as a file -- this also covers a `loop` run's iterations/iterNN.json, which is the
    same SuiteReport.to_dict() shape. `loop` dirs have no top-level report.json, so a bare loop
    dir is not auto-resolved -- point at the specific iteration file instead."""
    p = Path(path_str)
    if p.is_dir():
        candidate = p / "report.json"
        if not candidate.exists():
            raise FileNotFoundError(
                f"{p} has no report.json (a `loop` run dir has none -- point at a specific "
                f"iterations/iterNN.json file instead)"
            )
        p = candidate
    return json.loads(p.read_text())


def _samples_per_case(d: dict) -> int:
    return len(d["results"][0]["samples"]) if d["results"] else 0


def _split_counts(d: dict) -> tuple:
    return (
        sum(1 for r in d["results"] if r["split"] == "train"),
        sum(1 for r in d["results"] if r["split"] == "holdout"),
    )


def _compare_reports(paths: list) -> str:
    """Pure: reads already-written report.json-shaped files and renders them side by side plus
    deltas against the first. Raises ValueError/FileNotFoundError on bad input; never issues a
    model call."""
    if len(paths) < 2:
        raise ValueError("need at least 2 paths to compare")
    reports = [_load_report_dict(p) for p in paths]

    baseline_spc, baseline_splits = _samples_per_case(reports[0]), _split_counts(reports[0])
    warnings = []
    for d in reports[1:]:
        spc, splits = _samples_per_case(d), _split_counts(d)
        if spc != baseline_spc or splits != baseline_splits:
            warnings.append(
                f"WARNING: {d['model']!r} used samples-per-case={spc}, train/holdout "
                f"case counts={splits} vs the first report's samples-per-case={baseline_spc}, "
                f"case counts={baseline_splits} -- NOT a clean apples-to-apples comparison"
            )

    lines = list(warnings)
    base_scores = reports[0]["scores"]
    for i, d in enumerate(reports):
        s = d["scores"]
        n_train, n_holdout = _split_counts(d)
        lines.append(f"[{i}] model={d['model']}")
        lines.append(
            f"    protocol={d['protocol']}  context_version={d['context_version']}  "
            f"fingerprint={d['fingerprint_id']}  samples/case={_samples_per_case(d)}"
        )
        lines.append(
            f"    train={s['train']:.2f}  holdout={s['holdout']:.2f}  "
            f"strict_train={s['strict_train']}/{n_train}  "
            f"strict_holdout={s['strict_holdout']}/{n_holdout}  "
            f"flaky={s['flaky']}  tokens={s['total_tokens']}  "
            f"wall_clock_s={d['wall_clock_s']:.1f}"
        )
        if i > 0:
            lines.append(
                f"    Δtrain={s['train'] - base_scores['train']:+.2f}  "
                f"Δholdout={s['holdout'] - base_scores['holdout']:+.2f}  "
                f"Δstrict_train={s['strict_train'] - base_scores['strict_train']:+d}  "
                f"Δflaky={s['flaky'] - base_scores['flaky']:+d}  "
                f"(vs [0] {reports[0]['model']})"
            )

    protocols = {d["protocol"] for d in reports}
    if len(protocols) > 1:
        lines.append("")
        lines.append(
            f"NOTE: compared reports used different output protocols ({sorted(protocols)}) -- "
            "each model's protocol is chosen by its own capability probe, so a score delta "
            "above is model-AND-protocol jointly, not model alone."
        )

    return "\n".join(lines)


def _cmd_compare(args) -> int:
    if len(args.compare) < 2:
        print("--compare needs at least 2 paths", file=sys.stderr)
        return 1
    try:
        output = _compare_reports(args.compare)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(output)
    if args.out:
        Path(args.out).write_text(output + "\n")
        print(f"\nwrote {args.out}")
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

    rep = sub.add_parser("report", help="re-render a finished run, or compare finished runs")
    rep.add_argument("--run", default=None, help="re-render this one run dir (mutually "
                      "exclusive with --compare)")
    rep.add_argument("--compare", nargs="+", default=None,
                      help="2+ report.json paths (or run dirs containing one) to compare "
                           "side by side -- spends no new model calls")
    rep.add_argument("--out", default=None,
                      help="with --compare, also write the comparison table to this file")
    rep.set_defaults(fn=cmd_report)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
