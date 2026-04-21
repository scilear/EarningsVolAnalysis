id: T008
title: Macro taxonomy and mapping

objective:
  Define taxonomy for macro events and mapping to the event schema.

context:
  Need to support macro events (Fed, CPI, Jobs, etc.) alongside earnings.

inputs:
  - Research on macro event calendars
  - Common macro event types

outputs:
  - MacroEventFamily enum
  - Event name normalization rules
  - Mapping to standard schedule format

prerequisites:
  - T001 completed

dependencies:
  - T001

non_goals:
  - Live calendar fetching integration
  - Specific source implementation

requirements:
  - Taxonomy covers major macro events (Fed, CPI, NFP, GDP, etc.)
  - Event names normalized
  - Schedule format consistent with earnings

acceptance_criteria:
  - Taxonomy documented
  - Can create EventSpec for macro events
  - Mapping rules clear

tests:
  unit:
    - test_macro_event_taxonomy
    - test_event_name_normalization
  integration:
    - Create EventSpec for macro event

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - TODO: ASK FABIEN for implementation details

failure_modes:
  - Unknown event type → raise error with suggestion