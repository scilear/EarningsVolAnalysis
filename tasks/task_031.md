id: T031
title: Calibration loop

objective:
  Implement weekly calibration loop with edge ratio accuracy, TYPE accuracy, and no-trade audit.

context:
  Need regular calibration to ensure predictions remain accurate.

inputs:
  - T030 outcome tracking
  - Historical calibration data

outputs:
  - Weekly calibration script
  - Edge ratio accuracy metrics
  - TYPE accuracy metrics
  - No-trade audit

prerequisites:
  - T030

dependencies:
  - T030

non_goals:
  - No automated trading changes

requirements:
  - Weekly execution
  - Edge ratio accuracy tracking
  - TYPE accuracy tracking
  - No-trade pattern audit

acceptance_criteria:
  - Calibration runs weekly
  - Metrics calculated
  - Audit complete

tests:
  unit:
    - test_calibration_metrics
    - test_no_trade_audit
  integration:
    - Full calibration loop

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Calibration task
  - TODO: ASK FABIEN for schedule details

failure_modes:
  - Missing data → skip week