"""QuerySpec grading (add-mosaic-mcp-boundary task 2.5).

These protect the three things Mosaic's validator structurally cannot check. It answers
"is this spec legal"; every case here is legal and wrong.
"""
from exon.harness.cases import CriterionExpectation, RelatedExpectation, SpecExpectation, TestCase
from exon.harness.grading import (
    check_empty_related,
    check_result_shape,
    check_spec_faithfulness,
)

SCHEMA = {
    "Sample": {"fields": {"sample_type": {}, "brain_region": {}}},
    "Donor": {"fields": {"cohort": {}, "age_at_death": {}, "sex": {}}},
}


def case(spec_exp, cid="q00"):
    return TestCase(id=cid, instruction="x", question_capability="filter", spec=spec_exp)


def spec(anchor="Sample", criteria=()):
    return {"v": 1, "anchor": anchor, "mode": "AND", "criteria": list(criteria)}


def field(slot, value, op="eq"):
    return {"kind": "field", "slot": slot, "op": op, "value": value}


def test_accepts_a_faithful_spec():
    c = case(SpecExpectation(anchor="Sample",
                             required_criteria=(CriterionExpectation("sample_type", "tissue"),)))
    ok, detail = check_spec_faithfulness(spec(criteria=[field("sample_type", "tissue")]), c, SCHEMA)
    assert ok, detail


def test_compares_on_semantics_not_spelling():
    # `sampleType` and `sample_type` are the same assertion. Failing a correct spec on
    # cosmetics is the most likely way to waste a week chasing ghosts.
    c = case(SpecExpectation(anchor="Sample",
                             required_criteria=(CriterionExpectation("sample_type", "tissue"),)))
    ok, detail = check_spec_faithfulness(spec(criteria=[field("sampleType", "tissue")]), c, SCHEMA)
    assert ok, detail


def test_catches_a_dropped_constraint():
    c = case(SpecExpectation(anchor="Sample",
                             required_criteria=(CriterionExpectation("sample_type", "tissue"),)))
    ok, detail = check_spec_faithfulness(spec(), c, SCHEMA)
    assert not ok and "drops it" in detail


def test_catches_over_filtering():
    c = case(SpecExpectation(anchor="Sample",
                             required_criteria=(CriterionExpectation("sample_type", "tissue"),)))
    ok, detail = check_spec_faithfulness(
        spec(criteria=[field("sample_type", "tissue"), field("brain_region", "hippocampus")]),
        c, SCHEMA)
    assert not ok and "never asked for" in detail


def test_catches_the_wrong_anchor():
    # The anchor decides what a row IS, so this answers a different question entirely.
    c = case(SpecExpectation(anchor="Donor"))
    ok, detail = check_spec_faithfulness(spec(anchor="Sample"), c, SCHEMA)
    assert not ok and "different question" in detail


def test_catches_a_wrong_operator():
    c = case(SpecExpectation(anchor="Donor",
                             required_criteria=(CriterionExpectation("age_at_death", 65, op="gt"),)))
    ok, detail = check_spec_faithfulness(
        spec(anchor="Donor", criteria=[field("age_at_death", 65, op="eq")]), c, SCHEMA)
    # Degrading gt to eq returns a confidently wrong answer, which is the whole point.
    assert not ok and "op" in detail


def test_requires_the_related_edge_to_be_traversed():
    c = case(SpecExpectation(
        anchor="Sample",
        required_related=(RelatedExpectation("donor", criteria=(CriterionExpectation("sex", "female"),)),)))
    ok, detail = check_spec_faithfulness(spec(), c, SCHEMA)
    assert not ok and "does not traverse it" in detail


def test_requires_the_constraint_on_the_related_record():
    c = case(SpecExpectation(
        anchor="Sample",
        required_related=(RelatedExpectation("donor", criteria=(CriterionExpectation("sex", "female"),)),)))
    got = spec(criteria=[{"kind": "related", "edge": "donor", "quantifier": "some", "criteria": []}])
    ok, detail = check_spec_faithfulness(got, c, SCHEMA)
    assert not ok and "related record" in detail


def test_empty_related_is_a_graded_failure():
    # Validates, executes, returns every anchor with ANY related record. 2.5d.
    got = spec(criteria=[{"kind": "related", "edge": "donor", "quantifier": "some", "criteria": []}])
    ok, detail = check_empty_related(got)
    assert not ok and "asserts nothing" in detail


def test_populated_related_is_not_flagged_as_empty():
    got = spec(criteria=[{"kind": "related", "edge": "donor", "quantifier": "some",
                          "criteria": [{"slot": "sex", "op": "eq", "value": "female"}]}])
    assert check_empty_related(got)[0]


def test_row_shaped_question_passes_shape_check():
    assert check_result_shape(spec(), case(SpecExpectation()))[0]


def test_facet_question_answered_with_rows_is_graded_wrong():
    # The original observed failure: asked for per-cohort counts, returned all 300 donors.
    c = case(SpecExpectation(anchor="Donor", result_shape="facet"))
    ok, detail = check_result_shape(spec(anchor="Donor"), c)
    assert not ok and "structurally cannot" in detail
