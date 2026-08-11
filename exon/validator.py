"""Dry-run validator: reject, don't approximate.

See openspec/changes/add-exon-query-planner/design.md, Decision 3. This is what stops a
plausible-looking but wrong plan (e.g. a camelCase filter field, or an unsupported op) from
ever reaching the live GraphQL endpoint.
"""
from .ops import FilterStep, RelatedLookupStep, QueryPlan

UNSUPPORTED_FILTER_OPS = {"GT", "LT", "NE", "CONTAINS", "STARTS_WITH", "IS_NULL"}  # mosaic#96


class ValidationError(Exception):
    pass


def validate_plan(plan: QueryPlan, hippo_schema: dict, capability_manifest: dict) -> None:
    """Raises ValidationError with a specific reason on the first violation found."""
    for i, step in enumerate(plan.steps):
        if isinstance(step, FilterStep):
            _validate_filter_step(i, step, hippo_schema)
        elif isinstance(step, RelatedLookupStep):
            _validate_related_lookup_step(i, step, plan)
        else:
            raise ValidationError(f"step {i}: unrecognized op type {type(step)!r}")


def _validate_filter_step(i: int, step: FilterStep, hippo_schema: dict) -> None:
    if step.entity not in hippo_schema:
        raise ValidationError(
            f"step {i}: unknown entity {step.entity!r} -- not present in live hippoSchema"
        )
    entity_fields = hippo_schema[step.entity]["fields"]

    for f in step.filters:
        if f.op not in ("EQ", "IN"):
            raise ValidationError(
                f"step {i}: filter op {f.op!r} is unsupported -- FilterOp enum only has "
                f"EQ/IN (mosaic#96, open); rejecting rather than approximating"
            )
        if f.field not in entity_fields:
            raise ValidationError(
                f"step {i}: filter field {f.field!r} is not a hippoSchema slot on "
                f"{step.entity}. If this looks like a valid GraphQL field, that's the wrong "
                f"vocabulary for a filter (mosaic#149) -- known slots: "
                f"{sorted(entity_fields)}"
            )

    for sf in step.select_fields:
        if sf not in entity_fields:
            raise ValidationError(
                f"step {i}: select_fields entry {sf!r} is not a hippoSchema slot on "
                f"{step.entity} -- known slots: {sorted(entity_fields)}"
            )

    if step.forward_relation:
        rel_field = step.forward_relation.get("field")
        if rel_field not in entity_fields:
            raise ValidationError(
                f"step {i}: forward_relation field {rel_field!r} is not a slot on {step.entity}"
            )
        if entity_fields[rel_field]["kind"] != "reference":
            raise ValidationError(
                f"step {i}: forward_relation field {rel_field!r} is not a reference field "
                f"on {step.entity} (kind={entity_fields[rel_field]['kind']!r})"
            )
        target_entity = entity_fields[rel_field]["targetEntityType"]
        target_fields = hippo_schema.get(target_entity, {}).get("fields", {})
        for sf in step.forward_relation.get("select_fields", []):
            if sf not in target_fields:
                raise ValidationError(
                    f"step {i}: forward_relation select_fields entry {sf!r} is not a "
                    f"hippoSchema slot on {target_entity} -- known slots: "
                    f"{sorted(target_fields)}"
                )


def _validate_related_lookup_step(i: int, step: RelatedLookupStep, plan: QueryPlan) -> None:
    if not (0 <= step.source_step < i):
        raise ValidationError(
            f"step {i}: source_step ({step.source_step}) must reference an earlier step in "
            f"the same plan -- a related_lookup can only be scoped to already-identified ids, "
            f"never an unfiltered scan"
        )
    if step.client_filter is not None and step.client_filter.op not in ("EQ", "IN"):
        raise ValidationError(
            f"step {i}: client_filter op {step.client_filter.op!r} unsupported"
        )
    # No further check needed for relatedTo's own args: relationship_type is a free string
    # (the relationships-table's own relationship_type value, e.g. "input_samples") and
    # relatedTo itself accepts no predicate (mosaic#148) -- that's exactly why client_filter
    # exists as a separate, explicit field rather than being folded into the lookup call.
