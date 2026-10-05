## ADDED Requirements

### Requirement: One command starts Mosaic, Exon's turn service, and Aperture's web client together

`run-chat-demo.sh` SHALL start and supervise three services — Mosaic (GraphQL plus the
`converse_query_spec` capability), Exon's turn-taking HTTP service, and Aperture's web client — as
a single command, reusing its existing preflight (port-conflict detection naming the offending
process, and startup-owner verification) for the new Aperture service exactly as it already does
for Mosaic and Exon. All three SHALL be torn down together on exit, including on an interrupted or
failed startup.

#### Scenario: A port conflict on any of the three services fails fast and names the cause

- **WHEN** the port configured for Mosaic, Exon's turn service, or Aperture's web client is already
  held by another process at launch
- **THEN** the script exits before starting anything, naming the specific port, the offending PID,
  and that process's command, rather than silently reusing or failing against a foreign process

#### Scenario: Aperture is pointed at the locally-started Mosaic, not a stale or foreign one

- **WHEN** the script starts Aperture's web client
- **THEN** it is configured, via the same environment-variable mechanism Aperture's own endpoint
  resolution already uses, to reach the Mosaic instance the script itself just started, and
  startup waits for and verifies Aperture's dev server is answering before reporting the demo
  ready

#### Scenario: One interrupt tears down all three services

- **WHEN** the script is interrupted (e.g. Ctrl-C) or exits for any reason after starting one or
  more services
- **THEN** every service the script started is terminated, matching the existing cleanup-trap
  behavior already proven for the Mosaic/Exon pair
