id: T023
title: IV Rank + IV Percentile dual classifier

objective:
  Implement both IV Rank and IV Percentile for more nuanced vol classification.

context:
  IV Rank and IV Percentile are both used in the playbook. Need both classifiers.

inputs:
  - Historical IV data
  - Current IV-only classifier

outputs:
  - IV Rank implementation
  - IV Percentile implementation
  - Dual classification output
  - Playbook integration

prerequisites:
  - T022

dependencies:
  - T022

non_goals:
  - No new structures

requirements:
  - IV Rank = (current IV - 52W low) / (52W high - 52W low)
  - IV Percentile = % of days in last 52W with lower IV
  - Both classifiers available
  - Playbook uses dual classification

acceptance_criteria:
  - Both metrics calculated
  - Playbook can reference either
  - Tests cover normal and edge cases

tests:
  unit:
    - test_iv_rank
    - test_iv_percentile
    - test_dual_classification
  integration:
    - Full pipeline with dual classifier

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Playbook alignment task
  - TODO: ASK FABIEN for implementation details

failure_modes:
  - Insufficient history → calculate available