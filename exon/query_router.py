"""Result-shape routing for the single-shot path (`add-mosaic-mcp-boundary`
task 2.5c).

## The problem this fixes

Mosaic's boundary answers four differently-shaped questions with four tools,
but a `QuerySpec` alone says nothing about which shape was *asked for*. So a
planner that only ever emits a `QuerySpec` and calls `execute_query_spec`
silently degrades any aggregate question into a row query. Measured live
(2026-09-08), asked "how many donors are there per cohort?", the emitter
produced a perfectly *valid* spec for all 300 donors sorted by cohort --
`total: 300`, where the true answer is `control 125 / case 104 / at_risk 71`.
Mosaic's validator checks shape and legality, never faithfulness to the
instruction, so nothing in the pipeline rejects that. It is a confidently
wrong answer.

Worth being precise about the size of the gap, because the task's original
framing ("recognize a counting-style instruction") is broader than reality:

  - A **single count** does NOT need a tool change to be *correct*.
    `execute_query_spec`'s envelope carries `total` independently of the page,
    so "how many donors are in the case cohort?" already returned the right
    answer (104) via a plain row query. Routing it to `count_query_spec` is an
    efficiency win -- it stops materializing 104 rows to report one number --
    not a correctness fix.
  - A **grouped count** is the genuinely broken case. `total` is one scalar
    and structurally cannot express a per-category breakdown, so no row query
    answers it, ever.

## Why a separate tool rather than a field on SPEC_TOOL

The obvious implementation -- add `result_shape` to `SPEC_TOOL` -- is a trap.
`SPEC_TOOL["function"]["parameters"]` *is* the QuerySpec schema, and
`conversational_planner.TURN_TOOL` reuses it verbatim as its `query_spec`
property. A routing field added there would leak into the conversational turn
contract and break `add-exon-conversational-contract` task 2.4's guarantee
that the turn vocabulary offers no aggregation at all ("true by construction:
there is nothing to restrict because nothing broader was ever offered to the
model"). Composing the QuerySpec as one property beside a sibling
`result_shape` -- exactly how `TURN_TOOL` already composes it -- leaves
`SPEC_TOOL` untouched and that guarantee intact.

## Deliberately out of scope: search

`search_query_spec` takes a free-text `q` in addition to a spec, which is a
different *kind* of input rather than another shape of the same one, and a
mis-shaped search is not the silent-degradation failure 2.5c is about. Adding
it later is additive: one more enum value and a `q` property.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field as dc_field
from typing import Optional

import litellm
import openai

from .planner import MAX_ATTEMPTS, MAX_TOKENS, MODEL, REQUEST_TIMEOUT, decode_kwargs_for
from .spec_planner import (
    SPEC_TOOL,
    _normalize_spec,
    build_grounding_context,
)

#: The result shapes this router can dispatch. Ordered as the tool presents
#: them, with `rows` first because it is the default and much the commonest.
RESULT_SHAPES = ("rows", "count", "facets", "range")

#: Shapes needing a target field, and the manifest flag that makes a field a
#: legal target for each (the same flags Mosaic's own tools gate on, so a
#: client-side check here fails for the same reason the server would).
FIELD_REQUIRED = {"facets": "aggregatable", "range": "range_queryable"}

ROUTER_TOOL = {
    "type": "function",
    "function": {
        "name": "emit_query",
        "description": (
            "Emit a typed QuerySpec for the instruction AND declare what shape of "
            "answer the instruction asks for. The QuerySpec expresses the FILTER "
            "('which records'); result_shape expresses the ANSWER ('rows, a total, "
            "a per-category breakdown, or a min/max'). Both are always needed: a "
            "filter alone cannot distinguish 'show me the donors in each cohort' "
            "from 'how many donors are in each cohort'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "result_shape": {
                    "type": "string",
                    "enum": list(RESULT_SHAPES),
                    "description": (
                        "'rows': the records themselves ('show me...', 'list...', "
                        "'which samples...'). Use this whenever the user wants to SEE "
                        "records; it is the default.\n"
                        "'count': a single number, when the question asks how many "
                        "matching records there are IN TOTAL ('how many blood samples "
                        "are there?').\n"
                        "'facets': a per-category breakdown -- one count per distinct "
                        "value of `field`. Use this whenever the question says 'per', "
                        "'by', 'each', or 'broken down by' a category ('how many donors "
                        "per cohort?'). A 'count' CANNOT answer this: it returns one "
                        "number, not one per category.\n"
                        "'range': the minimum and maximum of a numeric/date `field` "
                        "('what's the age range of donors?', 'oldest and youngest')."
                    ),
                },
                "field": {
                    "type": "string",
                    "description": (
                        "REQUIRED for result_shape 'facets' (the field to break down "
                        "by) and 'range' (the field to take the min/max of). Must be a "
                        "field on the QuerySpec's own anchor entity, and must be listed "
                        "as a legal target in the grounding's aggregation section. Omit "
                        "entirely for 'rows' and 'count'."
                    ),
                },
                "query_spec": {
                    **SPEC_TOOL["function"]["parameters"],
                    "description": (
                        "The filter: which records the question is about. Emit this for "
                        "EVERY result_shape -- an aggregate is computed over the records "
                        "this selects, so 'how many donors per cohort' still needs an "
                        "anchor of Donor with (here) no criteria. Do NOT include 'sort' "
                        "unless result_shape is 'rows'; ordering is meaningless for a "
                        "count, a breakdown, or a min/max."
                    ),
                },
            },
            "required": ["result_shape", "query_spec"],
        },
    },
}


@dataclass
class RoutedQuery:
    result_shape: str
    query_spec: dict
    field: Optional[str] = None
    #: Client-side adjustments made to the model's raw output, surfaced rather
    #: than applied silently -- callers print these.
    notes: list = dc_field(default_factory=list)


@dataclass
class RouteAttempt:
    routed: Optional[RoutedQuery] = None
    raw_content: Optional[str] = None
    structured_arguments: Optional[str] = None
    finish_reason: Optional[str] = None
    parse_error: Optional[str] = None
    error: Optional[str] = None
    usage: Optional[dict] = None
    latency_s: Optional[float] = None

    @property
    def truncated(self) -> bool:
        return self.finish_reason == "length"


def render_aggregation_grounding(capabilities: dict) -> str:
    """List each entity's legal facet and range targets.

    Without this the model has to guess which fields can be aggregated, and
    `spec_planner`'s existing grounding does not carry the flags -- it renders
    filter operators, which is a different question. The manifest already
    computes `aggregatable`/`range_queryable` per field, so this is surfacing
    data that was present and unused, not new inference.
    """
    lines = [
        "## Aggregation targets",
        "",
        "For result_shape='facets', `field` must be listed under 'facet-able' for the",
        "anchor entity. For result_shape='range', under 'range-able'.",
        "",
    ]
    for entity in sorted(capabilities):
        fields = capabilities[entity].get("fields") or []
        if isinstance(fields, dict):
            fields = list(fields.values())
        facetable = [f["name"] for f in fields if f.get("aggregatable")]
        rangeable = [f["name"] for f in fields if f.get("range_queryable")]
        lines.append(f"- {entity}:")
        lines.append(f"    facet-able: {', '.join(facetable) if facetable else '(none)'}")
        lines.append(f"    range-able: {', '.join(rangeable) if rangeable else '(none)'}")
    return "\n".join(lines)


def _legal_targets(capabilities: dict, anchor: str, flag: str) -> list:
    fields = (capabilities.get(anchor) or {}).get("fields") or []
    if isinstance(fields, dict):
        fields = list(fields.values())
    return [f["name"] for f in fields if f.get(flag)]


def _normalize_routed(raw: dict, capabilities: dict) -> RoutedQuery:
    """Shape-normalize the model's raw arguments. Like `_normalize_spec`, this
    is NOT a validator of the QuerySpec itself -- Mosaic owns that. It checks
    only the routing decision, which Mosaic cannot check for us: the boundary
    validates whatever spec it is handed, but has no way to know the question
    asked for a breakdown rather than rows."""
    if not isinstance(raw, dict):
        raise TypeError(f"expected a JSON object, got {type(raw).__name__}")

    shape = raw.get("result_shape")
    if shape not in RESULT_SHAPES:
        raise ValueError(
            f"'result_shape' must be one of {list(RESULT_SHAPES)}, got {shape!r}"
        )

    spec = _normalize_spec(raw.get("query_spec") or {})
    notes = []

    # `sort` is rejected outright by count/facet/range on Mosaic's side
    # (SORT_NOT_APPLICABLE). The model reliably emits it anyway for phrasings
    # like "per cohort" -- q33 did exactly that. Dropping it is right (it is
    # genuinely meaningless for a scalar or a breakdown), but it is dropped
    # NOISILY: the note is printed, not swallowed, because "I changed your
    # query" should never be invisible.
    if shape != "rows" and spec.get("sort"):
        dropped = ", ".join(s.get("slot", "?") for s in spec["sort"])
        spec = {k: v for k, v in spec.items() if k != "sort"}
        notes.append(
            f"dropped sort ({dropped}): ordering has no meaning for result_shape="
            f"{shape!r}, and Mosaic rejects it outright"
        )

    target = raw.get("field") or None
    flag = FIELD_REQUIRED.get(shape)
    if flag:
        if not target:
            raise ValueError(f"result_shape={shape!r} requires a 'field'")
        legal = _legal_targets(capabilities, spec["anchor"], flag)
        if target not in legal:
            # Caught here rather than at the boundary purely for the error
            # text: Mosaic would reject it too, but this can name the legal
            # set for THIS anchor, which is what a retry needs.
            raise ValueError(
                f"field {target!r} is not {flag} on {spec['anchor']!r}; legal targets: "
                f"{legal or '(none)'}"
            )
    elif target:
        notes.append(f"ignored field={target!r}: not used by result_shape={shape!r}")
        target = None

    return RoutedQuery(result_shape=shape, query_spec=spec, field=target, notes=notes)


def request_route(
    instruction: str,
    capabilities: dict,
    *,
    model: str = None,
    max_tokens: int = None,
    decode_kwargs: dict = None,
) -> RouteAttempt:
    """One stateless call. No retries -- see `plan_routed_query`.

    Deliberately tool_call-only, unlike `request_spec`'s protocol ladder: the
    protocol ladder exists so the harness can measure a model's structured-
    output reliability, and this is the product path, which has a measured
    answer already (`tool_call`).
    """
    model = model or MODEL
    max_tokens = max_tokens or MAX_TOKENS
    grounding = (
        f"{build_grounding_context(capabilities)}\n\n"
        f"{render_aggregation_grounding(capabilities)}"
    )
    kwargs = decode_kwargs_for(model, decode_kwargs)
    kwargs.update(
        tools=[ROUTER_TOOL],
        tool_choice={"type": "function", "function": {"name": "emit_query"}},
    )

    started = time.monotonic()
    try:
        response = litellm.completion(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": _ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": f"{grounding}\n\n## Instruction\n{instruction}"},
            ],
            timeout=REQUEST_TIMEOUT,
            **kwargs,
        )
    except openai.APIError as e:
        return RouteAttempt(
            error=f"{type(e).__name__}: {e}", latency_s=time.monotonic() - started
        )

    latency = time.monotonic() - started
    choice = response.choices[0]
    attempt = RouteAttempt(
        raw_content=choice.message.content,
        finish_reason=choice.finish_reason,
        usage=dict(response.usage) if getattr(response, "usage", None) else None,
        latency_s=latency,
    )
    tool_calls = getattr(choice.message, "tool_calls", None)
    if tool_calls:
        attempt.structured_arguments = tool_calls[0].function.arguments
        try:
            attempt.routed = _normalize_routed(
                json.loads(attempt.structured_arguments), capabilities
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            attempt.parse_error = f"{type(e).__name__}: {e}"
    return attempt


_ROUTER_SYSTEM_PROMPT = """You translate a natural-language question about a \
biomedical entity graph into (a) a typed QuerySpec expressing the filter and \
(b) the shape of answer the question asks for.

Ground every entity name, field name, and operator ONLY in the capability \
manifest provided. Never invent a name that is not in the grounding, and never \
use an operator the grounding does not list as legal for that specific field. \
Never guess a filter VALUE's spelling -- when a field's legal values are listed \
in the grounding, use one of them exactly.

Choosing result_shape is as important as the filter, and getting it wrong \
produces a confidently wrong answer rather than an error. The decisive question \
is what the user wants BACK:
- records to look at -> 'rows'
- one number, how many in total -> 'count'
- one number PER CATEGORY -> 'facets' (with the category as `field`)
- the smallest and largest value of a field -> 'range' (with that field)

A question containing 'per', 'by', 'each', or 'broken down by' followed by a \
category is almost always 'facets', NOT 'count': a single total cannot express \
a per-category breakdown, so answering such a question with 'count' or 'rows' \
loses exactly the information asked for."""


def plan_routed_query(instruction: str, capabilities: dict) -> RoutedQuery:
    """Retrying facade for the product surface. Mirrors `plan_query_spec`."""
    last = None
    for _ in range(MAX_ATTEMPTS):
        last = request_route(instruction, capabilities)
        if last.error:
            raise RuntimeError(
                f"Call to model {MODEL!r} failed -- check the provider's API key env var "
                f"is set (see exon/README.md) and that the model string is valid for that "
                f"provider. Original error: {last.error}"
            )
        if last.routed is not None:
            return last.routed

    detail = last.parse_error or f"content: {(last.raw_content or '')[:400]!r}"
    if last.truncated:
        detail = f"response truncated (finish_reason=length) before completing; {detail}"
    raise RuntimeError(
        f"Model {MODEL!r} produced no usable routed query in {MAX_ATTEMPTS} attempt(s) "
        f"-- {detail}"
    )
