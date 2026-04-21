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
- Tasks 019/020/021 complete

---

## Now — Close + Foundation

**Objective:** finish open infrastructure so batch analysis is reliable and
auto-ingested.

| ID | Task | Status |
|----|------|--------|
| 019 | Multi-ticker batch mode — integrate auto-ingestion into batch | pending |
| 020 | Earnings calendar auto-ingestion — document source limitations | pending |
| 012 | Dependency and env cleanup | pending |
| 013 | Test strategy for migration | pending |

**Exit criteria:**

- Batch runs complete on a list of 10-20 tickers without manual intervention.
- Event date discovery failures are explicit and logged.
- Smoke tests pass before and after.

---

## Next — Playbook Alignment (4-Layer Snapshot)

**Objective:** replace generic regime output with the exact 4-layer snapshot
defined in `earnings-playbook.md`. Each layer produces a label + confidence
rating. Together they feed the TYPE classifier in the phase after.

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

## After — Decision Engine

**Objective:** encode the playbook TYPE 1–5 conditions as a deterministic
classifier. The tool outputs a TYPE, not a ranking of structures.

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

## Later — Calibration Loop + Automation

**Objective:** close the feedback loop — track edge ratio accuracy, TYPE
classification quality, and no-trade accuracy week over week.

### Task 030 — Post-Earnings Outcome Tracking

- Record per-event: implied move, conditional expected move, edge ratio, TYPE
  classification, actual realized move (close-to-close), Phase 1 category
  (held vs overshoot), Phase 2 confirmed trade or no-trade
- Store in event-store alongside existing outcome records
- Auto-populate actual move from price history after event date passes

### Task 031 — Calibration Loop

- Weekly report: edge ratio accuracy (implied vs realized), TYPE classification
  accuracy (ex-ante TYPE vs what actually happened), no-trade audit (did skipped
  names have exploitable moves?), decision quality (separate good-process /
  bad-outcome from bad-process / good-outcome)
- Threshold adjustment gate: 20 observations minimum before any parameter
  change; emit a warning if data is insufficient for inference
- Track by TYPE separately (TYPE 1 accuracy is different from TYPE 4 accuracy)

### Task 032 — Automated Earnings Season Workflow

- Daily cron: pull calendar (next 10-14 days) → apply hard liquidity filters →
  run 4-layer snapshot → classify TYPE → emit Telegram alert for any non-TYPE-5
  name
- Morning-scan report generated automatically and saved to `reports/daily/`
- Manual confirmation still required for any entry (human-in-the-loop)

---

## Deferred Backlog (Valid, Not Frontline)

- Broken-wing butterfly (structure coverage)
- Diagonal spread (structure coverage)
- Risk reversal (structure coverage)
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

## Task Execution Order

```
Close now: 019 → 020 → 012/013
Layer A:   023 (IVR/IVP dual classifier)
Layer B:   024 (conditional expected move) → 025 (edge ratio)
Layer C:   026 (positioning proxy)
Engine:    027 (TYPE classifier) → 028 (signal graph) → 029 (batch report)
Calibrate: 030 → 031 → 032
```

## Related Docs

- Task board: `docs/TASKS.md`
- User workflow: `docs/USER_GUIDE.md`
- Feature map: `docs/FUNCTIONALITY.md`
- Playbook: `../InvestmentDeskAgents/agents/vol-specialist/knowledge-base/strategies/earnings-playbook.md`
