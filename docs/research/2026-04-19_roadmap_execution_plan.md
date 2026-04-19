# Roadmap Execution Plan

Date: 2026-04-19
Source: `docs/PRODUCT_ROADMAP.md`

## Objective

Turn the roadmap into an execution sequence that improves trust first, then expands structure
coverage, then improves operator throughput for earnings season.

## Priority Interpretation

The roadmap has a clear dependency order even where explicit priorities differ:

1. Trust blockers
   Fix anything that makes the current output misleading or ticker-contaminated.
2. Coverage blockers
   Add the highest-value missing structure so the current regime engine has a more complete menu.
3. Operator blockers
   Add batch scan and event-date ingestion so the tool can actually be used across an earnings
   watchlist.
4. Modeling upgrades
   Improve simulation realism and ranking quality once the operational path is stable.

## Recommended Execution Sequence

### Phase 0: Trust Recovery

- `015_bug_gamma_alignment_fix`
- `016_ticker_agnostic_audit`
- `022_regression_smoke_harness`

Rationale:
- `BUG-01` makes alignment misleading today.
- `BUG-02` risks NVDA-shaped assumptions on every non-NVDA run.
- Both need regression coverage before adding more complexity.

Exit criteria:
- Alignment scores move when gamma regime changes.
- Non-NVDA test runs do not depend on `config.TICKER`.
- A small smoke suite covers at least one live-style path and one test-data path.

### Phase 1: High-Value Structure Coverage

- `017_symmetric_butterfly`
- `018_capital_normalized_ranking`

Rationale:
- The roadmap explicitly calls out the ATM pin / overpriced-move case as under-served.
- Butterfly implementation should land before ranking changes so it can be measured under both raw
  EV and capital-normalized EV.

Exit criteria:
- Butterfly appears only when a valid strike topology exists.
- Report and ranking outputs show both raw EV and capital-normalized columns.
- The new structure has scenario coverage and does not distort existing top-ranked structures
  unexpectedly in baseline tests.

### Phase 2: Earnings-Season Operator Workflow

- `019_multi_ticker_batch_mode`
- `020_earnings_calendar_auto_ingestion`

Rationale:
- The roadmap’s product vision is watchlist-first, not single-name-first.
- Batch mode without reliable event-date discovery will create operator error; event ingestion
  without batch mode still leaves the workflow too manual.

Exit criteria:
- One command can scan a watchlist and emit a per-name summary table plus per-name reports.
- Missing or ambiguous event dates are surfaced explicitly rather than silently falling back.
- Batch output is stable enough to use as a daily pre-earnings review.

### Phase 3: Core Modeling Upgrades

- `021_fat_tailed_move_distribution`
- `018_capital_normalized_ranking` if deferred from Phase 1

Rationale:
- The current log-normal Monte Carlo is a known structural limitation for earnings gaps.
- This should be upgraded after workflow stability, because it changes the core ranking behavior and
  will need regression comparison.

Exit criteria:
- Simulation engine supports at least one non-log-normal earnings distribution.
- Historical move data is actually used in calibration, not only in gating.
- Side-by-side comparison exists versus current log-normal output.

## High-Priority Backlog

### P0

1. `015_bug_gamma_alignment_fix`
2. `016_ticker_agnostic_audit`
3. `022_regression_smoke_harness`

### P1

4. `017_symmetric_butterfly`
5. `018_capital_normalized_ranking`
6. `019_multi_ticker_batch_mode`
7. `020_earnings_calendar_auto_ingestion`
8. `021_fat_tailed_move_distribution`

## Dependency Graph

- `015` before `022`
- `016` before `019` and before trusting any batch output
- `017` before finalizing ranking/report comparisons in `018`
- `018` before operator-facing ranking summaries are treated as final
- `020` can begin in parallel with `019`, but integration should land into the batch workflow
- `021` should land behind `022` so distribution changes can be compared safely

## Recommended Agent Strength

- `015_bug_gamma_alignment_fix`: `simple`
- `016_ticker_agnostic_audit`: `strong`
- `017_symmetric_butterfly`: `strong`
- `018_capital_normalized_ranking`: `medium`
- `019_multi_ticker_batch_mode`: `strong`
- `020_earnings_calendar_auto_ingestion`: `medium`
- `021_fat_tailed_move_distribution`: `strong`
- `022_regression_smoke_harness`: `medium`

## What To Defer

These are valid roadmap items, but they should not displace the tranche above:

- `STRUCT-02` Broken-wing butterfly
- `STRUCT-03` Diagonal spread
- `STRUCT-04` Risk reversal
- `STRUCT-05` Jade lizard
- `STRUCT-06` 1x2 ratio spread
- `MODEL-03` Skew dynamics in IV scenarios
- `MODEL-04` Early assignment warning
- `INFRA-03` Portfolio notional limit enforcement
- `INFRA-04` Automated realized-outcome backfill

Reason:
- They matter, but none of them should be built before the trust, batch, and highest-value
  structure gaps are closed.
