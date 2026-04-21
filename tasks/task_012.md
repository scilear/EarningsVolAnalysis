id: T012
title: Dependency and env cleanup

objective:
  Normalize Python environment usage and dependency entry points in the repo.

context:
  Multiple environment paths exist. Need clarity on canonical execution path.

inputs:
  - Current dependency files
  - Current launch scripts

outputs:
  - Canonical .venv path documented
  - Inventory of dependency files
  - Recommendation for consolidation

prerequisites:
  - None

dependencies:
  - None

non_goals:
  - No risky packaging migration
  - No dependency version changes

requirements:
  - Document canonical Python path
  - Identify legacy paths
  - Reduce ambiguity

acceptance_criteria:
  - One clearly documented execution path
  - Legacy paths identified

tests:
  unit:
    - N/A (documentation)
  integration:
    - Verify .venv works

definition_of_done:
  - Documentation complete
  - Task marked complete in docs/TASKS.md

notes:
  - TODO: ASK FABIEN for current state

failure_modes:
  - N/A (documentation)