"""Schema-grounded LLM query planner: NL instruction -> typed QueryPlan.

Never emits or accepts free-text GraphQL -- the model is forced (tool_choice) to call
emit_query_plan with a shape validator.validate_plan can check before anything executes.
See openspec/changes/add-exon-query-planner/design.md, Decision 7.

Provider-agnostic via `litellm`: EXON_MODEL is a litellm model string
(e.g. "anthropic/claude-opus-5-20251101", "openai/gpt-4o", "gemini/gemini-1.5-pro",
"ollama/llama3") -- the provider is a deployment-time choice, not a code change.
Credentials follow litellm's standard per-provider env var convention, inferred from the
model string's prefix (ANTHROPIC_API_KEY, OPENAI_API_KEY, ...).
"""
import json
import os

import litellm
import openai  # litellm normalizes all provider errors onto openai's exception hierarchy;
# catching openai.APIError below is the correct broad catch, not a stray dependency.

from .ops import FieldFilter, FilterStep, RelatedLookupStep, QueryPlan

MODEL = os.environ.get("EXON_MODEL", "anthropic/claude-opus-5-20251101")
MAX_TOKENS = int(os.environ.get("EXON_MAX_TOKENS", "8192"))
# Ollama's default context window (num_ctx) is 4096 tokens *total* (prompt + completion),
# independent of max_tokens -- a "thinking"-capable local model can burn through that on
# reasoning alone before ever emitting the tool call, truncating with an empty response and
# no error (finish_reason="length"). Verified empirically against ollama_chat/gemma4:12b:
# the full grounding context (~1774 prompt tokens) leaves the default nowhere near enough
# thinking room. 16384 was inconsistent (worked once, then failed a 3-attempt run entirely);
# 32768 succeeded on the first attempt (~6-8k completion tokens used). Only meaningful for
# ollama/ollama_chat -- passed conditionally below so it's never sent to providers that don't
# have this parameter.
OLLAMA_NUM_CTX = int(os.environ.get("EXON_OLLAMA_NUM_CTX", "32768"))
MAX_ATTEMPTS = int(os.environ.get("EXON_MAX_ATTEMPTS", "3"))

PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "emit_query_plan",
        "description": (
            "Emit a typed query plan for the given instruction, grounded ONLY in the live "
            "schema and capability manifest provided. Never invent field, entity, or "
            "relationship names not present in that grounding context."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step_type": {
                                "type": "string",
                                "enum": ["filter", "related_lookup"],
                                "description": (
                                    "'filter': a root list query on one entity type. "
                                    "'related_lookup': a bounded reverse "
                                    "relationship-existence lookup (relatedTo) scoped to the "
                                    "ids returned by an earlier 'filter' or 'related_lookup' "
                                    "step -- never a free scan."
                                ),
                            },
                            "entity": {
                                "type": "string",
                                "description": "Required for step_type=filter. Must be an "
                                "entity name present in the live schema grounding.",
                            },
                            "filters": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "field": {
                                            "type": "string",
                                            "description": "A field name from the schema "
                                            "grounding. Use the slot name as listed there; "
                                            "an unlisted name is rejected.",
                                        },
                                        "value": {},
                                        "op": {"type": "string", "enum": ["EQ", "IN"]},
                                    },
                                    "required": ["field", "value"],
                                },
                            },
                            "filter_mode": {"type": "string", "enum": ["AND", "OR"]},
                            "select_fields": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "hippoSchema slot names to return for this "
                                "entity.",
                            },
                            "forward_relation": {
                                "type": ["object", "null"],
                                "properties": {
                                    "field": {"type": "string"},
                                    "select_fields": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                            },
                            "limit": {"type": "integer"},
                            "source_step": {
                                "type": "integer",
                                "description": "Required for step_type=related_lookup: the "
                                "0-based index of the earlier step whose result ids this "
                                "lookup is scoped to.",
                            },
                            "relationship_type": {
                                "type": "string",
                                "description": "Required for step_type=related_lookup: the "
                                "relationships-table slot name (e.g. 'input_samples').",
                            },
                            "client_filter": {
                                "type": ["object", "null"],
                                "description": "Optional predicate applied client-side to "
                                "each related_lookup call's own small result (relatedTo "
                                "itself accepts no predicate -- mosaic#148).",
                                "properties": {
                                    "field": {"type": "string"},
                                    "value": {},
                                },
                            },
                        },
                        "required": ["step_type"],
                    },
                }
            },
            "required": ["steps"],
        },
    },
}


def build_grounding_context(hippo_schema: dict, capability_manifest: dict) -> str:
    """The ONLY source of field/entity names and capabilities the model may use."""
    lines = ["## Live schema -- the ONLY field names that exist, per entity:"]
    for entity, info in sorted(hippo_schema.items()):
        slots = ", ".join(sorted(info["fields"]))
        lines.append(f"- {entity} (accessor: {info['accessor_name']}): {slots}")
    lines.append("")
    lines.append(_related_lookup_grounding(hippo_schema))
    lines.append("")
    lines.append("## Known unsupported capabilities (reject plans needing these):")
    lines.append(_manifest_limitations(capability_manifest))
    return "\n".join(lines)


def _related_lookup_grounding(hippo_schema: dict) -> str:
    """Enumerates the ONLY valid relationship_type values for related_lookup steps, derived
    directly from hippoSchema field metadata -- never from the capability manifest's
    human-authored descriptive labels (e.g. "workflows_via_input_samples"), which are keys
    for *this documentation*, not values the API accepts. Confirmed empirically: a model
    given the manifest's raw dict passed its descriptive keys as relationship_type, which
    silently matches nothing (relatedTo finds zero edges for a relationship_type that was
    never written to the relationships table)."""
    lines = [
        "## Valid related_lookup relationship_type values (the ONLY strings accepted -- "
        "these are multivalued-reference SLOT NAMES, never a descriptive label):"
    ]
    found_any = False
    for owner_entity, info in sorted(hippo_schema.items()):
        for field_name, field_info in sorted(info["fields"].items()):
            if field_info.get("kind") == "reference" and field_info.get("multivalued"):
                target = field_info.get("targetEntityType")
                lines.append(
                    f'- relationship_type="{field_name}": finds {owner_entity} entities '
                    f"that reference an already-identified {target} id through this slot "
                    f"(e.g. source_step's result is a list of {target} ids)"
                )
                found_any = True
    if not found_any:
        lines.append("- (none found in this schema)")
    lines.append(
        "A forward single-valued reference (e.g. Sample.donor) is NOT a related_lookup -- "
        "use forward_relation on the SAME filter step instead."
    )
    return "\n".join(lines)


def _manifest_limitations(manifest: dict) -> str:
    lines = []
    meta = manifest.get("_meta", {})
    for k in ("known_gotcha", "known_gotcha_2"):
        if k in meta:
            lines.append(f"- {meta[k]}")
    for entity, caps in manifest.get("entities", {}).items():
        if not caps.get("range_filters", {}).get("supported", True):
            lines.append(f"- {entity}: {caps['range_filters']['note']}")
    return "\n".join(lines)


def plan_query(instruction: str, hippo_schema: dict, capability_manifest: dict) -> QueryPlan:
    """Calls the configured litellm model. Raises on any provider/auth error -- never falls
    back to a guess. EXON_MODEL selects the provider; see module docstring."""
    grounding = build_grounding_context(hippo_schema, capability_manifest)

    system = (
        "You are Exon, a query planner for a bioinformatics metadata graph. Translate the "
        "user's natural-language instruction into a typed query plan by calling "
        "emit_query_plan -- never respond with prose or raw GraphQL. Ground every field, "
        "entity, and relationship name STRICTLY in the schema and capability manifest given "
        "below; never guess a GraphQL camelCase field name for a filter (the wrong one "
        "is rejected outright by the server). If the instruction "
        "needs to know what references an already-identified entity (e.g. 'which workflows "
        "consumed this sample'), emit a related_lookup step scoped via source_step to the "
        "ids from an earlier step -- never propose scanning an entire entity table."
    )

    extra_params = {}
    if MODEL.startswith("ollama"):
        extra_params["num_ctx"] = OLLAMA_NUM_CTX

    # Forced tool_choice isn't 100% reliably honored by every model -- verified empirically
    # against ollama_chat/gemma4:12b: across repeated calls with identical grounding/
    # instruction, it sometimes returned a real tool_calls response and sometimes dumped the
    # same JSON as markdown-fenced prose instead, despite tool_choice forcing the named
    # function. A bounded retry absorbs this sampling variance without weakening the
    # contract: a retry still requires a genuine tool_calls response, never a fallback parse
    # of free-text content (that would silently reintroduce exactly the "trust the prose"
    # failure mode this design exists to avoid).
    last_content = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = litellm.completion(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                tools=[PLAN_TOOL],
                tool_choice={"type": "function", "function": {"name": "emit_query_plan"}},
                messages=[
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": f"{grounding}\n\n## Instruction\n{instruction}",
                    },
                ],
                **extra_params,
            )
        except openai.APIError as e:
            # litellm maps EVERY provider's errors onto openai's exception hierarchy
            # regardless of which provider actually served the request (confirmed
            # empirically: Anthropic's missing-key case raises AuthenticationError,
            # OpenAI's raises InternalServerError -- both are openai.APIError subclasses,
            # neither is guessable in advance). Catch the common base, and don't retry --
            # an auth/provider error won't resolve itself on a second attempt.
            raise RuntimeError(
                f"Call to model {MODEL!r} failed -- check the provider's API key env var "
                f"is set (see exon/README.md for the convention per provider) and that the "
                f"model string is valid for that provider. Original error: {e}"
            ) from e

        tool_calls = response.choices[0].message.tool_calls
        if tool_calls:
            raw = json.loads(tool_calls[0].function.arguments)
            return _parse_plan(instruction, raw)
        last_content = response.choices[0].message.content

    raise RuntimeError(
        f"Model {MODEL!r} did not call emit_query_plan in {MAX_ATTEMPTS} attempt(s) despite "
        f"forced tool_choice -- last response content: {last_content!r}"
    )


def _parse_plan(instruction: str, raw: dict) -> QueryPlan:
    steps = []
    for s in raw["steps"]:
        if s["step_type"] == "filter":
            steps.append(
                FilterStep(
                    entity=s["entity"],
                    filters=[FieldFilter(**f) for f in s.get("filters", [])],
                    filter_mode=s.get("filter_mode", "AND"),
                    select_fields=s.get("select_fields", []),
                    forward_relation=s.get("forward_relation"),
                    limit=s.get("limit", 100),
                )
            )
        elif s["step_type"] == "related_lookup":
            cf = s.get("client_filter")
            steps.append(
                RelatedLookupStep(
                    source_step=s["source_step"],
                    relationship_type=s["relationship_type"],
                    client_filter=FieldFilter(**cf) if cf else None,
                )
            )
        else:
            raise ValueError(f"unknown step_type {s['step_type']!r}")
    return QueryPlan(instruction=instruction, steps=steps)
