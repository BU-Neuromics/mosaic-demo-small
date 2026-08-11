"""Node [E]: refine the context.

The refiner returns a **patch**, never a rewritten context. Attribution -- which block moved which
failure code -- is only possible if changes arrive incrementally; a wholesale rewrite destroys it.

Bounded on purpose: at most MAX_BLOCK_CHANGES block edits, or one decode/protocol change, per
iteration. Beyond that, causality is unrecoverable and a score movement cannot be traced to
anything.

Two things the refiner is structurally prevented from doing, rather than merely told not to:
- It cannot touch code, the test suite, or the schema. Those types are not in its output schema.
- It cannot embed an answer key. Every candidate runs the memorization lint, and the holdout split
  was never in its input to begin with.
"""
import json
import os

import litellm
import openai

from ..context.template import (
    BlockKind,
    ContextBlock,
    ContextPatch,
    DecodeParams,
    TemplateError,
    memorization_findings,
)
from ..harness.probe import OutputProtocol

REFINER_MODEL = os.environ.get("EXON_REFINER_MODEL", "anthropic/claude-opus-5-20251101")
REFINER_MAX_TOKENS = int(os.environ.get("EXON_REFINER_MAX_TOKENS", "8192"))
MAX_BLOCK_CHANGES = int(os.environ.get("EXON_MAX_BLOCK_CHANGES", "3"))
MAX_EXEMPLARS = int(os.environ.get("EXON_MAX_EXEMPLARS", "8"))


class RefineError(Exception):
    pass


_BLOCK_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "stable kebab-case slug"},
        "kind": {"type": "string", "enum": [k.value for k in BlockKind]},
        "content": {"type": "string", "description": "the text inserted into the context"},
        "rationale": {"type": "string", "description": "why this block exists -- required"},
        "addresses_failures": {
            "type": "array",
            "items": {"type": "string"},
            "description": "failure codes from the report this block is meant to reduce",
        },
        "order": {"type": "integer"},
    },
    "required": ["id", "kind", "content", "rationale"],
}

REVISION_TOOL = {
    "type": "function",
    "function": {
        "name": "emit_context_revision",
        "description": (
            "Propose a bounded patch to the context. Return ONLY changes; unchanged blocks are "
            "carried over automatically."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "changelog": {
                    "type": "string",
                    "description": "what you changed, in one or two sentences",
                },
                "hypothesis": {
                    "type": "string",
                    "description": (
                        "which failure codes you expect to drop, and why. This is checked against "
                        "the next iteration's result."
                    ),
                },
                "add_blocks": {"type": "array", "items": _BLOCK_SCHEMA},
                "modify_blocks": {"type": "array", "items": _BLOCK_SCHEMA},
                "remove_block_ids": {"type": "array", "items": {"type": "string"}},
                "decode_params": {
                    "type": ["object", "null"],
                    "description": (
                        "Decode settings. Prefer this over prose for format/determinism failures."
                    ),
                    "properties": {
                        "temperature": {"type": "number"},
                        "top_p": {"type": ["number", "null"]},
                        "top_k": {"type": ["integer", "null"]},
                        "repeat_penalty": {"type": ["number", "null"]},
                        "num_ctx": {"type": ["integer", "null"]},
                        "seed": {"type": ["integer", "null"]},
                    },
                },
                "protocol": {
                    "type": ["string", "null"],
                    "enum": [p.value for p in OutputProtocol] + [None],
                    "description": "A stricter output protocol constrains decoding; prose does not.",
                },
            },
            "required": ["changelog", "hypothesis"],
        },
    },
}

SYSTEM = f"""You tune the CONTEXT given to a small local model that turns natural-language
questions into typed query plans over a bioinformatics metadata graph. The context is the ONLY
thing you may change: the test suite, the grader, the schema, and the model weights are fixed.

You will be shown a classified failure report. Propose a bounded patch by calling
emit_context_revision.

Rules:
- At most {MAX_BLOCK_CHANGES} block changes, OR one decode/protocol change, per patch. More than
  that and nobody can tell which change helped.
- Prefer, in order: (1) protocol/decode changes for format and determinism failures; (2) schema
  presentation for hallucinated or wrong field names; (3) a glossary entry for domain-vocabulary
  misses; (4) a constraint for systematic over- or under-constraining; (5) exemplars LAST -- they
  are the most token-expensive and the most overfit-prone.
- The context must be able to SHRINK. If a block from the previous iteration did not reduce the
  failure code it targeted, propose removing it. Unbounded growth eventually exceeds the model's
  context window and degrades everything at once.
- Write general instructions, never case-specific answers. Do NOT name a test case, quote a test
  question at length, or state the expected answer for a particular question. A context that
  encodes answers raises the score without improving anything, and such a patch is rejected
  automatically.
- Every block needs a rationale and the failure codes it targets.
"""


def _blocks_from(raw_list, iteration: int) -> list:
    out = []
    for b in raw_list or []:
        out.append(
            ContextBlock(
                id=b["id"],
                kind=BlockKind(b["kind"]),
                content=b["content"],
                rationale=b.get("rationale", ""),
                order=int(b.get("order", 0)),
                introduced_in_iteration=iteration,
                addresses_failures=list(b.get("addresses_failures") or []),
            )
        )
    return out


def parse_patch(raw: dict, iteration: int) -> ContextPatch:
    decode = raw.get("decode_params")
    proto = raw.get("protocol")
    return ContextPatch(
        changelog=raw.get("changelog", ""),
        hypothesis=raw.get("hypothesis", ""),
        add_blocks=_blocks_from(raw.get("add_blocks"), iteration),
        modify_blocks=_blocks_from(raw.get("modify_blocks"), iteration),
        remove_block_ids=list(raw.get("remove_block_ids") or []),
        decode_params=DecodeParams(**{k: v for k, v in decode.items() if v is not None})
        if decode
        else None,
        protocol=OutputProtocol(proto) if proto else None,
    )


def check_patch(patch: ContextPatch, candidate, cases) -> None:
    """Reject a patch that breaks the bounds or looks like an answer key. Raises RefineError."""
    if patch.change_count() > MAX_BLOCK_CHANGES and not patch.touches_decoding():
        raise RefineError(
            f"patch changes {patch.change_count()} blocks, over the {MAX_BLOCK_CHANGES} limit -- "
            f"a larger change makes score movement unattributable"
        )
    if patch.touches_decoding() and patch.change_count() > MAX_BLOCK_CHANGES:
        raise RefineError(
            "patch changes decoding AND more blocks than allowed in one iteration"
        )

    exemplars = [b for b in candidate.blocks if b.kind is BlockKind.EXEMPLAR and b.enabled]
    if len(exemplars) > MAX_EXEMPLARS:
        raise RefineError(
            f"{len(exemplars)} exemplars exceeds the cap of {MAX_EXEMPLARS} -- exemplars are the "
            f"most overfit-prone block kind"
        )

    findings = memorization_findings(
        candidate, [c.id for c in cases], [c.instruction for c in cases]
    )
    if findings:
        raise RefineError(
            "candidate looks like an answer key rather than a general instruction: "
            + "; ".join(findings[:3])
        )

    candidate.validate()


def propose_context_revision(
    artifact,
    bundle,
    cases,
    *,
    iteration: int,
    model: str = None,
) -> tuple:
    """-> (candidate_artifact, patch). Raises RefineError on a patch that must not be applied.

    `cases` is used ONLY for the memorization lint (ids and instruction text to check against);
    it is never sent to the refiner.
    """
    model = model or REFINER_MODEL
    current = json.dumps(
        {
            "version": artifact.version,
            "protocol": artifact.protocol.value,
            "decode_params": {
                k: v
                for k, v in artifact.decode_params.__dict__.items()
                if v not in (None, [], {})
            },
            "system_prompt": artifact.system_prompt,
            "grounding_body": artifact.grounding_body,
            "blocks": [
                {
                    "id": b.id,
                    "kind": b.kind.value,
                    "enabled": b.enabled,
                    "content": b.content,
                    "rationale": b.rationale,
                    "addresses_failures": b.addresses_failures,
                }
                for b in artifact.blocks
            ],
        },
        indent=2,
    )

    user = (
        f"## Current context (v{artifact.version:03d})\n```json\n{current}\n```\n\n"
        f"{bundle.to_markdown()}\n"
    )

    try:
        response = litellm.completion(
            model=model,
            max_tokens=REFINER_MAX_TOKENS,
            temperature=0,
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            tools=[REVISION_TOOL],
            tool_choice={
                "type": "function",
                "function": {"name": "emit_context_revision"},
            },
        )
    except openai.APIError as e:
        raise RefineError(
            f"refiner call to {model!r} failed -- set that provider's API key env var. "
            f"Original error: {e}"
        ) from e

    calls = response.choices[0].message.tool_calls
    if not calls:
        raise RefineError(
            f"refiner {model!r} did not call emit_context_revision; content: "
            f"{(response.choices[0].message.content or '')[:300]!r}"
        )

    patch = parse_patch(json.loads(calls[0].function.arguments), iteration)
    try:
        candidate = artifact.apply_patch(patch)
    except TemplateError as e:
        raise RefineError(f"patch could not be applied: {e}") from e
    check_patch(patch, candidate, cases)
    return candidate, patch
