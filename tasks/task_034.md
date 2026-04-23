id: T034
title: Charm exposure

objective:
  Add charm exposure diagnostics to the microstructure layer.

context:
  Macro binary workflows need a proxy for delta drift as expiry approaches,
  especially in short-DTE windows.

inputs:
  - Option chain with strike, iv, option type, and open interest
  - Spot and time-to-expiry

outputs:
  - `compute_charm_exposure(chain, spot, t)` in analytics gamma module
  - Net charm exposure surfaced in report diagnostics

prerequisites:
  - T022 completed

dependencies:
  - T022

non_goals:
  - No intraday charm forecasting engine
  - No regime retraining

requirements:
  - Deterministic one-day finite difference on delta
  - Follow existing dealer-sign convention
  - Include unit coverage

acceptance_criteria:
  - Net charm appears in microstructure diagnostics
  - Existing gamma tests remain green
  - New charm checks pass

tests:
  unit:
    - event_vol_analysis/tests/test_gamma.py
  integration:
    - Covered via main/report snapshot wiring

definition_of_done:
  - Code and tests merged
  - Task marked complete in docs/TASKS.md

notes:
  - Implemented as delta(t-1 day) - delta(t), aggregated by OI and sign.

failure_modes:
  - Near-expiry rows degrade to zero contribution to avoid instability.
