id: T045
title: Ranking Trust Hardening — Scale Consistency + Validation Gates

objective:
  Implement hard integrity gates to validate the earning volatility analysis ranking before trusting it for execution. Fix scale mismatch between implied and simulated movements, fix front expiry bug for TSLA, and add realized vs implied validation.

context:
  ### Problem Statement
  
  Current ranking has structural trust issues:
  
  1. **Scale Mismatch:** Implied move ~6-16% but simulated mean |move| ~0.2-0.4% (identical between lognormal and fat-tailed models). This is a 10-40x undervaluation.
  
  2. **Model Inefficiency:** `--move-model fat_tailed` flag exists but produces identical outputs to lognormal (report shows "Fat Tail Active: False").
  
  3. **TSLA Front Expiry Bug:** Auto-selected Aug 21 (30 DTE) instead of the nearest weekly (should be ~5 DTE).
  
  4. **Short-Vol Rankings Untrustworthy:** Without scale consistency, short-vol EV claims (Iron Condor, Calendar) have no empirical basis.
  
  ### Evidence
  
  - MSFT report: implied move 6.73%, simulated mean |move| 0.14%, P(|move|>6%) = 0.00%
  - NVDA baseline: implied move 10.15%, simulated mean |move| 0.23%
  - Fat-tailed validation: no difference from lognormal
  
  ### Why This Matters
  
  - Iron Condor play: "EV $493" but wing strikes hardcoded at 5% OTM don't protect against tail
  - Calendar spread: theta decay claim vs fat-tailed distribution unverified
  - No integrity gates = blind trust in unreliable rankings

inputs:
  - Current `event_vol_analysis/main.py` (Monte Carlo simulation)
  - Current `analytics/event_vol.py` (event_variance extraction)
  - Test reports: `reports/MSFT_pre_earnings.html`, `reports/NVDA_pre_earnings.html`
  - TSLA ticker with earnings data

outputs:
  - **Scale Fix:** simulation output matches implied move scale (within 50%)
  - **Model Fix:** fat-tailed model produces measurably different outputs
  - **TSLA Fix:** front expiry selects nearest weekly post-earnings
  - **Integrity Gate:** ranking rejected if simulated vs implied mismatch >2x
  - **Validation Report:** trust metrics in output section

prerequisites:
  - T021 (Fat-tailed move distribution) working
  - T022 (Regression smoke harness) passing
  - T044 (EOD cache) for data validation

dependencies:
  - T021, T022, T044

non_goals:
  - Not replacing Monte Carlo engine (fix calibration, not architecture)
  - Not adding external data sources (use existing)
  - Not building full backtest (validation only)

---

## Requirements

### 1. Scale Consistency Fix

#### Current Problem
- `event_variance()` returns daily-scale event_vol
- `simulate_moves()` applies extra `/sqrt(252)` → double time-scaling
- Result: simulated moves ~0.2% when implied is ~10%

#### Fix Required
```
# Option A: Remove scaling from simulate_moves
std_dev = np.sqrt(event_var)  # daily already, no /sqrt(252)

# Option B: Pass annualized to simulate_moves
std_dev = np.sqrt(event_var * 252)  # convert back to annual

# Whichever is chosen, implied vs simulated must agree within 50%
```

#### Validation
- Run baseline scenario: implied 10.15% → simulated mean should be 5-15%
- Run high_vol scenario: implied 15.60% → simulated mean should be 8-25%

### 2. Fat-Tailed Model Activation

#### Current Problem
- `--move-model fat_tailed` flag exists but doesn't change output
- Report shows "Fat Tail Active: False" and identical metrics

#### Fix Required
```
# In simulate_moves() or move generation:
if move_model == "fat_tailed":
    # Apply Student-t with calibrated df (typically 4-7)
    # Or add kurtosis scaling to normal draws
    std_dev *= kurtosis_multiplier  # ~1.3-1.5x
```

#### Validation
- Run same scenario with both models
- Fat-tailed P(|move|>6%) should be >0% (not 0.00%)

### 3. TSLA Front Expiry Fix

#### Current Problem
- `select_front_expiry()` picks furthestweekly (30 DTE) instead of nearest (~5 DTE)
- TSLA earnings Aug 21, auto-selected Aug 21 expiry = 30 days

#### Fix Required
```
# Sort expiries by days_post_event, select MIN (nearest)
# Current: max(earnings_date + weekly_expiries)
# Fixed: min(earnings_date + weekly_expiries) where days > 0
```

#### Validation
- TSLA earnings Aug 21 → front expiry should be ~5-8 days (not 30)

### 4. Integrity Gate

#### Requirement
Before outputting ranking, compute:
```
mismatch_ratio = implied_move / simulated_mean_abs_move

if mismatch_ratio > 2.0:
    # Reject ranking
    output.warning = "TRUST GATE FAILED: Scale mismatch {mismatch_ratio:.1f}x"
    ranking.confidence = "LOW"
elif mismatch_ratio > 1.5:
    ranking.confidence = "MEDIUM"
else:
    ranking.confidence = "HIGH"
```

#### Output Section
Add to report:
```
### Trust Metrics
| Metric | Value |
|--------|-------|
| Implied Move | X% |
| Simulated Mean | Y% |
| Mismatch Ratio | Zx |
| Fat Tail Active | true/false |
| Gate Status | PASS/FAIL |
```

### 5. DTE Guardrail (Short Vol)

#### Requirement
Short-vol strategies (Iron Condor, Calendar) only available when:
```
dte = days_to_front_expiry
if dte < 1 or dte > 10:
    short_vol_allowed = false
    reason = "DTE outside 1-10 day optimal range"
```

#### Rationale
- Very short DTE (< 5): vol crush too fast, gamma too high
- Longer DTE (> 21): theta too weak for calendar/iron condor

---

## File Changes

### analytics/event_vol.py
- Function: `event_variance()` — review scaling
- Add: `return {"annualized_event_vol": ..., "daily_event_vol": ...}`

### main.py
- Function: `simulate_moves()` — fix scale (Option A or B)
- Function: `select_front_expiry()` — fix TSLA bug
- Function: `compute_trust_metrics()` — new integrity gate
- Section: output report — add trust metrics

### config.py
- Add: `TRUST_MISMATCH_THRESHOLD = 2.0`
- Add: `SHORT_VOL_DTE_MIN = 1`
- Add: `SHORT_VOL_DTE_MAX = 10`

---

## Acceptance Criteria

| Criterion | Test | Pass Condition |
|-----------|------|--------------|
| Scale match | Baseline implied 10.15% | Simulated 5-15% |
| Scale match | High-vol implied 15.6% | Simulated 8-25% |
| Fat-tail active | Run fat_tailed | P(\|move\|>6%) > 0% |
| TSLA expiry | TSLA earnings + auto-select | Front DTE ~5-10 (not 30) |
| Trust gate | Mismatch 3x | Output "TRUST GATE FAILED" |
| DTE guardrail | Short vol at DTE=30 | Rejected with reason |

---

## Tests

### Unit Tests
```
test_scale_consistency_baseline()
test_scale_consistency_highvol()
test_fat_tailed_model_activation()
test_tsla_front_expiry_selection()
test_trust_gate_rejects_mismatch()
test_dte_guardrail_short_vol()
test_dte_allows_mid_vol()
```

### Integration Tests
```
test_full_ranking_with_trust_gate()
test_short_vol_strategy_rejected_at_high_dte()
test_fat_tailed_vs_lognormal_materially_different()
```

---

## Definition of Done

- [x] Scale mismatch detection fixed (removed double time-scaling path)
- [x] Fat-tailed model path active by default and materially differs in tails
- [x] TSLA/front-expiry selection logic fixed to nearest post-event expiry
- [x] Trust gate implemented in report + analysis summary (PASS/WARN/FAIL)
- [x] Short-vol guardrail enforced for front DTE outside [1, 10]
- [x] Unit/integration test suite green for implemented scope
- [ ] Scale mismatch calibrated to <1.5x on representative real-name runs
- [ ] Trust-gate FAIL behavior finalized for ranking suppression policy

---

## Progress Log

### Completed (first pass)
- Fixed Monte Carlo scale bug by removing extra sqrt(252) division in
  `simulate_moves()`.
- Added annualized/daily event-vol fields in event variance output to make
  scaling explicit.
- Enabled fat-tailed model as default (`MOVE_MODEL_DEFAULT = "fat_tailed"`).
- Added trust metrics and gate status (PASS/WARN/FAIL) to snapshot/report and
  blocking warnings in analysis summary.
- Added nearest post-event expiry selector and wired it into main + daily scan.
- Added short-vol DTE guardrail for `iron_condor` and `calendar`.

### In Progress (second pass)
- Calibrating simulation sigma against implied move so mismatch ratios converge
  toward acceptable production bounds.
- Finalized trust-gate semantics (`ranking_allowed`) and implemented
  recommendation suppression when trust gate FAILS.

### Remaining
- Real-data validation run set (multiple tickers/scenarios) to confirm
  mismatch ratio consistently <= 1.5x target band where expected.

### Newly Completed (second pass)
- Added calibrated simulation sigma field (`simulation_event_vol`) and
  surfaced it in console/report diagnostics.
- Added `ranking_allowed` to trust metrics and report display.
- Added hard recommendation suppression path: when trust gate FAILS,
  rankings are withheld from report/playbook payload while diagnostics remain.

---

## Notes

### Why This is P0
- Rankings can't be trusted for execution without integrity
- Short-vol "EV" claims are unverifiable without scale match
- Fat-tailed model claim is false advertising (flag does nothing)
- TSLA bug distorts one of the highest-vol names

### Root Cause Hypothesis
Double time-scaling:
1. `event_variance()` already returns daily variance (IV² / 252)
2. `simulate_moves()` divides by sqrt(252) again

This should be confirmed by reading both functions before implementing fix.

---

## Failure Modes

| Failure | Fix |
|---------|-----|
| Scale still off | Add explicit scaling assertion, fail fast |
| Fat-tailed still same | Debug move generation path |
| TSLA still wrong | Hardcode test case in unit test |
| Trust gate too strict | Adjust threshold to 2.5x |

---

## References

- Test reports: `reports/MSFT_pre_earnings.html`, `reports/NVDA_pre_earnings.html`
- Strategy docs: `docs/strategies/iron_condor.md` (warns about tail risk)
- Model limitations: `docs/strategies/index.md` (lists BSM assumptions)
