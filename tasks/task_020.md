id: T020
title: Earnings calendar auto-ingestion

objective:
  Auto-discover next earnings event date when user doesn't supply one.

context:
  Reduce operator error by inferring the next earnings date from yfinance.

inputs:
  - Ticker
  - yfinance earnings calendar

outputs:
  - Auto-discovery logic
  - Ambiguity handling (exit code 2)
  - Staleness detection

prerequisites:
  - None

dependencies:
  - None

non_goals:
  - No permanent calendar storage

requirements:
  - Auto-discover next earnings date
  - Handle ambiguous results (multiple dates)
  - Handle stale data
  - Document source assumptions

acceptance_criteria:
  - Discovered date clearly surfaced
  - Ambiguity stops with exit code 2
  - Batch mode can use this path

tests:
  unit:
    - test_auto_discovery
    - test_ambiguity_handling
    - test_staleness_detection
  integration:
    - Full pipeline with auto-ingestion

definition_of_done:
  - All 4 tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Completed in 2026
  - Uses yfinance API
  - Source limitations documented in USER_GUIDE

failure_modes:
  - No earnings data → exit code 1
  - Ambiguous → exit code 2