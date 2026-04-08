# Task 005: Storage Schema Extension

## Objective

Extend the current SQLite storage so event metadata and realized outcomes can be attached to quote
snapshots.

## Complexity

- band: `strong`
- recommended agent: Codex or Sonnet

## Dependencies

- requires: `001_event_schema_foundation.md`
- requires: `002_event_dataset_and_outcomes.md`

## Deliverables

- Proposed additive schema update for event metadata tables or columns
- Migration-safe implementation plan
- Query patterns for reconstructing an event before and after its catalyst

## Acceptance Criteria

- Existing quote storage remains backward-compatible or has a safe migration path
- The schema can link one option snapshot to one event identity and timeline position
- The schema supports recording realized move and realized IV changes
- The implementation avoids destructive rewrites of existing stored data
