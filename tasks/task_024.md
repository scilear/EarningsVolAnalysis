id: T024
title: Conditional expected move

objective:
  Implement conditional expected move with trimmed mean, 4Q recency, AMC/BMO conditioning.

context:
  Expected move calculation needs playbook-aligned conditioning.

inputs:
  - Historical moves
  - Current expected move logic

outputs:
  - Trimmed mean calculation
  - 4-quarter recency weighting
  - AMC/BMO conditioning
  - Conditional expected move metric

prerequisites:
  - T021

dependencies:
  - T021

non_goals:
  - No new structures

requirements:
  - Trimmed mean (remove outliers)
  - 4Q recency weighting
  - AMC vs BMO separate calculations
  - Conditional on market conditions

acceptance_criteria:
  - Trimmed mean implemented
  - Recency weighting works
  - AMC/BMO conditioning works

tests:
  unit:
    - test_trimmed_mean
    - test_recency_weighting
    - test_amc_bmo_conditioning
  integration:
    - Full pipeline with conditional EM

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Playbook alignment task
  - TODO: ASK FABIEN for implementation details

failure_modes:
  - Insufficient data → fallback to simple mean