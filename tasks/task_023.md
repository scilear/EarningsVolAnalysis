id: T023
title: IV Rank + IV Percentile Dual Classifier

objective:
  Replace the current P75-ratio vol label with a dual IVR + IVP classifier that
  produces CHEAP / NEUTRAL / EXPENSIVE / AMBIGUOUS and a confidence flag.

context:
  The current regime.py classifies vol pricing using implied_move / historical_p75.
  The playbook requires two independent metrics: IV Rank (IVR) and IV Percentile (IVP).
  When both agree, confidence is HIGH. When they disagree by more than one bucket, the
  name is flagged AMBIGUOUS and all downstream TYPE conditions that depend on a clear
  vol regime are blocked. The term structure slope and 25-delta put/call skew are already
  computed in analytics/skew.py but are not surfaced cleanly alongside the vol regime — this
  task wires them into the snapshot output as well.

inputs:
  - 52-week daily ATM IV history (per ticker, from loader or cached history)
  - Current front-month ATM IV
  - Existing skew metrics output from analytics/skew.py
  - Front and back-month IV for term structure slope

outputs:
  - classify_vol_regime(ivr, ivp) function in analytics/vol_regime.py (new module)
  - Updated regime.py snapshot to replace P75-ratio vol label with dual classifier output
  - Term structure slope (front vs back month, as %) surfaced in snapshot
  - 25-delta put/call skew surfaced in snapshot

prerequisites:
  - T022 (regression smoke harness)

dependencies:
  - T022

non_goals:
  - No change to move-pricing or edge ratio (those are T024, T025)
  - No new strategy structures
  - No learned or dynamic threshold adjustment

requirements:
  - IVR = (current_iv - 52W_low) / (52W_high - 52W_low) * 100
    - If 52W_high == 52W_low: IVR = 50 (degenerate case, mark LOW confidence)
  - IVP = % of trading days in last 52W where daily ATM IV < current_iv * 100
  - Bucket mapping (applies to both IVR and IVP independently):
    - CHEAP:      value < 30
    - NEUTRAL:    value 30-60
    - EXPENSIVE:  value > 60
  - Label logic:
    - Both buckets agree → use that label, confidence = HIGH
    - Buckets differ by exactly one step (e.g., CHEAP vs NEUTRAL) → use conservative
      label (closer to NEUTRAL), confidence = LOW
    - Buckets differ by two steps (CHEAP vs EXPENSIVE) → label = AMBIGUOUS,
      confidence = LOW
  - Output schema (TypedDict or dataclass):
    - label: str  # CHEAP | NEUTRAL | EXPENSIVE | AMBIGUOUS
    - ivr: float
    - ivp: float
    - bucket_ivr: str  # CHEAP | NEUTRAL | EXPENSIVE
    - bucket_ivp: str  # CHEAP | NEUTRAL | EXPENSIVE
    - confidence: str  # HIGH | LOW
    - term_structure_slope: float  # (front_iv - back_iv) / back_iv, contango < 0
    - skew_25d: float  # 25-delta put IV minus 25-delta call IV (positive = put skew)
  - New module: event_vol_analysis/analytics/vol_regime.py
  - Replace P75-ratio label in classify_regime() output in regime.py with dual label
  - Backward compatibility: keep existing vol_label key in regime output as alias

acceptance_criteria:
  - classify_vol_regime() returns AMBIGUOUS when IVR bucket and IVP bucket differ by 2 steps
  - classify_vol_regime() returns LOW confidence when buckets differ by 1 step
  - classify_vol_regime() returns HIGH confidence when both buckets agree exactly
  - Degenerate case (52W_high == 52W_low) sets IVR = 50 and confidence = LOW
  - term_structure_slope appears in snapshot output (contango negative, backwardation positive)
  - skew_25d appears in snapshot output
  - Regression smoke tests pass unchanged

tests:
  unit:
    - test_ivr_calculation_normal
    - test_ivp_calculation_normal
    - test_bucket_cheap (IVR=20, IVP=25 → CHEAP, HIGH)
    - test_bucket_expensive (IVR=70, IVP=75 → EXPENSIVE, HIGH)
    - test_bucket_ambiguous (IVR=20, IVP=75 → AMBIGUOUS, LOW)
    - test_bucket_one_step_disagreement (IVR=28, IVP=35 → NEUTRAL, LOW)
    - test_degenerate_flat_iv_history
    - test_term_structure_contango (front < back → slope < 0)
    - test_term_structure_backwardation
  integration:
    - Full pipeline run with CHEAP name → dual label appears in report
    - Full pipeline run with AMBIGUOUS name → AMBIGUOUS appears, not CHEAP or EXPENSIVE

definition_of_done:
  - vol_regime.py implements classify_vol_regime() with documented schema
  - regime.py uses dual label; legacy vol_label key aliased for backward compat
  - Dual label, confidence, term structure slope, and skew appear in report
  - All unit and integration tests pass
  - Regression smoke passes
  - Task marked complete in docs/TASKS.md

notes:
  - AMBIGUOUS is a first-class outcome, not an error state. It means: data is
    genuinely ambiguous, not that computation failed.
  - Do not hardcode the 52W window as 252 days — use actual calendar days of
    available history and document the actual window used in the output.
  - IVR requires min/max history; if history < 60 trading days, mark confidence LOW
    regardless of bucket agreement.

failure_modes:
  - History shorter than 60 days → confidence = LOW, label = NEUTRAL (conservative)
  - Current IV missing → raise ValueError with actionable message
  - Front expiry chain missing for term structure → term_structure_slope = None
  - Skew data missing → skew_25d = None (do not block output)
