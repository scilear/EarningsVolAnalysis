id: T018
title: Capital-normalized ranking

objective:
  Normalize strategy rankings by capital allocation for fair comparison.

context:
  Rankings should be comparable across different capital requirements.

inputs:
  - Strategy candidates
  - Capital requirements per structure

outputs:
  - Capital normalization logic
  - Adjusted scoring

prerequisites:
  - T017 (recommended)

dependencies:
  - T017

non_goals:
  - No new structures

requirements:
  - Account for capital requirements
  - Fair comparison across structures

acceptance_criteria:
  - Normalized scores account for capital
  - Rankings reflect capital efficiency

tests:
  unit:
    - test_capital_normalization
  integration:
    - Full pipeline with ranking

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Completed in 2026

failure_modes:
  - Zero capital → handle gracefully