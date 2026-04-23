id: T035
title: By-strike GEX breakdown

objective:
  Expose strike-level GEX concentration and pin-strike candidates.

context:
  Aggregate net/abs GEX hides concentration structure that matters for pin-risk
  interpretation.

inputs:
  - Strike-level GEX map from chain aggregation

outputs:
  - Strike-level GEX list for report output
  - `identify_pin_strikes(gex_by_strike, threshold_pct=0.15)` helper
  - Pin-strike section in HTML report

prerequisites:
  - T022 completed

dependencies:
  - T022

non_goals:
  - No charting library integration required
  - No intraday pin probability model

requirements:
  - Deterministic thresholding relative to abs GEX
  - Preserve existing top-strike diagnostics
  - Include unit coverage

acceptance_criteria:
  - Pin-strike list appears when concentration threshold is met
  - Strike-level GEX rows are visible in report output
  - Existing gamma tests remain green

tests:
  unit:
    - event_vol_analysis/tests/test_gamma.py
  integration:
    - Covered via main/report snapshot wiring

definition_of_done:
  - Code and tests merged
  - Task marked complete in docs/TASKS.md

notes:
  - Implemented with >=15% of abs GEX threshold.

failure_modes:
  - Empty chains produce empty strike outputs without crashing.
