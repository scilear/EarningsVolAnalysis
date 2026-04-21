id: T001
title: Event schema foundation

objective:
  Define the first stable generic event schema used by both earnings and macro workflows.

context:
  The system needs a unified vocabulary to represent different event types (earnings, macro)
  with consistent fields, timing windows, and serialization.

inputs:
  - N/A (foundational schema design)

outputs:
  - Domain objects for event family, event name, schedule, and entry window
  - Validation rules for required fields
  - Serialization helpers for storage and reporting

prerequisites:
  - None (foundational task)

dependencies:
  - None

non_goals:
  - No yfinance-specific earnings API binding
  - No legacy data migration

requirements:
  - EventFamily enum: earnings, macro, other
  - EventWindow: relative timing window with strict validation
  - EventSchedule: event date/time label + entry/evaluation windows
  - EventSpec: normalized generic event definition with serialization
  - Explicit error messages for invalid definitions

acceptance_criteria:
  - Same schema supports earnings and macro events
  - Family vs specific event name is explicit and validated
  - Pre-event and post-event windows are supported
  - Invalid definitions raise actionable errors
  - Implementation isolated in event_option_playbook module

tests:
  unit:
    - test_event_family normalization
    - test_event_window validation
    - test_event_schedule serialization
    - test_ambiguous_event_name rejection
  integration:
    - N/A (foundational)

definition_of_done:
  - All tests pass
  - Schema implemented in event_option_playbook.events
  - Task marked complete in docs/TASKS.md

notes:
  - Implemented in event_option_playbook.events with bridge compatibility
  - Schema v1 uses EventFamily, EventWindow, EventSchedule, EventSpec
  - Do not bind to yfinance-specific APIs

failure_modes:
  - Invalid event family → ValueError with supported families list
  - Ambiguous event name (same as family) → ValueError
  - Missing event_date → KeyError