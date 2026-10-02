## ADDED Requirements

### Requirement: converse_query_spec is reachable as a GraphQL mutation, not only an MCP tool

Mosaic SHALL expose the same in-process `converse_query_spec` handler as a GraphQL mutation
(`converseQuerySpec`) on its generated schema's Mutation root, alongside — not replacing — the
existing MCP tool of the same name. The mutation SHALL accept and return the identical
`{utterance, query_spec, turns, edit_turn_id}` request / `{turn, turns, suspended_turn_ids}`
response shapes the MCP tool uses, and SHALL be registered under the same
`MOSAIC_EXON_URL`-configured condition (present only when a conversational planning service is
configured).

#### Scenario: A browser client reaches the capability without an MCP client

- **WHEN** a GraphQL client (e.g. Aperture's urql-based SPA) sends a `converseQuerySpec` mutation
  over the same `/graphql` endpoint it already uses for every other query
- **THEN** it receives the same turn/proposal/clarification/error response shape the MCP tool
  would have returned for an equivalent call, with no MCP session, SSE stream, or separate CORS
  configuration required

#### Scenario: The mutation is absent when no planning service is configured

- **WHEN** `MOSAIC_EXON_URL` is not set
- **THEN** `converseQuerySpec` does not appear on the Mutation root at all, matching the existing
  MCP-tool registration behavior, so a client can treat the mutation's presence in introspection
  as the capability-gate signal (Aperture ADR-0029)
