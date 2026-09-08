"""Turn-taking planning core tests. No LLM calls except in
TestLiveTurn (opt-in, mirrors test_spec_planner.py's TestAgainstMosaicItself
in spirit but goes one step further: it actually calls a model, since this
module has no compiled-artifact ground truth to check offline the way
spec_planner.py's op-vocabulary sweep does -- there is no "real validator"
for whether a clarifying question was the RIGHT call, only for whether a
proposal's query_spec is legal).

The load-bearing test here is `TestNormalizeTurn` plus
`test_a_proposals_query_spec_passes_mosaics_real_validator`: together they
prove the shape this module hands upstream is exactly what
validate_query_spec accepts, using the same real demo-schema manifest
test_spec_planner.py already established as ground truth.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from exon.conversational_planner import (
    TURN_TOOL,
    _normalize_turn,
    build_turn_grounding,
    render_conversation_history,
    render_current_draft,
)

CAPS = {
    "Sample": {
        "name": "Sample", "accessor_name": "samples", "description": "A biological specimen.",
        "search_available": False,
        "fields": [
            {
                "name": "name", "kind": "scalar", "range": "string", "required": True,
                "multivalued": False, "enum_values": [], "target_entity_type": None,
                "filter_ops": ["eq", "neq", "in", "contains", "is_null"],
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
        "name": "Donor", "accessor_name": "donors", "description": "A tissue donor.",
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
    def test_query_spec_property_reuses_spec_tools_shape(self):
        from exon.spec_planner import SPEC_TOOL

        turn_qs_props = TURN_TOOL["function"]["parameters"]["properties"]["query_spec"]["properties"]
        spec_props = SPEC_TOOL["function"]["parameters"]["properties"]
        assert turn_qs_props["v"] == spec_props["v"]
        assert turn_qs_props["criteria"] == spec_props["criteria"]

    def test_status_is_required_and_exclusive(self):
        params = TURN_TOOL["function"]["parameters"]
        assert "status" in params["required"] and "message" in params["required"]
        assert "query_spec" not in params["required"]
        assert set(params["properties"]["status"]["enum"]) == {"proposal", "clarification"}


class TestNormalizeTurn:
    def test_valid_proposal_round_trips(self):
        turn = _normalize_turn({
            "status": "proposal",
            "message": "Filtering to samples from female donors.",
            "query_spec": {
                "anchor": "Sample", "mode": "AND",
                "criteria": [{
                    "kind": "related", "edge": "donor", "quantifier": "some",
                    "criteria": [{"slot": "sex", "op": "eq", "value": "female"}],
                }],
            },
        })
        assert turn["status"] == "proposal"
        assert turn["query_spec"]["anchor"] == "Sample"
        assert turn["query_spec"]["criteria"][0]["edge"] == "donor"

    def test_valid_clarification_round_trips(self):
        turn = _normalize_turn({"status": "clarification", "message": "Which donor's samples?"})
        assert turn == {"status": "clarification", "message": "Which donor's samples?", "query_spec": None}

    def test_unknown_status_is_rejected(self):
        with pytest.raises(ValueError, match="status"):
            _normalize_turn({"status": "maybe", "message": "hmm"})

    def test_missing_message_is_rejected(self):
        with pytest.raises(ValueError, match="message"):
            _normalize_turn({"status": "clarification"})

    def test_empty_message_is_rejected(self):
        with pytest.raises(ValueError, match="message"):
            _normalize_turn({"status": "clarification", "message": ""})

    def test_proposal_without_query_spec_is_rejected(self):
        with pytest.raises(ValueError, match="query_spec"):
            _normalize_turn({"status": "proposal", "message": "ok"})

    def test_clarification_with_query_spec_is_rejected_not_silently_dropped(self):
        # The one genuinely load-bearing rejection: a model that hedges by
        # asking a question AND proposing a spec change is contradicting
        # itself, not offering an ambiguous-but-fine shape.
        with pytest.raises(ValueError, match="clarification"):
            _normalize_turn({
                "status": "clarification", "message": "which donor?",
                "query_spec": {"anchor": "Sample", "mode": "AND", "criteria": []},
            })

    def test_non_dict_input_is_rejected(self):
        with pytest.raises(TypeError):
            _normalize_turn("not a dict")


class TestGrounding:
    def test_first_turn_shows_no_draft_and_no_history(self):
        text = build_turn_grounding(CAPS, None, ())
        assert "no draft yet" in text
        assert "none -- this is the first turn" in text

    def test_later_turn_shows_the_current_draft(self):
        spec = {"v": 1, "anchor": "Sample", "mode": "AND", "criteria": []}
        text = render_current_draft(spec)
        assert '"anchor": "Sample"' in text

    def test_history_renders_utterance_and_message_pairs(self):
        history = render_conversation_history((
            {"utterance": "samples from female donors", "message": "Filtering to female donors."},
        ))
        assert "samples from female donors" in history
        assert "Filtering to female donors." in history

    def test_grounding_has_no_unsubstituted_placeholders(self):
        assert "{{" not in build_turn_grounding(CAPS, None, ())

    def test_grounding_instructs_refining_not_regenerating(self):
        text = build_turn_grounding(CAPS, {"anchor": "Sample"}, ())
        assert "Refine the CURRENT DRAFT" in text


class TestAgainstMosaicItself:
    """Ground truth: does a normalized proposal's query_spec actually
    satisfy Mosaic's real validator, against the real demo schema?"""

    @pytest.fixture(scope="class")
    def manifest(self):
        from mosaic.core.schema_typing import build_capability_manifest
        from mosaic.linkml_bridge import SchemaRegistry

        schema = Path(__file__).resolve().parents[1] / "schemas" / "demo.yaml"
        return build_capability_manifest(SchemaRegistry.from_path(str(schema)))

    def test_a_proposals_query_spec_passes_mosaics_real_validator(self, manifest):
        from mosaic.core.query_spec import parse_query_spec, validate_query_spec

        turn = _normalize_turn({
            "status": "proposal",
            "message": "Filtering to samples with a replicate number over 2.",
            "query_spec": {
                "anchor": "Sample", "mode": "AND",
                "criteria": [{"kind": "field", "slot": "replicate_number", "op": "gt", "value": 2}],
            },
        })
        result = validate_query_spec(parse_query_spec(turn["query_spec"]), manifest)
        assert result.valid, f"Mosaic rejected {turn['query_spec']}: {result.errors}"

    def test_grounding_renders_from_the_real_manifest(self, manifest):
        from mosaic.mcp.serialize import entity_capability_to_dict

        caps = {n: entity_capability_to_dict(e) for n, e in manifest.items()}
        text = build_turn_grounding(caps, None, ())
        assert "{{" not in text
        for entity in caps:
            assert f'entity "{entity}"' in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
