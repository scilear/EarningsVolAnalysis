id: T004
title: Snapshot bridge

objective:
  Bridge legacy snapshot data to the new event schema for migration continuity.

context:
  Old system stored snapshots in legacy format. Need to map to new EventSpec format.

inputs:
  - Legacy snapshot files/records

outputs:
  - Bridge module converting legacy → new schema
  - EventSpec from legacy data
  - MarketContext coercion

prerequisites:
  - T001 completed

dependencies:
  - T001

non_goals:
  - No data migration of historical records
  - No new storage implementation

requirements:
  - Convert legacy snapshot fields to EventSpec
  - Preserve event identity and core market-context fields
  - Handle missing fields with defaults
  - Explicit coercion logging

acceptance_criteria:
  - Legacy snapshot can be expressed as EventSpec
  - Core market context preserved
  - Bridge imports cleanly

tests:
  unit:
    - test_legacy_snapshot_coercion
    - test_field_mapping
  integration:
    - Legacy snapshot → bridge → generic event objects

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Implemented in event_option_playbook.bridge

failure_modes:
  - Missing required field → raise error with field name
  - Corrupt data → log and skip