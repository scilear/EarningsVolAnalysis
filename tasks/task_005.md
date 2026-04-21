id: T005
title: Storage schema extension

objective:
  Extend the storage schema to support event metadata and outcomes needed for replay.

context:
  Current SQLite schema needs new tables for event tracking and outcome storage.

inputs:
  - Current SQLite schema
  - T002 design document

outputs:
  - New tables: event_registry, event_snapshot_binding, event_surface_metrics
  - New tables: event_evaluation_horizon, event_realized_outcome, structure_replay_outcome
  - Migration script or incremental CREATE statements

prerequisites:
  - T001, T002 completed

dependencies:
  - T001, T002

non_goals:
  - No legacy data migration
  - No real-time ingestion changes

requirements:
  - Additive-only schema changes
  - Backward compatible with existing tables
  - Proper foreign key relationships
  - Indexes for common query patterns

acceptance_criteria:
  - All new tables created via CREATE TABLE IF NOT EXISTS
  - Existing queries continue to work
  - New query paths functional

tests:
  unit:
    - test_schema_creation
    - test_foreign_keys
  integration:
    - Query event snapshots by horizon

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Use CREATE TABLE IF NOT EXISTS for safe deployment
  - Follow T002 design document

failure_modes:
  - Duplicate table → idempotent CREATE handled
  - Missing FK target → fail with clear error