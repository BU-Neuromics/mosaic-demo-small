"""Node [B]: execute the suite against the target, with an editable context.

Three rules, each load-bearing:

1. **k samples per case.** The problem is unreliability, not wrongness -- the same input does not
   yield the same quality of output. Running each case once measures correctness and calls it
   reliability. Running it k times measures the distribution.

2. **No retries inside the runner.** A retry hides exactly the unreliability being measured.
   (`plan_query` retries, deliberately, because a user asking a question wants an answer; the
   runner uses `request_plan`, which does not.) Transport errors are a different thing and *are*
   retried, then recorded rather than graded.

3. **Every sample is an independent, stateless single-turn call.** No conversation history, no
   prior plan, no expectation, no case id, no expected result ever reaches the model. The model's
   only knowledge of this schema is the injected context -- otherwise a rising score would measure
   memorisation rather than context quality, and the loop would be deceiving itself.
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import openai

from ..planner import request_plan
from .cases import split_cases
from .grading import grade_sample
from .outcome import CaseResult, FailureClass, SampleResult, SuiteReport

TRANSPORT_RETRIES = 3


def _load_expected_results(path="evals/expected-results.json") -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _is_transport(err: str) -> bool:
    """Connection-level trouble, distinct from the model producing a bad answer. Retrying this
    does not hide unreliability; retrying a generation would."""
    needles = ("APIConnectionError", "Timeout", "ServiceUnavailable", "InternalServerError",
               "connection", "timed out")
    return any(n.lower() in err.lower() for n in needles)


def _one_sample(case, index, ctx, hippo_schema, manifest, cfg) -> SampleResult:
    attempt = None
    for tri in range(TRANSPORT_RETRIES):
        attempt = request_plan(
            case.instruction,           # the ONLY case-derived text the model ever sees
            hippo_schema,
            manifest,
            model=cfg["model"],
            context=ctx,
            protocol=cfg["protocol"],
            decode_kwargs=cfg["decode_kwargs"],
            max_tokens=cfg["max_tokens"],
        )
        if not (attempt.error and _is_transport(attempt.error)):
            break
        if tri < TRANSPORT_RETRIES - 1:
            time.sleep(2 * (tri + 1))
    try:
        return grade_sample(
            attempt,
            case,
            index,
            hippo_schema,
            manifest,
            endpoint=cfg["endpoint"],
            expected_results=cfg["expected_results"],
        )
    except Exception as e:  # noqa: BLE001 - a harness bug must not be scored as a model failure
        return SampleResult(
            case_id=case.id,
            sample_index=index,
            outcome=FailureClass.HARNESS_ERROR,
            detail=f"{type(e).__name__}: {e}",
        )


def run_suite(
    cases,
    artifact,
    hippo_schema: dict,
    capability_manifest: dict,
    *,
    model: str,
    samples_per_case: int = 5,
    endpoint: str = "http://localhost:8080/graphql",
    max_workers: int = 4,
    split: str | None = None,
    max_tokens: int | None = None,
    expected_results: dict | None = None,
    iteration: int = 0,
    progress: bool = True,
) -> SuiteReport:
    """Run every selected case `samples_per_case` times against the rendered context."""
    selected = split_cases(cases, split)
    system_prompt, grounding = artifact.render(hippo_schema, capability_manifest)
    ctx = (system_prompt, grounding)

    cfg = {
        "model": model,
        "protocol": artifact.protocol.value,
        "decode_kwargs": artifact.decode_params.to_litellm_kwargs(model),
        "endpoint": endpoint,
        "max_tokens": max_tokens,
        "expected_results": (
            expected_results if expected_results is not None else _load_expected_results()
        ),
    }

    started = time.monotonic()
    buckets = {c.id: [] for c in selected}
    jobs = [(c, i) for c in selected for i in range(samples_per_case)]
    done = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_one_sample, c, i, ctx, hippo_schema, capability_manifest, cfg): (c, i)
            for c, i in jobs
        }
        for fut in as_completed(futures):
            case, _ = futures[fut]
            result = fut.result()
            buckets[case.id].append(result)
            done += 1
            if progress:
                print(
                    f"  [{done}/{len(jobs)}] {case.id} sample {result.sample_index}: "
                    f"{result.outcome.value}",
                    flush=True,
                )

    results = [
        CaseResult(
            case_id=c.id,
            split=c.split,
            capability=c.question_capability,
            samples=sorted(buckets[c.id], key=lambda s: s.sample_index),
        )
        for c in selected
    ]
    return SuiteReport(
        context_version=artifact.version,
        fingerprint_id=artifact.fingerprint_id,
        model=model,
        protocol=artifact.protocol.value,
        results=results,
        wall_clock_s=time.monotonic() - started,
        iteration=iteration,
    )
