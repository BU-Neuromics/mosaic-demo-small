"""Outcome taxonomy and reporting.

Every failure class here was observed in this project or is a direct consequence of a documented
platform limit -- none are invented for completeness.

The load-bearing distinction is **who can fix it**. A truncation caused by Ollama's num_ctx is not
a context problem, and handing it to the refiner invites it to reword prose that was never the
cause. Config and transport failures are therefore reported to the human and withheld from the
refiner's bundle.
"""
import statistics
from dataclasses import asdict, dataclass, field
from enum import Enum


class FailureClass(str, Enum):
    PASS = "pass"

    # --- not the context's fault: withheld from the refiner ---
    TRUNCATED = "truncated"                # finish_reason=length, nothing produced (num_ctx)
    PROVIDER_ERROR = "provider_error"      # auth/transport/model error
    HARNESS_ERROR = "harness_error"        # a bug here, not in the model

    # --- context-addressable ---
    NO_STRUCTURED_OUTPUT = "no_structured_output"  # ignored the protocol (prose/fences instead)
    UNPARSEABLE = "unparseable"                    # right protocol, malformed payload
    PLAN_INVALID = "plan_invalid"                  # validator rejected it
    PLAN_UNFAITHFUL = "plan_unfaithful"            # valid, but not what was asked  <-- the crux
    MISSING_REJECTION = "missing_rejection"        # should have refused, didn't
    EXEC_ERROR = "exec_error"                      # GraphQL error at execution
    RESULT_MISMATCH = "result_mismatch"            # ran, returned the wrong data


CONTEXT_ADDRESSABLE = frozenset(
    {
        FailureClass.NO_STRUCTURED_OUTPUT,
        FailureClass.UNPARSEABLE,
        FailureClass.PLAN_INVALID,
        FailureClass.PLAN_UNFAITHFUL,
        FailureClass.MISSING_REJECTION,
        FailureClass.EXEC_ERROR,
        FailureClass.RESULT_MISMATCH,
    }
)

ENVIRONMENT_CLASSES = frozenset(
    {FailureClass.TRUNCATED, FailureClass.PROVIDER_ERROR, FailureClass.HARNESS_ERROR}
)

# What a refiner should reach for first, per class. Included in the bundle because the single most
# common wrong move is answering a determinism or format problem with more prose.
REMEDY_HINTS = {
    FailureClass.NO_STRUCTURED_OUTPUT: (
        "protocol or decode change first (a stricter output protocol constrains decoding; prose "
        "instructions do not). Only then an OUTPUT_CONTRACT block."
    ),
    FailureClass.UNPARSEABLE: "protocol change, or an OUTPUT_CONTRACT block showing the exact shape.",
    FailureClass.PLAN_INVALID: "schema-presentation change so the valid names are unmissable.",
    FailureClass.PLAN_UNFAITHFUL: (
        "a CONSTRAINT block requiring every stated constraint to appear as a filter. This is a "
        "faithfulness failure, not a format one -- the plan was structurally fine."
    ),
    FailureClass.MISSING_REJECTION: (
        "a CONSTRAINT block naming the unsupported capability and requiring refusal instead of "
        "approximation."
    ),
    FailureClass.EXEC_ERROR: "schema-presentation or glossary change.",
    FailureClass.RESULT_MISMATCH: "glossary entry mapping the domain wording to the right field/value.",
}


@dataclass
class SampleResult:
    case_id: str
    sample_index: int
    outcome: FailureClass
    detail: str = ""
    plan_json: dict | None = None
    raw_content: str | None = None
    usage: dict | None = None
    latency_s: float = 0.0

    @property
    def passed(self) -> bool:
        return self.outcome is FailureClass.PASS

    def to_dict(self) -> dict:
        d = asdict(self)
        d["outcome"] = self.outcome.value
        return d


@dataclass
class CaseResult:
    case_id: str
    split: str
    capability: str
    samples: list = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return (sum(1 for s in self.samples if s.passed) / len(self.samples)) if self.samples else 0.0

    @property
    def is_flaky(self) -> bool:
        """Passed sometimes. Reported separately because the failures that motivated this harness
        were intermittent -- a single-sample suite would have called them green about half the
        time."""
        return 0.0 < self.pass_rate < 1.0

    @property
    def strict_pass(self) -> bool:
        return self.pass_rate == 1.0

    def outcome_counts(self) -> dict:
        counts = {}
        for s in self.samples:
            counts[s.outcome.value] = counts.get(s.outcome.value, 0) + 1
        return counts

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "split": self.split,
            "capability": self.capability,
            "pass_rate": self.pass_rate,
            "strict_pass": self.strict_pass,
            "is_flaky": self.is_flaky,
            "outcome_counts": self.outcome_counts(),
            "samples": [s.to_dict() for s in self.samples],
        }


@dataclass
class SuiteReport:
    context_version: int
    fingerprint_id: str
    model: str
    protocol: str
    results: list = field(default_factory=list)
    wall_clock_s: float = 0.0
    iteration: int = 0

    def _sel(self, split):
        return [r for r in self.results if split is None or r.split == split]

    def score(self, split: str | None = None) -> float:
        """Mean pass rate. Reported alongside strict_count, never instead of it -- the decision
        gate needs a boolean but an operator needs to see 0.2 -> 0.8 as progress."""
        rs = self._sel(split)
        return statistics.fmean(r.pass_rate for r in rs) if rs else 0.0

    def strict_count(self, split: str | None = None) -> int:
        return sum(1 for r in self._sel(split) if r.strict_pass)

    def flake_count(self, split: str | None = None) -> int:
        return sum(1 for r in self._sel(split) if r.is_flaky)

    def passing_cases(self, split=None, threshold: float = 1.0) -> int:
        return sum(1 for r in self._sel(split) if r.pass_rate >= threshold)

    def has_failures(self, split="train", threshold: float = 1.0) -> bool:
        """The decision diamond: 'are there failures?'"""
        return any(r.pass_rate < threshold for r in self._sel(split))

    def failures(self, *, split="train", addressable_only=True) -> list:
        out = []
        for r in self._sel(split):
            for s in r.samples:
                if s.passed:
                    continue
                if addressable_only and s.outcome not in CONTEXT_ADDRESSABLE:
                    continue
                out.append(s)
        return out

    def environment_failures(self, split=None) -> list:
        """Surfaced to the human, never to the refiner."""
        return [
            s
            for r in self._sel(split)
            for s in r.samples
            if s.outcome in ENVIRONMENT_CLASSES
        ]

    def total_tokens(self) -> int:
        return sum(
            (s.usage or {}).get("total_tokens", 0) or 0
            for r in self.results
            for s in r.samples
        )

    def summary_line(self, threshold: float = 1.0) -> str:
        return (
            f"iter {self.iteration:02d} v{self.context_version:03d} "
            f"proto={self.protocol:<11} "
            f"train={self.score('train'):.2f} holdout={self.score('holdout'):.2f} "
            f"strict={self.strict_count('train')}/{len(self._sel('train'))} "
            f"flaky={self.flake_count()} tokens={self.total_tokens()}"
        )

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "context_version": self.context_version,
            "fingerprint_id": self.fingerprint_id,
            "model": self.model,
            "protocol": self.protocol,
            "wall_clock_s": self.wall_clock_s,
            "scores": {
                "train": self.score("train"),
                "holdout": self.score("holdout"),
                "strict_train": self.strict_count("train"),
                "strict_holdout": self.strict_count("holdout"),
                "flaky": self.flake_count(),
                "total_tokens": self.total_tokens(),
            },
            "results": [r.to_dict() for r in self.results],
        }
