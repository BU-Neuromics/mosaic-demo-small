"""Derive the seed context (v000) from a model fingerprint.

This is the mechanism that makes the harness "suitable for whatever model it is pointed at"
without being told the model in advance: the probe measures behaviour, and the seed context's
protocol, decode parameters, and opening OUTPUT_CONTRACT/RECOVERY blocks are chosen from those
measurements rather than hardcoded.
"""
from ..harness.probe import ModelFingerprint, OutputProtocol
from ..planner import DEFAULT_GROUNDING_BODY, DEFAULT_SYSTEM_PROMPT
from .template import BlockKind, ContextArtifact, ContextBlock, DecodeParams


MAX_WORKING_NUM_CTX = 32768


def _working_num_ctx(fingerprint: ModelFingerprint) -> int | None:
    """A usable num_ctx, not the model's theoretical maximum.

    gemma4:12b advertises a 262144-token window; asking Ollama to allocate that much KV cache
    for a ~2k-token prompt would be slow at best and OOM at worst. The seed picks a working
    value large enough for the observed reasoning burn (6-8k completion tokens on this model,
    which is why the default is not 8192 either) and leaves growing it to the tuning loop, which
    can raise it as a decode-parameter change if truncation actually shows up.
    """
    if fingerprint.max_context_tokens is None:
        return MAX_WORKING_NUM_CTX
    return min(fingerprint.max_context_tokens, MAX_WORKING_NUM_CTX)


def seed_context(fingerprint: ModelFingerprint, *, num_ctx: int | None = None) -> ContextArtifact:
    """Build v000 for a probed model."""
    blocks: list[ContextBlock] = []

    # A model that wraps bare output in prose or fences needs to be told not to, explicitly.
    # Seeded only when the probe actually observed the tendency -- an unconditional block is
    # wasted tokens on a model that never does it, and the loop can add one later if needed.
    if fingerprint.preamble_tendency > 0.0:
        blocks.append(
            ContextBlock(
                id="no-prose-wrapper",
                kind=BlockKind.OUTPUT_CONTRACT,
                content=(
                    "Return only the structured plan. Do not prepend an explanation, do not "
                    "wrap it in markdown fences, and do not add commentary after it."
                ),
                rationale=(
                    f"probe measured preamble_tendency={fingerprint.preamble_tendency:.0%} for "
                    f"this model -- it wraps bare output in prose or fences that often enough "
                    f"to be worth an explicit contract"
                ),
                addresses_failures=["prose_wrapper", "markdown_fence", "no_tool_call"],
            )
        )

    # Below-perfect determinism at temperature 0 caps achievable reliability no matter what the
    # context says. Record it in the artifact so a later reader knows the ceiling was known,
    # rather than wondering why the loop plateaued.
    if fingerprint.determinism_at_temp_0 < 1.0:
        blocks.append(
            ContextBlock(
                id="determinism-ceiling-note",
                kind=BlockKind.RECOVERY,
                content=(
                    "When more than one plan would satisfy the instruction, prefer the one "
                    "using the fewest steps and the filters stated most explicitly in the "
                    "instruction."
                ),
                rationale=(
                    f"probe measured determinism_at_temp_0="
                    f"{fingerprint.determinism_at_temp_0:.0%}; this model varies between "
                    f"samples, so the context nudges it toward the same choice each time "
                    f"rather than relying on decoding alone"
                ),
                addresses_failures=["nondeterministic"],
            )
        )

    protocol = OutputProtocol(fingerprint.recommended_protocol)
    decode = DecodeParams(
        temperature=0.0,
        seed=0,
        num_ctx=num_ctx if num_ctx is not None else _working_num_ctx(fingerprint),
    )
    # Only spend the model's context on stop sequences it actually honours.
    if fingerprint.honours_stop_sequences:
        decode.stop = []

    artifact = ContextArtifact(
        version=0,
        parent_version=None,
        fingerprint_id=fingerprint.id,
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        grounding_body=DEFAULT_GROUNDING_BODY,
        blocks=blocks,
        decode_params=decode,
        protocol=protocol,
        changelog=(
            f"seeded from probe of {fingerprint.model} (fingerprint {fingerprint.id}): "
            f"protocol={protocol.value}, determinism="
            f"{fingerprint.determinism_at_temp_0:.0%}, preamble_tendency="
            f"{fingerprint.preamble_tendency:.0%}"
        ),
    )
    artifact.validate()
    return artifact
