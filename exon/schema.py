"""Live schema grounding: hippoSchema + the capability manifest, fetched fresh every run.

Never cache these across sessions and never assume field names from memory -- mosaic#149
exists precisely because a plausible-looking assumption (the GraphQL camelCase field name)
silently produces a wrong-but-valid-shaped answer instead of an error.
"""
import json
import urllib.request


def graphql_query(endpoint: str, query: str) -> dict:
    payload = {"query": query}
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        result = json.load(resp)
    if "errors" in result:
        raise RuntimeError(f"GraphQL error: {result['errors']}")
    return result["data"]


HIPPO_SCHEMA_QUERY = """
{ hippoSchema { name accessorName description fields { name kind range role required
  multivalued identifier description targetEntityType enumName enumValues }
  relationships { field targetEntityType } } }
"""


def fetch_hippo_schema(endpoint: str) -> dict:
    """{entity_name: {accessor_name, fields: {slot_name: field_info}}}.

    This is the ONLY source of truth for filter field names (mosaic#149) -- never build a
    filter from a GraphQL type's own `__type` field names.
    """
    data = graphql_query(endpoint, HIPPO_SCHEMA_QUERY)
    schema = {}
    for entity in data["hippoSchema"]:
        schema[entity["name"]] = {
            "accessor_name": entity["accessorName"],
            "fields": {f["name"]: f for f in entity["fields"]},
        }
    return schema


def load_capability_manifest(path: str) -> dict:
    with open(path) as f:
        return json.load(f)
