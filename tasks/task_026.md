id: T026
title: Positioning proxy

objective:
  Implement positioning proxy from OI, P/C ratio, drift, max pain for UNDER/BALANCED/CROWDED labeling.

context:
  Need positioning metrics for trade sizing and risk.

inputs:
  - Option chain data (OI, P/C)
  - Market data for drift

outputs:
  - OI concentration metric
  - P/C ratio
  - Drift vs sector
  - Max pain calculation
  - Positioning label (UNDER/BALANCED/CROWDED)

prerequisites:
  - None

dependencies:
  - None

non_goals:
  - No new structures

requirements:
  - Calculate OI concentration
  - Calculate P/C ratio
  - Calculate drift vs sector
  - Calculate max pain
  - Label: UNDER/BALANCED/CROWDED

acceptance_criteria:
  - All metrics calculated
  - Label assigned correctly

tests:
  unit:
    - test_oi_concentration
    - test_pc_ratio
    - test_drift_vs_sector
    - test_max_pain
    - test_positioning_label
  integration:
    - Full pipeline with positioning

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Playbook alignment task
  - TODO: ASK FABIEN for implementation details

failure_modes:
  - Missing OI data → mark as unavailable