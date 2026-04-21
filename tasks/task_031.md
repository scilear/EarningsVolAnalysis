id: T031
title: Calibration Loop

objective:
  Implement a weekly calibration report that compares ex-ante predictions to
  realized outcomes across four dimensions: edge ratio accuracy, TYPE classification
  accuracy, no-trade audit, and decision quality. Output is a markdown report
  saved to reports/calibration/ plus a console summary.

context:
  With small sample sizes (10-20 events per quarter), the calibration loop is
  for pattern recognition and sanity checking, not parameter optimization. It
  catches gross miscalibration (e.g., TYPE 1 firing 40% of the time, or edge
  ratio CHEAP consistently under-predicting realized moves by 2×) before it
  becomes a systematic loss. Threshold adjustment requires 20+ observations per
  parameter; until then, the report flags patterns without changing anything.

inputs:
  - earnings_outcomes table from T030 (queried for events in rolling 13-week
    window, or full history if fewer than 13 weeks available)
  - Minimum 5 completed records (outcome_complete=True) to generate report;
    if fewer, emit a "INSUFFICIENT DATA" warning and exit

outputs:
  - CalibrationReport dataclass (summary statistics per dimension)
  - run_calibration_report(db_path, output_dir) function
  - Weekly markdown report: reports/calibration/YYYY-WXX_calibration.md
  - Console summary: compact table of key metrics
  - Script: scripts/run_calibration.py (manual trigger or cron)

prerequisites:
  - T030 (earnings_outcomes table with completed records)

dependencies:
  - T030

non_goals:
  - No automated threshold adjustment (thresholds are hardcoded; adjustment
    is a manual decision requiring 20+ observations)
  - No real-time calibration (weekly batch only)
  - No ML or parameter fitting

requirements:
  - Dimension 1 — Edge Ratio Accuracy:
    - For each completed record: compute realized_vs_implied_ratio (already in T030)
    - Edge ratio label accuracy: what % of RICH names had realized < implied?
      What % of CHEAP names had realized > implied?
    - Mean absolute error: |realized - implied| / implied, by label bucket
    - Flag: if mean error > 30% for any bucket with >=5 obs, add calibration alert
  - Dimension 2 — TYPE Classification Accuracy (ex-ante vs ex-post):
    - For each TYPE that fired, compare to what actually happened:
      - TYPE 1: did IV expand before expiry? (realized move > implied suggests
        expansion; proxy only — we don't track pre-print option prices post-entry)
      - TYPE 4 POTENTIAL_OVERSHOOT: did price reverse the next day?
      - TYPE 4 HELD_REPRICING: did price continue in the same direction?
    - Accuracy rate per TYPE (% of predictions that matched ex-post behavior)
    - Flag: accuracy < 50% for any TYPE with >=5 obs → calibration alert
    - Track per TYPE separately (TYPE 1 accuracy ≠ TYPE 4 accuracy)
  - Dimension 3 — No-Trade Audit:
    - For TYPE 5 names where outcome_complete=True: did a significant move occur?
    - Significant = realized move > 1.3× conditional expected move
    - No-trade miss rate: % of TYPE 5 names with significant moves
    - Flag: miss rate > 30% with >=5 obs → potential alpha leakage
    - Subcategory: which no-trade condition fired most? (tracks whether
      AMBIGUOUS vol, LOW edge confidence, or efficient pricing is driving TYPE 5)
  - Dimension 4 — Decision Quality:
    - Separate four outcomes: good-decision/good-outcome, good-decision/bad-outcome,
      bad-decision/good-outcome, bad-decision/bad-outcome
    - Good decision = classification was ex-ante justified (TYPE conditions met)
    - Good outcome = trade was profitable (entry_taken=True, pnl > 0) OR
      no-trade was correct (TYPE 5, realized < 1.3× conditional expected)
    - Only applies to records where entry_taken is not None
  - Threshold gate: minimum 20 completed observations per parameter before
    any alert suggests changing a threshold; below 20, alerts say
    "PATTERN DETECTED — insufficient data for threshold change (N/20 observations)"
  - CalibrationReport fields:
    - period: str  (e.g., "2026-W17 to 2026-W30")
    - n_complete: int  (records with outcome_complete=True)
    - edge_ratio_accuracy: dict  (by label bucket)
    - type_accuracy: dict  (by type number)
    - no_trade_miss_rate: float
    - no_trade_condition_distribution: dict  (which conditions fired most)
    - decision_quality: dict  (four-quadrant counts)
    - alerts: list[str]  (calibration alerts for manual review)
    - threshold_gate_met: bool  (True if >=20 complete records)

acceptance_criteria:
  - Report generated with INSUFFICIENT DATA warning when <5 complete records
  - Edge ratio accuracy computed per label bucket
  - TYPE accuracy tracked separately per type number
  - No-trade miss rate computed from TYPE 5 records
  - Decision quality four-quadrant counts present when entry_taken data available
  - Alerts fired only when N >= 5 for that metric
  - Threshold change alerts include observation count vs 20-obs gate
  - Report saved to reports/calibration/ with ISO week in filename

tests:
  unit:
    - test_edge_ratio_accuracy_rich_bucket
    - test_edge_ratio_accuracy_cheap_bucket
    - test_type_accuracy_type1
    - test_type_accuracy_type4_overshoot
    - test_type_accuracy_type4_held
    - test_no_trade_miss_rate_calculation
    - test_no_trade_condition_distribution
    - test_decision_quality_four_quadrants
    - test_insufficient_data_warning_below_5
    - test_threshold_gate_message_below_20
    - test_alert_fires_on_poor_accuracy
    - test_report_saved_to_calibration_dir
  integration:
    - Full run with 10 synthetic complete records → report generated, console
      summary printed, alerts evaluated

definition_of_done:
  - run_calibration_report() implemented with CalibrationReport dataclass
  - scripts/run_calibration.py CLI script working
  - Reports saved to reports/calibration/ with ISO week naming
  - All unit and integration tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - With 10-20 trades per quarter, most accuracy metrics will be noisy. The
    calibration loop catches catastrophic miscalibration (consistently wrong
    in the same direction), not fine-grained parameter drift.
  - Do not over-optimize: if the system is roughly right and not systematically
    losing, the thresholds are working. The bar for changing a hardcoded
    threshold is: >=20 observations AND consistent pattern AND directional
    understanding of why it's miscalibrated.
  - Decision quality is the most important metric for learning: it separates
    good process from lucky outcomes. A TYPE 4 POTENTIAL_OVERSHOOT that didn't
    work because of a macro shock is a good decision / bad outcome — do not
    update rules based on it.

failure_modes:
  - DB unavailable → raise with path context
  - Fewer than 5 complete records → emit warning, exit 0 (not an error)
  - entry_taken=None for all records → decision quality section omitted with note
  - pnl data missing → decision quality uses outcome direction only (price reversal)
