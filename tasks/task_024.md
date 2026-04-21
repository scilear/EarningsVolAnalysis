id: T024
title: Conditional Expected Move

objective:
  Extend analytics/historical.py with a conditioning layer that produces a
  multi-estimate expected move: median, trimmed mean, and 4Q recency-weighted
  mean — each computed separately for AMC vs BMO events — and optionally
  conditioned on VIX quartile, pre-earnings drift direction, and same-cycle
  peer dispersion.

context:
  The current historical.py computes mean_abs_move and median_abs_move from the
  full signed-move series without any recency weighting, outlier trimming, or
  AMC vs BMO differentiation. The playbook requires all three sub-estimates plus
  conditioning to compute the edge ratio (T025). The AMC vs BMO split matters
  because the correct day pair differs: BMO = prior-close to open (same day);
  AMC = close on print day to close on next day. Using the wrong day pairs
  inflates or deflates the baseline systematically.

inputs:
  - Historical signed earnings moves from extract_earnings_moves() (already implemented)
  - Earnings date list with AMC/BMO timing flag (from event store or yfinance metadata)
  - VIX level at event time (optional, for quartile conditioning)
  - Pre-earnings 10D drift sign for the name (optional: +1 up, -1 down, 0 flat)
  - Same-cycle peer median realized move (optional, float or None)

outputs:
  - trimmed_mean_move(moves: list[float]) -> float (new function in historical.py)
  - recency_weighted_mean(moves, n_recent=4, recent_weight=2.0) -> float
  - split_by_timing(ticker, dates, moves) -> dict[str, list[float]]
    keys: 'amc', 'bmo', 'unknown'
  - ConditionalExpected dataclass
  - conditional_expected_move(moves, timing=None, vix_quartile=None,
      drift_sign=None, peer_median=None) -> ConditionalExpected

prerequisites:
  - T021 (fat-tailed distribution uses same historical move infrastructure)

dependencies:
  - T021

non_goals:
  - No new simulation paths (T021 owns simulation)
  - No edge ratio computation (T025 owns that)
  - No VIX quartile inference — caller provides vix_quartile as int (1-4) or None
  - No peer move computation — caller provides peer_median as float or None

requirements:
  - trimmed_mean_move(moves):
    - Operates on absolute values
    - Exclude exactly one top and one bottom observation
    - Require at least 4 observations after trimming; raise ValueError if fewer
  - recency_weighted_mean(moves, n_recent=4, recent_weight=2.0):
    - moves ordered oldest-first
    - Last n_recent observations each counted recent_weight times
    - Remaining observations counted 1 time each
    - Weighted mean of absolute values
    - Require at least n_recent observations; raise ValueError if fewer
  - split_by_timing(ticker, dates, moves):
    - dates: list of earnings dates aligned to moves (same index order)
    - Fetch AMC/BMO flag from event store; fall back to yfinance earnings metadata
    - Return dict with 'amc', 'bmo', 'unknown' keys (lists of absolute moves)
    - Log a warning for each date where timing cannot be resolved
    - Never raise on unresolvable dates — put them in 'unknown'
  - ConditionalExpected dataclass fields:
    - median: float
    - trimmed_mean: float | None  (None if <4 obs)
    - recency_weighted: float | None  (None if <4 obs)
    - timing_method: str  # 'amc' | 'bmo' | 'combined' | 'unknown'
    - n_observations: int  (count used after any split)
    - data_quality: str  # 'HIGH' >10 obs | 'MEDIUM' 6-10 | 'LOW' <6
    - conditioning_applied: list[str]  (which conditioning factors were used)
    - primary_estimate: float  (recency_weighted if available, else median)
  - AMC vs BMO split rule:
    - After split, use the sub-series matching event timing
    - If sub-series has <4 obs after split, fall back to combined series;
      set timing_method = 'combined' and log warning
    - Data quality flag reflects effective sample after split (post-split n)
  - Conditioning (additive, each optional):
    - VIX quartile: filter historical obs to same VIX quartile ± 1;
      if filtered sample < 4, skip conditioning entirely and log
    - Drift direction: filter to same-direction pre-earnings drift obs;
      if filtered sample < 4, skip and log
    - Peer median: store as additional field peer_conditioned in dataclass;
      never replaces primary_estimate
  - Existing mean_abs_move and median_abs_move keys must remain in output
    for backward compatibility — this task is additive

acceptance_criteria:
  - trimmed_mean excludes exactly one top and one bottom observation
  - recency_weighted applies 2x weight to the 4 most recent observations
  - split_by_timing returns 'unknown' for unresolvable dates, never raises
  - ConditionalExpected.primary_estimate uses recency_weighted when available,
    median otherwise
  - Conditioning that drops effective sample below 4 is skipped with log entry;
    output still produced from broader sample
  - timing_method always populated (never None)
  - data_quality correctly reflects post-split effective n

tests:
  unit:
    - test_trimmed_mean_normal (6 obs → mean of middle 4)
    - test_trimmed_mean_at_minimum (4 obs → trims to 2, raises ValueError)
    - test_trimmed_mean_too_few (3 obs → ValueError before trimming)
    - test_recency_weighted_normal (8 obs, last 4 at 2x weight)
    - test_recency_weighted_all_recent (4 obs, all at 2x)
    - test_recency_weighted_too_few (3 obs → ValueError)
    - test_split_by_timing_amc_bmo_mix
    - test_split_by_timing_unknown_fallback (all unknown → warning, 'unknown' key)
    - test_conditional_expected_no_conditioning
    - test_conditional_expected_amc_sufficient_split
    - test_conditional_expected_bmo_fallback_to_combined
    - test_data_quality_high (12 obs → HIGH)
    - test_data_quality_medium (8 obs → MEDIUM)
    - test_data_quality_low (4 obs → LOW)
    - test_vix_quartile_skip_if_insufficient
    - test_backward_compat_mean_abs_move_key_present
  integration:
    - Full pipeline: historical moves → split AMC/BMO → conditional expected →
      report shows timing_method and data_quality

definition_of_done:
  - trimmed_mean_move(), recency_weighted_mean(), split_by_timing(), and
    conditional_expected_move() implemented in analytics/historical.py
  - ConditionalExpected dataclass defined (consistent with existing module style)
  - Backward compatibility preserved (existing keys unchanged)
  - All unit tests pass
  - Integration test shows data_quality and timing_method in report output
  - Task marked complete in docs/TASKS.md

notes:
  - recency_weighted is the primary estimate because recent quarters reflect
    current market behavior regime. Median is the sanity check.
  - The conditioning layer degrades gracefully rather than blocking output.
    Data quality communicates estimate strength; it is not a pass/fail gate.
  - DO NOT silently replace the existing mean/median in the pipeline — add
    ConditionalExpected as a new snapshot field alongside existing fields.

failure_modes:
  - Moves list is empty → raise ValueError with ticker context
  - All dates have unknown timing → timing_method = 'unknown', log warning,
    use combined series
  - VIX quartile conditioning drops to <4 obs → skip, log, use original sample
  - recency_weighted fails (insufficient obs) → primary_estimate falls back to median
