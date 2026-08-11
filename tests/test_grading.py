"""Grader golden set. The harness is the measuring instrument -- if it is wrong, every number it
produces is noise. No LLM calls, so this is the fast regression test.

The anchor cases are REAL plans captured from ollama_chat/gemma4:12b during development: the
faithful one, and the one whose `filters: []` silently dropped every stated constraint while
remaining structurally valid. If the grader ever stops distinguishing those two, the harness has
lost the only thing it was built to detect.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from exon.harness.cases import load_suite
from exon.harness.grading import grade_sample
from exon.harness.outcome import FailureClass
from exon.ops import FieldFilter, FilterStep, QueryPlan, RelatedLookupStep
from exon.planner import PlanAttempt
from exon.schema import fetch_hippo_schema, load_capability_manifest

ENDPOINT = "http://localhost:8080/graphql"
HS = fetch_hippo_schema(ENDPOINT)
MANIFEST = load_capability_manifest("evals/schema/capabilities.json")
CASES = {c.id: c for c in load_suite()}

FOUR = ["hippocampus", "frontal_cortex", "cerebellum", "brainstem"]
DONOR_FWD = {"field": "donor", "select_fields": ["cohort", "sex", "history_of_rhi"]}
failures = []


def check(name, condition, extra=""):
    print(("PASS  " if condition else "FAIL  ") + name + (f"   [{extra}]" if extra and not condition else ""))
    if not condition:
        failures.append(name)


def graded(plan, case_id):
    """Tier 0-3 only -- no endpoint, so execution/comparison is out of scope here."""
    return grade_sample(
        PlanAttempt(protocol="tool_call", plan=plan, structured_arguments="{}"),
        CASES[case_id], 0, HS, MANIFEST,
    )


def q35_plan(*, filters=None, forward=DONOR_FWD, lookup=True, rel="input_samples",
             client=("workflow_type", "rna_seq")):
    steps = [FilterStep(
        entity="Sample",
        filters=[FieldFilter(*f) for f in (filters if filters is not None else
                 [("sample_type", "tissue"), ("brain_region", "hippocampus")])],
        forward_relation=forward)]
    if lookup:
        steps.append(RelatedLookupStep(
            source_step=0, relationship_type=rel,
            client_filter=FieldFilter(*client) if client else None))
    return QueryPlan("driving example", steps)


# ---- anchor 1: the REAL faithful plan (q35, the verbatim driving question) ----------------
r = graded(q35_plan(), "q35")
check("faithful driving-example plan passes", r.outcome is FailureClass.PASS, r.detail)

# ---- anchor 2: the REAL unfaithful plan -- filters: [] ------------------------------------
r = graded(q35_plan(filters=[]), "q35")
check("dropped-filter plan is PLAN_UNFAITHFUL", r.outcome is FailureClass.PLAN_UNFAITHFUL, r.outcome.value)
check("...and names the missing filter", "missing required filter" in r.detail, r.detail[:100])

# ---- spelling and ordering must NOT matter -----------------------------------------------
r = graded(QueryPlan("x", [FilterStep(
    entity="Sample",
    filters=[FieldFilter("sampleType", "tissue"), FieldFilter("brainRegion", FOUR, "IN")])]), "q09")
check("camelCase spelling passes (semantics, not spelling)", r.outcome is FailureClass.PASS, r.detail)

r = graded(QueryPlan("x", [FilterStep(
    entity="Sample",
    filters=[FieldFilter("brain_region", list(reversed(FOUR)), "IN"),
             FieldFilter("sample_type", "tissue")])]), "q09")
check("IN-list order and filter order don't matter", r.outcome is FailureClass.PASS, r.detail)

# ---- over-filtering is unfaithful too ----------------------------------------------------
r = graded(QueryPlan("x", [FilterStep(
    entity="Sample",
    filters=[FieldFilter("sample_type", "tissue"), FieldFilter("brain_region", FOUR, "IN"),
             FieldFilter("storage_condition", "frozen")])]), "q09")
check("silently ADDING a filter is unfaithful", r.outcome is FailureClass.PLAN_UNFAITHFUL, r.outcome.value)
check("...and says so", "never asked for" in r.detail, r.detail[:100])

# ---- wrong value / right value -----------------------------------------------------------
check("wrong filter value is unfaithful",
      graded(QueryPlan("x", [FilterStep(entity="Donor", filters=[FieldFilter("cohort", "control")])]),
             "q01").outcome is FailureClass.PLAN_UNFAITHFUL)
check("right filter value passes",
      graded(QueryPlan("x", [FilterStep(entity="Donor", filters=[FieldFilter("cohort", "case")])]),
             "q01").outcome is FailureClass.PASS)
check("wrong entity is caught",
      graded(QueryPlan("x", [FilterStep(entity="Sample", filters=[FieldFilter("id", "x")])]),
             "q01").outcome is FailureClass.PLAN_UNFAITHFUL)

# ---- validator failures are PLAN_INVALID, not unfaithful ---------------------------------
bogus = QueryPlan("x", [FilterStep(entity="Donor", filters=[FieldFilter("not_a_field", "x")])])
check("unknown field -> PLAN_INVALID", graded(bogus, "q01").outcome is FailureClass.PLAN_INVALID)
gt = QueryPlan("x", [FilterStep(entity="Donor", filters=[FieldFilter("age_at_death", 65, "GT")])])
check("unsupported op -> PLAN_INVALID", graded(gt, "q01").outcome is FailureClass.PLAN_INVALID)

# ---- blocked questions: refusing IS the correct answer -----------------------------------
r = graded(gt, "q32")
check("blocked question: rejected plan counts as PASS", r.outcome is FailureClass.PASS, r.outcome.value)
sneaky = QueryPlan("x", [FilterStep(entity="Donor", filters=[FieldFilter("age_at_death", 65)])])
r = graded(sneaky, "q32")
check("blocked question: accepted plan -> MISSING_REJECTION",
      r.outcome is FailureClass.MISSING_REJECTION, r.outcome.value)

# ---- the two-step rnaSeq leg -------------------------------------------------------------
r = graded(q35_plan(client=None), "q35")
check("dropping the client-side narrowing is unfaithful", r.outcome is FailureClass.PLAN_UNFAITHFUL, r.outcome.value)
check("...and explains the consequence", "every referencing entity" in r.detail, r.detail[:100])

r = graded(q35_plan(rel="workflows_via_input_samples"), "q35")
check("manifest-label as relationship_type is caught", r.outcome is FailureClass.PLAN_UNFAITHFUL, r.outcome.value)

r = graded(q35_plan(lookup=False), "q35")
check("missing the whole lookup step is unfaithful", r.outcome is FailureClass.PLAN_UNFAITHFUL, r.outcome.value)

r = graded(q35_plan(forward=None), "q35")
check("dropping the donor attributes is unfaithful", r.outcome is FailureClass.PLAN_UNFAITHFUL, r.outcome.value)

# ---- environment classes are NOT context failures ---------------------------------------
def env(attempt):
    return grade_sample(attempt, CASES["q01"], 0, HS, MANIFEST).outcome

check("truncation -> TRUNCATED (config, not context)",
      env(PlanAttempt(protocol="tool_call", finish_reason="length")) is FailureClass.TRUNCATED)
check("provider error -> PROVIDER_ERROR",
      env(PlanAttempt(protocol="tool_call", error="AuthenticationError: no key")) is FailureClass.PROVIDER_ERROR)
check("prose instead of structured output -> NO_STRUCTURED_OUTPUT",
      env(PlanAttempt(protocol="tool_call", raw_content="```json\n{...}\n```")) is FailureClass.NO_STRUCTURED_OUTPUT)
check("malformed payload -> UNPARSEABLE",
      env(PlanAttempt(protocol="json_schema", structured_arguments="{not json",
                      raw_content="{not json", parse_error="JSONDecodeError: x")) is FailureClass.UNPARSEABLE)

print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("all grader golden-set checks pass")
