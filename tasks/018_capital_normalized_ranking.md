# Task 018: Capital-Normalized Ranking

## Complexity

`medium`

## Objective

Upgrade rankings so structures are compared on raw EV and capital-adjusted EV, not on raw dollar EV
alone.

## Scope

- Add normalization fields to strategy metrics
- Add ranking/display columns
- Preserve the current raw EV view for transparency

## Deliverables

- `EV / premium_paid` metric
- `EV / max_loss` metric where defined
- Report/table updates
- Tests confirming metric computation and ranking stability behavior

## Acceptance Criteria

- Rankings expose raw EV and capital-normalized EV side by side
- Undefined-risk structures are handled explicitly rather than silently receiving misleading
  normalization values
- The ranking method is documented in the report or diagnostics output
- Existing consumers of the ranking payload do not break

## Notes

This is a ranking-policy change. Keep it auditable and reversible.
