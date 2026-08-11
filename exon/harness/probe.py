"""Node [0]: capability probe -- what kind of model am I actually talking to?

Runs once before the tuning loop. The requirement is to tune a context without knowing the
target model in advance, so the harness must discover the model's behaviour empirically rather
than assume it.

Deliberately adversarial: a local model's *declared* capability and its actual behaviour diverge
routinely, so the probe's finding always wins over library metadata. This is the direct answer to
the failure that motivated the harness -- `ollama_chat/gemma4:12b` intermittently ignoring a
forced `tool_choice`, which no amount of prose could fix but a protocol downgrade can.

Every check issues PROBE_SAMPLES calls at temperature 0. A protocol tier qualifies only on
unanimous success: anything less is not reliable, and treating "4 out of 5" as support is how you
get a harness that reports a context problem when it actually has a protocol problem.
"""
import hashlib
import json
import os
import re
from dataclasses import dataclass, field, asdict
from enum import Enum

import litellm
import openai

PROBE_SAMPLES = int(os.environ.get("EXON_PROBE_SAMPLES", "5"))
OLLAMA_NUM_CTX = int(os.environ.get("EXON_OLLAMA_NUM_CTX", "32768"))
PROBE_MAX_TOKENS = int(os.environ.get("EXON_PROBE_MAX_TOKENS", "4096"))
# Loaded checks are expensive (a realistic prompt on a local 12B model takes minutes), so they
# default to fewer samples than the cheap isolated checks. They are NOT optional though -- see
# _check_protocol_under_load for why an isolated-only probe is actively misleading.
LOADED_SAMPLES = int(os.environ.get("EXON_PROBE_LOADED_SAMPLES", "3"))
LOADED_MAX_TOKENS = int(os.environ.get("EXON_PROBE_LOADED_MAX_TOKENS", "8192"))


class OutputProtocol(str, Enum):
    """Descending strictness. The strictest tier the model honours unanimously wins."""

    JSON_SCHEMA = "json_schema"
    TOOL_CALL = "tool_call"
    JSON_OBJECT = "json_object"
    DELIMITED = "delimited"
    RAW = "raw"


PROTOCOL_LADDER = (
    OutputProtocol.JSON_SCHEMA,
    OutputProtocol.TOOL_CALL,
    OutputProtocol.JSON_OBJECT,
    OutputProtocol.DELIMITED,
    OutputProtocol.RAW,
)

# A trivially small plan the model is asked to emit in each candidate protocol. Kept minimal on
# purpose: the probe measures whether the model can hit the *format*, not whether it can plan.
_PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "emit_probe",
        "description": "Emit the requested entity name.",
        "parameters": {
            "type": "object",
            "properties": {"entity": {"type": "string"}},
            "required": ["entity"],
        },
    },
}
_PROBE_ASK = 'Return the entity name "Sample".'
_DELIMITED_ASK = (
    'Return the entity name "Sample" wrapped exactly as <answer>Sample</answer>. '
    "Output nothing else."
)
_PREAMBLE_MARKERS = re.compile(
    r"^\s*(sure|certainly|here'?s|here is|of course|okay|ok\b|i'?ll|let me|```)", re.I
)


@dataclass
class ProbeCheck:
    name: str
    passed: int
    total: int
    detail: str = ""
    evidence: list = field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def unanimous(self) -> bool:
        return self.total > 0 and self.passed == self.total


@dataclass
class ModelFingerprint:
    model: str
    honours_system_role: bool
    supports_json_schema: bool
    supports_tool_call: bool
    supports_json_object: bool
    honours_stop_sequences: bool
    determinism_at_temp_0: float
    preamble_tendency: float
    max_context_tokens: int | None
    recommended_protocol: str
    checks: dict
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = self.compute_id()

    def compute_id(self) -> str:
        """Stable hash over the behavioural findings, not over raw evidence.

        A context is only meaningful paired with a fingerprint; carrying one tuned for a
        different model without re-probing is a bug, so this id is what the loop checks.
        """
        payload = json.dumps(
            {
                "model": self.model,
                "honours_system_role": self.honours_system_role,
                "supports_json_schema": self.supports_json_schema,
                "supports_tool_call": self.supports_tool_call,
                "supports_json_object": self.supports_json_object,
                "honours_stop_sequences": self.honours_stop_sequences,
                "recommended_protocol": self.recommended_protocol,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ModelFingerprint":
        return cls(**d)


def _extra(model: str) -> dict:
    """Ollama's num_ctx covers prompt+completion and defaults to 4096 regardless of max_tokens;
    a thinking-capable model exhausts it on reasoning alone and truncates with no error. Only
    meaningful for ollama*, so it is passed conditionally."""
    return {"num_ctx": OLLAMA_NUM_CTX} if model.startswith("ollama") else {}


def _call(model: str, **kwargs) -> object:
    return litellm.completion(
        model=model, temperature=0, max_tokens=PROBE_MAX_TOKENS, **_extra(model), **kwargs
    )


def _text(resp) -> str:
    return (resp.choices[0].message.content or "").strip()


def _check_system_role(model: str) -> ProbeCheck:
    """Does a system instruction actually constrain output? Decides whether exemplars can be
    rendered as chat turns or must be inlined as text."""
    passed, evidence = 0, []
    for _ in range(PROBE_SAMPLES):
        try:
            out = _text(
                _call(
                    model,
                    messages=[
                        {"role": "system", "content": "Reply with exactly: ACK"},
                        {"role": "user", "content": "Go."},
                    ],
                )
            )
        except openai.APIError as e:
            out = f"<error: {e}>"
        evidence.append(out[:200])
        if out.strip().upper().rstrip(".") == "ACK":
            passed += 1
    return ProbeCheck("system_role", passed, PROBE_SAMPLES, evidence=evidence)


def _try_protocol(model: str, protocol: OutputProtocol) -> ProbeCheck:
    """One protocol tier, PROBE_SAMPLES attempts. Qualifies only if unanimous."""
    passed, evidence = 0, []
    for _ in range(PROBE_SAMPLES):
        got = ""
        try:
            if protocol is OutputProtocol.JSON_SCHEMA:
                resp = _call(
                    model,
                    messages=[{"role": "user", "content": _PROBE_ASK}],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "probe",
                            "schema": {
                                "type": "object",
                                "properties": {"entity": {"type": "string"}},
                                "required": ["entity"],
                            },
                        },
                    },
                )
                got = _text(resp)
                ok = json.loads(got).get("entity") == "Sample"
            elif protocol is OutputProtocol.TOOL_CALL:
                resp = _call(
                    model,
                    messages=[{"role": "user", "content": _PROBE_ASK}],
                    tools=[_PROBE_TOOL],
                    tool_choice={"type": "function", "function": {"name": "emit_probe"}},
                )
                calls = resp.choices[0].message.tool_calls
                got = str(calls[0].function.arguments) if calls else _text(resp)
                ok = bool(calls) and json.loads(calls[0].function.arguments).get(
                    "entity"
                ) == "Sample"
            elif protocol is OutputProtocol.JSON_OBJECT:
                resp = _call(
                    model,
                    messages=[
                        {"role": "user", "content": _PROBE_ASK + ' Reply as {"entity": ...}.'}
                    ],
                    response_format={"type": "json_object"},
                )
                got = _text(resp)
                ok = json.loads(got).get("entity") == "Sample"
            elif protocol is OutputProtocol.DELIMITED:
                resp = _call(model, messages=[{"role": "user", "content": _DELIMITED_ASK}])
                got = _text(resp)
                m = re.search(r"<answer>\s*(.*?)\s*</answer>", got, re.S)
                ok = bool(m) and m.group(1).strip() == "Sample"
            else:  # RAW -- last resort: fenced-code or bare extraction
                resp = _call(model, messages=[{"role": "user", "content": _PROBE_ASK}])
                got = _text(resp)
                ok = "Sample" in got
        except (openai.APIError, json.JSONDecodeError, TypeError, ValueError) as e:
            got = f"<error: {type(e).__name__}: {e}>"
            ok = False
        evidence.append(got[:300])
        passed += 1 if ok else 0
    return ProbeCheck(f"protocol:{protocol.value}", passed, PROBE_SAMPLES, evidence=evidence)


def _check_stop_sequences(model: str) -> ProbeCheck:
    passed, evidence = 0, []
    for _ in range(PROBE_SAMPLES):
        try:
            out = _text(
                _call(
                    model,
                    messages=[
                        {"role": "user", "content": "Count: one two THREE four five six."}
                    ],
                    stop=["THREE"],
                )
            )
        except openai.APIError as e:
            out = f"<error: {e}>"
        evidence.append(out[:200])
        if "THREE" not in out.upper():
            passed += 1
    return ProbeCheck("stop_sequences", passed, PROBE_SAMPLES, evidence=evidence)


def _check_determinism(model: str) -> ProbeCheck:
    """The single most important number in a run: it caps achievable reliability. If the model
    is not byte-identical at temperature 0, no amount of context tuning makes it so -- report it
    rather than chase it."""
    outs = []
    for _ in range(PROBE_SAMPLES):
        try:
            outs.append(
                _text(
                    _call(
                        model,
                        messages=[
                            {
                                "role": "user",
                                "content": "Name one brain region in a single word.",
                            }
                        ],
                    )
                )
            )
        except openai.APIError as e:
            outs.append(f"<error: {e}>")
    identical = sum(1 for o in outs if o == outs[0])
    return ProbeCheck(
        "determinism_temp_0",
        identical,
        PROBE_SAMPLES,
        detail=f"{identical}/{PROBE_SAMPLES} byte-identical to the first reply",
        evidence=[o[:120] for o in outs],
    )


def _check_preamble(model: str) -> ProbeCheck:
    """How often the model wraps bare output in prose or fences. Drives whether the seed context
    needs an aggressive OUTPUT_CONTRACT block."""
    wrapped, evidence = 0, []
    for _ in range(PROBE_SAMPLES):
        try:
            out = _text(
                _call(
                    model,
                    messages=[
                        {
                            "role": "user",
                            "content": "Output only the word Sample. No explanation.",
                        }
                    ],
                )
            )
        except openai.APIError as e:
            out = f"<error: {e}>"
        evidence.append(out[:200])
        if _PREAMBLE_MARKERS.match(out) or out.strip() != "Sample":
            wrapped += 1
    # `passed` counts CLEAN replies so rate stays "higher is better" like the other checks.
    return ProbeCheck(
        "preamble", PROBE_SAMPLES - wrapped, PROBE_SAMPLES, evidence=evidence
    )


def _check_protocol_under_load(
    model: str, protocol: OutputProtocol, grounding: str, instruction: str, plan_tool: dict
) -> ProbeCheck:
    """Does the protocol still hold on a REALISTICALLY SIZED request?

    This check exists because the isolated ladder above is actively misleading on its own.
    Measured against ollama_chat/gemma4:12b: every protocol passed 5/5 on a trivial prompt and
    determinism read 100%, yet the same model, on the real ~1800-token grounding with a
    multi-step planning task, intermittently ignored a forced tool_choice and emitted
    markdown-fenced JSON instead. An isolated-only probe would have told the loop "protocol is
    fine, so this must be a prose problem" and sent the refiner to reword instructions that
    were never the cause.

    So: the isolated ladder finds candidates cheaply; this confirms the choice under load.
    """
    passed, evidence = 0, []
    messages = [
        {"role": "system", "content": "Emit a typed query plan. No prose."},
        {"role": "user", "content": f"{grounding}\n\n## Instruction\n{instruction}"},
    ]
    for _ in range(LOADED_SAMPLES):
        got, ok = "", False
        try:
            kwargs = {}
            if protocol is OutputProtocol.TOOL_CALL:
                kwargs = dict(
                    tools=[plan_tool],
                    tool_choice={
                        "type": "function",
                        "function": {"name": plan_tool["function"]["name"]},
                    },
                )
            elif protocol is OutputProtocol.JSON_SCHEMA:
                kwargs = dict(
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "query_plan",
                            "schema": plan_tool["function"]["parameters"],
                        },
                    }
                )
            elif protocol is OutputProtocol.JSON_OBJECT:
                kwargs = dict(response_format={"type": "json_object"})

            resp = litellm.completion(
                model=model,
                temperature=0,
                max_tokens=LOADED_MAX_TOKENS,
                messages=messages,
                **_extra(model),
                **kwargs,
            )
            choice = resp.choices[0]
            calls = getattr(choice.message, "tool_calls", None)
            if protocol is OutputProtocol.TOOL_CALL:
                got = str(calls[0].function.arguments) if calls else (choice.message.content or "")
                ok = bool(calls) and "steps" in json.loads(calls[0].function.arguments)
            else:
                got = choice.message.content or ""
                ok = "steps" in json.loads(got)
            if choice.finish_reason == "length":
                got = f"<truncated: finish_reason=length> {got}"
                ok = False
        except (openai.APIError, json.JSONDecodeError, TypeError, ValueError, IndexError) as e:
            got = f"<error: {type(e).__name__}: {e}>"
            ok = False
        evidence.append(got[:300])
        passed += 1 if ok else 0
    return ProbeCheck(
        f"loaded:{protocol.value}", passed, LOADED_SAMPLES, evidence=evidence
    )


def _context_window(model: str) -> int | None:
    """Best-effort. Guards against silently truncating the context -- a very common cause of
    'it worked yesterday'. None (with a warning) rather than a guess when unavailable."""
    try:
        info = litellm.get_model_info(model)
        return info.get("max_input_tokens") or info.get("max_tokens")
    except Exception:
        pass
    if model.startswith("ollama"):
        try:
            import urllib.request

            tag = model.split("/", 1)[1]
            base = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434")
            req = urllib.request.Request(
                f"{base}/api/show",
                data=json.dumps({"model": tag}).encode(),
                headers={"content-type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                d = json.load(r)
            for k, v in (d.get("model_info") or {}).items():
                if k.endswith(".context_length"):
                    return int(v)
        except Exception:
            return None
    return None


def probe_model(
    model: str,
    *,
    verbose: bool = True,
    load_check: tuple = None,
) -> ModelFingerprint:
    """Run every check and return a persisted-ready fingerprint.

    `load_check` is an optional (grounding, instruction, plan_tool) triple. When supplied, the
    protocol chosen by the cheap isolated ladder is re-verified on a realistically sized
    request, and demoted if it does not hold. Strongly recommended: omitting it can yield a
    confidently wrong protocol choice (see _check_protocol_under_load).
    """
    checks: dict[str, ProbeCheck] = {}

    def log(msg):
        if verbose:
            print(msg, flush=True)

    log(f"Probing {model} ({PROBE_SAMPLES} calls per check)...")

    checks["system_role"] = _check_system_role(model)
    log(f"  system role adherence : {checks['system_role'].passed}/{PROBE_SAMPLES}")

    recommended = None
    for proto in PROTOCOL_LADDER:
        c = _try_protocol(model, proto)
        checks[c.name] = c
        log(f"  protocol {proto.value:<12}: {c.passed}/{PROBE_SAMPLES}"
            f"{'  <-- qualifies' if c.unanimous and recommended is None else ''}")
        if c.unanimous and recommended is None:
            recommended = proto
    if recommended is None:
        recommended = OutputProtocol.RAW
        log("  WARNING: no protocol qualified unanimously; falling back to RAW")

    checks["stop_sequences"] = _check_stop_sequences(model)
    log(f"  stop sequences        : {checks['stop_sequences'].passed}/{PROBE_SAMPLES}")

    checks["determinism_temp_0"] = _check_determinism(model)
    det = checks["determinism_temp_0"].rate
    log(f"  determinism @ temp 0  : {det:.0%}"
        f"{'   <-- CAPS ACHIEVABLE RELIABILITY' if det < 1.0 else ''}")

    checks["preamble"] = _check_preamble(model)
    log(f"  clean (no preamble)   : {checks['preamble'].passed}/{PROBE_SAMPLES}")

    if load_check is not None:
        grounding, instruction, plan_tool = load_check
        log(f"  -- verifying protocol under load ({LOADED_SAMPLES} samples, real grounding) --")
        for proto in PROTOCOL_LADDER:
            if proto not in (
                OutputProtocol.JSON_SCHEMA,
                OutputProtocol.TOOL_CALL,
                OutputProtocol.JSON_OBJECT,
            ):
                continue
            if not checks[f"protocol:{proto.value}"].unanimous:
                continue
            c = _check_protocol_under_load(model, proto, grounding, instruction, plan_tool)
            checks[c.name] = c
            log(f"  loaded {proto.value:<14}: {c.passed}/{LOADED_SAMPLES}")
            if c.unanimous:
                if proto is not recommended:
                    log(f"  NOTE: isolated ladder chose {recommended.value}; under load "
                        f"{proto.value} is the first that holds")
                recommended = proto
                break
        else:
            log("  WARNING: no protocol held unanimously UNDER LOAD -- the isolated ladder's "
                "choice is optimistic; expect format failures the context cannot fix")

    ctx = _context_window(model)
    log(f"  context window        : {ctx if ctx else 'unknown (warning)'}")

    fp = ModelFingerprint(
        model=model,
        honours_system_role=checks["system_role"].unanimous,
        supports_json_schema=checks[f"protocol:{OutputProtocol.JSON_SCHEMA.value}"].unanimous,
        supports_tool_call=checks[f"protocol:{OutputProtocol.TOOL_CALL.value}"].unanimous,
        supports_json_object=checks[f"protocol:{OutputProtocol.JSON_OBJECT.value}"].unanimous,
        honours_stop_sequences=checks["stop_sequences"].unanimous,
        determinism_at_temp_0=checks["determinism_temp_0"].rate,
        preamble_tendency=1.0 - checks["preamble"].rate,
        max_context_tokens=ctx,
        recommended_protocol=recommended.value,
        checks={k: asdict(v) for k, v in checks.items()},
    )
    log(f"  -> protocol={fp.recommended_protocol} fingerprint={fp.id}")
    return fp
