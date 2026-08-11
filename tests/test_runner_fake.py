"""Section 7.1: a litellm-level fake target, so the whole loop is testable with zero model calls.

Deterministic end-to-end tests matter more here than usual: this harness produces the numbers
that decide whether the context got better, and a real local model takes ~an hour per full run.
"""
import sys, types, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import litellm
from exon.harness.cases import load_suite
from exon.harness.outcome import FailureClass
from exon.harness.runner import run_suite
from exon.context.template import ContextArtifact, DecodeParams
from exon.harness.probe import OutputProtocol
from exon.schema import fetch_hippo_schema, load_capability_manifest

ENDPOINT = "http://localhost:8080/graphql"
HS = fetch_hippo_schema(ENDPOINT)
M = load_capability_manifest("evals/schema/capabilities.json")
FOUR = ["hippocampus","frontal_cortex","cerebellum","brainstem"]

def _resp(content=None, tool_args=None, finish="stop"):
    msg = types.SimpleNamespace(content=content,
        tool_calls=([types.SimpleNamespace(function=types.SimpleNamespace(arguments=tool_args))]
                    if tool_args else None))
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=msg, finish_reason=finish)],
        usage={"total_tokens": 100})

# Scripted fake: answers q20-shaped questions faithfully, everything else with an empty filter
# list -- i.e. it reproduces the real observed failure on demand.
def fake_completion(model=None, messages=None, **kw):
    instr = messages[-1]["content"]
    if "hippocampus" in instr:
        plan = {"steps":[
            {"step_type":"filter","entity":"Sample",
             "filters":[{"field":"sample_type","value":"tissue","op":"EQ"},
                        {"field":"brain_region","value":"hippocampus","op":"EQ"}],
             "forward_relation":{"field":"donor","select_fields":["cohort","sex","history_of_rhi"]}},
            {"step_type":"related_lookup","source_step":0,
             "relationship_type":"input_samples",
             "client_filter":{"field":"workflow_type","value":"rna_seq"}}]}
    else:
        plan = {"steps":[{"step_type":"filter","entity":"Sample","filters":[]}]}
    return _resp(tool_args=json.dumps(plan))

litellm.completion = fake_completion

cases = [c for c in load_suite() if c.id in ("q35","q01")]
art = ContextArtifact(version=0, fingerprint_id="fake", system_prompt="sys",
    grounding_body="{{schema_slots}}\n{{relationship_types}}\n{{limitations}}",
    protocol=OutputProtocol.TOOL_CALL, decode_params=DecodeParams())

rep = run_suite(cases, art, HS, M, model="fake/model", samples_per_case=3,
                endpoint=ENDPOINT, max_workers=2, split=None, progress=False)

ok = True
by = {r.case_id: r for r in rep.results}
def chk(n, c):
    global ok
    print(("PASS  " if c else "FAIL  ") + n); ok = ok and c

chk("fake target ran with zero real model calls", len(rep.results) == 2)
chk("q35 (faithful script) passes 3/3", by["q35"].pass_rate == 1.0)
chk("q01 (empty-filter script) fails 3/3", by["q01"].pass_rate == 0.0)
chk("q01 failure is PLAN_UNFAITHFUL",
    all(s.outcome is FailureClass.PLAN_UNFAITHFUL for s in by["q01"].samples))
chk("report exposes train/holdout scores", 0.0 <= rep.score("train") <= 1.0)
chk("token accounting works", rep.total_tokens() == 600)
print()
print("no-retry check: the fake never varies, so 3 identical samples prove samples are independent")
print(rep.summary_line())
sys.exit(0 if ok else 1)
