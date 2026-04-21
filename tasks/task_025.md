id: T025
title: Edge Ratio (Implied / Conditional Expected)

objective:
  Compute edge ratio as implied move divided by the primary conditional expected
  move, label it RICH / FAIR / CHEAP with playbook thresholds, inherit confidence
  from the conditional expected data quality flag, and surface it in the report
  with an explicit caveat when confidence is LOW.

context:
  The edge ratio is the central signal in the playbook's move pricing layer. It
  tells the operator whether the market is paying up for event risk (RICH:
  sell-premium or pass candidate) or underpricing it (CHEAP: buy-premium
  candidate). The implied move is already computed via implied_move_from_chain().
  This task connects it to ConditionalExpected from T024 and produces the labeled
  ratio with a confidence rating that flows into the TYPE classifier (T027).

inputs:
  - implied: float (from analytics/implied_move.py, slippage-adjusted, already implemented)
  - conditional_expected: ConditionalExpected dataclass (from T024)

outputs:
  - EdgeRatio dataclass
  - compute_edge_ratio(implied, conditional_expected) function
  - New module: event_vol_analysis/analytics/edge_ratio.py
  - Edge ratio visible in report alongside implied move, with LOW-confidence
    caveat banner when applicable

prerequisites:
  - T024 (ConditionalExpected dataclass and conditional_expected_move())

dependencies:
  - T024

non_goals:
  - No change to implied move computation (already handles slippage adjustment)
  - No strategy-level trade recommendations (that is T027)
  - No historical edge ratio backtesting (that is T030/T031)
  - No dynamic threshold adjustment (thresholds are hardcoded with calibration
    note; T031 will review them after 20+ observations)

requirements:
  - EdgeRatio dataclass fields:
    - implied: float  (decimal, e.g. 0.05 = 5%)
    - conditional_expected_primary: float  (ConditionalExpected.primary_estimate)
    - ratio: float  (implied / conditional_expected_primary)
    - label: str  # CHEAP | FAIR | RICH
    - confidence: str  # HIGH | MEDIUM | LOW (inherited from data_quality)
    - secondary_ratio: float | None  (implied / conditional_expected.median,
        for sanity check; None only if median is also None)
    - label_disagreement: bool  (True if primary and secondary ratios give
        different labels)
    - note: str  (which sub-estimate used as denominator + any caveats)
  - Label thresholds (from playbook; hardcoded, not configurable):
    - CHEAP:  ratio < 0.8
    - FAIR:   ratio 0.8 to 1.3 (inclusive)
    - RICH:   ratio > 1.3
  - Confidence inheritance:
    - ConditionalExpected.data_quality HIGH   → EdgeRatio.confidence HIGH
    - ConditionalExpected.data_quality MEDIUM → EdgeRatio.confidence MEDIUM
    - ConditionalExpected.data_quality LOW    → EdgeRatio.confidence LOW
  - Label disagreement rule:
    - If secondary_ratio gives a different label than primary ratio,
      set label_disagreement = True and downgrade confidence by one level
      (HIGH → MEDIUM, MEDIUM → LOW, LOW stays LOW)
  - Report behavior for LOW confidence:
    - Add visible caveat line in HTML report and console summary:
      "EDGE RATIO LOW CONFIDENCE: fewer than 6 observations or split sample.
       Treat as directional signal only — do not use as TYPE entry gate."
  - Guard: conditional_expected_primary == 0 or None → raise ValueError with
    message "Cannot compute edge ratio: no valid conditional expected move"

acceptance_criteria:
  - CHEAP fires when ratio < 0.8
  - FAIR fires when 0.8 <= ratio <= 1.3
  - RICH fires when ratio > 1.3
  - Confidence directly inherited from ConditionalExpected.data_quality
  - label_disagreement=True downgrades confidence by one level
  - Secondary ratio always computed and present in EdgeRatio output
  - LOW confidence caveat appears in both HTML report and console output
  - ZeroDivisionError is impossible (guarded by explicit check before division)

tests:
  unit:
    - test_cheap_label (implied=0.040, conditional=0.060 → ratio=0.667 → CHEAP)
    - test_fair_label (implied=0.050, conditional=0.050 → ratio=1.000 → FAIR)
    - test_rich_label (implied=0.080, conditional=0.050 → ratio=1.600 → RICH)
    - test_boundary_at_0_8 (ratio=0.800 → FAIR, not CHEAP)
    - test_boundary_at_1_3 (ratio=1.300 → FAIR, not RICH)
    - test_confidence_high_inherited
    - test_confidence_medium_inherited
    - test_confidence_low_inherited
    - test_label_disagreement_downgrades_confidence
    - test_no_disagreement_confidence_unchanged
    - test_zero_conditional_raises
    - test_none_conditional_raises
    - test_note_field_populated
    - test_secondary_ratio_present
  integration:
    - Full pipeline: chain → implied move → conditional expected → edge ratio →
      report shows ratio, label, confidence, and caveat when LOW

definition_of_done:
  - analytics/edge_ratio.py implemented with EdgeRatio dataclass and
    compute_edge_ratio()
  - Report displays edge ratio, label, and confidence per-name
  - LOW confidence caveat visible in HTML and console output
  - All unit and integration tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Thresholds 0.8 and 1.3 are starting points, not calibrated constants.
    Add a comment in code: "# Thresholds from earnings-playbook.md v1; review
    after 20+ observations in calibration loop (T031)."
  - RICH = market pricing in more move than history → sell premium or pass.
    It does not mean the move won't happen. Do not interpret as a direction call.
  - CHEAP = market pricing in less move than history → buy premium candidate.
    It does not guarantee a large move will occur.
  - The secondary ratio (vs median) serves as a sanity check. If primary and
    secondary agree, that is additional evidence. If they disagree, confidence
    downgrades — the right response, not a reason to pick one over the other.

failure_modes:
  - conditional_expected_primary is None → raise ValueError
  - conditional_expected_primary is zero → raise ValueError
  - implied move is None (chain not available) → propagate; caller must handle
    before calling compute_edge_ratio
  - ConditionalExpected.median is None → secondary_ratio = None, skip
    label_disagreement check
