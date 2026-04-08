# Task 002: Event Dataset And Outcomes

## Objective

Design the storage model needed to evaluate playbooks historically rather than only on one live
snapshot.

## Deliverables

- Proposed storage schema for event metadata
- Proposed storage schema for pre-event and post-event option surface snapshots
- Outcome schema for realized move, realized IV changes, and standardized structure PnL

## Acceptance Criteria

- The schema can answer: \"what was known before the event?\"
- The schema can answer: \"what happened after the event?\"
- The schema supports multiple evaluation horizons
- The schema supports structure-level PnL replay under standardized exits
- The design can be implemented incrementally on top of the current SQLite store

## Notes

Favor additive schema changes over destructive redesign.

## Proposed Design Output

Primary design document:

- `docs/research/architecture/event_dataset_and_outcomes_schema.md`

This design introduces additive tables for:

- event identity and scheduling metadata (`event_registry`)
- pre/post snapshot binding to existing quote timestamps (`event_snapshot_binding`)
- snapshot-level derived metrics (`event_surface_metrics`)
- standardized evaluation horizons (`event_evaluation_horizon`)
- realized move and IV outcome tracking (`event_realized_outcome`)
- structure-level replay PnL under versioned assumptions (`structure_replay_outcome`)

## Acceptance Criteria Traceability

- The schema can answer: "what was known before the event?"
  - Covered by `event_snapshot_binding` + `option_quotes` + `event_surface_metrics` query path
- The schema can answer: "what happened after the event?"
  - Covered by post-event bindings and `event_realized_outcome`
- The schema supports multiple evaluation horizons
  - Covered by `event_evaluation_horizon` and horizon-keyed outcomes
- The schema supports structure-level PnL replay under standardized exits
  - Covered by `structure_replay_outcome` with assumption/pricing versions
- The design can be implemented incrementally on top of the current SQLite store
  - Covered by additive-only `CREATE TABLE IF NOT EXISTS` approach and phased rollout
