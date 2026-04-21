id: T013
title: Test strategy for migration

objective:
  Define how to preserve confidence while the repo moves from earnings tool to generic event engine.

context:
  Need test plan to protect existing behavior during architecture changes.

inputs:
  - Current test suite
  - Architecture roadmap

outputs:
  - Test inventory by layer
  - Smoke/unit/integration recommendations
  - Business invariants list

prerequisites:
  - None

dependencies:
  - None

non_goals:
  - No new test framework

requirements:
  - Identify high-value behaviors to preserve
  - Distinguish stable math from changing interfaces
  - Plan for fixture-based tests

acceptance_criteria:
  - Current behavior identified
  - Test plan distinguishes stable math
  - Fixtures identified

tests:
  unit:
    - N/A (strategy document)
  integration:
    - N/A (strategy document)

definition_of_done:
  - Document complete
  - Task marked complete in docs/TASKS.md

notes:
  - Full strategy documented in tasks/task_013.md
  - See original spec for smoke/unit/integration breakdown

failure_modes:
  - N/A (strategy phase)