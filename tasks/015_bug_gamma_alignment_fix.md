# Task 015: Gamma Alignment Fix

## Complexity

`simple`

## Objective

Fix the broken gamma alignment axis so alignment scores react to the actual detected gamma regime.

## Scope

- Audit the regime key emitted by `classify_regime()`
- Audit the key consumed by `compute_alignment()`
- Normalize the naming mismatch in one place
- Add regression coverage for all gamma states

## Deliverables

- Code fix in the regime/alignment path
- Tests showing alignment changes across:
  - amplified-move regime
  - pin-risk regime
  - neutral gamma regime

## Acceptance Criteria

- Gamma alignment is no longer pinned at `0.50` for every strategy
- The implementation does not duplicate regime semantics in multiple inconsistent places
- Existing strategy ranking still runs after the change
- Tests fail on the pre-fix behavior and pass on the corrected behavior

## Notes

Prefer one canonical key name rather than a pile of aliases.
