# exon-context-harness Specification Delta

## ADDED Requirements

### Requirement: The harness stays with its fixtures until it grades the shipped path

The reliability harness SHALL NOT be extracted while it grades a path that is
being retired. It SHALL remain with the evaluation cases it scores against until
it has been re-based onto the artifact the planner actually emits, because the
before-and-after comparison the harness exists to provide is only available in
the repository where both paths are present.

Extracting the runtime ahead of the harness SHALL NOT be treated as extracting
the harness. The two are separable because only the harness depends on the
retired path; that dependency is what times its move, and nothing else.

#### Scenario: The runtime moves and the harness does not

- **WHEN** the turn-path runtime is extracted into its own package
- **THEN** the harness and the evaluation cases remain where they are, and
  continue to grade against the same wire contract across the new boundary

#### Scenario: The harness is not carried while it depends on the retired path

- **WHEN** an extraction of the harness is proposed before it has been re-based
  onto the emitted artifact
- **THEN** it is refused, on the grounds that the harness still resolves slots
  through the retired validator and would arrive unable to grade anything

### Requirement: Evaluation cases are reachable without being copied

The harness SHALL locate its case set through a configured path rather than by
copying the cases across the boundary, once the runtime and the harness are in
different repositories. Two copies of a case set are two answers to the same
question, and the one that is not regenerated becomes wrong silently.

#### Scenario: The harness reads cases it does not own

- **WHEN** the harness runs against a case set held in another repository
- **THEN** it resolves them through the configured path and grades normally,
  with no copy of those cases inside the harness's own repository
