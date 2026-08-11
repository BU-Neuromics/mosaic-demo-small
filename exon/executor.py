"""Executes a validated QueryPlan against the live GraphQL endpoint.

Must never be called on a plan that hasn't passed validator.validate_plan -- this module
does no safety checking of its own, by design (that's the validator's job, done once,
before any execution).
"""
from .ops import FilterStep, RelatedLookupStep, QueryPlan
from .schema import graphql_query


def _value_to_gql(value) -> str:
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(_value_to_gql(v) for v in value) + "]"
    return str(value)


def _filters_to_gql(filters, filter_mode: str) -> str:
    parts = [
        f'{{field: "{f.field}", value: {_value_to_gql(f.value)}, op: {f.op}}}' for f in filters
    ]
    return f"filters: [{', '.join(parts)}], filterMode: {filter_mode}"


def _to_camel(slot_name: str) -> str:
    """hippoSchema slot name -> GraphQL output field name (e.g. "brain_region" ->
    "brainRegion"). GraphQL output *selection* requires the camelCase form -- unlike filter
    `field` values, which accept either spelling since mosaic#149/PR#150. Keeping this
    conversion in one place, rather than asking the planner to know both vocabularies, is
    what stopped this confusion from becoming the planner's problem too. Idempotent, so an
    already-camelCase name passes through unchanged."""
    head, *rest = slot_name.split("_")
    return head + "".join(word.capitalize() for word in rest)


def execute_plan(plan: QueryPlan, endpoint: str, hippo_schema: dict) -> dict:
    results = {}
    for i, step in enumerate(plan.steps):
        if isinstance(step, FilterStep):
            results[i] = _execute_filter_step(step, endpoint, hippo_schema)
        elif isinstance(step, RelatedLookupStep):
            results[i] = _execute_related_lookup_step(step, results, endpoint)
        else:
            raise TypeError(f"step {i}: unexecutable op type {type(step)!r}")
    return {"steps": results, "final": results[len(plan.steps) - 1]}


def _execute_filter_step(step: FilterStep, endpoint: str, hippo_schema: dict) -> dict:
    # Read the accessor name from hippoSchema -- never guess it (the same "don't guess a
    # name, read it" discipline that mosaic#149 taught this pipeline the hard way).
    accessor = hippo_schema[step.entity]["accessor_name"]
    fields = ["id"] + [_to_camel(f) for f in step.select_fields if f != "id"]
    if step.forward_relation:
        rel = step.forward_relation
        rel_fields = " ".join(
            _to_camel(f) for f in rel.get("select_fields", ["id"])
        )
        fields.append(f'{_to_camel(rel["field"])} {{ id {rel_fields} }}')
    filter_clause = _filters_to_gql(step.filters, step.filter_mode) if step.filters else ""

    # Paginate until every matching record is retrieved -- returning just one page and
    # silently treating it as complete is exactly the failure mode this whole pipeline
    # exists to prevent (see cross_cutting.pagination in the capability manifest, and q20's
    # own note: "total exceeds the default page size -- a complete answer requires
    # pagination"). The planner's requested `limit` sets the page size, not a result cap.
    items = []
    offset = 0
    total = None
    while True:
        args = [a for a in [filter_clause, f"limit: {step.limit}", f"offset: {offset}"] if a]
        query = f'{{ {accessor}({", ".join(args)}) {{ total items {{ {" ".join(fields)} }} }} }}'
        data = graphql_query(endpoint, query)[accessor]
        total = data["total"]
        items.extend(data["items"])
        if len(items) >= total or not data["items"]:
            break
        offset += step.limit
    return {"total": total, "items": items}


def _execute_related_lookup_step(step: RelatedLookupStep, results: dict, endpoint: str) -> dict:
    source = results[step.source_step]
    ids = [item["id"] for item in source["items"]]
    matches = {}
    call_count = 0
    for entity_id in ids:
        query = (
            f'{{ relatedTo(id: "{entity_id}", relationshipType: '
            f'"{step.relationship_type}") {{ entityId entityType relationshipType data }} }}'
        )
        data = graphql_query(endpoint, query)
        call_count += 1
        related = data["relatedTo"]
        if step.client_filter is not None:
            f = step.client_filter
            related = [r for r in related if r["data"].get(f.field) == f.value]
        if related:
            matches[entity_id] = related
    return {"call_count": call_count, "matches": matches}
