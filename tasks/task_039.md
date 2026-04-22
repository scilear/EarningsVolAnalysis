id: T039
title: Structure Library + Payoff-Type Mapping

objective:
  Extend structures.py with missing structure definitions (diagonal spread,
  risk reversal) and create a PAYOFF_STRUCTURE_MAP that maps each of the six
  atomic payoff types to its list of candidate structure keys. This is the
  catalogue layer that T040 (Structure Advisor core) queries.

context:
  The Structure Advisor (T039–T041) replaces inline option chain analysis
  in the vol-specialist agent. Currently the agent loads full chains into
  context to price 3–4 structures — expensive and non-reproducible. The
  payoff-type map is the first building block: for any given payoff intent
  (crash, sideways, vol-expansion, etc.), the tool knows which structures
  to price. Full design spec: docs/STRUCTURE_ADVISOR_SPEC.md.

inputs:
  - Existing event_vol_analysis/strategies/structures.py
  - Existing event_vol_analysis/strategies/backspreads.py (ratio backspread
    already implemented — wire into crash map)
  - docs/STRUCTURE_ADVISOR_SPEC.md (payoff type taxonomy + structure library)

outputs:
  - Updated structures.py with DiagonalSpread and RiskReversal structure
    definitions added
  - New file event_vol_analysis/strategies/payoff_map.py containing:
    - PayoffType enum: CRASH, RALLY, SIDEWAYS, VOL_EXPANSION,
      VOL_COMPRESSION, DIRECTIONAL_CONVEX
    - PAYOFF_STRUCTURE_MAP: dict[PayoffType, list[str]] — structure keys
      per type
    - get_structures_for_payoff(payoff_type) → list[Structure]

prerequisites:
  - T022 (regression smoke harness — run before and after to protect trust path)

dependencies:
  - T022

non_goals:
  - No pricing logic here — only structure definitions and mapping
  - No CLI changes — that is T041
  - No fitness gate logic — that is T040
  - Do not add all deferred backlog structures — only diagonal and risk
    reversal are pulled forward; jade lizard, broken-wing butterfly, etc.
    remain deferred

requirements:
  - PayoffType enum with six members (CRASH, RALLY, SIDEWAYS, VOL_EXPANSION,
    VOL_COMPRESSION, DIRECTIONAL_CONVEX)
  - PAYOFF_STRUCTURE_MAP must include ≥3 candidate structures per payoff type
    (see spec for full list — minimums: crash ≥4, sideways ≥3, vol-expansion ≥2)
  - DiagonalSpread: short near-dated OTM put × N, long far-dated further-OTM
    put × 2N. Parameters: short_expiry, long_expiry, short_strike, long_strike,
    ratio (default 2). Required for crash map.
  - RiskReversal: short OTM put / long OTM call (or reverse). Parameters:
    put_strike, call_strike, expiry, direction (BULLISH/BEARISH).
  - Charter flag on structures requiring manual approval:
    - ShortStrangle, ShortStraddle → requires_naked_short_approval=True
    - CoveredCall → requires_existing_long=True
  - get_structures_for_payoff() must return Structure objects, not just keys
  - All new structure definitions must be independently testable via payoff.py
    terminal P&L calculation

acceptance_criteria:
  - PAYOFF_STRUCTURE_MAP["CRASH"] returns ≥4 structure keys
  - get_structures_for_payoff(PayoffType.CRASH) returns valid Structure list
  - DiagonalSpread terminal P&L computable via existing payoff.py
  - RiskReversal terminal P&L computable via existing payoff.py
  - Charter flags present on ShortStrangle, ShortStraddle, CoveredCall
  - Regression smoke tests pass after changes

tests:
  unit:
    - test_payoff_map_crash_has_min_4_structures
    - test_payoff_map_sideways_has_min_3_structures
    - test_payoff_map_vol_expansion_has_min_2_structures
    - test_all_payoff_types_present_in_map
    - test_diagonal_spread_payoff_at_expiry_long_leg
    - test_diagonal_spread_payoff_at_expiry_both_expired
    - test_risk_reversal_payoff_bullish
    - test_risk_reversal_payoff_bearish
    - test_charter_flag_on_short_strangle
    - test_charter_flag_on_covered_call
    - test_get_structures_for_payoff_returns_structure_objects
  integration:
    - Full smoke harness passes after changes to structures.py

definition_of_done:
  - payoff_map.py exists with PayoffType enum and PAYOFF_STRUCTURE_MAP
  - DiagonalSpread and RiskReversal defined in structures.py
  - All unit tests pass
  - Smoke harness passes
  - Task marked complete in docs/TASKS.md

notes:
  - Diagonal spread has a conditional loss zone (between short strike and
    long strike at near-expiry, if short leg assigned). Document this in
    the Structure definition — T040 uses it for loss zone computation.
  - Keep the structure registry (registry.py) in sync — add new structure
    keys there as well.

failure_modes:
  - payoff.py terminal P&L cannot handle two-expiry structures → diagonal
    must handle the case where near leg expires first; document expected
    behavior in the structure definition rather than computing it dynamically
