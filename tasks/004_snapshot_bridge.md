# Task 004: Snapshot Bridge

## Objective

Bridge the current `nvda_earnings_vol` runtime snapshot and strategy ranking output into the new
generic event-engine domain objects.

## Complexity

- band: `strong`
- recommended agent: Codex or Sonnet

## Dependencies

- requires: `001_event_schema_foundation.md`
- informed by: `003_playbook_policy_engine.md`

## Deliverables

- Bridge module converting current snapshot fields into `EventSpec` and `MarketContext`
- Bridge module converting ranked strategies into `PlaybookCandidate`
- Clear compatibility notes documenting what remains earnings-specific

## Acceptance Criteria

- The existing NVDA flow can emit generic event-domain objects without changing pricing math
- The bridge logic is isolated from the old pipeline so it can be swapped later
- Missing or earnings-specific fields are surfaced explicitly rather than silently guessed
- The bridge is covered by focused tests or executable examples
