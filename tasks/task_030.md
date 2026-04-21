id: T030
title: Post-earnings outcome tracking

objective:
  Track realized outcomes after earnings events for calibration.

context:
  Need to compare predictions vs actuals for calibration.

inputs:
  - Historical events with predictions
  - Actual post-event data

outputs:
  - Outcome tracking schema
  - Comparison metrics
  - Calibration data store

prerequisites:
  - T002, T027

dependencies:
  - T002, T027

non_goals:
  - No live trading integration

requirements:
  - Track predicted vs realized
  - IV crush accuracy
  - Move accuracy
  - Structure outcome tracking

acceptance_criteria:
  - Outcomes tracked
  - Comparison metrics available

tests:
  unit:
    - test_outcome_tracking
    - test_comparison_metrics
  integration:
    - Full outcome tracking flow

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Calibration task
  - TODO: ASK FABIEN for tracking details

failure_modes:
  - Missing actual → mark incomplete