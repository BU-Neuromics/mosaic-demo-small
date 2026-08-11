"""Grader golden set. The harness is the measuring instrument -- if it is wrong, every number it
produces is noise. No LLM calls here, so this is the fast regression test.

The two anchor cases are REAL plans captured from ollama_chat/gemma4:12b during development:
the faithful one, and the one that silently dropped every stated constraint. If the grader ever
stops distinguishing them, the harness has lost the only thing it was built to detect.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from exon.harness.cases import load_suite
from exon.harness.grading import check_faithfulness, grade_sample
from exon.harness.outcome import FailureClass
from exon.ops import FieldFilter, FilterStep, QueryPlan, RelatedLookupStep
from exon.planner import PlanAttempt
from exon.schema import fetch_hippo_schema, load_capability_manifest

ENDPOINT = "http://localhost:8080/graphql"
HS = fetch_hippo_schema(ENDPOINT)
MANIFEST = load_capability_manifest("evals/schema/capabilities.json")
CASES = {c.id: c for c in load_suite()}

FOUR_REGIONS = ["hippocampus", "frontal_cortex", "cerebellum", "brainstem"]
failures = []


def check(name, condition, extra=""):
    print(("PASS  " if condition else "FAIL  ") + name + (f"  [{extra}]" if extra and not condition else ""))
    if not condition:
        failures.append(name)


def attempt_for(plan):
    return PlanAttempt(protocol="tool_call", plan=plan, structured_arguments="{}")


def graded(plan, case_id, **kw):
    return grade_sample(attempt_for(plan), CASES[case_id], 0, HS, MANIFEST, **kw)


# ---- anchor 1: the REAL faithful plan (q20 / the driving example) -------------------------
faithful = QueryPlan("driving example", [
    FilterStep(entity="Sample",
               filters=[FieldFilter("sample_type", "tissue"),
                        FieldFilter("brain_region", FOUR_REGIONS, "IN")],
               select_fields=["name", "brain_region"],
               forward_relation={"field": "donor",
                                 "select_fields": ["cohort", "sex", "history_of_rhi"]}),
])
r = graded(faithful, "q20")
check("faithful driving-example plan passes", r.outcome is FailureClass.PASS, r.detail)

# ---- anchor 2: the REAL unfaithful plan -- filters: [] ------------------------------------
# Captured verbatim: structurally valid, validator accepts it, silently answers a different
# question. This is the failure the validator cannot catch and tier 3 exists for.
dropped = QueryPlan("driving example", [
    FilterStep(entity="Sample", filters=[], select_fields=["name", "accession"],
               forward_relation={"field": "donor",
                                 "select_fields": ["cohort", "sex", "history_of_rhi"]}),
])
r = graded(dropped, "q20")
check("dropped-filter plan is PLAN_UNFAITHFUL", r.outcome is FailureClass.PLAN_UNFAITHFUL, r.outcome.value)
check("...and names the missing filter", "missing required filter" in r.detail, r.detail[:90])

# ---- spelling must NOT matter (post-#150 both forms are valid) ----------------------------
camel = QueryPlan("x", [
    FilterStep(entity="Sample",
               filters=[FieldFilter("sampleType", "tissue"),
                        FieldFilter("brainRegion", FOUR_REGIONS, "IN")],
               forward_relation={"field": "donor",
                                 "select_fields": ["cohort", "sex", "historyOfRhi"]}),
])
r = graded(camel, "q20")
check("camelCase spelling still passes (semantics, not spelling)", r.outcome is FailureClass.PASS, r.detail)

# ---- region order must not matter ---------------------------------------------------------
reordered = QueryPlan("x", [
    FilterStep(entity="Sample",
               filters=[FieldFilter("sample_type", "tissue"),
                        FieldFilter("brain_region", list(reversed(FOUR_REGIONS)), "IN")],
               forward_relation={"field": "donor",
                                 "select_fields": ["sex", "cohort", "history_of_rhi"]}),
])
check("IN-list order and select order don't matter",
      graded(reordered, "q20").outcome is FailureClass.PASS)

# ---- over-filtering is also unfaithful ----------------------------------------------------
over = QueryPlan("x", [
    FilterStep(entity="Sample",
               filters=[FieldFilter("sample_type", "tissue"),
                        FieldFilter("brain_region", FOUR_REGIONS, "IN"),
                        FieldFilter("storage_condition", "frozen")],
               forward_relation={"field": "donor",
                                 "select_fields": ["cohort", "sex", "history_of_rhi"]}),
])
r = graded(over, "q20")
check("silently ADDING a filter is unfaithful too", r.outcome is FailureClass.PLAN_UNFAITHFUL, r.outcome.value)
check("...and says so", "never asked for" in r.detail, r.detail[:90])

# ---- wrong value / wrong op --------------------------------------------------------------
wrong_val = QueryPlan("x", [FilterStep(entity="Donor", filters=[FieldFilter("cohort", "control")])])
check("wrong filter value is unfaithful",
      graded(wrong_val, "q01").outcome is FailureClass.PLAN_UNFAITHFUL)
right = QueryPlan("x", [FilterStep(entity="Donor", filters=[FieldFilter("cohort", "case")])])
check("right filter value passes", graded(right, "q01").outcome is FailureClass.PASS)

# ---- validator failures classify as PLAN_INVALID, not unfaithful --------------------------
bogus = QueryPlan("x", [FilterStep(entity="Donor", filters=[FieldFilter("not_a_field", "x")])])
check("unknown field -> PLAN_INVALID",
      graded(bogus, "q01").outcome is FailureClass.PLAN_INVALID)
unsupported_op = QueryPlan("x", [FilterStep(entity="Donor", filters=[FieldFilter("age_at_death", 65, "GT")])])
check("unsupported op -> PLAN_INVALID",
      graded(unsupported_op, "q01").outcome is FailureClass.PLAN_INVALID)

# ---- expect_rejection cases ---------------------------------------------------------------
# q32 needs GT + sort. A plan the validator rejects is CORRECT behaviour here.
r = graded(unsupported_op, "q32")
check("blocked question: rejected plan counts as PASS", r.outcome is FailureClass.PASS, r.outcome.value)
# ...while a plan that slips through is a failure nothing else tests for.
sneaky = QueryPlan("x", [FilterStep(entity="Donor", filters=[FieldFilter("age_at_death", 65)])])
r = graded(sneaky, "q32")
check("blocked question: accepted plan -> MISSING_REJECTION",
      r.outcome is FailureClass.MISSING_REJECTION, r.outcome.value)

# ---- multi-step: the rnaSeq leg ----------------------------------------------------------
rnaseq = QueryPlan("x", [
    FilterStep(entity="Sample", filters=[FieldFilter("sample_type", "tissue"),
                                         FieldFilter("brain_region", FOUR_REGIONS, "IN")]),
    RelatedLookupStep(source_step=0, relationship_type="input_samples",
                      client_filter=FieldFilter("workflow_type", "rna_seq")),
])
check("two-step rnaSeq plan passes", graded(rnaseq, "q25").outcome is FailureClass.PASS)

missing_narrow = QueryPlan("x", [
    FilterStep(entity="Sample", filters=[FieldFilter("sample_type", "tissue"),
                                         FieldFilter("brain_region", FOUR_REGIONS, "IN")]),
    RelatedLookupStep(source_step=0, relationship_type="input_samples"),
])
r = graded(missing_narrow, "q25")
check("dropping the client-side narrowing is unfaithful", r.outcome is FailureClass.PLAN_UNFAITHFUL)
check("...and explains the consequence", "every referencing entity" in r.detail, r.detail[:90])

wrong_rel = QueryPlan("x", [
    FilterStep(entity="Sample", filters=[FieldFilter("sample_type", "tissue"),
                                         FieldFilter("brain_region", FOUR_REGIONS, "IN")]),
    RelatedLookupStep(source_step=0, relationship_type="workflows_via_input_samples",
                      client_filter=FieldFilter("workflow_type", "rna_seq")),
])
r = graded(wrong_rel, "q25")
check("manifest-label as relationship_type is caught", r.outcome is FailureClass.PLAN_UNFAITHFUL, r.outcome.value)

one_step_only = QueryPlan("x", [
    FilterStep(entity="Sample", filters=[FieldFilter("sample_type", "tissue"),
                                         FieldFilter("brain_region", FOUR_REGIONS, "IN")]),
])
check("missing the whole lookup step is unfaithful",
      graded(one_step_only, "q25").outcome is FailureClass.PLAN_UNFAITHFUL)

# ---- environment classes are NOT context failures ---------------------------------------
r = grade_sample(PlanAttempt(protocol="tool_call", finish_reason="length"), CASES["q01"], 0, HS, MANIFEST)
check("truncation -> TRUNCATED (config, not context)", r.outcome is FailureClass.TRUNCATED, r.outcome.value)
r = grade_sample(PlanAttempt(protocol="tool_call", error="AuthenticationError: no key"), CASES["q01"], 0, HS, MANIFEST)
check("provider error -> PROVIDER_ERROR", r.outcome is FailureClass.PROVIDER_ERROR, r.outcome.value)
r = grade_sample(PlanAttempt(protocol="tool_call", raw_content="```json\n{...}\n```"), CASES["q01"], 0, HS, MANIFEST)
check("prose instead of structured output -> NO_STRUCTURED_OUTPUT",
      r.outcome is FailureClass.NO_STRUCTURED_OUTPUT, r.outcome.value)
r = grade_sample(PlanAttempt(protocol="json_schema", structured_arguments="{not json",
                             raw_content="{not json", parse_error="JSONDecodeError: x"),
                 CASES["q01"], 0, HS, MANIFEST)
check("malformed payload -> UNPARSEABLE", r.outcome is FailureClass.UNPARSEABLE, r.outcome.value)

print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("all grader golden-set checks pass")
