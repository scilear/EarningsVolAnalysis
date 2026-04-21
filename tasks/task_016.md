id: T016
title: Ticker-agnostic audit

objective:
  Audit and fix the system to work with any ticker, not just NVDA.

context:
  System was hardcoded for NVDA. Need generalization.

inputs:
  - Full codebase audit

outputs:
  - Ticker-agnostic implementation
  - Multi-ticker tests

prerequisites:
  - None

dependencies:
  - None

non_goals:
  - No new features

requirements:
  - All tickers supported
  - No hardcoded NVDA
  - Generalize option chain handling

acceptance_criteria:
  - Works with non-NVDA tickers
  - Tests cover multiple tickers

tests:
  unit:
    - test_ticker_agnostic
    - test_multiple_tickers
  integration:
    - Full pipeline with different tickers

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Completed in 2026
  - Required for batch mode (T019)

failure_modes:
  - Hardcoded ticker → fail test