"""Node [D]: pass failures to the refiner.

Not raw logs. The refiner's leverage comes from a classified, deduplicated, evidence-bearing
bundle -- and, critically, from being told **what has already been tried and did not work**. Each
context block records which failure codes it targets, so the bundle can show the blocks that were
supposed to prevent a failure that happened anyway. That turns refinement from guesswork into a
review of prior attempts.

Two withholdings are enforced here rather than trusted to the caller:

- **Holdout is never included.** `build_bundle` raises if handed a non-train grade. Convergence is
  judged on holdout, so leaking it would destroy the only evidence that a change generalises.
- **Environment failures are never included.** A num_ctx truncation is a configuration problem;
  handing it to a refiner invites it to reword prose that was never the cause.
"""
from dataclasses import dataclass, field

from .outcome import (
    CONTEXT_ADDRESSABLE,
    ENVIRONMENT_CLASSES,
    REMEDY_HINTS,
    FailureClass,
)

MAX_EXAMPLES_PER_CLASS = 3


class TriageError(Exception):
    pass


@dataclass
class FailureGroup:
    code: FailureClass
    count: int
    case_ids: list = field(default_factory=list)
    capabilities: list = field(default_factory=list)
    examples: list = field(default_factory=list)      # (case_id, instruction, detail, raw)
    blocks_that_should_have_prevented: list = field(default_factory=list)

    @property
    def remedy_hint(self) -> str:
        return REMEDY_HINTS.get(self.code, "")


@dataclass
class RefinerBundle:
    context_version: int
    protocol: str
    train_score: float
    strict_count: int
    total_train_cases: int
    groups: list = field(default_factory=list)
    score_history: list = field(default_factory=list)
    previous_iteration_blocks: list = field(default_factory=list)
    environment_warnings: list = field(default_factory=list)
    determinism_ceiling: float | None = None

    def is_empty(self) -> bool:
        return not self.groups

    def to_markdown(self, *, max_chars: int = 16000) -> str:
        """Exactly what the refiner receives. Trimming drops examples before dropping classes --
        losing a whole failure class is worse than losing one illustration of it."""
        out = [
            f"# Failure report for context v{self.context_version:03d}",
            "",
            f"- output protocol in use: `{self.protocol}`",
            f"- train score (mean pass rate): {self.train_score:.2f}",
            f"- cases passing all samples: {self.strict_count}/{self.total_train_cases}",
        ]
        if self.score_history:
            hist = ", ".join(f"v{v:03d}={s:.2f}" for v, s in self.score_history[-3:])
            out.append(f"- recent train scores: {hist}")
        if self.determinism_ceiling is not None and self.determinism_ceiling < 1.0:
            out.append(
                f"- NOTE: this model measured {self.determinism_ceiling:.0%} determinism at "
                f"temperature 0. That caps achievable reliability regardless of context; do not "
                f"try to fix nondeterminism with prose."
            )
        if self.environment_warnings:
            out.append(
                f"- {len(self.environment_warnings)} sample(s) failed for environment/config "
                f"reasons and are EXCLUDED below (not context problems)."
            )
        if self.previous_iteration_blocks:
            out += ["", "## Blocks added last iteration (judge whether they earned their place)"]
            for b in self.previous_iteration_blocks:
                out.append(
                    f"- `{b['id']}` ({b['kind']}) targeting {b.get('addresses_failures') or '[]'}"
                    f" -- {b.get('rationale','')[:160]}"
                )

        out += ["", "## Failures by class (most frequent first)"]
        for g in self.groups:
            out += [
                "",
                f"### {g.code.value} -- {g.count} sample(s)",
                f"- affected cases: {', '.join(sorted(set(g.case_ids)))}",
                f"- capabilities: {', '.join(sorted(set(g.capabilities)))}",
            ]
            if g.remedy_hint:
                out.append(f"- try first: {g.remedy_hint}")
            if g.blocks_that_should_have_prevented:
                out.append(
                    f"- ALREADY TRIED and did not prevent this: "
                    f"{', '.join('`'+b+'`' for b in g.blocks_that_should_have_prevented)}"
                )
            for cid, instr, detail, raw in g.examples[:MAX_EXAMPLES_PER_CLASS]:
                out += [
                    "",
                    f"  question: {instr}",
                    f"  what went wrong: {detail}",
                ]
                if raw:
                    out.append(f"  model output (truncated): {raw[:300]}")

        text = "\n".join(out)
        if len(text) <= max_chars:
            return text
        # Over budget: shed illustrations, never whole classes -- losing a failure class hides a
        # problem, while losing one example of it only costs detail.
        for keep in (2, 1):
            trimmed = RefinerBundle(
                context_version=self.context_version,
                protocol=self.protocol,
                train_score=self.train_score,
                strict_count=self.strict_count,
                total_train_cases=self.total_train_cases,
                groups=[
                    FailureGroup(
                        code=g.code, count=g.count, case_ids=g.case_ids,
                        capabilities=g.capabilities, examples=g.examples[:keep],
                        blocks_that_should_have_prevented=g.blocks_that_should_have_prevented,
                    )
                    for g in self.groups
                ],
                score_history=self.score_history,
                previous_iteration_blocks=self.previous_iteration_blocks,
                environment_warnings=self.environment_warnings,
                determinism_ceiling=self.determinism_ceiling,
            )
            text = trimmed.to_markdown(max_chars=10**9)
            if len(text) <= max_chars:
                return text
        return text[:max_chars]


def build_bundle(
    report,
    cases,
    artifact,
    *,
    score_history=None,
    determinism_ceiling: float | None = None,
) -> RefinerBundle:
    """Classify train-split failures into a bundle. Raises if handed holdout data."""
    case_by_id = {c.id: c for c in cases}

    leaked = [r.case_id for r in report.results if r.split != "train"]
    if leaked:
        raise TriageError(
            f"build_bundle received non-train grades for {leaked[:5]} -- the holdout split must "
            f"never reach the refiner, or it stops being evidence that a change generalises"
        )

    groups: dict[FailureClass, FailureGroup] = {}
    for r in report.results:
        for s in r.samples:
            if s.passed or s.outcome not in CONTEXT_ADDRESSABLE:
                continue
            g = groups.setdefault(s.outcome, FailureGroup(code=s.outcome, count=0))
            g.count += 1
            g.case_ids.append(r.case_id)
            g.capabilities.append(r.capability)
            if len(g.examples) < MAX_EXAMPLES_PER_CLASS:
                case = case_by_id.get(r.case_id)
                g.examples.append(
                    (
                        r.case_id,
                        case.instruction if case else "",
                        s.detail,
                        s.raw_content or "",
                    )
                )

    # Which enabled blocks claimed to address each class, and clearly did not.
    for code, g in groups.items():
        g.blocks_that_should_have_prevented = [
            b.id
            for b in artifact.blocks
            if b.enabled and code.value in (b.addresses_failures or [])
        ]

    env = [
        f"{r.case_id}/{s.sample_index}: {s.outcome.value}"
        for r in report.results
        for s in r.samples
        if s.outcome in ENVIRONMENT_CLASSES
    ]

    prev_blocks = [
        {
            "id": b.id,
            "kind": b.kind.value,
            "rationale": b.rationale,
            "addresses_failures": b.addresses_failures,
        }
        for b in artifact.blocks
        if b.introduced_in_iteration == max(
            [bb.introduced_in_iteration for bb in artifact.blocks] or [0]
        )
        and b.introduced_in_iteration > 0
    ]

    train_cases = [r for r in report.results if r.split == "train"]
    return RefinerBundle(
        context_version=artifact.version,
        protocol=artifact.protocol.value,
        train_score=report.score("train"),
        strict_count=report.strict_count("train"),
        total_train_cases=len(train_cases),
        groups=sorted(groups.values(), key=lambda g: -g.count),
        score_history=list(score_history or []),
        previous_iteration_blocks=prev_blocks,
        environment_warnings=env,
        determinism_ceiling=determinism_ceiling,
    )
