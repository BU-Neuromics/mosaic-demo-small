"""The tuned artifact: a versioned, diffable context whose prose is editable but whose
schema-derived facts are rendered live at run time."""

from .template import (  # noqa: F401
    BlockKind,
    ContextArtifact,
    ContextBlock,
    ContextPatch,
    DecodeParams,
    REQUIRED_PLACEHOLDERS,
    TemplateError,
)
