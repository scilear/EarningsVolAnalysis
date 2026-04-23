id: T037
title: Regime-conditioned edge ratio for macro event types

objective:
  Extend edge-ratio diagnostics with macro event-type conditioning and optional
  VIX quartile filtering.

context:
  Macro events should not share a single unconditional denominator across
  different catalyst types. Conditioning improves signal quality when historical
  analogs exist.

inputs:
  - Base implied/conditional expected move
  - Macro event type
  - Optional VIX quartile
  - Macro outcomes store history

outputs:
  - `compute_macro_conditioned_edge_ratio(...)` helper
  - Tail-rate-conditioned denominator path when history is sufficient
  - Fallback path when history is insufficient

prerequisites:
  - T038 completed

dependencies:
  - T038

non_goals:
  - No model retraining
  - No override of base earnings edge-ratio path

requirements:
  - Base edge-ratio always available
  - Conditioning only enabled when >=2 tail analogs exist
  - Include history counts and fallback note in result payload
  - Unit tests for both conditioned and fallback paths

acceptance_criteria:
  - Conditioned function returns adjusted ratio when historical gate passes
  - Function returns explicit fallback metadata when gate fails
  - Tests pass for conditioned and insufficient-history scenarios

tests:
  unit:
    - event_vol_analysis/tests/test_edge_ratio.py
  integration:
    - N/A (helper-level addition)

definition_of_done:
  - Code, tests, and docs updated
  - Task marked complete in docs/TASKS.md

notes:
  - Conditioning scales primary denominator by observed tail rate.

failure_modes:
  - Missing/insufficient macro history explicitly degrades to unconditioned path.
