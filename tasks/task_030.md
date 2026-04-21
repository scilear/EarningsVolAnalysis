id: T030
title: Post-Earnings Outcome Tracking

objective:
  Extend the event store to record the ex-ante TYPE classification and edge
  ratio alongside the realized move and Phase 1 category for each earnings event,
  enabling the calibration loop (T031) to compare predictions against outcomes.

context:
  The calibration loop is only useful if prediction and outcome are stored
  together in a queryable form. This task adds a new outcome record per event
  that captures: what the tool predicted (TYPE, edge ratio, vol regime label)
  and what actually happened (realized move, Phase 1 classification, whether an
  entry was taken). The realized move is auto-populated from price history after
  the event date passes. Phase 1 classification is manually provided by the
  operator via a CLI command or data entry script.

inputs:
  - TypeClassification from T027 (ex-ante prediction, at analysis time)
  - EdgeRatio from T025 (ex-ante, at analysis time)
  - VolRegimeResult from T023 (ex-ante, at analysis time)
  - Ticker, event_date, timing (AMC/BMO)
  - Realized move: auto-fetched from price history after event_date passes
  - Phase 1 category: 'HELD_REPRICING' | 'POTENTIAL_OVERSHOOT' | 'NOT_ASSESSED'
    (provided by operator after event via update script)
  - Entry taken: bool (operator-provided post-event)
  - PnL if entered: float | None (operator-provided post-event, optional)

outputs:
  - EarningsOutcomeRecord dataclass
  - store_prediction(ticker, event_date, type_classification, edge_ratio,
      vol_regime) function (called at analysis time)
  - update_outcome(ticker, event_date, phase1_category, entry_taken, pnl)
      function (called post-event by operator)
  - auto_populate_realized_move(ticker, event_date) function (runs from cron or
    manually; fetches close-to-close move from price history)
  - New table in existing event store DB: earnings_outcomes
  - Script: scripts/update_earnings_outcome.py (CLI for operator to enter
    Phase 1 category and entry decision)

prerequisites:
  - T002 (event dataset and outcomes — existing event store infrastructure)
  - T027 (TYPE classifier produces the prediction to store)

dependencies:
  - T002
  - T027

non_goals:
  - No automated P&L tracking from brokerage (manual entry only)
  - No real-time price fetching (uses yfinance history, called once after event)
  - No modification of existing event store tables (additive new table only)

requirements:
  - EarningsOutcomeRecord fields:
    - id: int (autoincrement)
    - ticker: str
    - event_date: date
    - timing: str  # 'AMC' | 'BMO' | 'UNKNOWN'
    - analysis_timestamp: datetime  (when the prediction was generated)
    - predicted_type: int  (1-5)
    - predicted_confidence: str  # HIGH | MEDIUM | LOW
    - edge_ratio_label: str  # CHEAP | FAIR | RICH
    - edge_ratio_value: float
    - edge_ratio_confidence: str
    - vol_regime_label: str  # CHEAP | NEUTRAL | EXPENSIVE | AMBIGUOUS
    - implied_move: float
    - conditional_expected_move: float
    - realized_move: float | None  (populated post-event)
    - realized_move_direction: str | None  # UP | DOWN
    - realized_vs_implied_ratio: float | None  (realized / implied, post-event)
    - phase1_category: str | None  # HELD_REPRICING | POTENTIAL_OVERSHOOT | NOT_ASSESSED
    - entry_taken: bool | None
    - pnl_if_entered: float | None
    - outcome_complete: bool  (True when realized_move and phase1_category both set)
  - store_prediction(): inserts a new record at analysis time; sets
    outcome_complete=False, all realized fields to None
  - update_outcome(): updates existing record for (ticker, event_date);
    sets phase1_category, entry_taken, pnl; sets outcome_complete=True if
    realized_move also set
  - auto_populate_realized_move():
    - Fetch close-to-close price for the event day using get_price_history()
    - AMC: close on event_date vs close on next trading day
    - BMO: close on prior trading day vs open on event_date
    - Store in realized_move column; compute realized_vs_implied_ratio
    - Idempotent: if already populated, skip unless --force flag
  - scripts/update_earnings_outcome.py:
    - CLI: --ticker, --event-date, --phase1 [HELD_REPRICING|POTENTIAL_OVERSHOOT],
      --entry [yes|no], --pnl [float]
    - Prints current record before update for confirmation
    - Validates phase1 input against allowed values
  - earnings_outcomes table created with CREATE IF NOT EXISTS — additive

acceptance_criteria:
  - store_prediction() inserts record without error on first call for a ticker/date
  - store_prediction() raises if record already exists for same (ticker, event_date)
    (one prediction per event)
  - update_outcome() updates correct record; idempotent if called twice with same data
  - auto_populate_realized_move() correctly computes AMC and BMO day pairs
  - realized_vs_implied_ratio computed correctly after realized_move is set
  - outcome_complete = True only when both realized_move and phase1_category set
  - CLI script runs without error for a test record

tests:
  unit:
    - test_store_prediction_inserts_record
    - test_store_prediction_duplicate_raises
    - test_update_outcome_sets_fields
    - test_update_outcome_idempotent
    - test_auto_populate_amc_day_pair (close d → close d+1)
    - test_auto_populate_bmo_day_pair (close d-1 → open d)
    - test_outcome_complete_flag_false_when_partial
    - test_outcome_complete_flag_true_when_both_set
    - test_realized_vs_implied_ratio_calculation
  integration:
    - Full flow: store_prediction → auto_populate_realized_move → update_outcome
      → query record → outcome_complete = True

definition_of_done:
  - EarningsOutcomeRecord dataclass and earnings_outcomes table implemented
  - store_prediction(), update_outcome(), auto_populate_realized_move() implemented
  - scripts/update_earnings_outcome.py CLI script working
  - All unit and integration tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - PnL entry is optional and manual — the tool does not know what size was used
    or what the actual fill was. Operator enters approximate PnL from brokerage.
  - The record is immutable after outcome_complete=True except via explicit
    --force override (to correct data entry errors).
  - Phase 1 classification is always a human judgment — the tool suggests it
    from Phase 1 metrics (move held, volume, IV normalized) but the operator
    confirms. This task stores the confirmed category, not an inferred one.

failure_modes:
  - Price history unavailable for event date → realized_move stays None,
    log warning; operator can retry with --force later
  - Duplicate store_prediction call → raise ValueError with existing record ID
  - DB write failure → raise with context; do not partially write
  - CLI update with invalid phase1 value → print valid options and exit 1
