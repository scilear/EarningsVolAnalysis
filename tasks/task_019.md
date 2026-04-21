id: T019
title: Multi-ticker batch mode

objective:
  Turn the CLI into a watchlist scanner that evaluates multiple tickers in one run.

context:
  Operator needs to evaluate multiple earnings in one execution.

inputs:
  - Watchlist file or comma-separated tickers
  - Optional event dates per ticker

outputs:
  - Batch CLI entry point
  - Watchlist parser
  - Summary table output
  - Per-ticker failure handling

prerequisites:
  - T016, T020

dependencies:
  - T016, T020

non_goals:
  - New analysis features

requirements:
  - Process list of tickers with event dates or auto-discovery
  - Single failure doesn't abort batch
  - Output: ticker, event date, regime, top structure, score, warnings
  - Reuses single-ticker pipeline

acceptance_criteria:
  - One command processes multiple tickers
  - Bad ticker handled gracefully
  - Summary output complete
  - All tests pass

tests:
  unit:
    - test_batch_parser
    - test_batch_summary_format
    - test_partial_failure_handling
  integration:
    - Full batch execution

definition_of_done:
  - All 5 tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Completed in 2026
  - Uses resolve_next_earnings_date() for auto-discovery
  - Exit code 2 on ambiguous dates
  - event_date_source tracked in summary

failure_modes:
  - Empty watchlist → exit code 1
  - All failures → exit code 1