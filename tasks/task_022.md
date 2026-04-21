id: T022
title: Regression smoke harness

objective:
  Add regression harness to protect critical path while roadmap work continues.

context:
  Need tests to ensure roadmap changes don't break the operator path.

inputs:
  - Critical CLI path
  - Current test suite

outputs:
  - Focused smoke tests
  - Test command documented

prerequisites:
  - T015

dependencies:
  - T015

non_goals:
  - Full test suite

requirements:
  - Cover critical CLI path
  - Cover non-NVDA ticker
  - Cover report generation
  - Fast enough for repeated use

acceptance_criteria:
  - Runs in .venv
  - Validates: regime, ranking, report, playbook
  - Fast execution

tests:
  unit:
    - test_smoke_regime
    - test_smoke_ranking
    - test_smoke_report
    - test_smoke_playbook
  integration:
    - smoke command runs

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Completed in 2026
  - Part of P0 trust blockers

failure_modes:
  - Test data unavailable → skip gracefully