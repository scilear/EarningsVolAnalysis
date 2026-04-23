id: T036
title: Macro event vehicle support (SPY, XOP, XLE, VIX options)

objective:
  Add explicit support classification for macro event vehicles and surface
  caveats where forward-model handling is required.

context:
  Macro workflows need clarity on which underlyings are validated and where
  interpretation is qualitative only (e.g., VIX-family options).

inputs:
  - Macro ticker symbols used in scans/research

outputs:
  - Vehicle classifier module for macro support metadata
  - Regime output fields with support flags and notes
  - Report section showing vehicle class and forward-model requirement

prerequisites:
  - T033/T034/T035 completed

dependencies:
  - T033
  - T034
  - T035

non_goals:
  - No full VIX forward-pricing implementation in this task
  - No trade automation changes

requirements:
  - Support SPY/XOP/XLE as validated macro ETF vehicles
  - Flag VIX-family as supported with forward-model caveat
  - Mark unknown vehicles as unsupported with explicit note
  - Cover with unit tests

acceptance_criteria:
  - Regime snapshot includes macro vehicle support metadata
  - Report displays macro vehicle class and caveat note when applicable
  - Tests validate ETF, VIX-family, and unsupported classifications

tests:
  unit:
    - event_vol_analysis/tests/test_macro_vehicles.py
    - event_vol_analysis/tests/test_vol_regime.py
  integration:
    - event_vol_analysis/tests/test_main_ticker_agnostic.py

definition_of_done:
  - Code, tests, and docs updated
  - Task marked complete in docs/TASKS.md

notes:
  - VIX support is classification/caveat-only in this phase.

failure_modes:
  - Unsupported tickers degrade to explicit "other/unsupported" metadata.
