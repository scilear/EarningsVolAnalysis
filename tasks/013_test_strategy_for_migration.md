# Task 013: Test Strategy For Migration

## Objective

Define how to preserve confidence while the repo moves from an earnings tool to a generic event
engine.

## Complexity

- band: `medium`
- recommended agent: Kimi K2.5 class

## Dependencies

- requires: none

## Deliverables

- Test inventory by layer
- Recommendation for smoke, unit, and integration coverage during migration
- Explicit list of business invariants that must remain true

## Acceptance Criteria

- The current high-value behavior is identified before broad refactors start
- The proposed test plan distinguishes stable math from changing interfaces
- The plan identifies where golden examples or fixture-based tests are needed

## Strategy

The migration should keep the existing earnings workflow protected by a layered test net while the
new generic event engine grows beside it. The goal is not to freeze every implementation detail,
but to pin the math and entry/exit behavior that already works and let the event vocabulary and
playbook surface evolve.

### Current high-value behavior to preserve

The behavior worth freezing first is the end-to-end path that already powers the current product:

- synthetic or loaded market data is converted into a usable snapshot
- event variance, implied move, skew, gamma, and liquidity diagnostics are computed
- strategy gates decide what is eligible
- candidate structures are ranked and scored deterministically
- report/playbook output is produced from the ranked result set

That path is already covered in pieces by the current scenario and invariant tests, so the first
migration checkpoint should be the same workflow, not a new interface.

### Test inventory by layer

#### Smoke

Smoke tests should stay cheap and broad. They should verify:

- the package imports cleanly
- one representative baseline scenario runs through the legacy pipeline
- one post-event scenario runs through the new generic bridge path
- the bridge can build an `EventSpec`, `MarketContext`, and playbook recommendation from a legacy
  snapshot

Recommended smoke command pattern:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python -m pytest \
  nvda_earnings_vol/tests/test_snapshot_bridge.py -q
```

#### Unit

Unit tests should continue to own the exact math and validation rules:

- `event_option_playbook.events`: event family/name normalization, schedule validation,
  serialization, and key generation
- `event_option_playbook.context`: market-context validation and derived ratios
- `event_option_playbook.bridge`: snapshot coercion, default naming, candidate mapping, and
  recommendation shaping
- `nvda_earnings_vol.analytics.*`: BSM pricing/Greeks, implied move, event variance, skew, gamma,
  and historical move helpers
- `nvda_earnings_vol.strategies.*`: entry gates, builders, scoring order, payoff helpers, and
  post-event calendar calculations
- `nvda_earnings_vol.calibration` and `nvda_earnings_vol.data.filters`: calibration clamping and
  liquidity filters that feed the strategy gates

#### Integration

Integration tests should validate the workflow boundaries rather than every internal formula:

- scenario fixture -> gate -> builder -> scoring -> report/playbook output
- legacy snapshot -> bridge -> generic event objects -> recommendation
- representative baseline, high-vol, and post-event scenarios to prove the migration does not
  break current acceptance behavior

These tests should be few and stable. They are the place to confirm that the old earnings-focused
workflow and the new event-engine vocabulary still agree on the same user-visible result.

### Stable math vs changing interfaces

The migration plan should explicitly separate the parts that should stay numerically stable from the
parts that are expected to change.

Stable math:

- BSM pricing and Greeks
- event variance bounds and clipping
- strategy gate thresholds and boundary behavior
- score ordering and score range
- scenario determinism for repeated calls with the same inputs

Changing interfaces:

- event family/name taxonomy
- schedule payload shape
- playbook contract fields
- report formatting and output serialization
- storage schema and replay wiring

The stable math should be asserted with direct numeric expectations or tight tolerances. The
changing interfaces should be asserted with shape checks, required-field checks, and contract
examples, not brittle value snapshots.

### Business invariants

These are the invariants that should survive the migration unchanged unless there is a deliberate
design decision to alter them:

- event variance ratio remains within `[0, 1]` for well-formed scenarios
- negative event variance is clipped to zero
- IV crush values are non-positive and expansion values are positive after calibration
- `base_crush` remains unchanged by IV scenario calibration
- backspread gates only pass when all thresholds are met, and exact threshold boundaries remain
  inclusive
- strategy scores remain sorted in non-increasing order and stay inside `[0, 1]`
- positive dividend yield lowers call delta, increases put delta magnitude, and changes gamma
- the legacy snapshot bridge preserves event identity and core market-context fields
- post-event calendar eligibility remains scenario-dependent and deterministic

### Golden examples and fixture-based tests

Use fixture-based tests wherever the input data should not depend on live markets:

- scenario fixtures from `nvda_earnings_vol/data/test_data.py`
- legacy snapshot fixtures for bridge and recommendation tests
- one canonical baseline event fixture and one post-event fixture for migration checks

Use golden examples only where the output contract is intentionally stable and human-readable:

- bridge serialization for `EventSpec`
- playbook recommendation shape
- final report or summary payload once the generic engine output stabilizes

Avoid pinning raw floating-point goldens for formulas that are still being generalized. For those,
prefer invariant tests, tolerances, and relative comparisons.

### Migration order

1. Freeze the current behavior with the existing scenario and invariant tests.
2. Expand bridge coverage until legacy snapshots can be expressed in generic event objects.
3. Add integration tests that compare the legacy pipeline and the bridge output on the same
   fixtures.
4. Move contract tests to the generic event vocabulary once the new interfaces stabilize.
5. Add goldens only after the playbook/report schema stops churning.
