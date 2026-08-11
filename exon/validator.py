"""Dry-run validator: reject, don't approximate.

Stops a plausible-looking but wrong plan from ever reaching the live GraphQL endpoint.

Field-name vocabulary (mosaic#149, fixed upstream in 7669fac/PR#150): the server now accepts
BOTH the LinkML slot name (`sample_type`) and the camelCase spelling exposed on the entity type
(`sampleType`), and raises `UNKNOWN_FILTER_FIELD` on anything else rather than silently matching
zero rows. This validator mirrors that: it resolves either spelling through `hippoSchema` --
never by guessing a transformation -- and pre-empts the server's three error classes so a bad
plan is caught before execution rather than after.
"""
from .ops import FilterStep, RelatedLookupStep, QueryPlan

SUPPORTED_FILTER_OPS = ("EQ", "IN")  # FilterOp enum has no gt/lt/ne/contains -- mosaic#96, open

# Computed at read time from the provenance log rather than stored as columns (sec9 §9.7), so
# they are absent from hippoSchema's slot list and the server rejects filtering on them with a
# pointer to `asOf`. Named explicitly so the plan gets that same actionable message instead of a
# generic "unknown field".
COMPUTED_TEMPORAL_FIELDS = frozenset({"created_at", "updated_at", "created_by", "updated_by"})


class ValidationError(Exception):
    pass


def _slot_index(entity_fields: dict) -> dict:
    """Map every accepted spelling -> canonical slot name.

    Built from the live schema's own slot names (both the slot name and its camelCase form),
    so no transformation is ever guessed in the direction the server doesn't support.
    """
    index = {}
    for slot in entity_fields:
        index[slot] = slot
        head, *rest = slot.split("_")
        index[head + "".join(w.capitalize() for w in rest)] = slot
    return index


def resolve_field(entity_fields: dict, name: str) -> str | None:
    """Canonical slot name for either accepted spelling, or None if unrecognized."""
    return _slot_index(entity_fields).get(name)


def validate_plan(plan: QueryPlan, hippo_schema: dict, capability_manifest: dict) -> None:
    """Raises ValidationError with a specific reason on the first violation found."""
    for i, step in enumerate(plan.steps):
        if isinstance(step, FilterStep):
            _validate_filter_step(i, step, hippo_schema)
        elif isinstance(step, RelatedLookupStep):
            _validate_related_lookup_step(i, step, plan)
        else:
            raise ValidationError(f"step {i}: unrecognized op type {type(step)!r}")


def _resolve_or_raise(i: int, entity: str, entity_fields: dict, name: str, what: str) -> str:
    slot = resolve_field(entity_fields, name)
    if slot is not None:
        return slot
    if name in COMPUTED_TEMPORAL_FIELDS:
        raise ValidationError(
            f"step {i}: {entity}.{name} is computed at read time from the provenance log "
            f"rather than stored as a column, so it cannot be filtered on -- use the `asOf` "
            f"argument for transaction-time queries instead"
        )
    raise ValidationError(
        f"step {i}: {what} {name!r} is not a field on {entity}. Known slots (either the slot "
        f"name or its camelCase spelling is accepted): {sorted(entity_fields)}"
    )


def _validate_filter_step(i: int, step: FilterStep, hippo_schema: dict) -> None:
    if step.entity not in hippo_schema:
        raise ValidationError(
            f"step {i}: unknown entity {step.entity!r} -- not present in live hippoSchema"
        )
    entity_fields = hippo_schema[step.entity]["fields"]

    for f in step.filters:
        if f.op not in SUPPORTED_FILTER_OPS:
            raise ValidationError(
                f"step {i}: filter op {f.op!r} is unsupported -- FilterOp only has "
                f"{'/'.join(SUPPORTED_FILTER_OPS)} (mosaic#96, open); rejecting rather than "
                f"approximating"
            )
        slot = _resolve_or_raise(i, step.entity, entity_fields, f.field, "filter field")
        info = entity_fields[slot]
        if info.get("kind") == "reference" and info.get("multivalued"):
            raise ValidationError(
                f"step {i}: {step.entity}.{slot} is a multivalued reference, stored as "
                f"relationship edges rather than a column (ADR-0002), so it cannot be filtered "
                f"on -- use a related_lookup step (relatedTo) scoped to already-identified ids"
            )

    for sf in step.select_fields:
        _resolve_or_raise(i, step.entity, entity_fields, sf, "select_fields entry")

    if step.forward_relation:
        rel_field = step.forward_relation.get("field")
        rel_slot = _resolve_or_raise(
            i, step.entity, entity_fields, rel_field, "forward_relation field"
        )
        info = entity_fields[rel_slot]
        if info["kind"] != "reference":
            raise ValidationError(
                f"step {i}: forward_relation field {rel_slot!r} is not a reference field on "
                f"{step.entity} (kind={info['kind']!r})"
            )
        if info.get("multivalued"):
            raise ValidationError(
                f"step {i}: forward_relation field {rel_slot!r} is multivalued -- forward "
                f"nested selection is for single-valued references; use a related_lookup step "
                f"for relationship-table-backed multivalued references"
            )
        target_entity = info["targetEntityType"]
        target_fields = hippo_schema.get(target_entity, {}).get("fields", {})
        for sf in step.forward_relation.get("select_fields", []):
            _resolve_or_raise(
                i, target_entity, target_fields, sf, "forward_relation select_fields entry"
            )


def _validate_related_lookup_step(i: int, step: RelatedLookupStep, plan: QueryPlan) -> None:
    if not (0 <= step.source_step < i):
        raise ValidationError(
            f"step {i}: source_step ({step.source_step}) must reference an earlier step in "
            f"the same plan -- a related_lookup can only be scoped to already-identified ids, "
            f"never an unfiltered scan"
        )
    if step.client_filter is not None and step.client_filter.op not in SUPPORTED_FILTER_OPS:
        raise ValidationError(
            f"step {i}: client_filter op {step.client_filter.op!r} unsupported"
        )
    # relationship_type is the relationships-table's own value (e.g. "input_samples"); relatedTo
    # accepts no predicate on the referenced entity (mosaic#148, open) -- which is exactly why
    # client_filter is a separate, explicit field rather than folded into the lookup call.
