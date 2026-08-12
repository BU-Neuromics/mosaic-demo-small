"""Node [C]: evaluate.

Tier ladder, first failure stops that sample:

  0  a structured answer was produced at all (the protocol was honoured)
  1  the plan parses into typed ops
  2  the validator accepts it against the LIVE schema and capability manifest
  3  it is FAITHFUL to the instruction -- required constraints present, none silently added
  4  (tagged cases only) executed, it returns the expected data

Tier 3 is the whole reason this module exists. The validator answers "is this plan safe and
executable"; it cannot answer "does this plan represent what was asked". Those are different
questions, and the observed failure -- a structurally valid plan with an empty filter list that
had silently dropped every stated constraint -- passes the first and fails the second.

Comparison is on semantics, never spelling: field names resolve through hippoSchema so
`sample_type` and `sampleType` are the same assertion. Failing a correct plan on cosmetics is the
most likely way to waste a week chasing ghosts.
"""
from ..ops import FilterStep, RelatedLookupStep
from ..validator import ValidationError, resolve_field, validate_plan
from .outcome import FailureClass, SampleResult


def _canon(hippo_schema: dict, entity: str | None, name: str) -> str:
    """Canonical slot name, or the input unchanged when it can't be resolved (the validator will
    already have rejected a genuinely unknown name, so this only normalises spelling)."""
    fields = (hippo_schema.get(entity) or {}).get("fields", {}) if entity else {}
    return resolve_field(fields, name) or name


def _values_equal(expected, actual) -> bool:
    """Order-insensitive for IN lists, exact otherwise. A planner listing four brain regions in a
    different order has not made a mistake."""
    if isinstance(expected, (list, tuple)) and isinstance(actual, (list, tuple)):
        return sorted(map(str, expected)) == sorted(map(str, actual))
    return str(expected) == str(actual)


def check_faithfulness(plan, case, hippo_schema: dict) -> tuple:
    """-> (ok, detail). `detail` names the specific defect, because that string is what the
    refiner reasons over -- vagueness here directly degrades the loop."""
    exp_steps = case.steps
    if len(plan.steps) < len(exp_steps):
        return False, (
            f"plan has {len(plan.steps)} step(s) but the question needs {len(exp_steps)}: "
            f"{_describe_missing(plan, exp_steps)}"
        )

    for i, exp in enumerate(exp_steps):
        got = plan.steps[i]

        if exp.step_type == "filter":
            if not isinstance(got, FilterStep):
                return False, f"step {i}: expected a filter step, got {type(got).__name__}"
            if exp.entity and got.entity != exp.entity:
                return False, (
                    f"step {i}: queries {got.entity!r} but the question is about {exp.entity!r}"
                )

            actual = {
                _canon(hippo_schema, got.entity, f.field): (f.value, f.op) for f in got.filters
            }
            for rf in exp.required_filters:
                slot = _canon(hippo_schema, exp.entity, rf.field)
                if slot not in actual:
                    return False, (
                        f"step {i}: missing required filter {slot}={rf.value!r} -- the "
                        f"instruction states this constraint and the plan drops it "
                        f"(present filters: {sorted(actual) or 'none'})"
                    )
                val, op = actual[slot]
                if not _values_equal(rf.value, val):
                    return False, (
                        f"step {i}: filter {slot} has value {val!r} but the instruction says "
                        f"{rf.value!r}"
                    )
                if op != rf.op:
                    return False, (
                        f"step {i}: filter {slot} uses op {op!r}; {rf.op!r} is required to "
                        f"match the instruction"
                    )

            if exp.forbid_extra_filters:
                required = {
                    _canon(hippo_schema, exp.entity, rf.field) for rf in exp.required_filters
                }
                extra = sorted(set(actual) - required)
                if extra:
                    return False, (
                        f"step {i}: adds filter(s) {extra} the instruction never asked for -- "
                        f"over-filtering answers a narrower question than the one posed"
                    )

            for want in exp.select_fields_include:
                slot = _canon(hippo_schema, got.entity, want)
                have = {_canon(hippo_schema, got.entity, s) for s in got.select_fields}
                if slot not in have:
                    return False, (
                        f"step {i}: does not select {slot!r}, which the question asks about"
                    )

            if exp.required_forward_relation:
                fr = got.forward_relation or {}
                want_rel = _canon(hippo_schema, exp.entity, exp.required_forward_relation)
                got_rel = _canon(hippo_schema, exp.entity, fr.get("field", "")) if fr else ""
                if got_rel != want_rel:
                    return False, (
                        f"step {i}: the question asks for the related {want_rel!r} record's "
                        f"attributes, but the plan resolves {got_rel or 'no'} forward relation"
                    )
                target = (
                    (hippo_schema.get(exp.entity) or {})
                    .get("fields", {})
                    .get(want_rel, {})
                    .get("targetEntityType")
                )
                have = {
                    _canon(hippo_schema, target, s) for s in fr.get("select_fields", []) or []
                }
                for want in exp.required_forward_select:
                    slot = _canon(hippo_schema, target, want)
                    if slot not in have:
                        return False, (
                            f"step {i}: forward relation {want_rel!r} does not select {slot!r}, "
                            f"which the instruction asks for"
                        )

        elif exp.step_type == "related_lookup":
            if not isinstance(got, RelatedLookupStep):
                return False, (
                    f"step {i}: expected a bounded reverse lookup, got "
                    f"{type(got).__name__} -- the question asks what references an "
                    f"already-identified entity"
                )
            if exp.relationship_type and got.relationship_type != exp.relationship_type:
                return False, (
                    f"step {i}: relationship_type is {got.relationship_type!r}, expected "
                    f"{exp.relationship_type!r} (it must be the multivalued-reference slot name)"
                )
            if exp.source_step is not None and got.source_step != exp.source_step:
                return False, (
                    f"step {i}: scoped to step {got.source_step} but should follow step "
                    f"{exp.source_step}"
                )
            if exp.required_client_filter:
                cf = got.client_filter
                if cf is None:
                    return False, (
                        f"step {i}: missing the client-side narrowing "
                        f"{exp.required_client_filter.field}="
                        f"{exp.required_client_filter.value!r}; without it the lookup returns "
                        f"every referencing entity, not the ones asked for"
                    )
                if not _values_equal(exp.required_client_filter.value, cf.value) or _canon(
                    hippo_schema, None, cf.field
                ) != exp.required_client_filter.field:
                    return False, (
                        f"step {i}: client filter is {cf.field}={cf.value!r}, expected "
                        f"{exp.required_client_filter.field}="
                        f"{exp.required_client_filter.value!r}"
                    )
        else:
            return False, f"step {i}: unknown expected step_type {exp.step_type!r}"

    if len(plan.steps) > len(exp_steps):
        extra = [type(s).__name__ for s in plan.steps[len(exp_steps):]]
        return False, (
            f"plan has {len(plan.steps) - len(exp_steps)} extra step(s) {extra} beyond what the "
            f"question requires"
        )
    return True, ""


def _describe_missing(plan, exp_steps) -> str:
    kinds = [s.step_type for s in exp_steps]
    got = ["filter" if isinstance(s, FilterStep) else "related_lookup" for s in plan.steps]
    return f"expected {kinds}, got {got}"


def _truncation_detail(attempt) -> str:
    """Name the limit that ACTUALLY bound, not the one that usually does.

    There are two independent ceilings and they fail identically (finish_reason=length), so a
    generic "raise num_ctx" message sends people to change the wrong number. Measured on the
    first real baseline: completion_tokens hit exactly 8192 (max_tokens) while total_tokens was
    8932, nowhere near num_ctx=32768 -- the binding limit was the completion budget, and the
    original message said the opposite.
    """
    usage = attempt.usage or {}
    completion = usage.get("completion_tokens")
    total = usage.get("total_tokens")
    parts = ["finish_reason=length with no plan produced"]
    if completion:
        parts.append(f"completion_tokens={completion}")
    if total:
        parts.append(f"total_tokens={total}")
    parts.append(
        "raise EXON_MAX_TOKENS if completion_tokens is at the ceiling (the model spent its whole "
        "budget reasoning); raise EXON_OLLAMA_NUM_CTX if total_tokens is near num_ctx, since "
        "Ollama counts prompt+completion together"
    )
    parts.append(
        "either way this is a configuration limit, not something context wording can fix"
    )
    return " -- ".join(parts)


def grade_sample(
    attempt,
    case,
    sample_index: int,
    hippo_schema: dict,
    capability_manifest: dict,
    *,
    endpoint: str | None = None,
    expected_results: dict | None = None,
) -> SampleResult:
    """Run one attempt through the tier ladder."""
    base = dict(
        case_id=case.id,
        sample_index=sample_index,
        raw_content=(attempt.raw_content or "")[:2000],
        usage=attempt.usage,
        latency_s=attempt.latency_s,
        plan_json=None,
    )

    # --- environment, not context ---
    if attempt.error:
        return SampleResult(outcome=FailureClass.PROVIDER_ERROR, detail=attempt.error, **base)
    if attempt.truncated:
        return SampleResult(
            outcome=FailureClass.TRUNCATED,
            detail=_truncation_detail(attempt),
            **base,
        )

    # --- tier 0: did the protocol hold? ---
    if not attempt.structured_arguments:
        return SampleResult(
            outcome=FailureClass.NO_STRUCTURED_OUTPUT,
            detail=(
                f"no structured payload via protocol={attempt.protocol!r}; the model replied "
                f"with free text instead. NOTE: the harness deliberately does not parse that "
                f"text -- doing so would hide the failure."
            ),
            **base,
        )

    # --- tier 1: does it parse into typed ops? ---
    if attempt.plan is None:
        return SampleResult(
            outcome=FailureClass.UNPARSEABLE,
            detail=attempt.parse_error or "payload did not parse into a plan",
            **base,
        )
    base["plan_json"] = _plan_to_dict(attempt.plan)

    # --- tier 2: validator ---
    try:
        validate_plan(attempt.plan, hippo_schema, capability_manifest)
        rejected = None
    except ValidationError as e:
        rejected = str(e)

    if not case.expects_plan:
        # Refusing IS the correct answer here.
        if rejected:
            return SampleResult(outcome=FailureClass.PASS, detail=f"correctly rejected: {rejected}", **base)
        return SampleResult(
            outcome=FailureClass.MISSING_REJECTION,
            detail=(
                f"produced an accepted plan for a question that cannot be answered: "
                f"{case.rejection_reason.strip() or case.expect_rejection}"
            ),
            **base,
        )

    if rejected:
        return SampleResult(outcome=FailureClass.PLAN_INVALID, detail=rejected, **base)

    # --- tier 3: faithfulness ---
    ok, detail = check_faithfulness(attempt.plan, case, hippo_schema)
    if not ok:
        return SampleResult(outcome=FailureClass.PLAN_UNFAITHFUL, detail=detail, **base)

    # --- tier 4: execution (tagged cases only) ---
    if case.execute and endpoint:
        from ..executor import execute_plan

        try:
            result = execute_plan(attempt.plan, endpoint, hippo_schema)
        except Exception as e:  # noqa: BLE001 - any execution failure is a graded outcome
            return SampleResult(
                outcome=FailureClass.EXEC_ERROR, detail=f"{type(e).__name__}: {e}", **base
            )
        mismatch = _compare_expected(case.id, result, expected_results)
        if mismatch:
            return SampleResult(outcome=FailureClass.RESULT_MISMATCH, detail=mismatch, **base)

    return SampleResult(outcome=FailureClass.PASS, **base)


def _plan_to_dict(plan) -> dict:
    steps = []
    for s in plan.steps:
        if isinstance(s, FilterStep):
            steps.append(
                {
                    "step_type": "filter",
                    "entity": s.entity,
                    "filters": [
                        {"field": f.field, "value": f.value, "op": f.op} for f in s.filters
                    ],
                    "filter_mode": s.filter_mode,
                    "select_fields": list(s.select_fields),
                    "forward_relation": s.forward_relation,
                    "limit": s.limit,
                }
            )
        else:
            cf = s.client_filter
            steps.append(
                {
                    "step_type": "related_lookup",
                    "source_step": s.source_step,
                    "relationship_type": s.relationship_type,
                    "client_filter": (
                        {"field": cf.field, "value": cf.value, "op": cf.op} if cf else None
                    ),
                }
            )
    return {"steps": steps}


def _compare_expected(case_id: str, result: dict, expected_results: dict | None) -> str:
    """Compare an executed plan against the benchmark's recorded answer.

    Compares each stage against the figure that actually describes it: the filter step's `total`
    against the recorded response total, and a reverse-lookup step's match count against the
    recorded number of entities that matched. Comparing the wrong stage's number was a real bug
    here -- for a two-step plan the LAST step is the lookup, so checking its 9 matches against
    the 26-sample total reported a mismatch for a completely correct plan.

    Deliberately conservative: silent when the benchmark records no comparable figure. Inventing
    a stricter comparison than the recorded data supports would manufacture failures, which for a
    tuning loop is worse than checking nothing.
    """
    if not expected_results:
        return ""
    exp = expected_results.get(case_id)
    if not isinstance(exp, dict) or exp.get("status") != "ok":
        return ""

    steps = result.get("steps") or {}
    problems = []

    # Stage 1: the filtered record count.
    expected_total = None
    resp = exp.get("response")
    if isinstance(resp, dict):
        for v in resp.values():
            if isinstance(v, dict) and "total" in v:
                expected_total = v["total"]
                break
    first = steps.get(0) if isinstance(steps, dict) else None
    if expected_total is not None and isinstance(first, dict) and "total" in first:
        if int(first["total"]) != int(expected_total):
            problems.append(
                f"filter step returned {first['total']} record(s), benchmark says "
                f"{expected_total}"
            )

    # Stage 2: how many entities the bounded reverse lookup actually matched.
    expected_matches = exp.get("samples_with_rna_seq_workflow")
    lookup = next(
        (v for v in (steps.values() if isinstance(steps, dict) else []) if isinstance(v, dict) and "matches" in v),
        None,
    )
    if expected_matches is not None and lookup is not None:
        got = len(lookup["matches"])
        if int(got) != int(expected_matches):
            problems.append(
                f"reverse lookup matched {got} entity/entities, benchmark says "
                f"{expected_matches}"
            )

    return "; ".join(problems)
