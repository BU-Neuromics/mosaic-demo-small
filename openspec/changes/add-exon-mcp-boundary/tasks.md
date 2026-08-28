## 1. Enum-value validation (`exon/validator.py`)

- [ ] 1.1 Add the enum-value check to `_validate_filter_step`: for each filter, when
      `entity_fields[slot].get("enumValues")` is truthy, verify `f.value` (op `EQ`) or every
      element of `f.value` (op `IN`) is a member of that list; raise `ValidationError` naming the
      field and its valid `enumValues` otherwise.
- [ ] 1.2 Correct the `SUPPORTED_FILTER_OPS` comment (currently `# FilterOp enum has no
      gt/lt/ne/contains -- mosaic#96, open`) to state the real, current reason for the EQ/IN-only
      scope (see `design.md` Non-Goals), not a capability gap that no longer fully exists upstream.
- [ ] 1.3 Correct the `asOf` reference inside `_resolve_or_raise`'s computed-temporal-field error
      message so it no longer implies `asOf` is an available option in this pipeline today.
- [ ] 1.4 Add unit tests: a value outside `enumValues` is rejected (`EQ` and `IN`); a value inside
      `enumValues` still passes; a non-enum field is unaffected.

## 2. MCP server (`exon/mcp_server.py`, new)

- [ ] 2.1 Add the official MCP Python SDK to `exon/requirements.txt`; verify its current
      decorator API against the installed version before writing against it (do not copy examples
      predating this change).
- [ ] 2.2 Implement the `hippo-schema` and `capability-manifest` resources, each re-fetching fresh
      on every read via the existing `schema.fetch_hippo_schema`/`schema.load_capability_manifest`.
- [ ] 2.3 Implement `validate_query_plan(plan_json) -> {valid, error?}` wrapping
      `planner._parse_plan` + `validator.validate_plan`, catching `ValidationError` into the
      response rather than raising through the tool boundary.
- [ ] 2.4 Implement `execute_query_plan(plan_json) -> receipt` calling validation unconditionally
      before `executor.execute_plan`, and shaping the result into the receipt schema from
      `design.md` Decision 6.
- [ ] 2.5 Implement the optional `plan_query(instruction) -> plan_json` tool wrapping
      `planner.plan_query` unchanged; document it as experimentation-only.
- [ ] 2.6 Confirm via the MCP Inspector (`mcp dev exon/mcp_server.py` or current equivalent) that
      all resources/tools are visible and callable, and that no tool accepts raw GraphQL or
      performs a mutation.
- [ ] 2.7 Add tests covering: `execute_query_plan` never calls the executor on an invalid plan;
      resource reads reflect a schema change made between two reads (mock or a live re-fetch test).

## 3. Receipts (`exon/receipts.py`, new)

- [ ] 3.1 Implement the receipt shape from `design.md` Decision 6 as the return value of
      `execute_query_plan`.
- [ ] 3.2 Implement `replay_receipt(receipt) -> receipt`: fresh schema/manifest fetch, re-validate,
      re-execute if valid, explicit failure if not.
- [ ] 3.3 Implement `compare_receipts(a, b) -> diff` per `design.md` Decision 8.
- [ ] 3.4 Add tests: replay against an unchanged fixture reproduces the same result; replay against
      a fixture whose enum value was removed from the schema fails validation explicitly, not
      silently; compare reports the expected per-step deltas.

## 4. Documentation

- [ ] 4.1 Update `exon/README.md` with the MCP server (how to run it, what it exposes), the
      corrected validator comments' rationale, and the receipt/replay/compare workflow.
- [ ] 4.2 Update `DEMO.md` with a runnable MCP-boundary demo step (e.g. via the MCP Inspector) once
      implemented.

## 5. Validation

- [ ] 5.1 `openspec validate add-exon-mcp-boundary --strict` passes.
- [ ] 5.2 All existing tests (harness + validator/executor/planner) remain green after the enum
      check and comment corrections land.
