id: T038
title: Macro binary event outcomes store

objective:
  Add a persistent macro-event outcomes layer for event-type tail-rate checks.

context:
  K-012 activation logic requires evidence of prior analogous tail outcomes by
  event type. Earnings outcomes table is not the right store for this.

inputs:
  - Operator-provided macro event outcome fields
  - Event type taxonomy (geopolitical, fomc, election, regulatory)

outputs:
  - File-backed store at `data/macro_event_outcomes/`
  - Query helper `query_event_type_tail_rate(event_type, threshold_sd=1.0)`
  - CLI `scripts/update_macro_event_outcome.py` for add/query operations

prerequisites:
  - T002 completed

dependencies:
  - T002

non_goals:
  - No live auto-population from market feeds in this phase
  - No modification of existing earnings outcomes workflow

requirements:
  - Additive-only implementation
  - Deterministic ratio and threshold behavior
  - Optional VIX quartile filtering support
  - Unit test coverage for add/load/query paths

acceptance_criteria:
  - Records persist as JSON files and load correctly
  - Tail-rate query returns counts, rate, and binary min-2 flag
  - CLI add/query commands run successfully

tests:
  unit:
    - event_vol_analysis/tests/test_macro_outcomes.py
  integration:
    - CLI dry usage via script entrypoint

definition_of_done:
  - Code and tests merged
  - Task marked complete in docs/TASKS.md

notes:
  - Store supports future conditioning dimensions via additive fields.

failure_modes:
  - Invalid event_type or quartile inputs are rejected with explicit errors.
