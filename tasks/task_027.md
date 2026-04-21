id: T027
title: TYPE 1-5 Classifier

objective:
  Implement a deterministic rule engine in strategies/type_classifier.py that
  combines the four snapshot layers (vol regime, edge ratio, positioning proxy,
  signal graph) into exactly one TYPE per name. TYPE 5 is the default; other
  types require all listed conditions to hold. Output includes rationale, action
  guidance, and a Phase 2 checklist for TYPE 4.

context:
  The TYPE classifier is the decision engine at the core of the playbook. It
  replaces narrative-based trade decisions with a traceable, auditable rule
  check. Every condition that passes or fails is logged in the rationale list.
  TYPE 5 rationale must always be explicit — "conditions not met because X" is
  required, never an empty no-trade. The four layers (T023-T026) feed in; signal
  graph (T028) is optional but upgrades TYPE 4 confidence when available.

inputs:
  - vol_regime: VolRegimeResult (from T023)
  - edge_ratio: EdgeRatio (from T025)
  - positioning: PositioningResult (from T026)
  - signal_graph: SignalGraphResult | None (from T028; None until T028 is built)
  - event_state: dict with keys:
      event_date: date
      today: date
      phase1_category: str | None  # 'HELD_REPRICING' | 'POTENTIAL_OVERSHOOT' | None
      phase1_metrics: dict | None  # vol held, volume ratio, move vs implied
  - operator_inputs: dict with optional keys:
      falsifier: str | None  (required for TYPE 3; None → TYPE 3 blocked)
      narrative_label: str | None  # 'PRICED' | 'PARTIALLY_PRICED' | 'UNCERTAIN'
      has_position: bool | None  (for TYPE 2 portfolio ownership check)

outputs:
  - TypeClassification dataclass
  - classify_type() function
  - New module: event_vol_analysis/strategies/type_classifier.py

prerequisites:
  - T023 (vol regime dual classifier)
  - T025 (edge ratio)
  - T026 (positioning proxy)

dependencies:
  - T023
  - T025
  - T026

non_goals:
  - No ML or learned rules — all conditions are deterministic and hardcoded
  - No auto-execution of any trade recommendation
  - No intraday real-time classification (Phase 1 uses end-of-day data)
  - Signal graph (T028) is a soft input; classifier works without it

requirements:
  - TypeClassification dataclass fields:
    - type: int  # 1 | 2 | 3 | 4 | 5
    - rationale: list[str]  (each condition evaluated, pass or fail, one per entry)
    - action_guidance: str  (what to do next, specific and concise)
    - phase2_checklist: list[str] | None  (TYPE 4 only; None for all other types)
    - confidence: str  # HIGH | MEDIUM | LOW
    - is_no_trade: bool  (True when type == 5)
    - frequency_warning: bool  (True if TYPE 1 fires and universe-level gate check
        indicates >10% TYPE 1 rate — caller must track; classifier sets flag per-name
        when its own conditions fire)

  - Classification rules (evaluated in order; first match wins):

    TYPE 1 — Pre-Earnings Vol Buy (RARE):
      ALL of:
      - event_state.event_date > event_state.today  (event not yet printed)
      - vol_regime.label == 'CHEAP'  (IVR < 30 AND IVP < 30)
      - vol_regime.confidence != 'LOW'  (not AMBIGUOUS)
      - edge_ratio.label == 'CHEAP'  (ratio < 0.8)
      - edge_ratio.confidence != 'LOW'
      - operator_inputs.narrative_label == 'UNCERTAIN'
      - positioning drift signal != BULLISH or BEARISH with HIGH confidence
        (i.e. pre-earnings drift is flat — drift_vs_sector result is NEUTRAL
        or positioning.confidence == LOW)
      Action guidance: "Buy straddle or strangle with 7-10 DTE. Exit BEFORE print.
        No exceptions — this is a vol expansion trade, not an earnings bet."
      Confidence: HIGH if edge_ratio.confidence HIGH, MEDIUM otherwise

    TYPE 2 — Premium Sell on Existing Position:
      ALL of:
      - event_state.event_date > event_state.today  (event not yet printed)
      - vol_regime.label == 'EXPENSIVE'  (IVR > 80 and IVP > 80; strict threshold
          for TYPE 2, not just >60 EXPENSIVE bucket — check raw IVR/IVP values)
      - edge_ratio.label == 'RICH'  (ratio > 1.3)
      - operator_inputs.narrative_label == 'PRICED'
      - operator_inputs.has_position == True
      Action guidance: "Sell covered call on existing position. Defined risk only.
        No naked short. Size by max loss, max 2% NAV."
      Confidence: MEDIUM (positioning-dependent; covered call payoff is always
        defined risk regardless of positioning)
      Note: if has_position is None, TYPE 2 is blocked; include in rationale:
        "TYPE 2 blocked: portfolio ownership not confirmed"

    TYPE 3 — Convex Directional (RARE):
      ALL of:
      - event_state.event_date > event_state.today  (event not yet printed)
      - operator_inputs.falsifier is not None and len(falsifier.strip()) > 0
      Action guidance: "Buy small outright options only. Max 0.5% NAV. State
        falsifier at entry. Exit intraday if falsifier triggers. 2-day max hold."
      Confidence: LOW (non-consensus view cannot be verified systematically)
      Note: if falsifier is None or empty, TYPE 3 is blocked; emit rationale
        "TYPE 3 blocked: no falsifiable trigger provided — defaults to TYPE 5"

    TYPE 4 — Post-Earnings Reaction:
      ALL of:
      - event_state.event_date <= event_state.today  (earnings have printed)
      - event_state.phase1_category is not None  (Phase 1 assessment done)
      - edge_ratio.confidence != 'LOW'
      Sub-type from phase1_category:
        'POTENTIAL_OVERSHOOT':
          Action guidance: "Potential fade candidate. Check pre-market: is
            reversal continuing? Is IV normalizing? Has downstream follower
            already absorbed signal? Enter next morning only if all three confirm."
          Phase 2 checklist:
            - "Pre-market: price reversal continuing (not just close noise)?"
            - "IV: crushing toward normal levels (not still elevated)?"
            - "Signal graph: downstream follower has NOT already moved >50% of
               upstream move?"
            - "Volume: fading (not a new wave of directional volume)?"
            - "Only enter if ALL four confirm. Limit order at mid. No chasing."
        'HELD_REPRICING':
          Action guidance: "Move held, repricing confirmed. Do NOT fade the
            printed name. Check if downstream follower has not yet repriced."
          Phase 2 checklist:
            - "Signal graph: identify downstream follower with FRESH signal"
            - "Follower has NOT already moved >50% of upstream move?"
            - "Follower's own pre-earnings IV is still stale (not repriced yet)?"
            - "Enter follower next morning. Limit order at mid. 1-2% NAV."
      Confidence:
        - HIGH if signal_graph is not None and fresh follower identified
        - MEDIUM if phase1_category confirms but no signal graph available
        - LOW if phase1_metrics are incomplete or phase1 was uncertain

    TYPE 5 — No Trade (DEFAULT):
      Fires when no other type conditions are fully met.
      Explicit no-trade conditions (log whichever apply):
        - vol_regime.label == 'AMBIGUOUS'
        - edge_ratio.confidence == 'LOW'
        - move approximately equals implied AND narrative_label == 'PRICED'
          (implies efficient pricing)
        - signal_graph shows signal absorbed (follower already moved >50%)
        - positioning.label == 'BALANCED' with confidence LOW AND no other
          strong layer signal
        - event_state.phase1_category is None (earnings printed but Phase 1
          not yet assessed — operator must complete assessment first)
      Action guidance: "No trade. Reason: [first matching no-trade condition]."
      is_no_trade: True

  - Frequency gate (TYPE 1 only):
    - Set frequency_warning=True on every TYPE 1 classification
    - Caller (batch runner) is responsible for tracking universe-level rate
      and emitting a warning if >10% of names classify as TYPE 1

acceptance_criteria:
  - Exactly one TYPE assigned per call
  - TYPE 5 fires as default when no other conditions are fully met
  - TYPE 5 rationale always lists at least one explicit no-trade condition
  - TYPE 3 blocked when falsifier is None or empty string; falls to TYPE 5
  - TYPE 2 blocked when has_position is None; falls to TYPE 5
  - TYPE 4 requires phase1_category to be populated; without it → TYPE 5
  - Phase 2 checklist populated for TYPE 4 (both sub-types), None for others
  - TYPE 2 IVR/IVP raw value check uses >80 threshold, not just EXPENSIVE bucket
  - All conditions evaluated and logged in rationale list (pass AND fail)

tests:
  unit:
    - test_type1_all_conditions_met
    - test_type1_blocked_ambiguous_vol_regime
    - test_type1_blocked_low_edge_confidence
    - test_type1_blocked_edge_not_cheap
    - test_type1_blocked_narrative_not_uncertain
    - test_type2_all_conditions_met
    - test_type2_blocked_no_position_confirmed
    - test_type2_blocked_ivr_below_80 (vol EXPENSIVE bucket but IVR=65 → blocked)
    - test_type3_with_falsifier
    - test_type3_blocked_no_falsifier (→ TYPE 5)
    - test_type4_potential_overshoot_phase2_checklist
    - test_type4_held_repricing_phase2_checklist
    - test_type4_blocked_phase1_not_assessed (→ TYPE 5)
    - test_type4_blocked_low_edge_confidence (→ TYPE 5)
    - test_type5_ambiguous_vol (→ TYPE 5 with explicit rationale)
    - test_type5_efficient_pricing (→ TYPE 5 with explicit rationale)
    - test_type5_is_default_when_no_match
    - test_rationale_always_populated
    - test_phase2_checklist_none_for_non_type4
    - test_frequency_warning_set_on_type1
  integration:
    - Full pipeline: vol_regime + edge_ratio + positioning → TYPE 1 name
    - Full pipeline: post-earnings name → TYPE 4 with Phase 2 checklist
    - Full pipeline: ambiguous name → TYPE 5 with explicit rationale

definition_of_done:
  - strategies/type_classifier.py with TypeClassification dataclass and
    classify_type()
  - TYPE output is the primary result in the report (above strategy ranking)
  - Strategy ranking retained as secondary output (for structure selection)
  - All unit and integration tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - TYPE 2 uses >80 for IVR AND IVP (stricter than the EXPENSIVE bucket threshold
    of >60). This is intentional: TYPE 2 is a premium sell, so the bar is higher.
    The EXPENSIVE bucket (>60) is used in regime classification; TYPE 2 entry
    requires the top of the EXPENSIVE zone.
  - TYPE 3 requires a human-provided falsifier. This cannot be automated. If
    the operator has not provided one via operator_inputs, the trade does not exist.
  - TYPE 4 Phase 2 checklists are instructions for next-morning manual review,
    not automated checks. The tool provides them; the operator executes them.
  - ONE ATTEMPT PER NAME PER EVENT: the classifier has no memory of prior
    classifications. The batch runner or operator must enforce the one-attempt rule.
  - Signal graph (T028) upgrades TYPE 4 confidence but is not required. TYPE 4
    works at MEDIUM confidence without it.

failure_modes:
  - vol_regime is None → raise ValueError (required input)
  - edge_ratio is None → raise ValueError (required input)
  - positioning is None → raise ValueError (required input)
  - event_state missing required keys → raise KeyError with key name
  - All optional operator_inputs missing → TYPE 3 blocked, TYPE 2 blocked;
    proceed with classification using None defaults
