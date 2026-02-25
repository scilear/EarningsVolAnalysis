# NVDA Report v2.0 Implementation TODO

## Overview
Transform the report from "quant summary" to "execution-grade decision document" with institutional-quality depth.

---

## ✅ COMPLETED

### 1. Core Regime Classification (`nvda_earnings_vol/regime.py`)
**Status:** ✅ Implemented

**Contents:**
- `classify_regime(snapshot)` - Returns vol/event/term/gamma/composite regimes
- `compute_alignment_score(strategy, regime, population)` - Returns alignment scores
- Confidence scoring for all regime components
- Heatmap data structure for visual representation

### 2. Create `alignment.py` Module
**File:** `nvda_earnings_vol/alignment.py`  
**Status:** ✅ Implemented

**Contents:**
- `_percentile_rank(value, population)` - Returns 0-1 rank
- `_scaled_sign(value, desired_positive, scale)` - Maps to [0,1]
- `compute_alignment(strategy, regime, population_stats)` - Per-strategy alignment
- `compute_all_alignments(strategies, regime)` - Mutates strategies in-place

### 3. Extend `analytics/event_vol.py`
**Status:** ✅ Implemented

**New Fields Added:**
- `back2_iv` - ATM IV for second back expiry
- `front_back_spread` - front_iv - back1_iv
- `back_slope` - back1_iv - back2_iv
- `t_front`, `t_back1`, `t_back2` - Time values in years
- `dt_event` - Event time fraction
- `event_variance_ratio` - raw_event_var / total_front_var
- `interpolation_method` - "Two-point" or "Single-point"
- `negative_event_var` - Boolean flag
- `term_structure_note` - Warning message

### 4. Extend `analytics/historical.py`
**Status:** ✅ Implemented

**New Functions:**
- `compute_distribution_shape(signed_moves)` - Returns skewness, kurtosis, tail_probs
- `extract_earnings_moves(history, earnings_dates)` - Extracts signed moves

**New Return Fields:**
- `mean_abs_move` - Mean of absolute moves
- `median_abs_move` - Median of absolute moves
- `skewness` - Skewness of signed moves
- `kurtosis` - Excess kurtosis
- `tail_probs` - P(|Move| > threshold) for various thresholds

### 5. Extend `analytics/gamma.py`
**Status:** ✅ Implemented

**New Functions:**
- `find_gamma_flip(gex_by_strike)` - Finds strike where GEX crosses zero
- `top_gamma_strikes(gex_by_strike, n=3)` - Top N strikes by |GEX|

**New Return Fields:**
- `gamma_flip` - Strike where net GEX crosses zero
- `flip_distance_pct` - % distance from spot
- `top_gamma_strikes` - List of (strike, gex) tuples

### 6. Extend `strategies/structures.py`
**Status:** ✅ Implemented

**Updated OptionLeg:**
- Added `entry_price`, `iv`, `delta`, `gamma`, `vega`, `theta`
- Added `to_dict()` method for serialization

**Updated Strategy:**
- Added net greeks (delta, gamma, vega, theta)
- Added breakevens (lower, upper)
- Added capital metrics (max_loss, max_gain, capital_required, capital_efficiency)
- Added `is_defined_risk()` method

---

## 📋 REMAINING TASKS

### 7. Extend `strategies/scoring.py`
**File:** `nvda_earnings_vol/strategies/scoring.py`  
**Status:** 📋 Pending
    Returns: {
        "mean_abs_move": float,
        "median_abs_move": float,
        "skewness": float,
        "kurtosis": float,  # excess kurtosis
        "tail_probs": {0.05: 0.62, 0.08: 0.31, 0.10: 0.18},  # threshold: probability
    }
    """
```

**Interpretation Guide (for report footnotes):**
- `skewness > 0.3` → historical upside bias
- `skewness < -0.3` → historical downside bias
- `kurtosis > 3.0` → fat-tailed, jump-prone
- `kurtosis < 1.0` → thin-tailed

---

### 5. Extend `analytics/gamma.py`
**File:** `nvda_earnings_vol/analytics/gamma.py`  
**Status:** 📋 Pending

**New Functions:**
```python
def find_gamma_flip(gex_by_strike: dict) -> float | None:
    """
    gex_by_strike: {strike: gex_value} sorted by strike
    Returns interpolated strike where cumulative GEX crosses zero
    Returns None if no sign change exists
    """

def top_gamma_strikes(gex_by_strike: dict, n: int = 3) -> list[tuple]:
    """Returns top N strikes by absolute GEX value."""
    return sorted(gex_by_strike.items(), key=lambda x: abs(x[1]), reverse=True)[:n]
```

**Update `gex_summary()` return dict:**
```python
{
    # Existing fields...
    "net_gex": float,
    "abs_gex": float,
    
    # NEW
    "gamma_flip": float | None,
    "flip_distance_pct": float | None,  # (flip - spot) / spot * 100
    "top_gamma_strikes": list[tuple],  # [(strike, gex), ...] top 3
    "front_gex": float,  # GEX from front expiry only
    "back_gex": float,  # GEX from back expiry only
}
```

---

### 6. Extend `strategies/structures.py`
**File:** `nvda_earnings_vol/strategies/structures.py`  
**Status:** 📋 Pending

**Update Strategy dataclass/return:**
```python
strategy = {
    # Existing fields...
    "name": str,
    "legs": [...],
    
    # NEW — Leg-Level Detail (ensure present)
    "legs": [
        {
            "side": str,  # "BUY" | "SELL"
            "option_type": str,  # "call" | "put"
            "strike": float,
            "expiry": str,  # ISO date string
            "qty": int,
            "entry_price": float,  # mid-market at entry
            "iv": float,  # IV at entry (decimal)
            "delta": float,  # signed
            "gamma": float,
            "vega": float,  # per 1% IV move, in dollars
        }
    ],
    
    # NEW — Net Greeks
    "net_delta": float,
    "net_gamma": float,
    "net_vega": float,
    "net_theta": float | None,
    
    # NEW — Risk Boundaries
    "max_loss": float,
    "max_gain": float,
    "lower_breakeven": float | None,
    "upper_breakeven": float | None,
    "lower_be_pct": float | None,  # (lower_be - spot) / spot * 100
    "upper_be_pct": float | None,
    
    # NEW — Capital
    "capital_required": float,  # |max_loss|
    "capital_efficiency": float,  # same as capital_ratio
}
```

---

### 7. Extend `strategies/scoring.py`
**File:** `nvda_earnings_vol/strategies/scoring.py`  
**Status:** 📋 Pending

**New Function:**
```python
def decompose_score(strategy: dict, normalization_stats: dict) -> dict:
    """
    Returns per-component contribution to composite score.
    normalization_stats: {field: (min, max)} for each scored field.
    
    Returns:
    {
        "ev_norm": float,
        "ev_contribution": float,
        "cvar_norm": float,
        "cvar_contribution": float,
        # ... for each component
        "total": float,  # sum of all contributions
    }
    """
```

**Update `compute_metrics()` to include:**
```python
{
    # Existing fields...
    
    # NEW — For alignment scoring
    "net_gamma": float,
    "net_vega": float,
    "convexity": float,
    "cvar": float,  # already present
    
    # NEW — For scenarios
    "scenario_evs": dict[str, float],  # {"base_crush": 142.3, ...}
}
```

---

### 8. Extend `reports/reporter.py` Template
**File:** `nvda_earnings_vol/reports/reporter.py`  
**Status:** 📋 Pending

**New Sections to Add:**

#### Section B — Volatility Regime Summary
- Spot price and implied move
- Historical P75 comparison
- Front/Back IVs with term structure
- Event variance contribution %
- Term structure diagnostics (spreads, slopes)
- Historical distribution shape (skewness, kurtosis, mean/median)
- Tail probability table

#### Section C — Regime Classification Engine
- Vol Pricing Regime with signal strength
- Event Structure with signal strength
- Term Structure classification
- Dealer Gamma Regime with signal strength
- Composite Regime (highlighted) with composite confidence
- Strategic bias statement

#### Section D — Dealer Positioning (Extended)
- Net/Abs GEX with regime classification
- Gamma flip level and distance from spot
- Front vs Back GEX split
- Top 3 gamma concentration strikes

#### Section E — Strategy Rankings (Extended)
Add columns:
- Alignment score
- Weighted alignment

#### Section F — Trade Sheets (Top 3)
For each top strategy:
- Rank and name
- Composite score
- Legs table (side, type, strike, expiry, qty, entry, IV, greeks)
- Net greeks table
- Risk boundaries (max loss/gain, breakevens with %)
- Capital at risk
- Scenario EV sensitivity table
- Regime alignment scores
- Alignment heatmap (color-coded)

#### Formatting Helpers
```python
def format_gex(value: float) -> str:
    """Format large GEX values with B/M suffix."""
    # >= 1e9 → "1.23B"
    # >= 1e6 → "4.56M"
    # else → "789000"
```

**Heatmap Color Formula (RGB):**
```python
# s in [0,1]
r = int((1 - s) * 220)  # 0 → 220 (red)
g = int(s * 200)        # 0 → 200 (green)
b = 80                  # constant
```

---

### 9. Update `main.py` to Wire Everything
**File:** `nvda_earnings_vol/main.py`  
**Status:** 📋 Pending

**Integration Steps:**

#### A. After Event Variance Extraction
```python
# event_info already has new fields
snapshot.update({
    "front_iv": event_info["front_iv"],
    "back1_iv": event_info["back_iv"],
    "back2_iv": event_info.get("back2_iv"),
    "front_back_spread": event_info["front_iv"] - event_info["back_iv"],
    "back_slope": event_info.get("back_slope"),
    "t_front": event_info["t_front"],
    "t_back1": event_info["t_back1"],
    "dt_event": event_info["dt_event"],
    "event_variance_ratio": event_info["event_variance_ratio"],
    "interpolation_method": event_info["interpolation_method"],
    "negative_event_var": event_info["negative_event_var"],
})
```

#### B. After Historical Analysis
```python
from nvda_earnings_vol.analytics.historical import compute_distribution_shape

dist_shape = compute_distribution_shape(historical_moves)
snapshot.update(dist_shape)
```

#### C. After GEX Summary
```python
# gex already has new fields
snapshot.update({
    "gamma_flip": gex.get("gamma_flip"),
    "flip_distance_pct": gex.get("flip_distance_pct"),
    "top_gamma_strikes": gex.get("top_gamma_strikes", []),
    "front_gex": gex.get("front_gex"),
    "back_gex": gex.get("back_gex"),
})
```

#### D. Before Report Generation
```python
from nvda_earnings_vol.regime import classify_regime
from nvda_earnings_vol.alignment import compute_all_alignments

# Classify regime
snapshot["regime"] = classify_regime(snapshot)

# Compute alignments
compute_all_alignments(ranked_strategies, snapshot["regime"])

# Add score decomposition
for strat in ranked_strategies:
    strat["score_components"] = decompose_score(strat, normalization_stats)
```

#### E. Update `write_report()` Call
```python
write_report(
    report_path,
    {
        "snapshot": snapshot,  # All diagnostics nested under snapshot
        "regime": snapshot["regime"],
        "strategies": ranked_strategies,
        "move_plot": move_plot,
        "pnl_plot": pnl_plot,
    }
)
```

---

## 📋 IMPLEMENTATION ORDER

### Phase 1: Analytics Extensions (Foundation)
1. [ ] Extend `event_vol.py` with new fields
2. [ ] Extend `historical.py` with distribution shape
3. [ ] Extend `gamma.py` with flip level and concentration
4. [ ] Extend `structures.py` with detailed legs and breakevens
5. [ ] Extend `scoring.py` with score decomposition

### Phase 2: New Modules (Core Logic)
6. [ ] Create `alignment.py` module
7. [ ] Verify `regime.py` is complete

### Phase 3: Integration (Wiring)
8. [ ] Update `main.py` to compute and pass all new data
9. [ ] Ensure all snapshot fields are populated
10. [ ] Ensure strategy objects have all required fields

### Phase 4: Presentation (Report)
11. [ ] Update `reporter.py` HTML template
12. [ ] Add formatting helpers (format_gex)
13. [ ] Add heatmap color logic
14. [ ] Test template rendering

### Phase 5: Validation
15. [ ] Test flat term structure edge case
16. [ ] Test negative event variance warning
17. [ ] Test no gamma flip case
18. [ ] Test alignment neutral regime
19. [ ] Test full pipeline end-to-end

---

## 🎯 ACCEPTANCE CRITERIA

### Report Must Contain:
- [ ] Regime Classification section with all 4 regimes
- [ ] Volatility Regime Summary with term structure
- [ ] Event variance % contribution
- [ ] Historical distribution (skewness, kurtosis)
- [ ] Tail probability table
- [ ] Dealer Positioning with gamma flip and top 3 strikes
- [ ] Strategy rankings with alignment scores
- [ ] Top 3 strategy trade sheets with:
  - [ ] Full leg details (side, strike, expiry, entry, IV, greeks)
  - [ ] Net greeks
  - [ ] Breakevens with % distance
  - [ ] Capital at risk
  - [ ] Scenario EVs
  - [ ] Regime alignment heatmap

### Technical Requirements:
- [ ] All regime logic deterministic (no randomness)
- [ ] No ML or optimization in regime classification
- [ ] All outputs traceable to inputs
- [ ] Ranking logic unchanged
- [ ] Alignment scoring orthogonal to ranking
- [ ] HTML renders without errors
- [ ] Full pipeline runs successfully

---

## 📊 DATA FLOW DIAGRAM

```
main.py
├── event_variance() → snapshot[front_iv, back_iv, event_variance_ratio, ...]
├── compute_distribution_shape() → snapshot[skewness, kurtosis, tail_probs, ...]
├── gex_summary() → snapshot[gamma_flip, top_gamma_strikes, ...]
├── classify_regime(snapshot) → snapshot[regime]
├── build_strategies() → strategies with legs, breakevens, greeks
├── compute_metrics() → strategies with ev, cvar, convexity, scenario_evs
├── score_strategies() → ranked strategies
├── compute_all_alignments() → strategies with alignment scores
└── write_report(snapshot, regime, strategies)
    └── HTML with all sections
```

---

## 🚀 PRIORITY STACK

| Priority | Item | Impact |
|----------|------|--------|
| P0 | Strategy legs + strikes + greeks | **Actionability** |
| P0 | Term structure IVs + event variance % | **Vol context** |
| P1 | Regime classification engine | **Decision framing** |
| P1 | Scenario EV table per strategy | **Robustness transparency** |
| P2 | Regime alignment scoring | **Structural validation** |
| P2 | Heatmap visualization | **UX** |
| P3 | Historical distribution shape | **Tail context** |
| P3 | Gamma flip + concentration | **Microstructure depth** |

---

_Last Updated: 2026-02-23_
_Next Action: Begin Phase 1 - Extend event_vol.py_
