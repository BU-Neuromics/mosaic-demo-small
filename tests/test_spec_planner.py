"""QuerySpec emitter tests. No LLM calls -- the fast regression test for the shape
normalization and the capability grounding.

The load-bearing test here is
`test_normalized_specs_pass_mosaics_real_validator`: it feeds this module's output through
`mosaic.core.query_spec`'s ACTUAL parser and validator, against a capability manifest built
from this repo's real demo schema. Everything else in this file checks that the emitter puts
fields in the right place; only that test checks the emitter agrees with the thing that gets
the final say. Any assertion about what Mosaic accepts, made without going through Mosaic,
is a guess.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from exon.spec_planner import (
    FILTER_OPS,
    SPEC_TOOL,
    _normalize_spec,
    build_grounding_context,
    render_capability_grounding,
    render_traversable_edges,
)

# A capability manifest in the exact shape mosaic://capabilities serves (see
# mosaic/mcp/serialize.py's entity_capability_to_dict), trimmed to what these tests read.
CAPS = {
    "Sample": {
        "name": "Sample",
        "accessor_name": "samples",
        "description": "A biological specimen.",
        "search_available": False,
        "fields": [
            {
                "name": "name", "kind": "scalar", "range": "string", "required": True,
                "multivalued": False, "enum_values": [], "target_entity_type": None,
                "filter_ops": ["eq", "neq", "in", "contains", "is_null"],
                "predicate": False, "orderable": True,
            },
            {
                "name": "sample_type", "kind": "enum", "range": "SampleTypeEnum",
                "required": False, "multivalued": False,
                "enum_values": ["blood", "tissue"], "target_entity_type": None,
                "filter_ops": ["eq", "neq", "in", "is_null"],
                "predicate": False, "orderable": True,
            },
            {
                "name": "volume_ml", "kind": "scalar", "range": "float", "required": False,
                "multivalued": False, "enum_values": [], "target_entity_type": None,
                "filter_ops": ["eq", "neq", "in", "gt", "gte", "lt", "lte", "is_null"],
                "predicate": False, "orderable": True,
            },
            {
                "name": "donor", "kind": "reference", "range": "Donor", "required": True,
                "multivalued": False, "enum_values": [], "target_entity_type": "Donor",
                "filter_ops": [], "predicate": True, "orderable": False,
            },
        ],
    },
    "Donor": {
        "name": "Donor",
        "accessor_name": "donors",
        "description": "A tissue donor.",
        "search_available": False,
        "fields": [
            {
                "name": "sex", "kind": "enum", "range": "SexEnum", "required": False,
                "multivalued": False, "enum_values": ["male", "female"],
                "target_entity_type": None,
                "filter_ops": ["eq", "neq", "in", "is_null"],
                "predicate": False, "orderable": True,
            },
        ],
    },
}


class TestToolSchema:
    def test_op_enum_matches_mosaics_filter_ops_exactly(self):
        # Not a restatement of the constant -- this pins the tool schema the MODEL sees to
        # Mosaic's own FilterOp spelling. A drift here means the model is offered an operator
        # the server rejects, or denied one it accepts.
        from mosaic.core.schema_typing import FilterOp

        assert FILTER_OPS == [o.value for o in FilterOp]
        props = SPEC_TOOL["function"]["parameters"]["properties"]
        assert props["criteria"]["items"]["properties"]["op"]["enum"] == FILTER_OPS

    def test_ops_are_lowercase_not_queryplans_uppercase(self):
        # QueryPlan used "EQ"/"IN"; QuerySpec uses "eq"/"in". Emitting the old spelling
        # would fail validation on every single criterion.
        assert "eq" in FILTER_OPS and "EQ" not in FILTER_OPS

    def test_required_fields_match_queryspecs_own_requirements(self):
        assert set(SPEC_TOOL["function"]["parameters"]["required"]) == {
            "v", "anchor", "mode", "criteria"
        }


class TestNormalization:
    def test_minimal_spec_is_filled_out(self):
        spec = _normalize_spec({"anchor": "Sample"})
        assert spec == {"v": 1, "anchor": "Sample", "mode": "AND", "criteria": []}

    def test_field_criterion_round_trips(self):
        spec = _normalize_spec({
            "anchor": "Sample", "mode": "AND",
            "criteria": [{"kind": "field", "slot": "volume_ml", "op": "gt", "value": 5.0}],
        })
        assert spec["criteria"] == [
            {"kind": "field", "slot": "volume_ml", "op": "gt", "value": 5.0}
        ]

    def test_related_criterion_round_trips(self):
        spec = _normalize_spec({
            "anchor": "Sample", "mode": "AND",
            "criteria": [{
                "kind": "related", "edge": "donor", "quantifier": "some",
                "criteria": [{"slot": "sex", "op": "eq", "value": "female"}],
            }],
        })
        (c,) = spec["criteria"]
        assert c["kind"] == "related" and c["edge"] == "donor"
        assert c["criteria"] == [{"kind": "field", "slot": "sex", "op": "eq",
                                  "value": "female"}]

    def test_missing_kind_is_inferred_from_the_payload(self):
        # A whole-spec parse failure becomes a spec Mosaic can give a precise error about.
        spec = _normalize_spec({
            "anchor": "Sample",
            "criteria": [{"edge": "donor", "criteria": [{"slot": "sex", "op": "eq",
                                                         "value": "male"}]}],
        })
        assert spec["criteria"][0]["kind"] == "related"
        assert spec["criteria"][0]["quantifier"] == "some"

    def test_is_null_without_an_operand_is_filled_with_true(self):
        # Regression: Mosaic requires a BOOLEAN operand on is_null and rejects an absent one
        # with INVALID_VALUE_TYPE. An emitter that omitted it failed validation on every
        # is_null criterion -- caught only by running the real validator, not by shape review.
        spec = _normalize_spec({
            "anchor": "Sample",
            "criteria": [{"kind": "field", "slot": "volume_ml", "op": "is_null"}],
        })
        assert spec["criteria"][0]["value"] is True

    def test_is_null_false_is_preserved_not_overwritten(self):
        # false is meaningful ("is NOT null"), so the fill above must not clobber it.
        spec = _normalize_spec({
            "anchor": "Sample",
            "criteria": [{"kind": "field", "slot": "volume_ml", "op": "is_null",
                          "value": False}],
        })
        assert spec["criteria"][0]["value"] is False

    def test_is_null_with_a_non_boolean_operand_is_coerced(self):
        # Models sometimes send null or a string here; either is rejected upstream.
        spec = _normalize_spec({
            "anchor": "Sample",
            "criteria": [{"kind": "field", "slot": "volume_ml", "op": "is_null",
                          "value": None}],
        })
        assert spec["criteria"][0]["value"] is True

    def test_sort_is_omitted_when_empty_not_emitted_as_empty_list(self):
        assert "sort" not in _normalize_spec({"anchor": "Sample", "sort": []})

    def test_sort_direction_defaults_to_asc(self):
        spec = _normalize_spec({"anchor": "Sample", "sort": [{"slot": "volume_ml"}]})
        assert spec["sort"] == [{"slot": "volume_ml", "direction": "asc"}]

    def test_missing_anchor_is_a_structural_error(self):
        with pytest.raises(ValueError, match="anchor"):
            _normalize_spec({"mode": "AND", "criteria": []})

    def test_normalization_does_not_validate_field_names(self):
        # Deliberate: an unknown slot must survive normalization so Mosaic can name it in a
        # precise UNKNOWN_SLOT error. Rejecting it here would rebuild Exon's local validator.
        spec = _normalize_spec({
            "anchor": "Nonexistent",
            "criteria": [{"kind": "field", "slot": "nope", "op": "eq", "value": 1}],
        })
        assert spec["anchor"] == "Nonexistent"
        assert spec["criteria"][0]["slot"] == "nope"


class TestGrounding:
    def test_scalar_fields_list_their_legal_ops(self):
        text = render_capability_grounding(CAPS)
        assert "volume_ml: float -- ops: eq, neq, in, gt, gte, lt, lte, is_null" in text

    def test_enum_fields_list_their_allowed_values(self):
        text = render_capability_grounding(CAPS)
        assert "allowed values: blood, tissue" in text

    def test_reference_fields_are_rendered_as_edges_not_filterable_fields(self):
        # The manifest gives references no direct FilterOp (mosaic#181's where:-only
        # decision). Presenting one as a filterable field would ground the model into
        # producing exactly the criterion the server rejects.
        text = render_capability_grounding(CAPS)
        assert "donor: reference -> Donor (to-one)" in text
        assert "NOT a direct field filter" in text

    def test_traversable_edges_name_the_anchor_they_belong_to(self):
        # Two unrelated models previously put the wrong identifier in the relationship slot
        # when the grounding listed names without saying where each belonged.
        text = render_traversable_edges(CAPS)
        assert 'on anchor "Sample": edge="donor" reaches Donor' in text

    def test_non_traversable_schema_says_so_rather_than_rendering_empty(self):
        text = render_traversable_edges({"Donor": CAPS["Donor"]})
        assert "no traversable references" in text

    def test_grounding_states_the_single_sort_entry_cap(self):
        text = build_grounding_context(CAPS)
        assert "AT MOST ONE entry" in text

    def test_grounding_has_no_unsubstituted_placeholders(self):
        assert "{{" not in build_grounding_context(CAPS)


class TestAgainstMosaicItself:
    """The ground-truth tests: does what this emitter produces actually satisfy Mosaic?"""

    @pytest.fixture(scope="class")
    def manifest(self):
        from mosaic.core.schema_typing import build_capability_manifest
        from mosaic.linkml_bridge import SchemaRegistry

        schema = Path(__file__).resolve().parents[1] / "schemas" / "demo.yaml"
        return build_capability_manifest(SchemaRegistry.from_path(str(schema)))

    def test_capability_grounding_renders_from_the_real_manifest(self, manifest):
        from mosaic.mcp.serialize import entity_capability_to_dict

        caps = {n: entity_capability_to_dict(e) for n, e in manifest.items()}
        text = build_grounding_context(caps)
        assert "{{" not in text
        # Every entity the server exposes must appear, or the model cannot query it.
        for entity in caps:
            assert f'entity "{entity}"' in text

    @pytest.mark.parametrize(
        "raw",
        [
            {"anchor": "Sample", "mode": "AND", "criteria": []},
            {
                "anchor": "Sample", "mode": "AND",
                "criteria": [{"kind": "field", "slot": "name", "op": "contains",
                              "value": "S1"}],
            },
            {
                "anchor": "Sample", "mode": "AND",
                "criteria": [{"kind": "field", "slot": "name", "op": "is_null"}],
            },
            {"anchor": "Sample", "mode": "AND", "criteria": [],
             "sort": [{"slot": "name", "direction": "desc"}]},
        ],
    )
    def test_normalized_specs_pass_mosaics_real_validator(self, manifest, raw):
        from mosaic.core.query_spec import parse_query_spec, validate_query_spec

        spec = _normalize_spec(raw)
        # parse_query_spec raises QuerySpecShapeError on a shape it cannot read at all --
        # reaching validate at all already proves the emitter's shape is structurally right.
        result = validate_query_spec(parse_query_spec(spec), manifest)
        assert result.valid, f"Mosaic rejected {spec}: {result.errors}"

    def test_a_related_criterion_passes_the_real_validator(self, manifest):
        from mosaic.core.query_spec import parse_query_spec, validate_query_spec

        # Find a real traversable edge in this repo's schema rather than hardcoding one.
        anchor, edge, target = next(
            (name, f.slot.name, f.slot.target_class)
            for name, e in manifest.items()
            for f in e.fields
            if f.predicate
        )
        target_field = next(
            f.slot.name for f in manifest[target].fields if f.filter_ops
        )
        spec = _normalize_spec({
            "anchor": anchor, "mode": "AND",
            "criteria": [{
                "kind": "related", "edge": edge, "quantifier": "some",
                "criteria": [{"slot": target_field, "op": "is_null"}],
            }],
        })
        result = validate_query_spec(parse_query_spec(spec), manifest)
        assert result.valid, f"Mosaic rejected {spec}: {result.errors}"

    def test_the_emitters_op_vocabulary_is_accepted_on_a_field_that_allows_it(self, manifest):
        # Guards the lowercase-op decision against the real validator, per field, rather
        # than trusting the enum comparison alone.
        from mosaic.core.query_spec import parse_query_spec, validate_query_spec

        checked = 0
        for name, entity in manifest.items():
            for f in entity.fields:
                for op in f.filter_ops:
                    value = _sample_value(f)
                    spec = _normalize_spec({
                        "anchor": name, "mode": "AND",
                        "criteria": [{
                            "kind": "field", "slot": f.slot.name, "op": op.value,
                            # `in` takes a list; is_null's boolean is filled by the emitter.
                            "value": [value] if op.value == "in" else value,
                        }],
                    })
                    result = validate_query_spec(parse_query_spec(spec), manifest)
                    assert result.valid, (
                        f"{name}.{f.slot.name} op={op.value} rejected: {result.errors}"
                    )
                    checked += 1
        assert checked > 0, "manifest exposed no filterable field -- test proved nothing"


def _sample_value(field):
    """A type-appropriate operand, so value-type validation is exercised, not sidestepped."""
    if field.slot.enum_values:
        return field.slot.enum_values[0]
    return {
        "integer": 1, "float": 1.0, "double": 1.0, "decimal": 1.0,
        "date": "2026-01-01", "datetime": "2026-01-01T00:00:00", "time": "00:00:00",
        "boolean": True,
    }.get(field.slot.range, "x")


if __name__ == "__main__":
    # Runnable as a script like its neighbours (`python3 tests/test_spec_planner.py`, the
    # invocation DEMO.md documents), while staying a normal pytest module -- the fixtures
    # and parametrize here are worth more than hand-rolled assertion counting.
    raise SystemExit(pytest.main([__file__, "-q"]))
