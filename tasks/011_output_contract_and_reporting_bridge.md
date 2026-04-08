# Task 011: Output Contract And Reporting Bridge

## Objective

Detach the product definition from the current HTML report by bridging reporting onto the new
playbook output contract.

## Complexity

- band: `strong`
- recommended agent: Codex or Sonnet

## Dependencies

- requires: `003_playbook_policy_engine.md`
- requires: `004_snapshot_bridge.md`

## Deliverables

- Report adapter from `PlaybookRecommendation` to current or next reporting layer
- Migration note describing what remains presentation-specific

## Acceptance Criteria

- HTML becomes a rendering layer rather than the canonical output contract
- A no-trade outcome can be rendered cleanly
- Practical risk notes, key levels, and management rules are renderable
- The adapter does not re-encode strategy logic that belongs upstream
