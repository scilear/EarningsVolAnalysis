# Earnings Volatility Analysis System
## Decision-Oriented Documentation

*Purpose: Allow a reviewer to validate the system's logic without reading code.*

---

## 1. System Overview

### What Problem This Tool Solves

The system analyzes option chains around corporate earnings events to determine:
1. Whether implied volatility is cheap, fair, or rich relative to historical earnings moves
2. What volatility regime the market is in (event-dominant vs distributed)
3. Which options strategy to employ (long vol, short vol, or no trade)
4. The confidence level of that recommendation

### High-Level Workflow

```
Ticker + Event Date → Option Chain Data → Volatility Metrics → Regime Classification → Strategy Recommendations → Ranked Outputs
```

### Key Outputs

| Output | Description |
|--------|------------|
| Implied Move | ATM straddle cost as % of spot |
| Edge Ratio | Implied / Conditional-Expected move ratio |
| Event Variance | Volatility attributable to the earnings event |
| TYPE Classification | 1-5 playbook signal type |
| Ranked Strategies | Scored strategy candidates |
| HTML Report | Full analysis with visualizations |

---

## 2. Entry Points / Use Cases

### Use Case 1: Single-Ticker Deep-Dive Analysis

**Goal**: Generate a comprehensive HTML report for one ticker around an earnings event.

**Inputs**: Ticker symbol, optional event date (auto-discovered), optional cache directory.

**Output**: HTML report + analysis_summary.json

---

### Use Case 2: Batch Mode Analysis

**Goal**: Run analysis across multiple tickers.

**Output**: Per-ticker HTML reports + batch summary JSON

---

### Use Case 3: Daily Scan Workflow

**Goal**: Morning review of earnings universe with Telegram alerts.

**Modes**: full-window, pre-market, overnight, open-confirmation

**Output**: Playbook scan HTML + Telegram alerts for actionable setups

---

### Use Case 4: Structure Advisor Query

**Goal**: Query and price structures by payoff intent without full analysis.

**Output**: Ranked structure table or JSON

---

### Use Case 5: Open Confirmation

**Goal**: Detect material changes between overnight snapshot and live market open.

**Output**: Comparison table with shift percentages

---

## 2.1 Data & Data Origin

### Data Sources

| Source | What It Provides | Used For |
|--------|----------------|----------|
| **yfinance** | Spot prices, option chains, earnings dates, price history, market cap, dividend yield | All runtime analysis |
| **SQLite (options_intraday.db)** | Cached option chains at specific timestamps | Overnight mode, pre-market mode, EOD snapshots |

### yfinance Live Fetch

| Data | Method | Key Fields |
|------|--------|------------|
| Spot price | `history(period="5d")` | last close |
| Option chains | `option_chain(expiry)` | strike, bid, ask, iv, oi |
| Price history | `history(start, end)` | daily OHLCV (default 5 years) |
| Earnings dates | `get_earnings_dates()` | earnings timestamps |
| Dividend yield | `info["dividendYield"]` | decimal |
| Market cap | `info["marketCap"]` | 0.5% used for GEX threshold |

### Database Schema (options_intraday.db)

**Layer 1: Raw Option Quotes**
- `option_quotes`: timestamp, ticker, expiry, strike, option_type, bid, ask, mid (generated), spread (generated), volume, open_interest, implied_volatility, underlying_price, days_to_expiry, data_quality (valid/missing/empty/invalid/inverted)

**Layer 2: Snapshot Metadata**
- `option_snapshots`: timestamp, ticker, quality_tag (valid/partial/stale/zero), records_total/valid/invalid, expiry_set, spot_price

**Layer 3: Event Registry**
- `event_registry`: event_id, event_family, underlying_symbol, event_date, event_ts_utc, source_system
- `event_snapshot_binding`: binds chain snapshots to event timeline positions
- `event_surface_metrics`: atm_iv_front, iv_ratio, implied_move_pct, event_variance_ratio, skew, gex_proxy
- `earnings_outcomes`: predicted_type, edge_ratio, realized_move, realized_vs_implied_ratio

### Backfill Operations

- **Auto-ingestion**: `auto_ingest_earnings_calendar()` fetches from yfinance, upserts into event_registry
- **Manifest-based**: `backfill_event_manifest()` registers events, binds snapshots, stores metrics and outcomes

### Cache Modes

| Mode | Behavior |
|------|----------|
| No cache | Fetch live from yfinance |
| File cache | CSV in `data/cache/` |
| DB cache | SQLite option_quotes table |
| EOD snapshot | Captured at market close, labeled with quality_tag |
| cache_only | Fail if data not in cache |

### Data Quality Signals

| Tag | Meaning |
|-----|---------|
| valid | bid > 0, ask > 0, bid < ask |
| partial | Some strikes invalid (90-95% valid) |
| stale | No new capture in 24h |
| zero | All bids/asks are zero (market closed) |

### Rate Limiting

- All yfinance calls throttled: 100ms between requests
- Exponential backoff on 429: 2^attempt seconds
- Max retries: 3

---

## 3. Decision Trees

### 3.1 Strategy Gate (should_build_strategy)

```
├── Backspread (call/put)
│   ├── IV ratio >= 1.40 ? → FAIL if no
│   ├── Event variance ratio >= 0.30 ? → FAIL if no
│   ├── implied_move <= P75 * 1.15 ? → FAIL if no (overpriced)
│   ├── short_delta >= 0.30 ? → FAIL if no
│   └── back DTE in [21, 60] ? → FAIL if no
│   └── PASS → include
│
├── Post-Event Calendar
│   ├── days_after_event in [1, 3] ? → FAIL if no
│   └── PASS → include
│
└── All others
    └── Include (no gates)
```

### 3.2 TYPE Classification (Primary Signal)

```
├── edge_ratio < 0.8 (CHEAP)?
│   ├── event_variance_ratio >= 0.50?
│   │   ├── gamma_regime "Amplified Move"?
│   │   │   └── TYPE 1 (Long vol convex)
│   │   └── TYPE 2 (Long vol directional)
│   └── edge_ratio >= 1.3 (RICH)?
│       ├── gamma_regime "Pin Risk"?
│       │   └── TYPE 4 (Short vol harvest)
│       └── TYPE 5 (Premium harvest)
│   └── TYPE 3 (No trade / small directional)
```

### 3.3 Liquidity Filter

```
├── min_oi >= threshold ? → FAIL if no (calibrated 20th percentile OI in ATM ±15%, clamped [10, 200])
├── max_spread_pct <= threshold ? → FAIL if no (calibrated 65th percentile spread%, clamped [0.03, 0.20])
├── moneyness in [0.70, 1.30] ? → FAIL if no
└── PASS → include
```

### 3.4 Trust Score Decision

```
├── quantile_trust_score >= 80 ? → PASS (HIGH confidence)
├── quantile_trust_score >= 50 ? → WARN (MEDIUM confidence)
└── quantile_trust_score < 50 ? → FAIL (LOW confidence)
```

### 3.5 Vol Regime Classification

```
├── iv_percentile > 80 ? → EXPENSIVE
├── iv_percentile < 30 ? → CHEAP
└── iv_percentile in [30, 80] → FAIR
```

---

## 4. Algorithms (When They Matter)

### 4.1 Event Variance Extraction

**Purpose**: Decompose front IV into event-specific and structural components.

**Mathematical Formulation**:

```
T_front = business_days(today, front_expiry) / 252
T_back = business_days(today, back_expiry) / 252
T_event = business_days(event_date, front_expiry) / 252

If back2 exists:
  TV_pre = linear_interp(T_back, T_back*IV_back², T_back2, T_back2*IV_back2², T_front - T_event)
Else:
  TV_pre = (T_front - T_event) * IV_back²  # constant IV assumption

event_var_annualized = (T_front * IV_front² - TV_pre) / T_event
event_var_daily = event_var_annualized / 252
event_variance_ratio = event_var_annualized * T_event / (T_front * IV_front²)
```

**Limitations**: If event_var < 0: clamps to 0. Inverted term structures produce negative values.

---

### 4.2 Implied Move Calculation

**Purpose**: Derive the market's expected move from ATM straddle pricing.

```
ATM_strike = min(|strike - spot|)
call_slippage_price = mid_call - (spread * slippage_pct)
put_slippage_price = mid_put - (spread * slippage_pct)
implied_move = (call_slippage_price + put_slippage_price) / spot
```

**Limitations**: Wide spreads logged but not rejected. Does not adjust for delta skew.

---

### 4.3 Monte Carlo Move Simulation

**Models**:
1. **Lognormal**: log(S_T/S_0) ~ N(0, σ²)
2. **Fat-Tailed**: Skew-normal calibrated to historical kurtosis (inflates sigma until kurtosis matches target)

**Purpose**: Validate implied move reasonableness by comparing to simulated quantiles.

---

### 4.4 IV Scenario Calibration

```
evr = event_variance_ratio
hard_crush_front = sqrt(1 - evr) - 1
hard_crush_back = -max(0.03, evr * 0.12)
expansion_front = 0.05 + (1 - evr) * 0.08
expansion_back = 0.03 + (1 - evr) * 0.03
```

---

## 5. Financial Interpretation

### What Constitutes a Valid Opportunity

**Long Vol (TYPE 1-2)**:
- Edge ratio < 0.8 AND event variance ratio >= 0.50
- Gamma regime: Amplified OR Neutral

**Short Vol (TYPE 4-5)**:
- Edge ratio > 1.3 AND gamma regime: Pin Risk OR Amplified
- Historical track record of implied > realized

### Signals Being Exploited

| Signal | Interpretation |
|--------|---------------|
| Edge Ratio | Market mispricing vs historical earnings moves |
| Event Variance | How much premium is "event-specific" vs structural |
| GEX | Dealer gamma positioning (amplified = move risk) |

---

## 6. Assumptions

### Explicit

| Assumption | Source |
|------------|--------|
| Historical moves predict future distribution | Historical analysis |
| Black-Scholes for Greeks | Config default |
| Term structure interpolates linearly | Algorithm spec |
| Slippages are uniform % | Config |
| OI reflects liquidity | Liquidity filter |

### Implicit (Inferred)

| Assumption | Inferred From |
|------------|---------------|
| ATM options are most liquid | Calculation method |
| Event variance is positive | Variance decomposition |
| 20th percentile OI is minimum for valid pricing | Calibration formula |

---

## 7. Failure Modes & Blind Spots

1. **Negative Event Variance**: Clamps to 0, masking inverted structures
2. **Wide ATM Spreads**: Warning logged but calculation proceeds
3. **Insufficient Historical Data**: LOW confidence caveat fires but TYPE still classifies
4. **GEX Data Quality**: OI may be stale
5. **Backspread Gate Sensitivity**: Tight IV ratio (>=1.40) may miss opportunities

---

## 8. Gaps / Unknowns

| Gap | Status |
|-----|--------|
| Delta adjustment to implied move | Unknown - not implemented |
| Stochastic vol adjustment | Unknown - not implemented |
| Historical earnings surprise magnitude | Unknown - not factored |
| Options market maker positioning | Unknown - not gamed |
| Sector correlation | Unknown - single-ticker focus |

---

## 9. Reviewer Checklist

### Data Integrity
- [ ] Earnings dates verified (not fabricated)?
- [ ] Implied move from ATM straddle prices?
- [ ] Historical moves from price history?
- [ ] Event variance uses total variance framework?

### Volatility Logic
- [ ] IV computed consistently across strikes/maturities?
- [ ] Event variance positive for inverted structures handled?
- [ ] Fat-tailed model matches historical kurtosis?

### Strategy Gates
- [ ] Backspread requires IV ratio >= 1.40?
- [ ] Backspread requires event variance ratio >= 0.30?
- [ ] Post-event calendar requires days [1, 3] after?

### Liquidity Filters
- [ ] Illiquid options filtered correctly?
- [ ] min_oi calibrated from data (not hardcoded)?
- [ ] spread% filtered from data (not hardcoded)?

### Confidence Assessment
- [ ] LOW confidence caveat when sample < 6?
- [ ] Trust score computed and displayed?

---

---

# PART II: CANONICAL DECISION MODEL SPECIFICATION

*The following sections transform the system into a deterministic decision machine where every trade outcome is derivable from explicit rules.*

---

## 10. Decision Component Classification

### A. Hard Filters (Binary Rejection)

If ANY hard filter fails → **NO_TRADE** (no exceptions, no override).

| Filter | Metric | Threshold | Resolution |
|--------|--------|-----------|------------|
| **Liquidity minimum OI** | min_oi (calibrated 20th percentile) | >= threshold | Reject chain |
| **Liquidity maximum spread** | max_spread_pct (calibrated 65th percentile) | <= threshold | Reject chain |
| **Moneyness range** | strike / spot | [0.70, 1.30] | Reject OTM strikes |
| **Market status** | bid == 0 AND ask == 0 | TRUE | Reject (market closed) |
| **Backspread IV ratio** | front_iv / back_iv | >= 1.40 | Reject strategy |
| **Backspread event variance** | event_variance_ratio | >= 0.30 | Reject strategy |
| **Backspread move pricing** | implied_move | <= P75 * 1.15 | Reject strategy |
| **Backspread delta** | short_delta | >= 0.30 | Reject strategy |
| **Backspread back DTE** | back_expiry - today | [21, 60] days | Reject strategy |
| **Post-event calendar entry** | days_after_event | [1, 3] | Reject strategy |

### B. Primary Decision Drivers

These determine the direction: **LONG_VOL**, **SHORT_VOL**, or **NO_TRADE**.

| Priority | Signal | Values | Decision |
|----------|--------|--------|----------|
| **1** | edge_ratio | < 0.8 (CHEAP) | Candidate LONG_VOL |
| **1** | edge_ratio | > 1.3 (RICH) | Candidate SHORT_VOL |
| **1** | edge_ratio | [0.8, 1.3] (FAIR) | **NO_TRADE** |
| **2** | event_variance_ratio | >= 0.50 | Event-Dominant or Pure Binary |
| **2** | event_variance_ratio | < 0.50 | Distributed Volatility |
| **3** | gamma_regime | "Amplified Move" | Amplifies move risk |
| **3** | gamma_regime | "Pin Risk" | Short vol protection zone |
| **3** | gamma_regime | "Neutral Gamma" | No gamma bias |

### C. Secondary Modifiers

These adjust confidence or sizing. They **do not change the direction** but affect weighting/scoring.

| Modifier | Signal | Values | Effect |
|----------|--------|--------|--------|
| trust_score | Quantile deviation + KS test | >= 80: PASS, >= 50: WARN, < 50: FAIL | Confidence level |
| historical_sample_size | Number of earnings observations | >= 6: HIGH, < 6: LOW | Edge ratio confidence |
| vol_regime | IV percentile | > 80: EXPENSIVE, < 30: CHEAP, [30-80]: FAIR | Context for edge |
| term_structure | front_iv - back_iv | > 0.10: Elevated, > 0.20: Extreme, < -0.05: Inverted | Structural context |

### D. Diagnostic Signals

These are **informational only** and **do not affect the decision**.

| Signal | Purpose | Used For |
|--------|---------|----------|
| skew_25d | 25-delta skew measurement | Context reporting |
| gex_by_strike | Strike-level gamma map | Visualization |
| pin_strikes | Concentrated gamma strikes | Context reporting |
| vanna_net, charm_net | Secondary Greeks | Not used in TYPE decision |
| macro_vehicle_class | Asset class classification | Not used in TYPE decision |

---

## 11. Conflict Resolution Rules

### Conflict 1: Edge Ratio and Gamma Regime Mismatch

**Rule**: Edge ratio takes precedence over gamma regime for direction.

| Edge Ratio | Gamma Regime | Resolution |
|------------|-------------|------------|
| CHEAP (<0.8) | Amplified | LONG_VOL (TYPE 1) |
| CHEAP (<0.8) | Neutral | LONG_VOL (TYPE 2) |
| CHEAP (<0.8) | Pin Risk | LONG_VOL (TYPE 2) |
| RICH (>1.3) | Amplified | SHORT_VOL (TYPE 5) |
| RICH (>1.3) | Pin Risk | SHORT_VOL (TYPE 4) |
| RICH (>1.3) | Neutral | SHORT_VOL (TYPE 5) |
| **Any** | **Any** | Edge ratio direction wins |

**Rationale**: The market's implied vs historical comparison is the primary signal. Gamma regime is secondary context.

---

### Conflict 2: Trust Score Disagreement with Edge Ratio

**Rule**: Trust score is advisory only. Edge ratio decision stands regardless of trust score.

| Trust Score | Edge Ratio | Resolution |
|-------------|-----------|------------|
| FAIL (<50) | CHEAP | LONG_VOL with LOW CONFIDENCE caveat |
| FAIL (<50) | RICH | SHORT_VOL with LOW CONFIDENCE caveat |
| PASS (>=80) | FAIR | NO_TRADE (fair priced regardless) |

**Rationale**: Trust score validates the quality of the simulation. Low trust means the validation is uncertain, not that the edge doesn't exist.

**Exception**: Trust score PASS is required for TYPE 4 (short vol harvest) to filter high-risk entries. Not enforced for TYPE 5.

---

### Conflict 3: Multiple Strategies Simultaneously Valid

**Rule**: Strategies are ranked by composite score, not selected by conflict.

| Scenario | Resolution |
|----------|------------|
| Backspread AND standard strategies both valid | Backspread included if gates pass; all ranked by score |
| Long straddle AND calendar both pass gates | Both ranked; top-ranked returned |
| Backspread fails gates but implied move is cheap | Long straddle/strangle considered instead |

**Precedence Order**:
1. Backspread (if gates pass) - highest priority due to convex payoff
2. Standard strategies (ranked by score)
3. No-trade if no valid strategy

---

### Conflict 4: Inverted Term Structure (front_iv < back_iv)

**Rule**: Event variance is clamped to 0. Event variance ratio treated as 0.

| Term Structure | event_variance_ratio | Resolution |
|---------------|---------------------|------------|
| Normal (front_iv > back_iv) | Computed normally | Used in TYPE |
| Inverted (front_iv < back_iv) | Clamped to 0 | Event regime = Distributed |
| Extreme (spread > 0.20) | Computed but flagged | Logged warning |

**Rationale**: Inverted structures indicate front IV already crushed or term structure dislocation. Treating as distributed prevents overconfident binary event framing.

---

### Conflict 5: FAIR Edge Ratio with Amplified Gamma

**Rule**: Edge ratio dominates. FAIR always results in NO_TRADE regardless of gamma regime.

| Edge Ratio | Gamma Regime | Event Variance | Resolution |
|-----------|-------------|----------------|------------|
| FAIR (0.8-1.3) | Amplified | Any | **NO_TRADE** |
| FAIR (0.8-1.3) | Pin Risk | Any | **NO_TRADE** |
| FAIR (0.8-1.3) | Neutral | Any | **NO_TRADE** |

**Rationale**: Fairly priced vol offers no edge regardless of gamma positioning. Shorting fair vol with elevated gamma risk is not justified.

---

## 12. Canonical Decision Function

```
FINAL_DECISION = f(
    liquidity_filter_passed: bool,
    edge_ratio_label: str,           # "CHEAP" | "FAIR" | "RICH"
    event_variance_ratio: float,
    gamma_regime: str,              # "Amplified Move" | "Pin Risk" | "Neutral Gamma"
    trust_score: float,
    historical_sample_size: int,
    short_vol_history_allowed: bool  # from earnings_outcomes table
)
```

### Decision Hierarchy (Evaluation Order)

```
LEVEL 1: HARD FILTERS
├── IF liquidity_filter_passed == False:
│   └── RETURN NO_TRADE, reason = "liquidity_failed"
│
LEVEL 2: PRIMARY DIRECTION (edge ratio)
├── IF edge_ratio_label == "CHEAP":
│   │   RETURN LONG_VOL_CANDIDATE
│   ├── THEN CHECK event_variance_ratio:
│   │   IF >= 0.50 AND gamma_regime == "Amplified Move":
│   │   └── RETURN LONG_VOL, TYPE = 1
│   │   ELSE:
│   │   └── RETURN LONG_VOL, TYPE = 2
│   │
├── ELIF edge_ratio_label == "RICH":
│   │   RETURN SHORT_VOL_CANDIDATE
│   ├── THEN CHECK short_vol_history_allowed:
│   │   IF short_vol_history_allowed == False:
│   │   └── LOG "short vol history not validated"
│   ├── THEN CHECK gamma_regime:
│   │   IF gamma_regime == "Pin Risk":
│   │   └── RETURN SHORT_VOL, TYPE = 4
│   │   ELSE:
│   │   └── RETURN SHORT_VOL, TYPE = 5
│   │
├── ELIF edge_ratio_label == "FAIR":
│   └── RETURN NO_TRADE, reason = "fairly_priced"
│
LEVEL 3: CONFIDENCE ADJUSTMENT (advisory only)
├── IF trust_score < 50:
│   └── APPEND confidence = "LOW"
├── ELIF trust_score >= 80:
│   └── APPEND confidence = "HIGH"
│   ELSE:
│   └── APPEND confidence = "MEDIUM"
│
LEVEL 4: SAMPLE SIZE ADJUSTMENT
├── IF historical_sample_size < 6:
│   └── APPEND EDGE_RATIO_LOW_CONFIDENCE_CAVEAT
```

---

## 13. Full Deterministic Decision Tree

```
FUNCTION get_final_decision(inputs):

    # ── LEVEL 1: HARD FILTERS ──────────────────────────────────
    
    IF inputs.liquidity_filter_passed == False:
        RETURN {
            decision: "NO_TRADE",
            reason: "liquidity_filter_failed",
            type: null,
            confidence: null
        }
    
    # ── LEVEL 2: PRIMARY DIRECTION ──────────────────────────────
    
    IF inputs.edge_ratio_label == "CHEAP":
        # Primary direction = LONG_VOL
        IF inputs.event_variance_ratio >= 0.50 AND inputs.gamma_regime == "Amplified Move":
            RETURN {
                decision: "LONG_VOL",
                type: 1,
                thesis: "Convex long-vol setup",
                confidence: _assess_confidence(inputs)
            }
        ELSE:
            RETURN {
                decision: "LONG_VOL",
                type: 2,
                thesis: "Directional long-vol setup",
                confidence: _assess_confidence(inputs)
            }
    
    ELIF inputs.edge_ratio_label == "RICH":
        # Primary direction = SHORT_VOL
        IF inputs.gamma_regime == "Pin Risk":
            RETURN {
                decision: "SHORT_VOL",
                type: 4,
                thesis: "Short-vol harvest with pin risk",
                confidence: _assess_confidence(inputs),
                check_short_vol_history: True
            }
        ELSE:
            RETURN {
                decision: "SHORT_VOL",
                type: 5,
                thesis: "Premium harvest",
                confidence: _assess_confidence(inputs),
                check_short_vol_history: True
            }
    
    ELIF inputs.edge_ratio_label == "FAIR":
        # No edge regardless of other signals
        RETURN {
            decision: "NO_TRADE",
            reason: "fairly_priced",
            type: 3,
            confidence: _assess_confidence(inputs)
        }
    
    # ── CATCH-ALL: UNKNOWN EDGE RATIO ───────────────────────────
    
    ELSE:
        RETURN {
            decision: "NO_TRADE",
            reason: "edge_ratio_unknown",
            type: null,
            confidence: null
        }

END FUNCTION

# ── Confidence Assessment ──────────────────────────────────────────

FUNCTION _assess_confidence(inputs):
    IF inputs.trust_score >= 80:
        trust_level = "HIGH"
    ELIF inputs.trust_score >= 50:
        trust_level = "MEDIUM"
    ELSE:
        trust_level = "LOW"
    
    IF inputs.historical_sample_size < 6:
        sample_note = "EDGE_RATIO_LOW_CONFIDENCE_CAVEAT"
    ELSE:
        sample_note = null
    
    RETURN {
        trust_level: trust_level,
        sample_note: sample_note
    }

END FUNCTION
```

### Final Node States

Every invocation resolves to exactly ONE of:

| Node | Decision | TYPE | Required Signals |
|------|----------|------|------------------|
| **LONG_VOL_CONVEX** | LONG_VOL | 1 | edge=CHEAP + evr>=0.50 + gamma=Amplified |
| **LONG_VOL_DIRECTIONAL** | LONG_VOL | 2 | edge=CHEAP + (evr<0.50 OR gamma!=Amplified) |
| **SHORT_VOL_HARVEST** | SHORT_VOL | 4 | edge=RICH + gamma=Pin Risk |
| **SHORT_VOL_PREMIUM** | SHORT_VOL | 5 | edge=RICH + (gamma!=Pin Risk) |
| **NO_TRADE_FAIR** | NO_TRADE | 3 | edge=FAIR |
| **NO_TRADE_LIQUIDITY** | NO_TRADE | null | liquidity_filter_failed |
| **NO_TRADE_UNKNOWN** | NO_TRADE | null | edge_ratio_unknown |

---

## 14. Signal Priority Matrix

| Signal | Priority | Type | Can Override? |
|--------|----------|------|---------------|
| liquidity_filter | 1 (FIRST) | Hard Filter | Cannot be overridden |
| edge_ratio | 2 (PRIMARY) | Primary Driver | Determines direction |
| event_variance_ratio | 3 (SECONDARY) | Secondary Modifier | Context for TYPE |
| gamma_regime | 4 (CONTEXT) | Secondary Modifier | Context for TYPE |
| trust_score | 5 (ADVISORY) | Diagnostic | Never overrides |
| vol_regime | 6 (CONTEXT) | Diagnostic | Never used in decision |
| term_structure | 7 (CONTEXT) | Diagnostic | Logged only |
| skew_25d | 8 (CONTEXT) | Diagnostic | Not in TYPE decision |
| gex_by_strike | 9 (CONTEXT) | Diagnostic | Visualization only |

---

## 15. Audit Validation Checklist

### Completeness Check

- [ ] Every metric in the codebase is classified into A/B/C/D above
- [ ] No signal influences decision without defined priority
- [ ] No parallel decision authority exists
- [ ] All conflict types have explicit resolution rules

### Determinism Check

- [ ] For any given input state, same decision output
- [ ] No random/probabilistic elements in TYPE classification
- [ ] All thresholds are hard-coded, not runtime-configurable
- [ ] No "advisory" signals can flip direction

### Conflict Resolution Check

- [ ] Edge ratio always takes precedence over gamma regime
- [ ] Fair edge ratio always results in NO_TRADE
- [ ] Trust score never overrides edge ratio
- [ ] Liquidity failure is unrecoverable
- [ ] Inverted term structure handled consistently

### Threshold Audit

| Threshold | Value | Location | Used In |
|-----------|-------|----------|---------|
| CHEAP | < 0.8 | edge_ratio.py | TYPE 1-2 |
| RICH | > 1.3 | edge_ratio.py | TYPE 4-5 |
| BACKSPREAD_MIN_IV_RATIO | 1.40 | config.py | Backspread gate |
| BACKSPREAD_MIN_EVENT_VAR_RATIO | 0.30 | config.py | Backspread gate |
| BACKSPREAD_MAX_IMPLIED_OVER_P75 | 1.15 | config.py | Backspread gate |
| BACKSPREAD_MIN_SHORT_DELTA | 0.30 | config.py | Backspread gate |
| BACKSPREAD_LONG_DTE_MIN | 21 | config.py | Backspread gate |
| BACKSPREAD_LONG_DTE_MAX | 60 | config.py | Backspread gate |
| POST_CALENDAR_DAYS_MIN | 1 | config.py | Calendar gate |
| POST_CALENDAR_DAYS_MAX | 3 | config.py | Calendar gate |
| TRUST_SCORE_PASS | 80 | config.py | Confidence |
| TRUST_SCORE_WARN | 50 | config.py | Confidence |
| CHEAP_THRESHOLD | 0.8 | edge_ratio.py | Edge label |
| RICH_THRESHOLD | 1.3 | edge_ratio.py | Edge label |
| IMPLIED_MOVE_MAX_SPREAD_PCT | 0.15 | config.py | Wide spread warning |

### Decision Path Coverage

- [ ] All 7 final nodes reachable
- [ ] All hard filters tested in unit tests
- [ ] Conflict 1 (edge+gamma): tested
- [ ] Conflict 2 (trust+edge): tested
- [ ] Conflict 3 (multiple strategies): tested
- [ ] Conflict 4 (inverted structure): tested
- [ ] Conflict 5 (fair+amplified): tested

### Unused Signals

The following are computed but **not used in TYPE decision**:
- skew_25d (computed in regime.py but not passed to TYPE)
- vanna_net (computed in regime.py but not used in decision)
- charm_net (computed in regime.py but not used in decision)
- macro_vehicle_class (computed but not used in decision)
- term_structure (computed but informational only)

---

*Documentation version: 2026-04-26*

*Part I: System reconstruction
*Part II: Canonical decision model specification