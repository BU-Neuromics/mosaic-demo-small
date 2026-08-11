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
import time
from dataclasses import dataclass

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
# A loaded generation on a local model runs for minutes. litellm's default request timeout cuts
# it off, and the resulting APIConnectionError is indistinguishable from a real transport fault
# unless you know to look -- it silently turned one measurement arm into noise before this was
# raised.
REQUEST_TIMEOUT = int(os.environ.get("EXON_REQUEST_TIMEOUT", "1800"))

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


def render_schema_slots(hippo_schema: dict) -> str:
    """Placeholder renderer: the per-entity field listing. Substituted into the context
    template at render time from LIVE introspection, never stored in the artifact."""
    lines = []
    for entity, info in sorted(hippo_schema.items()):
        slots = ", ".join(sorted(info["fields"]))
        lines.append(f"- {entity} (accessor: {info['accessor_name']}): {slots}")
    return "\n".join(lines)


def render_relationship_types(hippo_schema: dict) -> str:
    """Placeholder renderer: the ONLY valid relationship_type values for related_lookup steps,
    derived directly from hippoSchema field metadata -- never from the capability manifest's
    human-authored descriptive labels (e.g. "workflows_via_input_samples"), which are keys for
    documentation, not values the API accepts. Confirmed empirically: a model given the
    manifest's raw dict passed those descriptive keys as relationship_type, which silently
    matches nothing (relatedTo finds zero edges for a type never written to the table)."""
    lines = []
    for owner_entity, info in sorted(hippo_schema.items()):
        for field_name, field_info in sorted(info["fields"].items()):
            if field_info.get("kind") == "reference" and field_info.get("multivalued"):
                target = field_info.get("targetEntityType")
                lines.append(
                    f'- relationship_type="{field_name}": finds {owner_entity} entities '
                    f"that reference an already-identified {target} id through this slot "
                    f"(e.g. source_step's result is a list of {target} ids)"
                )
    if not lines:
        lines.append("- (none found in this schema)")
    lines.append(
        "A forward single-valued reference (e.g. Sample.donor) is NOT a related_lookup -- "
        "use forward_relation on the SAME filter step instead."
    )
    return "\n".join(lines)


def render_limitations(manifest: dict) -> str:
    """Placeholder renderer: what this instance genuinely cannot do, so the model is not
    tuned toward asking for it."""
    lines = []
    meta = manifest.get("_meta", {})
    for k in ("known_gotcha", "known_gotcha_2", "unfilterable_fields"):
        if k in meta:
            lines.append(f"- {meta[k]}")
    for entity, caps in manifest.get("entities", {}).items():
        if not caps.get("range_filters", {}).get("supported", True):
            lines.append(f"- {entity}: {caps['range_filters']['note']}")
    return "\n".join(lines)


# Default composition, used when no tuned context artifact is injected. The harness renders
# the same three placeholders through a versioned template instead -- same renderers, so a
# tuning gain reaches `python -m exon` unchanged.
DEFAULT_GROUNDING_BODY = """## Live schema -- the ONLY field names that exist, per entity:
{{schema_slots}}

## Valid related_lookup relationship_type values (multivalued-reference SLOT NAMES, never a descriptive label):
{{relationship_types}}

## Known unsupported capabilities (reject plans needing these):
{{limitations}}"""


def build_grounding_context(hippo_schema: dict, capability_manifest: dict) -> str:
    """The source of field/entity names and capabilities the model may use."""
    return (
        DEFAULT_GROUNDING_BODY.replace("{{schema_slots}}", render_schema_slots(hippo_schema))
        .replace("{{relationship_types}}", render_relationship_types(hippo_schema))
        .replace("{{limitations}}", render_limitations(capability_manifest))
    )


@dataclass
class PlanAttempt:
    """One model call, whatever happened. Deliberately records failure modes rather than
    raising, because the harness grades the distribution of outcomes -- a raised exception
    would collapse the very signal being measured."""

    protocol: str
    plan: QueryPlan | None = None
    raw_content: str | None = None
    structured_arguments: str | None = None
    finish_reason: str | None = None
    usage: dict | None = None
    error: str | None = None
    latency_s: float = 0.0
    parse_error: str | None = None

    @property
    def truncated(self) -> bool:
        """Ran out of budget before producing anything. On Ollama this is usually num_ctx
        (prompt+completion, independent of max_tokens) rather than the model's fault, so the
        harness must classify it as a config problem, not a context problem."""
        return self.finish_reason == "length" and self.plan is None


DEFAULT_SYSTEM_PROMPT = (
    "You are Exon, a query planner for a bioinformatics metadata graph. Translate the user's "
    "natural-language instruction into a typed query plan. Never respond with prose or raw "
    "GraphQL. Ground every field, entity, and relationship name STRICTLY in the schema given "
    "below -- a name that is not listed there is rejected by the server. Preserve EVERY "
    "constraint the instruction states: if it names a region, a type, or an attribute, that "
    "must appear as a filter. If the instruction asks what references an already-identified "
    "entity (e.g. 'which workflows consumed this sample'), emit a related_lookup step scoped "
    "via source_step to the ids from an earlier step -- never propose scanning an entire "
    "entity table."
)

PLAN_JSON_SCHEMA = PLAN_TOOL["function"]["parameters"]


def request_plan(
    instruction: str,
    hippo_schema: dict,
    capability_manifest: dict,
    *,
    model: str = None,
    context: tuple = None,
    protocol: str = "tool_call",
    decode_kwargs: dict = None,
    max_tokens: int = None,
) -> PlanAttempt:
    """One stateless single-turn call. No retries -- see plan_query for the retrying facade.

    `context` is an optional (system_prompt, grounding) pair, letting the harness swap in a
    tuned context artifact; omitted, the module defaults are rendered. The call carries no
    conversation history, no prior plan, and no expectation, so the model's only knowledge of
    this schema is what the injected context supplies.
    """
    model = model or MODEL
    max_tokens = max_tokens or MAX_TOKENS
    if context is None:
        system = DEFAULT_SYSTEM_PROMPT
        grounding = build_grounding_context(hippo_schema, capability_manifest)
    else:
        system, grounding = context

    kwargs = dict(decode_kwargs or {})
    if model.startswith("ollama") and "num_ctx" not in kwargs:
        kwargs["num_ctx"] = OLLAMA_NUM_CTX

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"{grounding}\n\n## Instruction\n{instruction}"},
    ]
    if protocol == "tool_call":
        kwargs.update(
            tools=[PLAN_TOOL],
            tool_choice={"type": "function", "function": {"name": "emit_query_plan"}},
        )
    elif protocol == "json_schema":
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "query_plan", "schema": PLAN_JSON_SCHEMA},
        }
    elif protocol == "json_object":
        kwargs["response_format"] = {"type": "json_object"}
    elif protocol not in ("delimited", "raw"):
        raise ValueError(f"unsupported protocol {protocol!r}")

    started = time.monotonic()
    try:
        response = litellm.completion(
            model=model, max_tokens=max_tokens, messages=messages,
            timeout=REQUEST_TIMEOUT, **kwargs
        )
    except openai.APIError as e:
        # litellm maps EVERY provider's errors onto openai's exception hierarchy regardless of
        # which provider served the request (verified: Anthropic's missing-key case raises
        # AuthenticationError, OpenAI's raises InternalServerError). Catch the common base.
        return PlanAttempt(
            protocol=protocol,
            error=f"{type(e).__name__}: {e}",
            latency_s=time.monotonic() - started,
        )

    latency = time.monotonic() - started
    choice = response.choices[0]
    attempt = PlanAttempt(
        protocol=protocol,
        raw_content=choice.message.content,
        finish_reason=choice.finish_reason,
        usage=dict(response.usage) if getattr(response, "usage", None) else None,
        latency_s=latency,
    )

    payload = None
    tool_calls = getattr(choice.message, "tool_calls", None)
    if protocol == "tool_call":
        if tool_calls:
            attempt.structured_arguments = tool_calls[0].function.arguments
            payload = attempt.structured_arguments
    else:
        # Structured-output protocols put the object in content. NOTE: no fenced-code or prose
        # extraction here, ever -- parsing a reply that ignored the requested format would
        # silently reintroduce the "trust the prose" failure mode this design exists to avoid.
        payload = attempt.raw_content
        attempt.structured_arguments = payload

    if payload:
        try:
            attempt.plan = _parse_plan(instruction, json.loads(payload))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            attempt.parse_error = f"{type(e).__name__}: {e}"
    return attempt


def plan_query(
    instruction: str,
    hippo_schema: dict,
    capability_manifest: dict,
    *,
    context: tuple = None,
    protocol: str = "tool_call",
) -> QueryPlan:
    """Retrying facade for the product surface (`python -m exon "<question>"`).

    A bounded retry is right here -- a user asking a question wants an answer, and the observed
    format failures are sampling variance. It is deliberately NOT used by the harness runner,
    where a retry would conceal the unreliability being measured.
    """
    last = None
    for _ in range(MAX_ATTEMPTS):
        last = request_plan(
            instruction,
            hippo_schema,
            capability_manifest,
            context=context,
            protocol=protocol,
        )
        if last.error:
            raise RuntimeError(
                f"Call to model {MODEL!r} failed -- check the provider's API key env var is "
                f"set (see exon/README.md for the convention per provider) and that the model "
                f"string is valid for that provider. Original error: {last.error}"
            )
        if last.plan is not None:
            return last.plan

    detail = last.parse_error or f"content: {(last.raw_content or '')[:400]!r}"
    if last.truncated:
        detail = (
            f"response truncated (finish_reason=length) before producing a plan -- for an "
            f"ollama model raise EXON_OLLAMA_NUM_CTX (currently {OLLAMA_NUM_CTX}); {detail}"
        )
    raise RuntimeError(
        f"Model {MODEL!r} produced no usable plan in {MAX_ATTEMPTS} attempt(s) via "
        f"protocol={protocol!r} -- {detail}"
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
