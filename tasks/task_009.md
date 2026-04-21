id: T009
title: Macro ETF research workbook

objective:
  Extend the research workbook for macro event analysis on ETF underlyings.

context:
  Apply macro event analysis to ETFs (SPY, QQQ, IWM) for sector/benchmark analysis.

inputs:
  - T007 workbook foundation
  - Macro event taxonomy (T008)
  - ETF underlying data

outputs:
  - Extended workbook for macro on ETFs
  - Template for sector analysis
  - Benchmark comparison helpers

prerequisites:
  - T006, T008 completed

dependencies:
  - T006, T008

non_goals:
  - Live trading signals
  - Portfolio construction

requirements:
  - Load ETF snapshots for macro dates
  - Compare pre/post macro behavior
  - Sector-level analysis template
  - Benchmark-relative metrics

acceptance_criteria:
  - Workbook handles ETF underlyings
  - Macro events analyzed correctly
  - Benchmark comparison works

tests:
  unit:
    - test_etf_load
    - test_benchmark_comparison
  integration:
    - Load macro event, analyze ETF

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - TODO: ASK FABIEN for implementation details

failure_modes:
  - Missing ETF data → graceful empty state
  - Invalid macro date → clear error