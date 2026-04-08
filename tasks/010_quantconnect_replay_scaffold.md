# Task 010: QuantConnect Replay Scaffold

## Objective

Create the first QuantConnect-compatible scaffold for event replay research.

## Complexity

- band: `strong`
- recommended agent: Codex or Sonnet

## Dependencies

- requires: `002_event_dataset_and_outcomes.md`
- requires: `006_event_replay_framework.md`

## Deliverables

- QuantConnect research or algorithm scaffold
- Event input contract
- Logging fields aligned with the generic event/playbook model

## Acceptance Criteria

- The scaffold can represent an event and its replay window cleanly
- Inputs and outputs align with the repo’s new generic vocabulary
- The result is useful for later workbook expansion, not just a throwaway script
- QuantConnect-specific assumptions are documented
