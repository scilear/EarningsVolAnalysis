# Task 020: Earnings Calendar Auto-Ingestion

## Complexity

`medium`

## Objective

Reduce operator error by auto-discovering the next earnings event date when the user does not supply
one.

## Scope

- Audit the current event-date lookup path
- Normalize success/failure behavior
- Add explicit ambiguity and staleness handling
- Document source assumptions

## Deliverables

- More reliable earnings-date discovery
- Clear fallback/error behavior
- Tests for missing, ambiguous, and stale event-date scenarios

## Acceptance Criteria

- When auto-ingestion succeeds, the discovered date is clearly surfaced in output/logging
- When it fails or returns ambiguous data, the tool stops with an explicit actionable message
- Batch mode can consume this path without hiding failures
- Source-specific limitations are documented

## Notes

This task is not “just fetch a date.” It is about reducing silent event-date mistakes.
