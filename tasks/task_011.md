id: T011
title: Output contract and reporting bridge

objective:
  Define and implement the output contract for playbook reports.

context:
  Need standardized output for playbook recommendations.

inputs:
  - Policy engine output (T003)
  - Ranking data
  - Market context

outputs:
  - Output schema defining all report fields
  - Report generation module
  - JSON and HTML output formatters

prerequisites:
  - T001, T003, T004 completed

dependencies:
  - T001, T003, T004

non_goals:
  - No real-time dashboard

requirements:
  - Define all output fields
  - Support JSON and HTML formats
  - Include management guidance
  - Structured for programmatic use

acceptance_criteria:
  - Output schema documented
  - JSON output valid
  - HTML output renders correctly
  - All required fields present

tests:
  unit:
    - test_output_schema
    - test_json_format
    - test_html_format
  integration:
    - Full pipeline produces valid output

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Schema in docs/schemas/playbook_output.yaml
  - Implementation in nvda_earnings_vol.reports

failure_modes:
  - Missing required field → raise error
  - Invalid format → fallback to JSON