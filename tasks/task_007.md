id: T007
title: Earnings research workbook

objective:
  Create a workbook for ad-hoc earnings event analysis using the replay framework.

context:
  Analysts need interactive tools to explore historical earnings events and test hypotheses.

inputs:
  - Historical earnings data from T006
  - Scenario fixtures

outputs:
  - Interactive workbook (Jupyter/observable)
  - Template for common analyses
  - Export helpers

prerequisites:
  - T002, T006 completed

dependencies:
  - T002, T006

non_goals:
  - Automated trading integration
  - Production reporting

requirements:
  - Load and display event outcomes
  - Filter by date, ticker, regime
  - Calculate realized vs implied moves
  - Export to common formats

acceptance_criteria:
  - Workbook loads and displays data
  - Filters work correctly
  - Export produces valid output

tests:
  unit:
    - test_workbook_filters
    - test_export_format
  integration:
    - Load dataset, filter, export

definition_of_done:
  - Workbook functional
  - Task marked complete in docs/TASKS.md

notes:
  - TODO: ASK FABIEN for implementation details

failure_modes:
  - Missing data → graceful empty state
  - Export error → clear error message