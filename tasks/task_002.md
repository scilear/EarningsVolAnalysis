id: T002
title: Event dataset and outcomes

objective:
  Design the storage model needed to evaluate playbooks historically rather than only on one live snapshot.

context:
  Current system works on live market data. Need to store and replay historical events for backtesting and calibration.

inputs:
  - Research requirements for event replay
  - Current SQLite schema

outputs:
  - Proposed schema document in docs/research/architecture/event_dataset_and_outcomes_schema.md
  - Additive tables: event_registry, event_snapshot_binding, event_surface_metrics
  - Additive tables: event_evaluation_horizon, event_realized_outcome, structure_replay_outcome

prerequisites:
  - T001 completed

dependencies:
  - T001

non_goals:
  - No destructive redesign of existing schema
  - No real-time data flow changes

requirements:
  - Schema can answer "what was known before the event?"
  - Schema can answer "what happened after the event?"
  - Support multiple evaluation horizons
  - Support structure-level PnL replay under standardized exits
  - Additive-only changes (CREATE TABLE IF NOT EXISTS)

acceptance_criteria:
  - Design document exists and describes all tables
  - Query paths documented for pre/post-event questions
  - Can be implemented incrementally on top of current SQLite store

tests:
  unit:
    - N/A (design document only)
  integration:
    - N/A (design document only)

definition_of_done:
  - Design document complete
  - Task marked complete in docs/TASKS.md

notes:
  - Proposed design in docs/research/architecture/event_dataset_and_outcomes_schema.md
  - Six additive tables proposed
  - Favor additive changes over destructive redesign

failure_modes:
  - N/A (design phase)