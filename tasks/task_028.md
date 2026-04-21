id: T028
title: Signal Graph Module

objective:
  Implement analytics/signal_graph.py that maps upstream reporters (already
  printed this cycle) to downstream reactors (not yet printed), identifies
  leader vs follower roles, and detects signal decay. Output is an attention
  prioritizer that feeds TYPE 4 confidence in T027.

context:
  The signal graph exists to identify where to look for TYPE 4 follower trades,
  not to trigger trades on its own. The primary edge in TYPE 4 is in the
  downstream follower that has not yet repriced after an upstream print (e.g.,
  SYF prints bad credit → AXP hasn't moved → AXP is the trade, not SYF). The
  signal graph formalizes this mapping. Edge weights are based on human-curated
  sector/factor associations (not inferred), stored in a config file. The graph
  is directional and time-ordered: a node is a LEADER only if it has already
  printed; it is a FOLLOWER if it prints after today.

inputs:
  - calendar_df: pd.DataFrame with columns [ticker, event_date, sector, factors]
  - sector_map: dict (loaded from config/signal_graph_sectors.json)
  - factor_map: dict (loaded from config/signal_graph_sectors.json)
  - today: date (to classify LEADER vs FOLLOWER)
  - price_moves: dict[str, float] (ticker → recent % move since earnings, for
    signal decay detection; optional, pass empty dict if unavailable)

outputs:
  - SignalEdge dataclass: source, target, revenue_overlap, factor_overlap, weight
  - SignalNode dataclass: ticker, role (LEADER/FOLLOWER), event_date,
    has_signal, signal_decay_status
  - SignalGraphResult dataclass: nodes, edges, tradeable_followers
  - build_graph() function
  - classify_nodes() function
  - detect_signal_decay() function
  - get_tradeable_followers() function
  - Config file: config/signal_graph_sectors.json (initial chains seeded below)
  - New module: event_vol_analysis/analytics/signal_graph.py

prerequisites:
  - T027 (TYPE classifier consumes signal graph output)

dependencies:
  - T027

non_goals:
  - No causal inference or learned graph structure
  - No real-time price feed (price_moves passed in by caller from daily history)
  - No graph visualization (readable list output is sufficient)
  - No automated trade triggering (graph is attention prioritizer only)

requirements:
  - build_graph(calendar_df, sector_map, factor_map) -> list[SignalEdge]:
    - Create directed edge from A to B if both in calendar and A.event_date < B.event_date
    - Assign revenue_overlap weight: HIGH | MEDIUM | LOW (from sector_map config)
    - Assign factor_overlap weight: HIGH if same primary factor, MEDIUM if secondary
    - Combined edge weight = max(revenue_overlap, factor_overlap)
    - Exclude self-loops
  - classify_nodes(calendar_df, today) -> dict[str, SignalNode]:
    - LEADER: event_date <= today (already printed)
    - FOLLOWER: event_date > today (not yet printed)
    - has_signal: True for FOLLOWER nodes that have at least one LEADER edge
  - detect_signal_decay(follower_ticker, upstream_move_pct, follower_move_pct)
      -> str:
    - If follower already moved >= 50% of abs(upstream_move_pct) in same direction
      → ABSORBED
    - Otherwise → FRESH
    - If follower_move_pct is None (not available) → UNKNOWN
  - get_tradeable_followers(nodes, edges, price_moves) -> list[SignalNode]:
    - Return FOLLOWER nodes where:
      - has_signal = True (at least one upstream LEADER)
      - signal_decay_status = FRESH or UNKNOWN (not ABSORBED)
  - SignalGraphResult fields:
    - nodes: dict[str, SignalNode]
    - edges: list[SignalEdge]
    - tradeable_followers: list[SignalNode]  (already filtered for FRESH/UNKNOWN)
    - absorbed_followers: list[SignalNode]  (for transparency — signal already in)
  - config/signal_graph_sectors.json initial chains (seed with known pairs):
    Consumer credit chain: SYF → COF → AXP → V → MA → AMZN
    AI/tech suppliers: ASML → LRCX → AMAT → KLAC
    Semiconductors: NVDA → AMD → INTC → QCOM
    Energy majors: XOM → CVX → COP → SLB
    Revenue overlap and factor tags per pair documented in the config
  - The config is human-maintained. No inference from price data.
  - Scope hard limit: the graph tells WHERE to look (which followers),
    not WHAT to trade or HOW MUCH. Signal graph output never overrides the
    vol gate (T023) or edge ratio (T025).

acceptance_criteria:
  - LEADER/FOLLOWER tagging is correct relative to today's date
  - Signal decay ABSORBED fires when follower has already moved >=50% of upstream
  - Signal decay FRESH fires otherwise when price data available
  - Signal decay UNKNOWN fires when price data unavailable (not an error)
  - tradeable_followers contains only FOLLOWER nodes with FRESH or UNKNOWN decay
  - absorbed_followers is populated and readable (not hidden)
  - Config file seeded with at least 4 sector chains
  - Graph works on partial calendar (not all tickers in config must be in calendar)
  - No circular dependency detection needed — earnings graphs are naturally DAGs
    by time ordering

tests:
  unit:
    - test_build_graph_two_tickers_same_sector (→ one edge)
    - test_build_graph_different_sectors (→ no edge if no shared factor)
    - test_classify_nodes_leader (event_date <= today → LEADER)
    - test_classify_nodes_follower (event_date > today → FOLLOWER)
    - test_classify_nodes_has_signal_false (follower with no upstream → False)
    - test_detect_signal_decay_absorbed (follower moved 60% of upstream → ABSORBED)
    - test_detect_signal_decay_fresh (follower moved 20% of upstream → FRESH)
    - test_detect_signal_decay_opposite_direction (not absorbed, different direction)
    - test_detect_signal_decay_unknown (follower_move_pct=None → UNKNOWN)
    - test_get_tradeable_followers_excludes_absorbed
    - test_get_tradeable_followers_includes_unknown
    - test_empty_calendar (→ empty graph, no errors)
    - test_single_ticker_no_edges
    - test_config_loads_without_error
  integration:
    - Consumer credit chain: SYF leader, COF leader, AXP follower FRESH →
      AXP in tradeable_followers
    - Consumer credit chain: AXP already moved 60% of SYF move →
      AXP in absorbed_followers, not tradeable

definition_of_done:
  - analytics/signal_graph.py with all dataclasses and functions
  - config/signal_graph_sectors.json seeded with 4+ chains
  - SignalGraphResult wired into TYPE 4 classification in T027 (as optional input)
  - tradeable_followers and absorbed_followers both visible in batch report (T029)
  - All unit and integration tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Revenue overlap + factor correlation is not causal. Earnings reactions
    propagate through positioning and narrative, not stable graph edges.
    Treat as an attention guide, validate each link empirically over time.
  - Signal graph is additive to TYPE 4 confidence (MEDIUM → HIGH when fresh
    follower identified). It does not create TYPE 4 where conditions are not met.
  - The 50% decay threshold is a starting point, not a calibrated constant.
    Add comment referencing calibration loop (T031).
  - Keep the config simple: sector chain + revenue overlap tag + primary factor.
    Do not over-engineer the weighting scheme before it has been validated.

failure_modes:
  - calendar_df is empty → return empty SignalGraphResult (no error)
  - Ticker in price_moves not in calendar → ignore (no error)
  - Config file missing → raise FileNotFoundError with path
  - Config file malformed → raise ValueError with context
  - upstream_move_pct is zero → treat as UNKNOWN (avoid division ambiguity)
