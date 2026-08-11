"""Typed query-plan ops. An LLM planner emits exactly these shapes -- never free-text GraphQL.

See openspec/changes/add-exon-query-planner/design.md, Decision 2 (op catalog).
"""
from dataclasses import dataclass, field
from typing import Optional, Union


@dataclass
class FieldFilter:
    field: str  # A field on the entity. Either the hippoSchema slot name ("sample_type")
    #             or its camelCase spelling ("sampleType") is accepted upstream since
    #             mosaic#149/PR#150; the validator resolves both through hippoSchema and
    #             rejects anything else. Prefer slot names -- resolve, never guess.
    value: object
    op: str = "EQ"  # "EQ" | "IN" -- anything else is unsupported (mosaic#96)


@dataclass
class FilterStep:
    """Root query: list an entity type with filters, optionally selecting a forward
    single-valued reference's fields in the same call (e.g. Sample.donor)."""

    entity: str
    filters: list = field(default_factory=list)  # list[FieldFilter]
    filter_mode: str = "AND"
    select_fields: list = field(default_factory=list)
    forward_relation: Optional[dict] = None  # {"field": "donor", "select_fields": [...]}
    limit: int = 100


@dataclass
class RelatedLookupStep:
    """Reverse relationship-existence lookup (relatedTo), bounded to already-identified ids
    from a prior step's result. relatedTo has no server-side predicate (mosaic#148), so any
    narrowing on the referenced entities' own fields MUST be an explicit client_filter here,
    never silently folded into the relatedTo call itself."""

    source_step: int  # index into plan.steps whose result ids feed this lookup
    relationship_type: str
    client_filter: Optional[FieldFilter] = None


Step = Union[FilterStep, RelatedLookupStep]


@dataclass
class QueryPlan:
    instruction: str
    steps: list  # list[Step], in order
