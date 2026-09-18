#!/usr/bin/env python3
"""Generate the rows that describe a Mosaic deployment's own schema.

Emits one ``SchemaEntityType`` row per class and one ``SchemaField`` row per
slot, in the shape the ``schema-metadata`` recipe declares.

WHY THE MCP RESOURCE AND NOT GRAPHQL. ``mosaic://schema`` carries all thirteen
attributes Mosaic models about a slot. GraphQL's ``MosaicSlotInfo`` carries
eleven -- it drops ``has_default`` and ``is_external_xref``. Reading GraphQL
would produce a description that is incomplete *by construction*, which is the
one thing this recipe exists to prevent, so the MCP resource is the source.

WHY THE SERVER AND NOT THE SCHEMA FILE. A schema file edited but not migrated
describes data the deployment is not serving. Drift is the failure this guards
against, so the served schema is the honest source. The cost is that a server
must be running to regenerate -- acceptable, since regeneration is wired into
``make migrate``, which already assumes one.

This module deliberately imports nothing from ``exon``: the recipe must apply
to any deployment, and a generator that depended on this project's planner
would not be portable.

    python -m recipes.schema_metadata.generate_schema_metadata -o data/schema_metadata.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

DEFAULT_MCP_URL = "http://localhost:8080/mcp"
MCP_URL_ENV = "MOSAIC_MCP_URL"

#: Every attribute Mosaic models about a slot (`core/schema_typing.py:88`).
#: The recipe carries one column per entry. When the runtime grows another --
#: `inverse_of` arrives with mosaic#210 -- the drift check fails loudly rather
#: than the description quietly going incomplete.
SLOT_ATTRIBUTES = (
    "name",
    "kind",
    "range",
    "role",
    "required",
    "multivalued",
    "identifier",
    "has_default",
    "description",
    "target_entity_type",
    "enum_name",
    "is_external_xref",
    "enum_values",
)

#: The recipe's own classes. Excluded by default: self-description is
#: consistent but roughly doubles the rows and answers a question no
#: researcher asked. `--include-self` opts in.
META_CLASSES = frozenset({"SchemaEntityType", "SchemaField"})


class GeneratorError(RuntimeError):
    """The schema could not be read. Distinct from 'the schema is empty'."""


def mcp_url() -> str:
    return os.environ.get(MCP_URL_ENV, "").strip() or DEFAULT_MCP_URL


async def _read_schema_resource() -> dict[str, Any]:
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise GeneratorError(
            "Reading the schema needs the `mcp` package: pip install -r exon/requirements.txt"
        ) from exc

    url = mcp_url()
    try:
        async with streamable_http_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.read_resource("mosaic://schema")
    except GeneratorError:
        raise
    except Exception as exc:
        raise GeneratorError(
            f"Could not read mosaic://schema at {url}: {exc!r}. Is the server running "
            f"with --mcp? Set {MCP_URL_ENV} to point elsewhere."
        ) from exc

    for content in getattr(result, "contents", []):
        text = getattr(content, "text", None)
        if text:
            return json.loads(text)
    raise GeneratorError("mosaic://schema returned no readable content.")


def _field_row(entity_name: str, slot: dict[str, Any]) -> dict[str, Any]:
    """One SchemaField row. Composed id keeps regeneration idempotent."""
    slot_name = slot["name"]
    row: dict[str, Any] = {
        "id": f"{entity_name}.{slot_name}",
        "entity": entity_name,
        # Inherited from `Entity` and required on the ingest wire format.
        # These rows describe a live schema, so they are always available;
        # retiring one means the slot is gone, which regeneration handles by
        # not emitting it at all.
        "is_available": True,
    }
    for attr in SLOT_ATTRIBUTES:
        value = slot.get(attr)
        if attr == "enum_values":
            # Absent and empty are the same thing for a non-enum slot; keep the
            # column absent rather than writing an empty list, so "which fields
            # constrain their values?" stays a presence test.
            if value:
                row[attr] = list(value)
        elif attr in ("required", "multivalued", "identifier", "has_default", "is_external_xref"):
            # Booleans are declared required in the recipe: a missing flag would
            # read as false, which is an assertion the source never made.
            row[attr] = bool(value)
        elif value is not None:
            row[attr] = value
    return row


def build_rows(
    schema: dict[str, Any],
    accessors: dict[str, str],
    include_self: bool = False,
) -> dict[str, list[dict]]:
    """Walk every class the registry reports -- never a hardcoded list.

    That is what makes this apply to a schema authored later with no code
    change, which is the whole point of shipping it as a recipe.
    """
    entity_types: list[dict[str, Any]] = []
    fields: list[dict[str, Any]] = []

    for class_name in sorted(schema):
        if not include_self and class_name in META_CLASSES:
            continue
        entity = schema[class_name]
        entity_row: dict[str, Any] = {
            "id": class_name,
            "name": class_name,
            "is_available": True,
        }
        if entity.get("description"):
            entity_row["description"] = entity["description"]
        entity_types.append(entity_row)

        for slot in entity.get("fields", []):
            fields.append(_field_row(class_name, slot))

    if not entity_types:
        raise GeneratorError(
            "The schema reported no entity types. That is almost certainly a "
            "connection or configuration problem, not an empty schema."
        )
    # Keyed by ACCESSOR name, not class name: that is the ingest wire format
    # (`donors`, not `Donor`). Read from the schema rather than guessed, so a
    # deployment that overrides an accessor via `hippo_accessor` still works.
    return {
        accessors["SchemaEntityType"]: entity_types,
        accessors["SchemaField"]: fields,
    }


def meta_accessors(schema: dict[str, Any]) -> dict[str, str]:
    """Accessor names for the recipe's own two classes.

    Taken from the served schema when it already carries them. Before the
    recipe is migrated they are absent, so fall back to Mosaic's own
    convention (snake_case, pluralized) -- which is exactly what
    `class_accessor_name` computes.
    """
    resolved: dict[str, str] = {}
    for class_name, default in (
        ("SchemaEntityType", "schema_entity_types"),
        ("SchemaField", "schema_fields"),
    ):
        served = schema.get(class_name, {}).get("accessor_name")
        resolved[class_name] = served or default
    return resolved


def missing_attributes(schema: dict[str, Any]) -> set[str]:
    """Slot attributes the runtime EMITS that the recipe does not carry.

    The shape half of the drift check. A new attribute on the runtime's slot
    model surfaces as a failure rather than a silent omission -- this is what
    catches `inverse_of` when mosaic#210 lands and a schema declares an
    inverse slot.

    KNOWN LIMIT, stated rather than papered over: this compares against what
    the server actually emitted, so an attribute the runtime models but never
    emits for THIS schema is invisible here. `is_external_xref` is exactly
    that today -- the recipe carries the column, no slot in this schema
    populates it, and nothing would notice if the recipe dropped it. Catching
    that would mean reading Mosaic's internals, which would cost the
    portability this recipe exists for.
    """
    seen: set[str] = set()
    for entity in schema.values():
        for slot in entity.get("fields", []):
            seen.update(slot.keys())
    return seen - set(SLOT_ATTRIBUTES)


def _describe_drift(stored: dict, fresh: dict) -> str:
    """Name what changed, so the failure is actionable rather than just loud."""
    notes: list[str] = []
    for collection in sorted(set(stored) | set(fresh)):
        old = {r["id"]: r for r in stored.get(collection, [])}
        new = {r["id"]: r for r in fresh.get(collection, [])}
        added, removed = sorted(set(new) - set(old)), sorted(set(old) - set(new))
        changed = sorted(i for i in set(old) & set(new) if old[i] != new[i])
        for label, ids in (("added", added), ("removed", removed), ("changed", changed)):
            if ids:
                shown = ", ".join(ids[:4]) + (f" (+{len(ids) - 4} more)" if len(ids) > 4 else "")
                notes.append(f"{collection}: {len(ids)} {label} -- {shown}")
    return "; ".join(notes) or "contents differ"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-o", "--output", help="Write here instead of stdout.")
    parser.add_argument(
        "--include-self",
        action="store_true",
        help="Also describe the recipe's own two classes.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the stored description has drifted; write nothing.",
    )
    parser.add_argument(
        "--against",
        default="data/schema_metadata.yaml",
        help="Stored description --check compares the live schema to.",
    )
    args = parser.parse_args(argv)

    try:
        schema = asyncio.run(_read_schema_resource())
    except GeneratorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    unknown = missing_attributes(schema)
    if unknown:
        print(
            "error: the runtime models slot attributes this recipe does not carry: "
            f"{', '.join(sorted(unknown))}.\n"
            "       Add them to the recipe's SchemaField class and to "
            "SLOT_ATTRIBUTES, then regenerate. Leaving them out would make the "
            "description quietly incomplete.",
            file=sys.stderr,
        )
        return 3

    rows = build_rows(schema, meta_accessors(schema), include_self=args.include_self)

    if args.check:
        rows = build_rows(schema, meta_accessors(schema), include_self=args.include_self)
        import yaml

        try:
            with open(args.against, encoding="utf-8") as handle:
                stored = yaml.safe_load(handle) or {}
        except FileNotFoundError:
            print(
                f"error: no stored description at {args.against}. Run `make metadata`.",
                file=sys.stderr,
            )
            return 4

        if stored != rows:
            print(
                f"error: {args.against} has drifted from the live schema.\n"
                f"       {_describe_drift(stored, rows)}\n"
                "       Run `make metadata` to regenerate. A stale description "
                "is worse than none: it answers confidently and wrongly.",
                file=sys.stderr,
            )
            return 5

        print(
            f"ok: {sum(len(v) for v in rows.values())} rows across "
            f"{len(rows)} collections match the live schema; all "
            f"{len(SLOT_ATTRIBUTES)} slot attributes represented."
        )
        return 0

    import yaml

    text = yaml.safe_dump(rows, sort_keys=False, allow_unicode=True, width=100)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
        print(
            f"wrote {args.output}: "
            + ", ".join(f"{len(v)} {k}" for k, v in rows.items())
        )
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
