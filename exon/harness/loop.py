"""Node [F] and loop control.

    probe -> load suite -> [B] run -> [C] grade -> failures?
       no  -> done
       yes -> [D] triage -> [E] refine -> [B]

Three decisions that are not in the flowchart but without which the loop lies to you:

1. **The run returns the best HOLDOUT-scoring version, not the last.** Train score can be improved
   by memorising; holdout is the only evidence a change generalises.
2. **A revision that regresses holdout is rolled back** rather than built upon.
3. **Regression stop**: train rising while holdout falls, twice running, is a clean overfitting
   signature. Stop and say so loudly rather than continuing to "improve".

Everything is written to `runs/<ts>/` per iteration so a regression stays diffable afterwards, and
so a long local run (an hour is normal) can be resumed rather than restarted.
"""
import json
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..context.template import ContextArtifact
from .refine import RefineError, propose_context_revision
from .runner import run_suite
from .triage import build_bundle

RUNS_ROOT = Path("exon/harness/runs")


@dataclass
class LoopConfig:
    model: str
    samples_per_case: int = 5
    max_iterations: int = 10
    reliability_threshold: float = 0.8   # not 1.0 -- see design.md; perfection was never the goal
    plateau_iterations: int = 3
    regression_iterations: int = 2
    max_total_tokens: int | None = None
    endpoint: str = "http://localhost:8080/graphql"
    max_workers: int = 4
    auto_refine: bool = False            # default: report and stop
    max_template_chars: int = 12000


@dataclass
class LoopOutcome:
    best_artifact: ContextArtifact
    best_holdout: float
    baseline_holdout: float
    baseline_train: float
    reports: list = field(default_factory=list)
    stop_reason: str = ""
    run_dir: Path | None = None

    def improvement(self) -> float:
        return self.best_holdout - self.baseline_holdout


class _Interrupt:
    """SIGINT -> finish the current iteration, flush state, stop. A long local run that cannot be
    interrupted cleanly is a run people kill with -9 and lose."""

    def __init__(self):
        self.requested = False
        self._prev = None

    def __enter__(self):
        def handler(signum, frame):  # noqa: ARG001
            self.requested = True
            print("\n  interrupt received -- finishing this iteration, then stopping", flush=True)

        self._prev = signal.signal(signal.SIGINT, handler)
        return self

    def __exit__(self, *exc):
        signal.signal(signal.SIGINT, self._prev)
        return False


def new_run_dir(root: Path = RUNS_ROOT) -> Path:
    root = Path(root)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    d = root / stamp
    (d / "contexts").mkdir(parents=True, exist_ok=True)
    (d / "iterations").mkdir(parents=True, exist_ok=True)
    return d


def _persist(run_dir: Path, artifact, report, bundle=None, patch=None) -> None:
    it = report.iteration
    artifact_path = artifact.path_in(run_dir / "contexts")
    if not artifact_path.exists():
        artifact.save(run_dir / "contexts")
    (run_dir / "iterations" / f"iter{it:02d}.json").write_text(
        json.dumps(report.to_dict(), indent=2, default=str) + "\n"
    )
    if bundle is not None:
        (run_dir / "iterations" / f"iter{it:02d}-bundle.md").write_text(bundle.to_markdown())
    if patch is not None:
        (run_dir / "iterations" / f"iter{it:02d}-patch.json").write_text(
            json.dumps(
                {
                    "changelog": patch.changelog,
                    "hypothesis": patch.hypothesis,
                    "remove_block_ids": patch.remove_block_ids,
                    "added": [b.id for b in patch.add_blocks],
                    "modified": [b.id for b in patch.modify_blocks],
                    "protocol": patch.protocol.value if patch.protocol else None,
                    "decode_params": patch.decode_params.__dict__ if patch.decode_params else None,
                },
                indent=2,
            )
            + "\n"
        )


def run_refinement_loop(
    cases,
    seed: ContextArtifact,
    hippo_schema: dict,
    capability_manifest: dict,
    cfg: LoopConfig,
    *,
    fingerprint=None,
    run_dir: Path | None = None,
) -> LoopOutcome:
    run_dir = Path(run_dir) if run_dir else new_run_dir()
    train_cases = [c for c in cases if c.split == "train"]
    determinism = getattr(fingerprint, "determinism_at_temp_0", None)

    artifact = seed
    best = seed
    best_holdout = -1.0
    baseline_train = baseline_holdout = 0.0
    reports = []
    history = []
    plateau = regression = 0
    stop_reason = "max_iterations reached"

    print(f"run dir: {run_dir}")
    print(f"threshold: pass_rate >= {cfg.reliability_threshold} "
          f"({cfg.samples_per_case} samples/case)")

    with _Interrupt() as interrupt:
        for iteration in range(cfg.max_iterations):
            print(f"\n=== iteration {iteration} (context v{artifact.version:03d}) ===")
            report = run_suite(
                cases,
                artifact,
                hippo_schema,
                capability_manifest,
                model=cfg.model,
                samples_per_case=cfg.samples_per_case,
                endpoint=cfg.endpoint,
                max_workers=cfg.max_workers,
                iteration=iteration,
                progress=False,
            )
            reports.append(report)
            history.append((artifact.version, report.score("train")))
            print("  " + report.summary_line())

            train, holdout = report.score("train"), report.score("holdout")
            if iteration == 0:
                baseline_train, baseline_holdout = train, holdout

            if holdout > best_holdout:
                best_holdout, best = holdout, artifact
            else:
                # A revision that did not improve the only signal that matters is not kept.
                if iteration > 0:
                    print(f"  holdout did not improve ({holdout:.2f} <= {best_holdout:.2f}) "
                          f"-- rolling back to v{best.version:03d}")
                    artifact = best
                    plateau += 1

            env = report.environment_failures()
            if env:
                print(f"  NOTE: {len(env)} sample(s) failed for environment/config reasons "
                      f"(excluded from refinement): {env[:3]}")

            if not report.has_failures("train", cfg.reliability_threshold):
                stop_reason = "done -- no train failures at threshold"
                _persist(run_dir, artifact, report)
                break

            if iteration > 0 and train > history[-2][1] and holdout < best_holdout:
                regression += 1
                if regression >= cfg.regression_iterations:
                    stop_reason = (
                        "REGRESSION STOP -- train improved while holdout fell for "
                        f"{regression} consecutive iterations, a clean overfitting signature"
                    )
                    _persist(run_dir, artifact, report)
                    break
            else:
                regression = 0

            if plateau >= cfg.plateau_iterations:
                stop_reason = f"plateau -- no holdout improvement in {plateau} iterations"
                _persist(run_dir, artifact, report)
                break

            if cfg.max_total_tokens and report.total_tokens() and sum(
                r.total_tokens() for r in reports
            ) > cfg.max_total_tokens:
                stop_reason = "token budget exhausted"
                _persist(run_dir, artifact, report)
                break

            if interrupt.requested:
                stop_reason = "interrupted by operator"
                _persist(run_dir, artifact, report)
                break

            train_report = _train_only(report)
            bundle = build_bundle(
                train_report,
                train_cases,
                artifact,
                score_history=history,
                determinism_ceiling=determinism,
            )

            if not cfg.auto_refine:
                stop_reason = "report-only mode (--auto-refine not set)"
                _persist(run_dir, artifact, report, bundle=bundle)
                break

            if bundle.is_empty():
                stop_reason = "only environment/config failures remain -- not context-addressable"
                _persist(run_dir, artifact, report, bundle=bundle)
                break

            try:
                candidate, patch = propose_context_revision(
                    artifact, bundle, train_cases, iteration=iteration + 1
                )
            except RefineError as e:
                stop_reason = f"refinement rejected: {e}"
                _persist(run_dir, artifact, report, bundle=bundle)
                break

            _persist(run_dir, artifact, report, bundle=bundle, patch=patch)
            print(f"  patch v{artifact.version:03d} -> v{candidate.version:03d}: "
                  f"{patch.changelog[:110]}")
            artifact = candidate

    outcome = LoopOutcome(
        best_artifact=best,
        best_holdout=max(best_holdout, 0.0),
        baseline_holdout=baseline_holdout,
        baseline_train=baseline_train,
        reports=reports,
        stop_reason=stop_reason,
        run_dir=run_dir,
    )
    _write_report(run_dir, outcome, cfg)
    return outcome


def _train_only(report):
    """A shallow copy carrying only train grades -- build_bundle refuses anything else, and this is
    where that boundary is crossed deliberately and visibly."""
    from .outcome import SuiteReport

    return SuiteReport(
        context_version=report.context_version,
        fingerprint_id=report.fingerprint_id,
        model=report.model,
        protocol=report.protocol,
        results=[r for r in report.results if r.split == "train"],
        wall_clock_s=report.wall_clock_s,
        iteration=report.iteration,
    )


def _write_report(run_dir: Path, outcome: LoopOutcome, cfg: LoopConfig) -> None:
    lines = [
        "# Context tuning run",
        "",
        f"- model: `{cfg.model}`",
        f"- samples per case: {cfg.samples_per_case}",
        f"- reliability threshold: {cfg.reliability_threshold}",
        f"- stop reason: **{outcome.stop_reason}**",
        "",
        "## Per-iteration",
        "",
        "| iter | ctx | protocol | train | holdout | strict | flaky | tokens |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in outcome.reports:
        lines.append(
            f"| {r.iteration} | v{r.context_version:03d} | {r.protocol} | "
            f"{r.score('train'):.2f} | {r.score('holdout'):.2f} | "
            f"{r.strict_count('train')} | {r.flake_count()} | {r.total_tokens()} |"
        )
    lines += [
        "",
        "## Outcome",
        "",
        f"- baseline holdout: {outcome.baseline_holdout:.2f}",
        f"- best holdout: {outcome.best_holdout:.2f} (context v{outcome.best_artifact.version:03d})",
        f"- improvement: {outcome.improvement():+.2f}",
        "",
        "The returned context is the best holdout-scoring version, not the last one -- train score "
        "can be raised by memorising, so holdout is the only evidence a change generalises.",
    ]
    (run_dir / "report.md").write_text("\n".join(lines) + "\n")
    (run_dir / "best_context.json").write_text(
        json.dumps(outcome.best_artifact.to_dict(), indent=2) + "\n"
    )
