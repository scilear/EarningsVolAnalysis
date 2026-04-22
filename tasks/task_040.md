id: T040
title: Structure Advisor Core (structure_advisor.py)

objective:
  Implement event_vol_analysis/structure_advisor.py — the core engine that
  takes a payoff-type query, fetches only the required strikes from the option
  chain, prices each candidate structure, runs fitness gates, and returns a
  ranked StructureAdvisorResult with a compact summary table. No raw chain
  data enters the caller's context.

context:
  The vol-specialist agent currently loads full option chains (200–400 lines)
  into reasoning context to extract 6–8 numbers for structure pricing. This
  module replaces that pattern entirely. The agent calls query_structures() and
  receives a pre-built comparison table — the agent only applies narrative
  judgment on top of it. Full design spec: docs/STRUCTURE_ADVISOR_SPEC.md.

inputs:
  - T039: payoff_map.py (PayoffType enum + get_structures_for_payoff())
  - T039: DiagonalSpread and RiskReversal structure definitions
  - OptionTrader tools (~/Documents/OptionTrader/tools/option_chain.py) for
    targeted strike fetching — call via subprocess with --strikes flag

outputs:
  - New module event_vol_analysis/structure_advisor.py containing:
    - query_structures(payoff_type, ticker, expiry, spot, budget=None,
      context=None) → StructureAdvisorResult
    - StructureAdvisorResult dataclass:
        ranked_structures: list[ScoredStructure]
        excluded: list[ExcludedStructure]
        fitness_flags: list[str]
        vol_regime_summary: str
        to_table() → str  (compact ≤60 line output)
    - ScoredStructure dataclass:
        structure_name: str
        net_debit: float
        annualized_carry_pct: float
        max_loss: float
        breakeven: float | None
        loss_zone: tuple[float, float] | None
        rank: int
        note: str | None
    - ExcludedStructure dataclass:
        structure_name: str
        reason: str  (BUDGET_EXCEEDED / CHARTER_BLOCKED / LIQUIDITY_INSUFFICIENT)

prerequisites:
  - T039 (structure library + payoff map)
  - OptionTrader installed and accessible at ~/Documents/OptionTrader/

dependencies:
  - T039

non_goals:
  - No Monte Carlo EV/CVaR scoring (that is full scoring.py — overkill for
    this use case; use deterministic pricing only)
  - No portfolio-level analysis (aggregate delta, notional limits)
  - No trade execution or recommendation outside of structure comparison
  - No intraday data or real-time streaming

requirements:
  - Strike targeting: for each candidate structure, compute required strikes
    from spot + standard offset rules (do not load full chain):
    - OTM put: spot × (1 - otm_pct), where otm_pct ∈ {0.02, 0.04, 0.07, 0.10}
    - Put spread: two strikes (near-OTM + far-OTM)
    - Diagonal: short strike (spot × 0.96), long strike (spot × 0.93),
      two expiries
    - Fetch only those strikes + expiries via option_chain.py --strikes A,B,C
  - Pricing: use mid = (bid + ask) / 2 for each leg; net debit = sum of legs
    with signs
  - Annualized carry: net_debit / (spot × dte / 365) × 100
  - Diagonal conditional cost note: if short leg expires OTM → effective cost
    = net_debit; if assigned → add assignment cost; both figures in output
  - Loss zone: for ratio/diagonal structures, compute strike range where
    terminal P&L < −net_debit; display as (lower, upper) or None
  - Fitness gates (per docs/STRUCTURE_ADVISOR_SPEC.md):
    - IVP >80% for crash/rally: warn, do not block
    - IVP >60% for vol-expansion: warn, do not block
    - Binary event within DTE for sideways: warn, do not block
    - Naked short (requires_naked_short_approval=True): hard block → move to
      excluded with reason CHARTER_BLOCKED
    - Budget: if net_debit > budget → BUDGET_EXCEEDED in excluded
  - Ranking: primary sort by annualized_carry_pct ascending (cheaper is better
    for debit structures); ratio/diagonal structures penalized for conditional
    cost
  - to_table() output: ≤60 lines, compact ASCII table matching spec format
    (see docs/STRUCTURE_ADVISOR_SPEC.md Output Format section)
  - context dict accepts: iv_percentile (float), dte (int), vix (float) —
    all optional; fitness gates degrade gracefully if absent

acceptance_criteria:
  - query_structures(PayoffType.CRASH, "GLD", "2026-05-15", 429.57) returns
    StructureAdvisorResult with ≥3 ranked structures
  - to_table() output is ≤60 lines
  - Diagonal structure appears in output with conditional cost note
  - ShortStrangle excluded with reason CHARTER_BLOCKED
  - Budget filter correctly excludes structures above threshold
  - No raw chain data in returned object (only extracted fields per structure)
  - Annualized carry computed correctly for a 23 DTE, $342 debit, $429.57 spot
    → expected ~12.5%

tests:
  unit:
    - test_strike_targeting_crash_puts
    - test_strike_targeting_diagonal_two_expiries
    - test_annualized_carry_calculation
    - test_loss_zone_diagonal_between_strikes
    - test_loss_zone_none_for_debit_spread
    - test_fitness_gate_ivp_warning_not_blocking
    - test_fitness_gate_naked_short_hard_block
    - test_budget_filter_excludes_over_budget
    - test_to_table_line_count_under_60
    - test_ranking_cheaper_first
    - test_diagonal_conditional_cost_note_present
    - test_context_optional_graceful_degradation
  integration:
    - query_structures with mocked option_chain subprocess → full
      StructureAdvisorResult returned, smoke passes

definition_of_done:
  - structure_advisor.py exists with query_structures() and all dataclasses
  - All unit tests pass
  - Integration test with mocked chain data passes
  - to_table() output validated to ≤60 lines on a 4-structure result
  - Task marked complete in docs/TASKS.md

notes:
  - Call OptionTrader's option_chain.py via subprocess with --strikes flag and
    --output json to get targeted data. Parse only the fields needed (bid, ask,
    iv, delta, vega). Do not import OptionTrader directly — subprocess boundary
    keeps the dependency clean and avoids venv conflicts.
  - If option_chain.py subprocess fails (IB gateway down, network issue),
    return a StructureAdvisorResult with an explicit data_unavailable flag
    and empty ranked_structures — do not fall back to estimated pricing.

failure_modes:
  - option_chain.py subprocess fails → return data_unavailable result, do
    not estimate prices
  - Strike not found in chain response (illiquid) → exclude structure with
    reason LIQUIDITY_INSUFFICIENT
  - context iv_percentile absent → fitness gate warning omitted, not errored
