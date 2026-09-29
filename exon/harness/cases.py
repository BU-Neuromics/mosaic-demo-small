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
class CriterionExpectation:
    """One `kind: field` condition the spec must carry.

    `op` mirrors the QuerySpec vocabulary (lowercase `eq`/`gt`/`in`/...), not the old
    QueryPlan FilterOp enum — the artifacts spell operators differently and silently
    accepting either would hide a real emitter mistake.
    """

    slot: str
    value: object
    op: str = "eq"


@dataclass(frozen=True)
class RelatedExpectation:
    """One `kind: related` condition: an edge, a quantifier, and conditions on the SAME
    related record.

    A QuerySpec expresses as one `related` criterion what a QueryPlan expressed as a
    second `related_lookup` step chained by `source_step`. That is why the two
    expectation shapes cannot be compared structurally (2.5a) — same question, different
    arity, and a structural diff would report every relationship case as a regression.
    """

    edge: str
    quantifier: str = "some"
    criteria: tuple = ()


@dataclass(frozen=True)
class SpecExpectation:
    """What a correct `QuerySpec` for this question asserts.

    Deliberately not a mirror of `StepExpectation`. It describes ONE artifact, and it adds
    `result_shape`, which has no QueryPlan equivalent: a question asking for grouped counts
    is not answerable by any row query, so "which tool should this have gone to" becomes a
    gradeable property rather than an unstated assumption (2.5c).
    """

    anchor: str | None = None
    required_criteria: tuple = ()
    required_related: tuple = ()
    forbid_extra_criteria: bool = True
    #: rows | facet | range | search — what shape of answer the instruction asks for.
    #: Anything but `rows` means a row query is a silent degradation, however valid.
    result_shape: str = "rows"


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
    #: The QuerySpec-shaped expectation. Present alongside `steps` during the port so the
    #: suite grades both artifacts against the same questions and the before/after the
    #: harness exists to provide is not lost mid-migration (the pattern task 2.2 used for
    #: the emitter itself).
    spec: object = None

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


def _criterion_exp(d: dict) -> CriterionExpectation:
    return CriterionExpectation(slot=d["slot"], value=d.get("value"), op=d.get("op", "eq"))


def _related_exp(d: dict) -> RelatedExpectation:
    return RelatedExpectation(
        edge=d["edge"],
        quantifier=d.get("quantifier", "some"),
        criteria=tuple(_criterion_exp(c) for c in d.get("criteria", [])),
    )


_RESULT_SHAPES = {"rows", "facet", "range", "search"}


def _spec_exp(d: dict, cid: str) -> SpecExpectation:
    shape = d.get("result_shape", "rows")
    if shape not in _RESULT_SHAPES:
        raise SuiteError(
            f"expectation {cid!r}: result_shape {shape!r} is not one of "
            f"{sorted(_RESULT_SHAPES)}"
        )
    return SpecExpectation(
        anchor=d.get("anchor"),
        required_criteria=tuple(_criterion_exp(c) for c in d.get("required_criteria", [])),
        required_related=tuple(_related_exp(r) for r in d.get("required_related", [])),
        forbid_extra_criteria=d.get("forbid_extra_criteria", True),
        result_shape=shape,
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
        if not e.get("expect_rejection") and not e.get("steps") and not e.get("spec"):
            raise SuiteError(
                f"expectation {cid!r} has neither steps, spec, nor expect_rejection -- it "
                f"asserts nothing"
            )
        cases.append(
            TestCase(
                id=cid,
                instruction=q["question"],
                question_capability=q.get("capability", "unknown"),
                steps=tuple(_step_exp(s) for s in e.get("steps", [])),
                spec=_spec_exp(e["spec"], cid) if e.get("spec") else None,
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
