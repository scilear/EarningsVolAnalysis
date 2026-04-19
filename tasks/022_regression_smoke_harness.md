# Task 022: Regression Smoke Harness

## Complexity

`medium`

## Objective

Add a small but real regression harness around the current earnings workflow so future roadmap work
does not quietly break the operator path.

## Scope

- Cover the critical CLI/test-data path
- Cover at least one non-NVDA ticker path
- Cover the report-generation path
- Keep runtime short enough for repeated use during active development

## Deliverables

- Focused smoke/regression tests
- A documented command to run the smoke slice
- Assertions around output shape, not just process exit

## Acceptance Criteria

- Smoke suite runs in the project `.venv`
- It validates at least:
  - regime classification
  - ranking generation
  - report generation
  - generic playbook payload generation
- It is fast enough to run before and after roadmap work on the critical path

## Notes

This task exists to protect the user-facing workflow while batch mode and model changes land.
