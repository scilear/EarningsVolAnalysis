id: T033
title: Vanna exposure by underlying

objective:
  Add vanna exposure diagnostics to the microstructure layer.

context:
  Macro binary workflows need a proxy for dealer flow sensitivity when IV and
  spot move together.

inputs:
  - Option chain with strike, iv, option type, and open interest
  - Spot and time-to-expiry

outputs:
  - `compute_vanna_exposure(chain, spot, t)` in analytics gamma module
  - Net vanna exposure surfaced in report diagnostics

prerequisites:
  - T022 completed

dependencies:
  - T022

non_goals:
  - No model-based flow forecasting
  - No live trading automation

requirements:
  - Deterministic finite-difference implementation
  - Follow existing dealer-sign convention
  - Include unit coverage

acceptance_criteria:
  - Net vanna appears in microstructure diagnostics
  - Existing gamma tests remain green
  - New vanna checks pass

tests:
  unit:
    - event_vol_analysis/tests/test_gamma.py
  integration:
    - Covered via main/report snapshot wiring

definition_of_done:
  - Code and tests merged
  - Task marked complete in docs/TASKS.md

notes:
  - Implemented with finite-difference delta sensitivity to IV bump.

failure_modes:
  - Missing IV/OI rows return degraded exposure quality, not hard failure.
