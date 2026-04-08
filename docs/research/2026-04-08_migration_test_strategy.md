# Migration Test Strategy

## Purpose

Define the test net that keeps the earnings workflow trustworthy while the repository migrates to
a generic event engine.

## Layered Inventory

### Smoke

- package import sanity
- one baseline scenario through the legacy pipeline
- one post-event scenario through the compatibility bridge
- one bridge round-trip from legacy snapshot to `EventSpec` / `MarketContext` / playbook

### Unit

- event-domain validation and serialization
- market-context validation and derived metrics
- bridge coercion and recommendation shaping
- analytics math: BSM, implied move, event variance, skew, gamma
- strategy gates, builders, payoff helpers, and score ordering
- calibration and filter clamping

### Integration

- scenario fixture -> gate -> builder -> score -> output
- legacy snapshot -> bridge -> generic objects -> recommendation
- baseline, high-vol, and post-event fixtures as representative regression points

## Stable Math vs Interface Drift

Stable math should be checked with exact or tolerance-based assertions:

- BSM pricing and Greeks
- event variance clipping
- gate boundary conditions
- score ordering and range
- deterministic repeated calls

Changing interfaces should be checked with contract-shape tests:

- event family/name taxonomy
- schedule payload fields
- playbook output contract
- report serialization
- storage/replay schema

## Business Invariants

- event variance ratio remains in `[0, 1]`
- negative event variance clamps to zero
- IV crush is non-positive and expansion is positive
- `base_crush` is not mutated by calibration
- backspread thresholds are inclusive at the boundary
- scores remain sorted descending and stay in `[0, 1]`
- positive dividend yield lowers call delta and raises put delta magnitude
- bridge output keeps event identity and core market-context values intact
- post-event calendar eligibility remains deterministic

## Golden and Fixture Guidance

Use fixture-based tests for:

- synthetic scenarios from `nvda_earnings_vol/data/test_data.py`
- legacy snapshots used by bridge tests
- baseline and post-event reference events

Use golden examples for:

- `EventSpec` serialization
- playbook recommendation shape
- final report payloads once the generic schema stabilizes

Avoid raw floating-point goldens for active formulas. Prefer invariant checks and tolerances until
the migration stops changing the contract.

## Execution Notes

The first regression gate should be runnable with the project-local virtual environment:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python -m pytest \
  nvda_earnings_vol/tests/test_business_invariants.py \
  nvda_earnings_vol/tests/test_post_event_calendar.py \
  nvda_earnings_vol/tests/test_snapshot_bridge.py -q
```

