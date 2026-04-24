id: T047
title: Ranking Trust Hardening v2 — Corrected Approach
status: completed

objective:
  Implement integrity gates with corrected methodology based on adversarial review. Replace arbitrary thresholds with statistical tests, replace single-axis DTE filter with multi-dimensional risk weighting.

context:
  ### Why T047 Exists
  
  T045 was submitted for adversarial review and critical flaws identified:
  
  | Issue | T045 Approach | Flaw | Corrected Approach |
  |-------|--------------|------|-------------------|
  | Scale Fix | Remove sqrt(252) | Naive, mixes risk-neutral w/ diffusion | Trace time units, use quantile matching |
  | Fat-Tailed | Student-t df 4-7 | Assumes symmetric tails | Diffusion + jump mixture |
  | Trust Gate | Ratio > 2.0 fails | Mean vs quantile mismatch | KS test or quantile-deviation |
  | DTE Guardrail | 1-10 days only | Eliminates high-edge setups | DTE-dependent risk weighting |

dependencies:
  - T045 (being worked on by another party)

non_goals:
  - Not repeating T045's mistakes
  - Not adding new model architecture (use existing, fix calibration)

requirements:

### 1. Scale Consistency (Corrected)
- Instead of scalar ratio, use quantile comparison
- Compare P10, P50, P90 of simulated to implied quantiles
- Report: absolute deviation at each quantile, not single ratio

### 2. Fat-Tailed Model (Corrected)
- Model as diffusion + jump mixture (not Student-t)
- Calibrate jump probability and magnitude to historical earnings moves
- Or: use skew-normal or normal mixture

### 3. Trust Gate (Corrected)
- Use Kolmogorov-Smirnov or Anderson-Darling test
- Continuous confidence score (0-100), not binary HIGH/MEDIUM/LOW
- Include direction of mismatch in diagnostic

### 4. DTE Guardrail (Corrected)
- Drop hard exclusion
- Instead: apply risk weight multiplier based on DTE
- Multiplier: 1.0 at 5-10 DTE, scales down outside (not to 0)
- Continue allowing all strategies, just with adjusted risk scores

### 5. TSLA Fix (Keep)
- select_front_expiry() fix from T045 is valid
- Document as strategy preference injection

### 6. Short-Vol Earnings Evidence Gate
- NEW requirement: for short-vol strategies
- Require evidence that implied move > realized move historically
- Query event_outcomes table for past 8 quarters
- Only allow if implied > realized in majority of events
- This addresses "short-vol EV claims unverified"

acceptance_criteria:
- All T045 criteria still met (scale match, TSLA fix, etc.)
- Trust gate uses continuous score (not binary)
- DTE filter uses weighting (not exclusion)
- Fat-tailed uses mixture model or evidence-based distribution

tests:
- test_trust_gate_continuous_score()
- test_dte_weighting_allows_边界_cases()
- test_short_vol_earnings_evidence_gate()

definition_of_done:
- [x] Scale fix works with quantile matching
- [x] Trust gate continuous
- [x] DTE uses weighting not exclusion
- [x] Short-vol requires earnings evidence
- [x] All tests pass

completion_notes:
  - Added quantile-based trust diagnostics (`p10/p50/p90`) with per-quantile
    deviation and mismatch direction.
  - Added continuous trust score (0-100), fused with KS p-value signal,
    and kept PASS/WARN/FAIL mapping from thresholds.
  - Updated fat-tail simulation from Student-t to diffusion+jump mixture.
  - Replaced hard short-vol DTE exclusion with continuous DTE risk weighting
    (score impact, never hard-zero by DTE alone).
  - Added short-vol evidence gate from `earnings_outcomes`
    (`realized_vs_implied_ratio < 1` majority over last 8 completed events).
  - Added targeted trust/short-vol tests and passed focused suites.
