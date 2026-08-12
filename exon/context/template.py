"""The tuned artifact.

The context is the ONLY thing the tuning loop may change. Everything else -- test suite, grader,
schema, model weights -- is fixed within a run. That constraint is what makes a score movement
attributable to anything at all.

Two rules are enforced structurally rather than by convention:

1. **Prose is editable; schema facts are not.** The body carries required placeholders that are
   substituted from LIVE introspection at render time. A revision that drops one is rejected,
   because hardcoding schema facts into the artifact is how hallucinated field names get
   laundered into something that looks authoritative.

2. **Decode parameters are part of the artifact,** on equal footing with prose. On local models
   `temperature`/`seed`/`num_ctx` usually dominate wording for reliability -- the num_ctx
   truncation this project hit by hand is exactly that class of bug, and a refiner that can
   rewrite a persona paragraph but not set temperature=0 is crippled.

Plain dataclasses + stdlib json, matching `exon/ops.py`, rather than pydantic: the validation
that matters here (placeholders, size cap, memorization lint) is custom regardless, and one
idiom per package beats two.
"""
import json
import re
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from pathlib import Path

from ..harness.probe import OutputProtocol

REQUIRED_PLACEHOLDERS = frozenset({"{{schema_slots}}", "{{relationship_types}}", "{{limitations}}"})

DEFAULT_MAX_CHARS = 12000


class TemplateError(Exception):
    pass


class BlockKind(str, Enum):
    """Render order is the declaration order below -- stable so the same artifact always
    produces a byte-identical prompt."""

    ROLE = "role"                       # who the model is
    SCHEMA = "schema"                   # how the live schema is presented
    GLOSSARY = "glossary"               # domain term -> schema field
    CONSTRAINT = "constraint"           # a "never do X" rule
    OUTPUT_CONTRACT = "output_contract"  # the exact shape of a valid reply
    RECOVERY = "recovery"               # what to do when unsure
    EXEMPLAR = "exemplar"               # one worked NL -> plan pair


RENDER_ORDER = tuple(BlockKind)


@dataclass
class ContextBlock:
    id: str                          # stable slug, e.g. "no-markdown-fence"
    kind: BlockKind
    content: str
    rationale: str                   # WHY this exists -- required, non-empty
    order: int = 0                   # tie-break within a kind
    enabled: bool = True
    introduced_in_iteration: int = 0
    addresses_failures: list = field(default_factory=list)

    def __post_init__(self):
        if isinstance(self.kind, str):
            self.kind = BlockKind(self.kind)
        if not self.rationale.strip():
            raise TemplateError(
                f"block {self.id!r} has no rationale -- every block must say why it exists, or "
                f"the loop cannot later judge whether it earned its place"
            )


@dataclass
class DecodeParams:
    temperature: float = 0.0
    top_p: float | None = None
    top_k: int | None = None
    repeat_penalty: float | None = None
    num_ctx: int | None = None
    seed: int | None = 0
    stop: list = field(default_factory=list)
    # Ollama-only. For a model with the `thinking` capability this is the single highest-impact
    # setting there is: measured on gemma4:12b, the same request went from 2631 completion tokens
    # with NO tool call (thinking on) to 135 tokens WITH the tool call (thinking off). Left as
    # None for models that have no such mode.
    think: bool | None = None

    def to_litellm_kwargs(self, model: str) -> dict:
        """Only params the provider actually accepts. num_ctx/top_k/repeat_penalty are
        Ollama-specific; sending them elsewhere is an error rather than a no-op."""
        kw = {"temperature": self.temperature}
        if self.top_p is not None:
            kw["top_p"] = self.top_p
        if self.seed is not None:
            kw["seed"] = self.seed
        if self.stop:
            kw["stop"] = list(self.stop)
        if model.startswith("ollama"):
            if self.think is not None:
                kw["think"] = self.think
            if self.num_ctx is not None:
                kw["num_ctx"] = self.num_ctx
            if self.top_k is not None:
                kw["top_k"] = self.top_k
            if self.repeat_penalty is not None:
                kw["repeat_penalty"] = self.repeat_penalty
        return kw


@dataclass
class ContextPatch:
    """What the refiner returns. A patch, never a rewrite -- attribution of which block moved
    which failure code is only possible if changes arrive incrementally."""

    changelog: str = ""
    hypothesis: str = ""
    add_blocks: list = field(default_factory=list)      # list[ContextBlock]
    remove_block_ids: list = field(default_factory=list)
    modify_blocks: list = field(default_factory=list)   # list[ContextBlock], matched by id
    toggle_blocks: dict = field(default_factory=dict)   # {block_id: enabled}
    decode_params: DecodeParams | None = None
    protocol: OutputProtocol | None = None

    def change_count(self) -> int:
        """Block-level churn. Decode/protocol changes are counted separately by the caller,
        since one of those is allowed in place of three block edits."""
        return (
            len(self.add_blocks)
            + len(self.remove_block_ids)
            + len(self.modify_blocks)
            + len(self.toggle_blocks)
        )

    def touches_decoding(self) -> bool:
        return self.decode_params is not None or self.protocol is not None


@dataclass
class ContextArtifact:
    version: int
    fingerprint_id: str
    system_prompt: str
    grounding_body: str
    blocks: list = field(default_factory=list)          # list[ContextBlock]
    decode_params: DecodeParams = field(default_factory=DecodeParams)
    protocol: OutputProtocol = OutputProtocol.TOOL_CALL
    parent_version: int | None = None
    changelog: str = ""

    def __post_init__(self):
        if isinstance(self.protocol, str):
            self.protocol = OutputProtocol(self.protocol)
        if isinstance(self.decode_params, dict):
            self.decode_params = DecodeParams(**self.decode_params)
        self.blocks = [
            b if isinstance(b, ContextBlock) else ContextBlock(**b) for b in self.blocks
        ]

    # ---- validation ----------------------------------------------------------------

    def validate(self, *, max_chars: int = DEFAULT_MAX_CHARS) -> None:
        missing = sorted(p for p in REQUIRED_PLACEHOLDERS if p not in self.grounding_body)
        if missing:
            raise TemplateError(
                f"grounding_body is missing required placeholder(s) {missing}. These are "
                f"substituted from live introspection at render time; dropping one would let "
                f"schema facts be hardcoded (i.e. hallucinated) into the artifact."
            )
        size = len(self.system_prompt) + len(self.grounding_body) + sum(
            len(b.content) for b in self.blocks if b.enabled
        )
        if size > max_chars:
            raise TemplateError(
                f"context is {size} chars, over the {max_chars} budget -- unbounded growth is "
                f"the signature of accumulating special cases; remove a block that isn't "
                f"earning its place instead of adding another"
            )
        ids = [b.id for b in self.blocks]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise TemplateError(f"duplicate block ids: {dupes}")

    # ---- rendering -----------------------------------------------------------------

    def render(self, hippo_schema: dict, capability_manifest: dict) -> tuple[str, str]:
        """-> (system_prompt, grounding). Deterministic: same artifact + same schema always
        yields a byte-identical pair, which is what makes iteration-to-iteration comparison
        meaningful."""
        from ..planner import (
            render_limitations,
            render_relationship_types,
            render_schema_slots,
        )

        body = self.grounding_body
        for placeholder, value in (
            ("{{schema_slots}}", render_schema_slots(hippo_schema)),
            ("{{relationship_types}}", render_relationship_types(hippo_schema)),
            ("{{limitations}}", render_limitations(capability_manifest)),
        ):
            body = body.replace(placeholder, value)

        rendered_blocks = []
        for kind in RENDER_ORDER:
            for b in sorted(
                (b for b in self.blocks if b.enabled and b.kind is kind),
                key=lambda b: (b.order, b.id),
            ):
                rendered_blocks.append(b.content.strip())
        if rendered_blocks:
            body = body + "\n\n" + "\n\n".join(rendered_blocks)
        return self.system_prompt, body

    # ---- patching ------------------------------------------------------------------

    def apply_patch(self, patch: ContextPatch) -> "ContextArtifact":
        """Returns a NEW artifact at version+1; never mutates in place, so every version stays
        on disk and a regression is diffable after the fact."""
        blocks = {b.id: b for b in self.blocks}

        for bid in patch.remove_block_ids:
            blocks.pop(bid, None)
        for b in patch.modify_blocks:
            block = b if isinstance(b, ContextBlock) else ContextBlock(**b)
            blocks[block.id] = block
        for b in patch.add_blocks:
            block = b if isinstance(b, ContextBlock) else ContextBlock(**b)
            if block.id in blocks:
                raise TemplateError(
                    f"add_blocks would overwrite existing block {block.id!r} -- use "
                    f"modify_blocks to change it, so the change is visible as a modification"
                )
            blocks[block.id] = block
        for bid, enabled in patch.toggle_blocks.items():
            if bid not in blocks:
                raise TemplateError(f"toggle_blocks names unknown block {bid!r}")
            blocks[bid] = replace(blocks[bid], enabled=bool(enabled))

        return ContextArtifact(
            version=self.version + 1,
            parent_version=self.version,
            fingerprint_id=self.fingerprint_id,
            system_prompt=self.system_prompt,
            grounding_body=self.grounding_body,
            blocks=list(blocks.values()),
            decode_params=patch.decode_params or self.decode_params,
            protocol=patch.protocol or self.protocol,
            changelog=patch.changelog,
        )

    # ---- persistence ---------------------------------------------------------------

    def to_dict(self) -> dict:
        d = asdict(self)
        d["protocol"] = self.protocol.value
        d["blocks"] = [{**asdict(b), "kind": b.kind.value} for b in self.blocks]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ContextArtifact":
        return cls(**d)

    def path_in(self, directory: Path) -> Path:
        return Path(directory) / f"v{self.version:03d}.json"

    def save(self, directory: Path) -> Path:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        p = self.path_in(directory)
        if p.exists():
            raise TemplateError(
                f"{p} already exists -- versions are append-only so a regression stays "
                f"inspectable; bump the version instead of overwriting"
            )
        p.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
        return p

    @classmethod
    def load(cls, path: Path) -> "ContextArtifact":
        return cls.from_dict(json.loads(Path(path).read_text()))

    @classmethod
    def latest(cls, directory: Path) -> "ContextArtifact | None":
        files = sorted(Path(directory).glob("v*.json"))
        return cls.load(files[-1]) if files else None

    def assert_fingerprint(self, fingerprint_id: str) -> None:
        """A context is only meaningful paired with the model it was fitted to. Carrying one
        across models without re-probing silently measures the wrong thing."""
        if self.fingerprint_id != fingerprint_id:
            raise TemplateError(
                f"context v{self.version:03d} was fitted to fingerprint "
                f"{self.fingerprint_id!r} but the current target is {fingerprint_id!r} -- "
                f"re-probe rather than reusing it"
            )


# ---- memorization lint ------------------------------------------------------------------

_WORD = re.compile(r"[A-Za-z0-9']+")
VERBATIM_SPAN_WORDS = 8


def memorization_findings(
    artifact: ContextArtifact, case_ids: list, instructions: list
) -> list:
    """Reasons this artifact looks like an answer key rather than a general instruction.

    The natural failure mode of the loop: a refiner shown "case q20 must filter brain_region to
    hippocampus" can simply write that sentence into the context. The score rises and nothing
    generalizes. Holdout scoring catches it statistically; this catches it structurally.
    """
    haystack = " ".join(
        [artifact.system_prompt, artifact.grounding_body]
        + [b.content for b in artifact.blocks if b.enabled]
    )
    findings = []

    for cid in case_ids:
        if re.search(rf"\b{re.escape(cid)}\b", haystack):
            findings.append(f"names test case id {cid!r}")

    hay_words = [w.lower() for w in _WORD.findall(haystack)]
    hay_spans = {
        " ".join(hay_words[i : i + VERBATIM_SPAN_WORDS])
        for i in range(max(0, len(hay_words) - VERBATIM_SPAN_WORDS + 1))
    }
    for instr in instructions:
        words = [w.lower() for w in _WORD.findall(instr)]
        for i in range(max(0, len(words) - VERBATIM_SPAN_WORDS + 1)):
            span = " ".join(words[i : i + VERBATIM_SPAN_WORDS])
            if span in hay_spans:
                findings.append(
                    f"quotes {VERBATIM_SPAN_WORDS}+ consecutive words of a test question: "
                    f"...{span}..."
                )
                break
    return findings
