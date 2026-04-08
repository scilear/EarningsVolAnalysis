# Task 006: Event Replay Framework

## Objective

Create the framework that replays historical events and evaluates standardized option structures.

## Complexity

- band: `strong`
- recommended agent: Codex or Sonnet

## Dependencies

- requires: `002_event_dataset_and_outcomes.md`
- requires: `005_storage_schema_extension.md`

## Deliverables

- Replay module design
- Event selection interface
- Standardized evaluation horizons and exit assumptions

## Acceptance Criteria

- A replay run can define what was known pre-event and what is measured post-event
- Standardized structures can be evaluated consistently across multiple events
- Exit assumptions are explicit and reproducible
- The framework is neutral enough to support both earnings and macro research later
