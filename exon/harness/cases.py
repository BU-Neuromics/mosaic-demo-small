"""Node [A]: the test suite.

The natural-language questions are NOT authored here. They come from `evals/questions.yaml`,
already curated and with expected results that were actually executed against live data, and are
joined by id to plan-level expectations in `evals/plan-expectations.yaml`. Authoring fresh
questions would discard that verification, and a wrong test is worse than no test -- the loop
would happily tune the context toward it.

Expectations assert query *semantics*, never spelling: field names resolve through hippoSchema, so
`sample_type` and `sampleType` satisfy the same expectation (both are accepted upstream since
mosaic#149/PR#150). Failing a correct plan on cosmetics is the most likely way to send the refiner
chasing ghosts.
"""
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class SuiteError(Exception):
    pass


@dataclass(frozen=True)
class FilterExpectation:
    field: str
    value: object
    op: str = "EQ"


@dataclass(frozen=True)
class StepExpectation:
    step_type: str                                   # "filter" | "related_lookup"
    entity: str | None = None
    required_filters: tuple = ()
    forbid_extra_filters: bool = True
    select_fields_include: tuple = ()
    required_forward_relation: str | None = None
    required_forward_select: tuple = ()
    relationship_type: str | None = None
    required_client_filter: FilterExpectation | None = None
    source_step: int | None = None


@dataclass(frozen=True)
class TestCase:
    id: str
    instruction: str                 # verbatim from questions.yaml
    question_capability: str         # the benchmark's own tag, for stratification/reporting
    steps: tuple = ()
    expect_rejection: str | None = None
    rejection_reason: str = ""
    execute: bool = False
    split: str = "train"
    tags: tuple = ()

    @property
    def expects_plan(self) -> bool:
        return self.expect_rejection is None


def _filter_exp(d: dict) -> FilterExpectation:
    return FilterExpectation(field=d["field"], value=d["value"], op=d.get("op", "EQ"))


def _step_exp(d: dict) -> StepExpectation:
    cf = d.get("required_client_filter")
    return StepExpectation(
        step_type=d["step_type"],
        entity=d.get("entity"),
        required_filters=tuple(_filter_exp(f) for f in d.get("required_filters", [])),
        forbid_extra_filters=d.get("forbid_extra_filters", True),
        select_fields_include=tuple(d.get("select_fields_include", [])),
        required_forward_relation=d.get("required_forward_relation"),
        required_forward_select=tuple(d.get("required_forward_select", [])),
        relationship_type=d.get("relationship_type"),
        required_client_filter=_filter_exp(cf) if cf else None,
        source_step=d.get("source_step"),
    )


def load_suite(
    questions_yaml: str | Path = "evals/questions.yaml",
    expectations_yaml: str | Path = "evals/plan-expectations.yaml",
) -> list:
    """Join expectations onto questions by id.

    Raises on drift in either direction that matters: an expectation naming an unknown question is
    a hard error (the file has gone stale), while a question with no expectation is a deliberate
    scope exclusion and is simply not part of the suite.
    """
    questions = {q["id"]: q for q in yaml.safe_load(Path(questions_yaml).read_text())}
    expectations = yaml.safe_load(Path(expectations_yaml).read_text())

    seen = set()
    cases = []
    for e in expectations:
        cid = e["id"]
        if cid in seen:
            raise SuiteError(f"duplicate expectation id {cid!r}")
        seen.add(cid)
        q = questions.get(cid)
        if q is None:
            raise SuiteError(
                f"expectation {cid!r} names a question that does not exist in "
                f"{questions_yaml} -- the files have drifted apart"
            )
        if not e.get("expect_rejection") and not e.get("steps"):
            raise SuiteError(
                f"expectation {cid!r} has neither steps nor expect_rejection -- it asserts "
                f"nothing"
            )
        cases.append(
            TestCase(
                id=cid,
                instruction=q["question"],
                question_capability=q.get("capability", "unknown"),
                steps=tuple(_step_exp(s) for s in e.get("steps", [])),
                expect_rejection=e.get("expect_rejection"),
                rejection_reason=e.get("rejection_reason", ""),
                execute=bool(e.get("execute")),
                split=e.get("split", "train"),
                tags=tuple(e.get("tags", [])) or (q.get("category", ""),),
            )
        )
    bad_splits = {c.split for c in cases} - {"train", "holdout"}
    if bad_splits:
        raise SuiteError(f"unknown split(s): {sorted(bad_splits)}")
    return cases


def split_cases(cases: list, split: str | None) -> list:
    return [c for c in cases if split is None or c.split == split]
