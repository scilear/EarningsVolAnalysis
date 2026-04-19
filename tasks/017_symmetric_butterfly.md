# Task 017: Symmetric Butterfly Structure

## Complexity

`strong`

## Objective

Add a symmetric butterfly structure for overpriced-move / ATM pin regimes so the structure menu is
not forced to substitute iron condors for pin-risk trades.

## Scope

- Implement structure construction
- Integrate with payoff and strategy evaluation
- Add rationale/report output
- Ensure strike selection is deterministic and robust to sparse chains

## Deliverables

- New butterfly builder
- Inclusion in strategy generation
- Metrics/scoring compatibility
- Tests for valid and invalid chain topologies

## Acceptance Criteria

- The structure is only built when a symmetric strike topology exists
- The structure has deterministic leg ordering and naming
- The structure flows through scenario EV, CVaR, convexity, and alignment without special-case
  breakage
- Reports and rankings display it alongside other structures
- Tests cover at least:
  - normal valid build
  - missing wing case
  - sparse strike grid case

## Notes

Do not bundle broken-wing behavior into this task. Keep this implementation strictly symmetric.
