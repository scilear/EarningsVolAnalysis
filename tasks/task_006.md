id: T006
title: Event replay framework

objective:
  Enable replay of historical events for backtesting and calibration.

context:
  Need to load historical snapshots and evaluate them through the playbook.

inputs:
  - Historical event data (from T005 storage)
  - Test scenarios

outputs:
  - Replay engine to load and evaluate historical events
  - Comparison helpers (baseline vs post-event)
  - Outcome aggregation

prerequisites:
  - T002, T005 completed

dependencies:
  - T002, T005

non_goals:
  - No live market data integration on replay

requirements:
  - Load event by identifier
  - Evaluate through existing playbook pipeline
  - Compare pre vs post event results
  - Aggregate outcomes across events

acceptance_criteria:
  - Can replay a stored event through the pipeline
  - Can compare evaluation horizons
  - Outcomes aggregated correctly

tests:
  unit:
    - test_event_loader
    - test_horizon_comparison
  integration:
    - Replay multiple historical events

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - TODO: ASK FABIEN for implementation details

failure_modes:
  - Missing event data → raise error
  - Incomplete snapshot → log warning, skip