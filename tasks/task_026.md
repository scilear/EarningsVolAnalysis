id: T026
title: Positioning Proxy Module

objective:
  Implement analytics/positioning.py with four observable positioning signals
  (OI concentration, P/C ratio trend, price drift vs sector, max pain distance)
  and combine them into a UNDER-POSITIONED / BALANCED / CROWDED classification
  with explicit confidence and individual signal transparency.

context:
  The playbook's Layer C is explicitly low-confidence. OI, P/C ratios, drift,
  and max pain are weak proxies for actual positioning, which is unobservable at
  retail scale. The goal is signal agreement, not precision measurement. All four
  signals must agree for HIGH confidence; any disagreement defaults to BALANCED
  with LOW confidence. This layer is a tiebreaker that feeds T027, not a gate
  that blocks trades on its own. The module docstring must explicitly state this
  limitation.

inputs:
  - Option chain DataFrame (from data/loader.py — needs OI, strike, option_type,
    volume, call/put type columns)
  - pc_5d: float (recent 5-day avg put/call volume ratio; caller computes from chain)
  - pc_20d_avg: float (trailing 20-day avg P/C ratio; caller provides or config default)
  - ticker_10d_ret: float (ticker 10-day return; caller fetches from price history)
  - sector_10d_ret: float (sector ETF 10-day return; caller provides)
  - spot: float (current spot price)

outputs:
  - PositioningSignal enum: BULLISH | BEARISH | NEUTRAL
  - PositioningResult dataclass
  - Four individual signal functions + classify_positioning()
  - New module: event_vol_analysis/analytics/positioning.py

prerequisites:
  - None (inputs come from existing loader and chain infrastructure)

dependencies:
  - None

non_goals:
  - No intraday tape reading or real-time order flow
  - No dealer gamma inference (analytics/gamma.py owns that)
  - No direct T027 integration in this task (T027 wires it)
  - No sector ETF return fetching — caller provides sector_10d_ret as float or None

requirements:
  - PositioningSignal: enum with BULLISH, BEARISH, NEUTRAL values
  - SignalResult: dataclass with {signal: PositioningSignal, is_available: bool, note: str}
  - Signal 1 — oi_concentration(chain: pd.DataFrame) -> SignalResult:
    - Compute total OI per strike, separately for calls and puts
    - BULLISH: top-3 call strikes hold >40% of total call OI AND >2x the put OI
      concentration in those same strikes
    - BEARISH: mirror logic for put side
    - NEUTRAL: everything else
    - is_available=False if chain has no OI column or OI is all zeros
  - Signal 2 — pc_ratio_signal(pc_5d: float | None, pc_20d_avg: float | None)
      -> SignalResult:
    - BEARISH (crowded downside): pc_5d > 1.2 * pc_20d_avg
    - BULLISH (crowded upside): pc_5d < 0.8 * pc_20d_avg
    - NEUTRAL: otherwise
    - is_available=False if either input is None
  - Signal 3 — drift_vs_sector(ticker_10d_ret: float | None,
      sector_10d_ret: float | None) -> SignalResult:
    - relative_drift = ticker_10d_ret - sector_10d_ret
    - BULLISH: relative_drift > 2 * abs(sector_10d_ret)
    - BEARISH: relative_drift < -2 * abs(sector_10d_ret)
    - NEUTRAL: otherwise
    - Degenerate: if sector_10d_ret == 0, use 2% absolute threshold instead
    - is_available=False if either input is None
  - Signal 4 — max_pain_distance(chain: pd.DataFrame, spot: float) -> SignalResult:
    - Compute max pain internally: for each strike, sum OI-weighted P&L for all
      option writers; max pain = strike minimizing total writer loss
    - distance = (max_pain_strike - spot) / spot
    - BULLISH: distance > 0.03 (max pain >3% above spot)
    - BEARISH: distance < -0.03
    - NEUTRAL: |distance| <= 0.03
    - is_available=False if chain empty or no OI data
  - classify_positioning(oi, pc, drift, mp: SignalResult) -> PositioningResult:
    - Count votes from available signals only (skip is_available=False)
    - CROWDED: 3+ available signals, all same direction (BULLISH or BEARISH);
      direction stored as 'UPSIDE' or 'DOWNSIDE'
    - UNDER-POSITIONED: all available signals NEUTRAL (min 2 available)
    - BALANCED: any disagreement, or fewer than 2 available signals
    - Confidence:
      - HIGH: all 4 available AND all agree
      - MEDIUM: exactly 3 available AND all agree (one is_available=False)
      - LOW: everything else (default for BALANCED)
  - PositioningResult dataclass fields:
    - label: str  # UNDER-POSITIONED | BALANCED | CROWDED
    - direction: str | None  # UPSIDE | DOWNSIDE | None
    - confidence: str  # HIGH | MEDIUM | LOW
    - signals: dict[str, SignalResult]  # keys: 'oi', 'pc', 'drift', 'max_pain'
    - available_count: int
    - note: str  (human-readable summary of agreement/disagreement)

acceptance_criteria:
  - CROWDED fires only when 3+ signals agree directionally
  - BALANCED fires on any disagreement or <2 available signals
  - HIGH confidence only when all 4 available AND all agree
  - Max pain computed internally from chain when not pre-computed
  - Unavailable signals excluded from consensus count
  - All 4 individual SignalResult objects present in PositioningResult.signals
  - note field always populated with human-readable signal summary
  - Module docstring explicitly states: "weak proxies, use as tiebreaker only"

tests:
  unit:
    - test_oi_concentration_bullish (call-heavy top strikes → BULLISH)
    - test_oi_concentration_bearish (put-heavy top strikes → BEARISH)
    - test_oi_concentration_neutral (balanced → NEUTRAL)
    - test_oi_no_oi_column (→ NEUTRAL, is_available=False)
    - test_pc_ratio_elevated_puts (pc_5d = 1.5 * pc_20d → BEARISH)
    - test_pc_ratio_elevated_calls (pc_5d = 0.6 * pc_20d → BULLISH)
    - test_pc_ratio_normal (within band → NEUTRAL)
    - test_pc_ratio_missing_input (→ NEUTRAL, is_available=False)
    - test_drift_outperform (→ BULLISH)
    - test_drift_underperform (→ BEARISH)
    - test_drift_flat (→ NEUTRAL)
    - test_drift_sector_zero_degenerate (→ uses 2% absolute threshold)
    - test_max_pain_above_spot (→ BULLISH)
    - test_max_pain_below_spot (→ BEARISH)
    - test_max_pain_at_spot (→ NEUTRAL)
    - test_classify_all_agree_bullish (→ CROWDED UPSIDE, HIGH)
    - test_classify_all_agree_bearish (→ CROWDED DOWNSIDE, HIGH)
    - test_classify_disagreement (→ BALANCED, LOW)
    - test_classify_two_unavailable (→ BALANCED, LOW)
    - test_classify_three_agree_one_missing (→ CROWDED, MEDIUM)
    - test_classify_all_neutral (→ UNDER-POSITIONED)
  integration:
    - Full pipeline: chain → all 4 signals → classify_positioning → report shows
      label, confidence, and all 4 individual signals

definition_of_done:
  - analytics/positioning.py with PositioningSignal, SignalResult,
    PositioningResult, four signal functions, and classify_positioning()
  - PositioningResult appears per-name in report
  - All 4 individual signals visible in report detail
  - All unit and integration tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Module docstring must include: "OI does not equal directional conviction.
    P/C ratios are distorted by hedging and structured products. Max pain is
    noise at a 10-day horizon. These are weak proxies — use as tiebreaker only."
  - If CROWDED fires on >30% of screened universe, thresholds are too loose —
    add a warning log when batch mode detects this.
  - BALANCED + LOW is the correct and expected default for most names.

failure_modes:
  - Empty chain → all signals NEUTRAL, is_available=False; BALANCED, LOW, count=0
  - sector_10d_ret is None → drift_vs_sector returns NEUTRAL, is_available=False
  - Max pain computation fails (degenerate chain) → NEUTRAL, is_available=False
  - OI all zeros in chain → oi_concentration returns NEUTRAL, is_available=False
