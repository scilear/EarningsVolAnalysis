id: T017
title: Symmetric butterfly

objective:
  Add a symmetric butterfly structure for overpriced-move / ATM pin regimes.

context:
  Need butterfly for pin-risk trades when iron condors are not desired.

inputs:
  - Option chain data
  - Current strategy builders

outputs:
  - New symmetric butterfly builder
  - Integration with scoring
  - Tests

prerequisites:
  - T022 (recommended)

dependencies:
  - T022

non_goals:
  - No broken-wing behavior

requirements:
  - Only when symmetric strike topology exists
  - Deterministic leg ordering
  - Flows through EV, CVaR, convexity, alignment

acceptance_criteria:
  - Structure builds when valid
  - Tests cover: normal, missing wing, sparse grid
  - Reports display correctly

tests:
  unit:
    - test_symmetric_build
    - test_missing_wing
    - test_sparse_strikes
  integration:
    - Full pipeline with butterfly

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Completed in 2026
  - Part of structure coverage

failure_modes:
  - No symmetric strikes → structure not built
  - Invalid topology → clear error