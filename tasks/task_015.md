id: T015
title: Gamma alignment fix

objective:
  Fix gamma alignment issue in options pricing.

context:
  Gamma calculation had alignment issues causing incorrect risk metrics.

inputs:
  - Option chain data
  - Current gamma implementation

outputs:
  - Fixed gamma calculation
  - Test verification

prerequisites:
  - None

dependencies:
  - None

non_goals:
  - No other Greek changes

requirements:
  - Correct gamma calculation
  - Alignment with industry standards

acceptance_criteria:
  - Gamma values aligned
  - Tests pass

tests:
  unit:
    - test_gamma_computation
  integration:
    - Full pipeline with gamma

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Completed in 2026
  - Part of trust blocker fixes

failure_modes:
  - Invalid input → NaN or error