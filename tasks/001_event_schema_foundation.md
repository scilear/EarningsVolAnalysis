# Task 001: Event Schema Foundation

## Objective

Define the first stable generic event schema used by both earnings and macro workflows.

## Deliverables

- Domain objects for event family, event name, schedule, and entry window semantics
- Validation rules for required fields
- Serialization helpers suitable for storage and reporting

## Acceptance Criteria

- A developer can represent both an earnings event and a macro event with the same schema
- The schema distinguishes top-level family from specific event name
- The schema supports pre-event and post-event timing windows
- Invalid event definitions fail with explicit, actionable errors
- The implementation is isolated from the old `nvda_earnings_vol` package enough to be reused later

## Notes

Do not bind this layer to yfinance-specific earnings APIs.

## Implementation Notes (2026-04-08)

Implemented in `event_option_playbook.events` with compatibility update in
`event_option_playbook.bridge`.

### Schema v1

- `EventFamily`: top-level family enum (`earnings`, `macro`, `other`)
- `EventWindow`: relative timing window with strict timing/day-range validation
- `EventSchedule`: event date/time label + entry/evaluation windows
- `EventSpec`: normalized generic event definition with serialization helpers

### Validation behavior

- Event family must be a supported family label
- Event name is required and must be specific (cannot equal a family label)
- Underlying is required and normalized uppercase
- Schedule requires a valid `event_date`
- Invalid windows fail with explicit errors (invalid ordering, timing mismatch, duplicates)

### Serialization behavior

- `EventWindow.to_dict` / `.from_dict`
- `EventSchedule.to_dict` / `.from_dict`
- `EventSpec.to_dict` / `.from_dict`
- `EventSpec.to_dict` retains compatibility keys (`event_date`, `event_time_label`,
  `entry_windows`) while adding canonical nested `schedule`

### Acceptance Criteria Coverage

- Same schema supports earnings and macro events: `EventSpec(family=..., name=..., schedule=...)`
- Family vs specific event name is explicit and validated
- Pre-event and post-event windows are supported in `EventSchedule.entry_windows`
- Invalid definitions raise actionable `TypeError`/`ValueError`/`KeyError`
- Implementation remains isolated in `event_option_playbook` with no yfinance binding
