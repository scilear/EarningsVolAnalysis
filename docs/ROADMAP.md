# Roadmap

This is the latest-only roadmap for EarningsVolAnalysis.

## Vision

Deliver a systematic earnings options decision engine for a single-operator desk:

- **Decide:** run the full 4-layer playbook snapshot per name, classify it into TYPE
  1–5, and output a ranked, fully-reasoned action list — leaving as little as
  possible to narrative or ad-hoc interpretation.
- **Research:** persist event datasets, track realized outcomes, and feed the
  calibration loop with edge ratio accuracy and classification quality.

The tool must be the baseline, not the starting point. Discretionary overlay
sits on top of a systematic answer, not in place of one.

## Current State

Working now:

- Single-name and batch Analyze flows in `event_vol_analysis.main`
- Regime classification (Vol Pricing via P75 ratio, Event Variance, Term
  Structure, Dealer Gamma, Composite)
- Strategy construction + Monte Carlo EV/CVaR/convexity scoring + ranking
- Capital-normalized ranking and symmetric butterfly
- Fat-tailed move distribution (calibrated, 18 tests passing)
- Generic bridge payload emission (event/context/playbook)
- Event-store backfill, replay, earnings/macro workbooks

Still weak:

- IV Rank and IV Percentile not computed (regime uses P75 ratio, not IVR/IVP)
- Conditional expected move not built (no trimmed mean, no 4Q recency
  weighting, no AMC vs BMO split, no VIX quartile or peer dispersion
  conditioning)
- Edge ratio (Implied / Conditional Expected) not computed
- Positioning proxy entirely absent
- Signal graph (upstream/downstream chain) entirely absent
- No TYPE 1–5 classification engine
- No post-earnings outcome tracking or calibration loop

---

## Just Closed — Foundation Complete

Infrastructure work (T019, T020, T021) completed. Batch runs now reliable and
auto-ingested.

| ID | Task | Status |
|----|------|--------|
| 019 | Multi-ticker batch mode — integrate auto-ingestion into batch | completed |
| 020 | Earnings calendar auto-ingestion — document source limitations | completed |
| 021 | Fat-tailed move distribution (calibrated, 18 tests passing) | completed |

**Remaining foundation work (deprioritized, run as needed):**

| ID | Task | Status |
|----|------|--------|
| 012 | Dependency and env cleanup | pending |
| 013 | Test strategy for migration | pending |

---

## Now — Playbook Alignment (4-Layer Snapshot) [P1]

**Objective:** replace generic regime output with the exact 4-layer snapshot
defined in `earnings-playbook.md`. Each layer produces a label + confidence
rating. Together they feed the TYPE classifier in the phase after.

**Execution path (priority order):**

1. **T023** — IV Rank + IV Percentile dual classifier (foundation for vol regime)
2. **T024** — Conditional expected move (foundation for edge ratio)
3. **T025** — Edge ratio (CHEAP/FAIR/RICH label with confidence)
4. **T026** — Positioning proxy (weak signals, tiebreaker only)

**Exit criteria:**

- All four layers produce label + confidence per name
- Batch report includes all four layers
- Regression smoke tests pass

### Task 023 — IV Rank + IV Percentile Dual Classifier

**What's needed:**

The current regime module classifies vol via P75 ratio. The playbook requires
IVR (current IV vs 52-week range) AND IV percentile (rank vs 52-week history)
separately. When they disagree by more than one bucket, the name is flagged
AMBIGUOUS.

**Deliverable:**

- New function `classify_vol_regime(ivr, ivp)` producing:
  - `label`: CHEAP / NEUTRAL / EXPENSIVE / AMBIGUOUS
  - `ivr`: float (0-100)
  - `ivp`: float (0-100)
  - `confidence`: HIGH (both agree) / LOW (disagree by >1 bucket)
  - `bucket_ivr`: CHEAP (<30) / NEUTRAL (30-60) / EXPENSIVE (>60)
  - `bucket_ivp`: same buckets
- Replace P75-ratio vol label in the regime output with this dual classifier.
- Wire into term structure slope (front vs back month) and 25-delta put/call
  skew — already in `analytics/skew.py`, just surface them cleanly.

**Acceptance criteria:**

- Dual label and AMBIGUOUS flag appear in the report.
- Regression smoke tests pass.

---

### Task 024 — Conditional Expected Move

**What's needed:**

The playbook requires the expected move to be computed as:

1. Median of historical earnings moves (already in `analytics/historical.py`)
2. Trimmed mean (exclude top and bottom outlier from the sample)
3. Recent-4Q weighted mean (last 4 quarters counted 2× vs older ones)
4. All of the above computed separately for AMC vs BMO events (the day pairs
   differ: BMO uses prior-close → open, AMC uses close → next-day close)
5. Conditioned on: VIX quartile at event time, pre-earnings 10D drift
   direction, and (when available) same-cycle peer median move so far

**Deliverable:**

- Extend `analytics/historical.py` with:
  - `trimmed_mean_move(moves)` (exclude top and bottom observation)
  - `recency_weighted_mean(moves, n_recent=4, recent_weight=2.0)` for the 4Q
    recency weighting
  - `split_by_timing(ticker, dates, moves)` to segregate AMC vs BMO
    observations — requires timing metadata from the event store
  - `conditional_expected_move(moves, vix_quartile=None, drift_sign=None,
    peer_median=None)` — applies available conditioning and returns a
    `ConditionalExpected` object with all sub-estimates and a data quality flag
- Data quality flag: LOW if <6 observations, MEDIUM if 6-10, HIGH if >10
- AMC vs BMO split degrades data quality by halving effective sample size —
  propagate this into the flag

**Acceptance criteria:**

- All four sub-estimates are present in the output for any name with ≥6
  observations.
- AMC vs BMO split is explicit and documented (label which methodology was
  used).
- Conditioning on VIX quartile and drift direction is additive and optional
  (graceful degradation when unavailable).

---

### Task 025 — Edge Ratio + RICH/FAIR/CHEAP Labeling

**What's needed:**

Edge ratio = Implied move (from ATM straddle, Task already working) / Conditional
expected move (from Task 024). The ratio is labeled and confidence-rated.

**Deliverable:**

- New function `compute_edge_ratio(implied, conditional_expected)`:
  - `ratio`: float
  - `label`: RICH (>1.3) / FAIR (0.8–1.3) / CHEAP (<0.8)
  - `confidence`: HIGH / MEDIUM / LOW — inherited from conditional expected
    data quality flag
  - `note`: string explaining which sub-estimate was used as the denominator
    (median, trimmed mean, or recency-weighted — use recency-weighted as
    primary, median as secondary check)
- Wire the edge ratio into the report alongside the implied move display.
- CRITICAL: add a caveat banner when confidence is LOW — "edge ratio is noisy
  with fewer than 6 observations; treat as directional signal only."

**Acceptance criteria:**

- Edge ratio, label, and confidence appear per-name in the report.
- LOW-confidence output carries an explicit flag visible in the operator view.

---

### Task 026 — Positioning Proxy Module

**What's needed:**

The playbook uses observable market signals as weak proxies for positioning
state. These are explicitly low-confidence tiebreakers, not primary signals.

**Deliverable:**

- New module `analytics/positioning.py` with:
  - `oi_concentration(chain)` — identify strike clusters with OI >20% of total
    OI; flag if clustering is directional (clustered on calls vs puts)
  - `pc_ratio_signal(pc_5d, pc_20d_avg)` — recent 5D P/C ratio vs 20D average;
    signal if >1.2× or <0.8× of average
  - `drift_vs_sector(ticker_10d_ret, sector_10d_ret)` — pre-earnings 10-day
    return vs sector median; flag if >2× sector move
  - `max_pain_distance(max_pain, spot)` — distance as % of spot; signal if
    >3% gap
  - `classify_positioning(oi_signal, pc_signal, drift_signal, max_pain_signal)`
    → UNDER-POSITIONED / BALANCED / CROWDED with confidence:
    - HIGH only if all four signals agree
    - LOW (default BALANCED) if mixed signals
- Wire into the 4-layer snapshot output.

**Acceptance criteria:**

- Positioning proxy classification and individual signals appear in report.
- BALANCED with low confidence is the default when signals disagree.
- Individual signals are individually readable (not collapsed into a single
  opaque score).

---

## Then — Decision Engine [P1]

**Objective:** encode the playbook TYPE 1–5 conditions as a deterministic
classifier. The tool outputs a TYPE, not a ranking of structures.

**Execution path (depends on T023–T026):**

1. **T027** — TYPE 1–5 classifier (gates decision engine; optional signal graph)
2. **T028** — Signal graph (optional; upgrades T027 confidence for TYPE 4 only)
3. **T029** — 4-layer batch report with --mode playbook-scan CLI flag

**Exit criteria:**

- All batch outputs include TYPE classification (1–5)
- TYPE 5 rationale is always explicit (what condition prevented another type)
- TYPE 4 gets Phase 2 checklist (not a trade instruction)
- Report saves to `reports/daily/` with date in filename

### Task 027 — TYPE 1–5 Classifier

**What's needed:**

The four layers (Vol Regime, Edge Ratio, Positioning Proxy, and Signal Graph
from Task 028) feed a deterministic rule engine that outputs exactly one TYPE
per name.

**Classification rules (deterministic, from playbook):**

```
TYPE 5 (default): fire unless all conditions for another type are met

TYPE 1 — Pre-Earnings Vol Buy:
  ALL of:
  - vol_regime.label == CHEAP (IVR <30, IVP <30)
  - edge_ratio.label == CHEAP (<0.8)
  - narrative = UNCERTAIN (no pre-guide, no consensus specificity)
  - pre-earnings 10D drift: flat (|drift_vs_sector| < 1×)
  - vol_regime.confidence != AMBIGUOUS
  - edge_ratio.confidence != LOW
  → Action: buy straddle/strangle, 7-10 DTE, exit before print

TYPE 2 — Premium Sell on Existing Positions:
  ALL of:
  - vol_regime.label == EXPENSIVE (IVR >80, IVP >80)
  - edge_ratio.label == RICH (>1.3)
  - narrative = PRICED
  - position exists in portfolio (external check; flag for manual confirm if unknown)
  → Action: covered call on existing position only (no naked short)

TYPE 3 — Convex Directional:
  ALL of:
  - specific non-consensus view with falsifiable metric (human input required)
  → This type cannot be fully automated — emit a prompt for operator input
  → Only activate if operator provides falsifier string via --falsifier flag

TYPE 4 — Post-Earnings Reaction:
  ALL of:
  - earnings have printed (event_date <= today)
  - Phase 1 classification: HELD REPRICING or POTENTIAL OVERSHOOT (see below)
  - edge_ratio.confidence != LOW
  - signal_graph: follower with fresh signal exists (from Task 028)
  Phase 1 classification:
  - HELD REPRICING: move held through close + volume >2× ADV + options
    repriced cleanly (new IV levels stable)
  - POTENTIAL OVERSHOOT: move partially reversed, or volume faded, or move
    >1.5× implied
  → Phase 2 required before entry (next-morning confirmation, cannot automate
    fully — emit pre-market checklist for operator)

TYPE 5:
  - Everything else, including:
  - vol_regime.label == AMBIGUOUS
  - edge_ratio.confidence == LOW
  - move ≈ implied AND aligns with consensus
  - signal absorbed (follower already moved >50% of upstream's move)
```

**Deliverable:**

- New module `strategies/type_classifier.py`:
  - `classify_type(vol_regime, edge_ratio, positioning, signal_graph, event_state,
    operator_inputs)` → `TypeClassification`:
    - `type`: int (1–5)
    - `rationale`: list of str (which conditions passed / which blocked)
    - `action_guidance`: str (what to do)
    - `phase2_checklist`: list of str (for TYPE 4 only)
    - `confidence`: HIGH / MEDIUM / LOW
    - `is_no_trade`: bool (True when type == 5)
- Wire TYPE output as the primary output in the report — above strategy
  rankings.
- Strategy ranking output is retained as secondary (for sizing and structure
  selection once TYPE is determined).

**Frequency gate:** if TYPE 1 fires on >10% of screened universe, emit a
warning that the cheapness metric may be miscalibrated.

**Acceptance criteria:**

- Each name in batch output has exactly one TYPE.
- TYPE 5 rationale is always explicit (what condition was not met).
- TYPE 4 names get a Phase 2 checklist, not a trade instruction.
- TYPE 3 requires operator --falsifier input; without it, defaults to TYPE 5.

---

### Task 028 — Signal Graph Module

**What's needed:**

Map upstream reporters (already printed this cycle) to downstream reactors
(not yet printed). Identify leader vs follower relationships. Detect signal
decay (follower already moved before entry opportunity).

**Deliverable:**

- New module `analytics/signal_graph.py`:
  - Input: earnings calendar with dates + sector/factor tags, current price moves
  - `build_graph(calendar_df, sector_map, factor_map)` → directed graph
    (upstream → downstream edges)
  - Edge weights: revenue overlap tag (HIGH/MEDIUM/LOW, manual or from config
    file), factor correlation tag (same factor = HIGH weight)
  - `classify_nodes(graph, today)` → each node tagged LEADER or FOLLOWER based
    on whether it has already printed
  - `detect_signal_decay(follower_ticker, upstream_move_pct,
    follower_move_pct)` → ABSORBED if follower already moved >50% of upstream
    move; FRESH otherwise
  - `get_tradeable_followers(graph, today)` → list of FOLLOWER nodes with FRESH
    signal only

- Sector/factor map lives in a config file (`config/signal_graph_sectors.json`)
  — human-maintained, not inferred. Start with the consumer credit and AI/tech
  chains that are already known.

- **Scope limit:** signal graph is an attention prioritizer, not a trade
  trigger. It feeds TYPE 4 classification only. It never overrides the vol gate
  or edge ratio.

**Acceptance criteria:**

- Leader/follower tagging is correct relative to today's date.
- Signal decay detection fires when follower has already moved.
- Graph is readable in batch output (list of chains, not opaque score).

---

### Task 029 — 4-Layer Batch Report

**What's needed:**

A single batch report format that shows all four layers + TYPE classification
per name, designed for a 5-10 minute morning review.

**Deliverable:**

- New report section `4-layer-summary` (above current strategy ranking):
  - One row per name with: ticker | earnings date | Vol Regime | Edge Ratio |
    Positioning | Signal Graph | TYPE | Confidence | Action
  - Color-coded TYPE column (1=green, 2=yellow, 3=blue, 4=orange, 5=grey)
  - Collapsible detail per row showing layer-level reasoning
- CLI flag: `--mode playbook-scan` for the condensed morning-review format vs
  the full deep-dive.

**Acceptance criteria:**

- Full universe of 10-20 names fits in a single scrollable view.
- TYPE 5 names are de-emphasized (greyed), not hidden.
- Operator can expand any row to see layer detail.

---

## After — Calibration Loop + Automation [P2]

**Objective:** close the feedback loop — track edge ratio accuracy, TYPE
classification quality, and no-trade accuracy week over week. Deploy daily
automated cron workflow for morning earnings reviews.

**Execution path (depends on T027 baseline; T029 strongly recommended):**

1. **T030** — Post-earnings outcome tracking (schema + CLI script for operator data entry) [completed]
   - Record per-event: TYPE classification, edge ratio, realized move, Phase 1/2 categories
   - Auto-populate realized move from price history after event date passes
   
2. **T031** — Calibration loop (weekly report comparing ex-ante to ex-post) [completed]
   - Edge ratio accuracy by label bucket
   - TYPE classification accuracy per type number
   - No-trade audit (TYPE 5 miss rate)
   - Decision quality (good-process / bad-outcome separation)
   - Threshold adjustment gate: 20 obs minimum before suggesting changes

3. **T032** — Automated earnings season workflow (daily cron + Telegram alerting) [completed]
   - Daily cron: pull calendar (next 10-14 days) → apply hard liquidity filters → run 4-layer snapshot → classify TYPE → Telegram alert for non-TYPE-5 names
   - Morning-scan report saved to `reports/daily/YYYY-MM-DD_playbook_scan.html`
   - Manual confirmation required for any entry (human-in-the-loop always)

**Exit criteria:**

- Outcome records stored and queryable per event
- Weekly calibration report generated and readable
- Daily cron runs at 08:00 CET, sends Telegram alerts, saves report
- Dry-run mode (--dry-run) suppresses Telegram and prints to console

---

## T043 — Pre-Market Same-Day Earnings Window [P1]

**Objective:** Add pre-market (3:45 AM ET / 08:45 CET) scan for same-day earnings names, complementing T032's 10–14 day forward window. Enable early analysis of names printing at market open.

**Scope:** 
- 7–10 companies typically report at earnings season open each trading day
- T032 captures (tomorrow → 14 days ahead); T043 captures (today's open)
- Pre-market scan runs at 08:45 CET (3:45 AM ET) before market opens at 09:30 ET

**Deliverable:**

1. New CLI mode: `daily_scan --mode pre-market --date <YYYY-MM-DD>`
   - Pulls earnings calendar for exactly that date
   - Applies same 4-layer snapshot + TYPE classification
   - Uses `telegram-send` (CLI command, not Python library) for alert delivery
   - Falls back to console log if `telegram-send` config unavailable

2. Cron entry (new, separate from T032):
   - Time: 08:45 CET (3:45 AM ET) on trading days
   - Command: `./scripts/run_pre_market_scan.sh`
   - Report saved to: `reports/pre-market/YYYY-MM-DD_pre_market_scan.html`

3. Script: `scripts/run_pre_market_scan.sh`
   - Wraps `daily_scan.py --mode pre-market --date $(date +%Y-%m-%d)`
   - Calls `telegram-send` for each non-TYPE-5 name (if configured)
   - Message format: `[PRE-MARKET EARNINGS SCAN] TICKER: TYPE X | IV Regime: [label] | Edge Ratio: [label]`
   - Logs to: `logs/pre_market_scan.log`

4. Integration point: `event_vol_analysis/workflow/daily_scan.py`
   - Add `--mode` flag: `pre-market` (new) vs `full-window` (default = T032 behavior)
   - When `--mode pre-market`, calendar query filters for exact date only (not >=date)
   - Re-use all 4-layer snapshot + filtering logic from T032

**Acceptance criteria:**

- ✅ `daily_scan --mode pre-market --date 2026-04-24` outputs same 4-layer structure as full window
- ✅ Cron entry installed and dry-run succeeds
- ✅ `telegram-send` integration works (alerts fire when CLI available)
- ✅ Console fallback activates when `telegram-send` unavailable (graceful degradation)
- ✅ Reports save to `reports/pre-market/` with correct date in filename
- ✅ No hard filtering changes (same liquidity gates as T032)

**Dependencies:**
- T032 (daily_scan.py infrastructure must exist)
- `telegram-send` CLI tool (user-provided, not installed by script)

**Non-blocking notes:**
- Pre-market scan assumes valid options data available (unlikely true at 3:45 AM ET; use test-data mode for validation)
- Operator can skip this scan if no market data available; T032 still captures the same names 14+ days forward
- Daily reports will show same names in both pre-market and 10-14 day windows on days with same-day earnings

---

## Macro Binary Event Extension [P2] — from K-012

**Context:** K-012 binary event playbook (InvestmentDeskAgents) uses GEX regime from this tool for Tier B (opportunistic) entries. Five data gaps block full K-012 integration. These are backlog items, not blocking current earnings work.

| ID | Task | Needed For | Status |
|----|------|-----------|--------|
| T033 | Vanna exposure by underlying (∂(vega)/∂(spot)) | Dealer flow in stress regimes — governs forced delta hedging as vol moves | pending |
| T034 | Charm exposure (∂(delta)/∂(time)) | Timing of forced delta hedging as DTE collapses | pending |
| T035 | By-strike GEX breakdown (not just net/abs aggregate) | Pin risk identification by strike level | pending |
| T036 | Macro event vehicle support (SPY, XOP, XLE, VIX options) | Current tool is earnings-focused; K-012 needs GEX for macro binary vehicles | pending |
| T037 | Regime-conditioned edge ratio for macro event types | Edge ratio conditioned on VIX quartile + event type (geo/FOMC/election). Current T025 is unconditional | pending |

**T033 — Vanna Exposure**

Vanna = ∂(vega)/∂(spot) = ∂(delta)/∂(IV). When spot drops + IV rises, dealers with short vega positions must buy spot → amplifies moves. Knowing aggregate vanna helps predict whether a stress event creates forced dealer flows.

Deliverable: `compute_vanna_exposure(chain)` → net vanna in dollar terms, per-name, alongside gex_net/gex_abs in regime output.

**T034 — Charm Exposure**

Charm = ∂(delta)/∂(time). As options approach expiry, dealer delta hedges decay/grow even without price moves. Near high-vol events (within 2–3 DTE), charm flows can dominate intraday vol.

Deliverable: `compute_charm_exposure(chain, dte)` → net charm in delta-per-day terms.

**T035 — By-Strike GEX Breakdown**

Current `gex_net`/`gex_abs` are aggregates. Pin risk requires knowing WHERE gamma is concentrated. A net neutral GEX with large long gamma at $580 + large short gamma at $590 is very different from uniformly distributed gamma.

Deliverable: strike-level GEX bar chart data in regime output, plus `identify_pin_strikes(chain)` → list of strikes with GEX magnitude >15% of total absolute GEX.

**T036 — Macro Event Vehicle Support**

Current regime module is tested against earnings-event option chains. Macro binary events use SPY (large cap index), VIX options, sector ETFs (XOP, XLE), and leveraged ETFs (UVXY). These have different chain structures, liquidity profiles, and GEX calculation nuances (VIX options especially are complex).

Deliverable: validate and test regime.py against macro event vehicles. Expose any structural differences (VIX option GEX calculation needs separate treatment — VIX options are on a forward, not spot).

**T037 — Regime-Conditioned Edge Ratio for Macro Events**

Current T025 edge ratio uses unconditional historical median. For macro binaries: conditioning on (a) VIX quartile at event time, (b) event type (geopolitical / FOMC / election), and (c) prior events of the same type matters significantly. A geopolitical event edge ratio should not share a denominator with an FOMC event.

Deliverable: extend T025 to accept an `event_type` tag and `vix_quartile` and filter historical comparison events to the same category. Requires event taxonomy from `docs/research/2026-04-08_macro_event_taxonomy_and_proxy_mapping.md`.

---

**T038 — Macro Binary Event Outcomes Store**

**What's needed (from K-012 v1.5 structural activation filter):**

K-012 Tier B has a structural activation filter that requires a binary check: "has this event type produced a move >1 SD above implied in ≥2 prior analogous events?" This requires a persistent outcomes log for macro binary events — separate from the earnings outcomes log (T030), which is single-name earnings-focused.

**Deliverable:**

- New data store: `data/macro_event_outcomes/` — one YAML/JSON file per event, keyed by event_type + date
- Schema per entry:
  - `event_type`: geopolitical / FOMC / election / regulatory
  - `event_date`: ISO date
  - `underlying`: primary vehicle (SPY, XOP, etc.)
  - `implied_move_pct`: ATM straddle implied move at entry
  - `realized_move_pct`: actual underlying move from entry to post-event close
  - `move_vs_implied_ratio`: realized / implied
  - `vix_at_entry`: VIX level
  - `vvix_percentile_at_entry`: rolling 1Y percentile
  - `gex_zone`: Strong Amplified / Uncertain / Neutral / Pin
  - `vol_crush`: IV change from entry to 1 session post-event (%)
  - `notes`: free text
- New query function `query_event_type_tail_rate(event_type, threshold_sd=1.0)`:
  - Returns: count of events where move_vs_implied_ratio > threshold
  - Returns: total events of that type in log
  - Returns: binary flag `has_min_2_tail_events` (True/False)
  - This is the direct input to K-012 Tier B activation filter condition #4

**Population (manual initially):** Operator fills entries from the K-012 calibration log after each macro binary event. Auto-population of realized_move_pct can be added via price history lookup (same pattern as T030).

**Acceptance criteria:**
- At least 3 entries in the store (seeded from T-002 Iran/Hormuz events)
- `query_event_type_tail_rate()` returns correct counts
- K-012 playbook Section 2b can use the binary flag directly

**Note:** This is also the primary data feed for T037 (regime-conditioned edge ratio). T038 should be built before T037 — T037 depends on this data.

---

## Structure Advisor — Generic Payoff Query Interface [P2] [completed]

**Context:** vol-specialist agent currently loads full option chains into context to price structures. This moves quantitative analysis into the tool and returns a compact comparison table to the agent.

**Full spec:** `docs/STRUCTURE_ADVISOR_SPEC.md`

| ID | Task | Depends on | Status |
|----|------|------------|--------|
| T039 | Structure library + payoff-type mapping | structures.py diagonal/risk-reversal additions | completed |
| T040 | `structure_advisor.py` core — query, price, gate, rank | T039 | completed |
| T041 | CLI `earningsvol query` + agent skill integration | T040 | completed |

**Exit criteria:**
- `earningsvol query --payoff crash --ticker GLD --expiry 2026-05-15 --spot 429.57` returns a ranked comparison table in ≤60 lines
- No raw chain data enters agent context
- Naked short structures hard-blocked; diagonal flagged with conditional cost note

---

## Deferred Backlog (Valid, Not Frontline)

- Broken-wing butterfly (structure coverage)
- Diagonal spread (structure coverage) — **pulled forward into T039**
- Risk reversal (structure coverage) — **pulled forward into T039**
- Jade lizard, 1×2 ratio spread (structure coverage)
- Skew-dynamics modeling
- Early assignment warning layer
- Portfolio notional limit enforcement
- Relative value expression (long/short pair trades — deferred until single-name
  directional is validated over at least one full earnings season)
- Same-day fade pathway for TYPE 4 leader overshoot (requires intraday data;
  deferred until TYPE 4 follower strategy proves profitable with daily resolution)

---

## Execution Rules

- Protect trust path first: run smoke before/after every change.
- Each layer (023–026) is independently testable — do not bundle them.
- TYPE classifier (027) depends on layers 023–026 being stable; do not write
  027 until at least 023 and 025 are passing smoke.
- Signal graph (028) is additive — TYPE classifier works without it (TYPE 4
  degrades to requires-manual-signal-check); add it after 027.
- No learned policy logic in the decision engine — all TYPE conditions are
  deterministic and rule-based.

## Recommended Execution Order

**Phase 1 [P1] — Playbook Alignment (4-Layer Snapshot):**
```
T023 (IVR/IVP dual classifier)
  ↓
T024 (conditional expected move) → T025 (edge ratio)
  ↓
T026 (positioning proxy)
```

**Phase 2 [P1] — Decision Engine:**
```
T027 (TYPE 1–5 classifier, gates the system)
  ↓
T028 (signal graph, optional; upgrades T027 confidence)
  ↓
T029 (4-layer batch report + --mode playbook-scan)
```

**Phase 3 [P2] — Calibration + Automation (after T029 is working):**
```
T030 (post-earnings outcome tracking)
  ↓
T031 (calibration loop, weekly)
  ↓
T032 (daily cron workflow + Telegram)
```

**Optional (deprioritized):**
```
T012 (dependency cleanup)
T013 (test strategy migration)
```

## Related Docs

- Task board: `docs/TASKS.md`
- User workflow: `docs/USER_GUIDE.md`
- Feature map: `docs/FUNCTIONALITY.md`
- Playbook: `../InvestmentDeskAgents/agents/vol-specialist/knowledge-base/strategies/earnings-playbook.md`
