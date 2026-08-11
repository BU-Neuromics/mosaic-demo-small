"""Section 8.3: prove the target model's prompt is independent of everything but the context.

If the model could see an expectation, a case id, or a prior sample's output, then a rising score
would be evidence of leakage rather than of a better context -- and the whole loop would be
measuring itself. This asserts on the ACTUAL assembled prompt, captured at the litellm boundary,
rather than trusting the code to be written correctly.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import litellm

from exon.context.template import ContextArtifact, DecodeParams
from exon.harness.cases import load_suite
from exon.harness.probe import OutputProtocol
from exon.harness.runner import run_suite
from exon.schema import fetch_hippo_schema, load_capability_manifest

ENDPOINT = "http://localhost:8080/graphql"
HS = fetch_hippo_schema(ENDPOINT)
M = load_capability_manifest("evals/schema/capabilities.json")
CASES = load_suite()
failures = []
captured = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   [{extra}]" if extra and not cond else ""))
    if not cond:
        failures.append(name)


import types, json


def spy(model=None, messages=None, **kw):
    captured.append({"model": model, "messages": messages, "kwargs": kw})
    plan = {"steps": [{"step_type": "filter", "entity": "Donor",
                       "filters": [{"field": "cohort", "value": "case", "op": "EQ"}]}]}
    msg = types.SimpleNamespace(
        content=None,
        tool_calls=[types.SimpleNamespace(
            function=types.SimpleNamespace(arguments=json.dumps(plan)))])
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=msg, finish_reason="stop")],
        usage={"total_tokens": 10})


litellm.completion = spy

art = ContextArtifact(
    version=0, fingerprint_id="fp", system_prompt="You are Exon.",
    grounding_body="{{schema_slots}}\n{{relationship_types}}\n{{limitations}}",
    protocol=OutputProtocol.TOOL_CALL, decode_params=DecodeParams(temperature=0, seed=0))

subset = [c for c in CASES if c.id in ("q01", "q09", "q35", "q32")]
run_suite(subset, art, HS, M, model="fake/model", samples_per_case=2,
          endpoint=ENDPOINT, max_workers=1, progress=False)

check("every sample issued its own call", len(captured) == len(subset) * 2, str(len(captured)))

# 1. Single-turn: system + one user message. No assistant turns, so no history.
shapes = {tuple(m["role"] for m in c["messages"]) for c in captured}
check("every call is exactly (system, user) -- no conversation history",
      shapes == {("system", "user")}, str(shapes))

blob = json.dumps(captured)

# 2. No case ids reach the model.
leaked_ids = [c.id for c in CASES if f'"{c.id}"' in blob or f" {c.id} " in blob]
check("no case id appears in any prompt", not leaked_ids, str(leaked_ids))

# 3. No expectation content reaches the model.
leaked_exp = []
for c in subset:
    for s in c.steps:
        for f in s.required_filters:
            # the VALUE may legitimately appear (it's in the question); the expectation
            # STRUCTURE must not
            if "required_filters" in blob or "forbid_extra_filters" in blob:
                leaked_exp.append("expectation structure")
    if c.expect_rejection and c.rejection_reason and c.rejection_reason[:40] in blob:
        leaked_exp.append(f"{c.id} rejection_reason")
check("no expectation structure or rejection reason leaks", not leaked_exp, str(set(leaked_exp)))

# 4. No expected-results content reaches the model.
expected = json.loads(Path("evals/expected-results.json").read_text())
markers = []
for cid in ("q05", "q35", "q24"):
    e = expected.get(cid, {})
    for key in ("samples_with_rna_seq_workflow", "final_result", "call_count"):
        if key in e and str(e[key]) not in ("", "None") and f'"{key}"' in blob:
            markers.append(f"{cid}.{key}")
check("no expected-results content leaks", not markers, str(markers))

# 5. Samples of the same case are byte-identical -> nothing carried between them.
by_case = {}
for c in captured:
    key = c["messages"][1]["content"]
    by_case.setdefault(key, []).append(c)
check("repeated samples of a case send an identical prompt (no cross-sample state)",
      all(len({json.dumps(x["messages"]) for x in v}) == 1 for v in by_case.values()))

# 6. Decode params are provider-appropriate and deterministic settings are actually sent.
kw = captured[0]["kwargs"]
check("temperature/seed are passed through", kw.get("temperature") == 0 and kw.get("seed") == 0, str(kw))
check("num_ctx is NOT sent to a non-ollama provider", "num_ctx" not in kw, str(kw))

# 7. The only case-derived text is the instruction itself.
user = captured[0]["messages"][1]["content"]
q01 = next(c for c in CASES if c.id == "q01")
check("the instruction IS present (that's the input)", q01.instruction in user)

print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("all independence checks pass")
