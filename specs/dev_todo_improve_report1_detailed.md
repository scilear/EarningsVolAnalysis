# NVDA Earnings Vol Engine — Report Upgrade Specification
## From Quant Summary → Execution-Grade Decision Document

**Version:** 2.0  
**Status:** Implementation Spec  
**Scope:** Report layer only — core engine untouched unless noted

---

## 0. OVERVIEW & GUIDING PRINCIPLES

The current report surfaces raw diagnostics. This spec upgrades it to a decision-grade document by adding:

1. Regime classification (deterministic, rule-based)
2. Strategy structural transparency (legs, greeks, breakevens)
3. Regime–strategy alignment scoring
4. Visual heatmaps
5. Term structure and variance attribution

**Non-negotiable constraints:**
- No changes to ranking logic
- No ML or probabilistic classifiers
- Every output fully traceable to an input
- All new fields computed deterministically

**Implementation order (priority stack):**

| Priority | Item | Impact |
|----------|------|--------|
| P0 | Strategy legs + strikes + greeks | Actionability |
| P0 | Term structure IVs + event variance % | Vol context |
| P1 | Regime classification engine | Decision framing |
| P1 | Scenario EV table per strategy | Robustness transparency |
| P2 | Regime alignment scoring | Structural validation |
| P2 | Heatmap visualization | UX |
| P3 | Historical distribution shape | Tail context |
| P3 | Gamma flip + concentration | Microstructure depth |

---

## 1. DATA MODEL EXTENSIONS

All new fields must be computed **before** `write_report()` is called. They are injected into the `snapshot` and `strategies` dicts.

### 1.1 Snapshot Extensions

```python
# In snapshot dict — add these fields:
snapshot = {
    # EXISTING
    "spot": float,
    "event_date": str,
    "front_expiry": str,
    "implied_move": float,
    "historical_p75": float,

    # NEW — Term Structure
    "front_iv": float,          # ATM IV for front expiry
    "back1_iv": float,          # ATM IV for first back expiry
    "back2_iv": float,          # ATM IV for second back expiry (or None)
    "front_back_spread": float, # front_iv - back1_iv
    "back_slope": float,        # back1_iv - back2_iv (or None)

    # NEW — Variance Attribution
    "event_variance_ratio": float,  # raw_event_var / (t_front * front_iv^2)
    "t_front": float,               # front expiry in years
    "t_back1": float,               # back1 expiry in years
    "dt_event": float,              # always 1/252
    "interpolation_method": str,    # "Two-point total variance" or "Single-point"
    "negative_event_var": bool,     # True if raw_event_var < 0

    # NEW — Historical Distribution Shape
    "mean_abs_move": float,
    "median_abs_move": float,
    "skewness": float,              # signed move skewness
    "kurtosis": float,              # signed move excess kurtosis
    "tail_probs": dict,             # {0.05: 0.62, 0.08: 0.31, 0.10: 0.18}

    # NEW — GEX Extensions
    "gamma_flip": float | None,     # strike where net GEX crosses zero
    "flip_distance_pct": float | None,  # (flip - spot) / spot * 100
    "top_gamma_strikes": list[tuple],   # [(strike, gex_val), ...] top 3
    "front_gex": float,             # GEX from front-expiry options only
    "back_gex": float,              # GEX from back-expiry options only

    # NEW — Regime (injected by regime.py)
    "regime": dict,                 # see section 3
}
```

### 1.2 Strategy Extensions

For each strategy in the ranked list:

```python
strategy = {
    # EXISTING
    "rank": int,
    "name": str,
    "score": float,
    "ev": float,
    "cvar": float,
    "convexity": float,
    "capital_ratio": float,
    "risk": str,  # "defined_risk" | "undefined_risk"

    # NEW — Leg-Level Detail
    "legs": [
        {
            "side": str,          # "BUY" | "SELL"
            "option_type": str,   # "call" | "put"
            "strike": float,
            "expiry": str,        # ISO date string
            "qty": int,
            "entry_price": float, # mid-market at entry
            "iv": float,          # IV at entry (decimal)
            "delta": float,       # signed (positive for long)
            "gamma": float,       # always positive
            "vega": float,        # per 1% IV move, in dollars
        }
    ],

    # NEW — Net Greeks
    "net_delta": float,
    "net_gamma": float,
    "net_vega": float,
    "net_theta": float,   # optional — set to None if not computed

    # NEW — Risk Boundaries
    "max_loss": float,    # worst case PnL (negative number)
    "max_gain": float,    # best case PnL
    "lower_breakeven": float | None,   # None for undefined risk
    "upper_breakeven": float | None,
    "lower_be_pct": float | None,      # (lower_be - spot) / spot * 100
    "upper_be_pct": float | None,

    # NEW — Scenario EVs
    "scenario_evs": dict,  # {"base_crush": 142.3, "hard_crush": 110.5, "expansion": 155.0}

    # NEW — Score Decomposition
    "score_components": dict,  # {"ev_norm": 0.28, "cvar_norm": -0.05, ...}

    # NEW — Regime Alignment (injected by alignment.py)
    "alignment": dict,   # see section 4
}
```

---

## 2. MODULE: `event_vol.py` — Additions

### 2.1 Expose Term Structure Fields

`extract_event_vol()` currently returns only `event_vol`. Extend its return dict:

```python
def extract_event_vol(chain, front_expiry, back1_expiry, back2_expiry=None) -> dict:
    return {
        # existing
        "event_vol": float,
        "raw_event_var": float,
        "negative": bool,
        # new
        "front_iv": float,
        "back1_iv": float,
        "back2_iv": float | None,
        "front_back_spread": float,
        "back_slope": float | None,
        "t_front": float,
        "t_back1": float,
        "dt_event": float,          # hardcoded 1/252
        "interpolation_method": str,
        "event_variance_ratio": float,  # raw_event_var / (t_front * front_iv^2)
        "term_structure_note": str | None,
    }
```

**event_variance_ratio formula:**

```python
total_front_var = t_front * front_iv ** 2
event_variance_ratio = raw_event_var / total_front_var if total_front_var > 0 else 0.0
```

**Interpretation guide (for logs, not report):**

```
> 0.70 → Pure binary event: >70% of front variance is earnings day
0.50–0.70 → Event-dominant
< 0.50 → Distributed volatility: other factors matter
```

---

## 3. NEW MODULE: `regime.py`

Create `nvda_earnings_vol/regime.py`.

### 3.1 Full Implementation

```python
"""
Deterministic regime classification.
No ML. No optimization. Fully auditable.
"""

def classify_regime(snapshot: dict) -> dict:
    """
    Returns structured regime dict. Injected into snapshot before report.
    """

    # ─── Vol Pricing Regime ───────────────────────────────────────────────
    p75 = snapshot["historical_p75"]
    implied = snapshot["implied_move"]
    ratio_p75 = implied / p75 if p75 > 0 else 1.0

    if ratio_p75 < 0.85:
        vol_label = "Tail Underpriced"
    elif ratio_p75 > 1.10:
        vol_label = "Tail Overpriced"
    else:
        vol_label = "Fairly Priced"

    vol_conf = min(abs(ratio_p75 - 1.0) / 0.20, 1.0)

    # ─── Event Dominance Regime ───────────────────────────────────────────
    ev_ratio = snapshot.get("event_variance_ratio", 0.5)

    if ev_ratio > 0.70:
        event_label = "Pure Binary Event"
    elif ev_ratio > 0.50:
        event_label = "Event-Dominant"
    else:
        event_label = "Distributed Volatility"

    event_conf = min(ev_ratio / 0.80, 1.0)

    # ─── Term Structure Regime ────────────────────────────────────────────
    spread = snapshot.get("front_back_spread", 0.0)

    if spread > 0.20:
        term_label = "Extreme Front Premium"
    elif spread > 0.10:
        term_label = "Elevated Front Premium"
    elif spread < -0.05:
        term_label = "Inverted Structure"
    else:
        term_label = "Normal Structure"

    # ─── Dealer Gamma Regime ──────────────────────────────────────────────
    gex_net = snapshot.get("gex_net", 0.0)
    gex_abs = snapshot.get("gex_abs", 1.0)
    gex_ratio = abs(gex_net) / gex_abs if gex_abs > 0 else 0.0

    if gex_net < 0 and gex_ratio > 0.70:
        gamma_label = "Amplified Move Regime"
        gamma_bias = "long_gamma"
    elif gex_net > 0 and gex_ratio > 0.70:
        gamma_label = "Pin Risk Regime"
        gamma_bias = "short_gamma"
    else:
        gamma_label = "Neutral / Mixed Gamma"
        gamma_bias = "neutral"

    gamma_conf = min(gex_ratio, 1.0)

    # ─── Composite Regime ─────────────────────────────────────────────────
    if (
        vol_label == "Tail Underpriced"
        and gamma_label == "Amplified Move Regime"
        and ev_ratio > 0.60
    ):
        composite = "Convex Breakout Setup"
        strategic_bias = "Favor long gamma, long vega. Backspreads, strangles."
    elif (
        vol_label == "Tail Overpriced"
        and gamma_label == "Pin Risk Regime"
    ):
        composite = "Premium Harvest Setup"
        strategic_bias = "Favor short gamma, short vega. Condors, spreads."
    elif vol_label == "Tail Underpriced" and ev_ratio > 0.60:
        composite = "Binary Long Vol Setup"
        strategic_bias = "Long vol bias. Gamma regime mixed — prefer defined risk structures."
    elif vol_label == "Tail Overpriced":
        composite = "Premium Collection Setup"
        strategic_bias = "Short vol bias. Gamma regime mixed — prefer tight spreads."
    else:
        composite = "Mixed / Transitional Setup"
        strategic_bias = "No strong directional vol bias. Regime signal weak."

    # ─── Composite Confidence ─────────────────────────────────────────────
    composite_conf = (
        0.40 * vol_conf +
        0.30 * gamma_conf +
        0.30 * event_conf
    )

    return {
        # Labels
        "vol_regime": vol_label,
        "event_regime": event_label,
        "term_structure_regime": term_label,
        "gamma_regime": gamma_label,
        "composite_regime": composite,
        "strategic_bias": strategic_bias,
        # Metrics
        "vol_ratio": round(ratio_p75, 4),
        "gex_ratio": round(gex_ratio, 4),
        "event_variance_ratio": round(ev_ratio, 4),
        # Confidence
        "vol_confidence": round(vol_conf, 3),
        "gamma_confidence": round(gamma_conf, 3),
        "event_confidence": round(event_conf, 3),
        "confidence": round(composite_conf, 3),
        # Internal bias tag (used by alignment.py)
        "gamma_bias": gamma_bias,
    }
```

### 3.2 Integration into `main.py`

```python
# After all diagnostics are computed, before write_report():
from nvda_earnings_vol.regime import classify_regime

snapshot["regime"] = classify_regime(snapshot)
```

---

## 4. NEW MODULE: `alignment.py`

Create `nvda_earnings_vol/alignment.py`.

### 4.1 Design Rules

- Scores are 0.0–1.0 continuous
- No binary thresholds (use scaled sign alignment)
- Population-relative comparison for convexity and CVaR
- Does NOT alter ranking

### 4.2 Full Implementation

```python
"""
Regime–strategy structural alignment scoring.
Orthogonal to ranking. Fully deterministic.
"""
import numpy as np
from typing import List


def _percentile_rank(value: float, population: List[float]) -> float:
    """Returns 0–1 rank of value within population."""
    if len(population) == 0:
        return 0.5
    return sum(1 for x in population if x <= value) / len(population)


def _scaled_sign(value: float, desired_positive: bool, scale: float) -> float:
    """
    Maps value onto [0,1] relative to scale.
    desired_positive=True → high positive value → score near 1.0
    """
    if scale == 0:
        return 0.5
    normalized = max(min(value / scale, 1.0), -1.0)
    if desired_positive:
        return (normalized + 1.0) / 2.0
    else:
        return (1.0 - normalized) / 2.0


def compute_alignment(strategy: dict, regime: dict, population_stats: dict) -> dict:
    """
    Parameters
    ----------
    strategy : dict with net_gamma, net_vega, convexity, cvar (negative number)
    regime   : dict returned by classify_regime()
    population_stats : dict with median_abs_gamma, median_abs_vega,
                       convexities (list), cvars (list of negative numbers)

    Returns
    -------
    dict with alignment_score, alignment_weighted, alignment_breakdown, alignment_heatmap
    """

    # ─── Axis 1: Gamma ────────────────────────────────────────────────────
    gamma_bias = regime["gamma_bias"]
    desired_long_gamma = (gamma_bias == "long_gamma")
    desired_short_gamma = (gamma_bias == "short_gamma")

    if gamma_bias == "neutral":
        gamma_score = 0.5
    elif desired_long_gamma:
        gamma_score = _scaled_sign(
            strategy["net_gamma"],
            desired_positive=True,
            scale=population_stats.get("median_abs_gamma", 1.0)
        )
    else:  # desired_short_gamma
        gamma_score = _scaled_sign(
            strategy["net_gamma"],
            desired_positive=False,
            scale=population_stats.get("median_abs_gamma", 1.0)
        )

    # ─── Axis 2: Vega ─────────────────────────────────────────────────────
    vol_regime = regime["vol_regime"]

    if vol_regime == "Tail Underpriced":
        vega_score = _scaled_sign(
            strategy["net_vega"],
            desired_positive=True,
            scale=population_stats.get("median_abs_vega", 1.0)
        )
    elif vol_regime == "Tail Overpriced":
        vega_score = _scaled_sign(
            strategy["net_vega"],
            desired_positive=False,
            scale=population_stats.get("median_abs_vega", 1.0)
        )
    else:
        vega_score = 0.5

    # ─── Axis 3: Convexity ────────────────────────────────────────────────
    composite = regime["composite_regime"]
    conv_rank = _percentile_rank(
        strategy["convexity"],
        population_stats.get("convexities", [])
    )

    if composite == "Convex Breakout Setup":
        convexity_score = conv_rank          # high convexity aligned
    elif composite == "Premium Harvest Setup":
        convexity_score = 1.0 - conv_rank    # low convexity aligned
    else:
        convexity_score = 0.5

    # ─── Axis 4: Tail Risk (CVaR) ─────────────────────────────────────────
    # CVaR is a negative number — more negative = heavier tail loss
    # percentile rank of cvar: 0 = best (least negative), 1 = worst
    cvar_rank = _percentile_rank(
        strategy["cvar"],
        population_stats.get("cvars", [])
    )
    # For tail underpriced: prefer strategies with less severe CVaR (low rank)
    if vol_regime == "Tail Underpriced":
        tail_score = 1.0 - cvar_rank
    else:
        tail_score = 0.5

    # ─── Composite ────────────────────────────────────────────────────────
    alignment_score = (gamma_score + vega_score + convexity_score + tail_score) / 4.0
    alignment_weighted = alignment_score * regime["confidence"]

    return {
        "alignment_score": round(alignment_score, 3),
        "alignment_weighted": round(alignment_weighted, 3),
        "alignment_breakdown": {
            "gamma_alignment": round(gamma_score, 3),
            "vega_alignment": round(vega_score, 3),
            "convexity_alignment": round(convexity_score, 3),
            "tail_alignment": round(tail_score, 3),
        },
        # Raw values for heatmap cells (same as breakdown)
        "alignment_heatmap": {
            "Gamma": round(gamma_score, 3),
            "Vega": round(vega_score, 3),
            "Convexity": round(convexity_score, 3),
            "Tail Risk": round(tail_score, 3),
        }
    }


def compute_all_alignments(strategies: list, regime: dict) -> None:
    """
    Mutates each strategy dict in-place.
    Computes population stats first, then scores per strategy.
    """
    gammas = [abs(s["net_gamma"]) for s in strategies]
    vegas = [abs(s["net_vega"]) for s in strategies]
    convexities = [s["convexity"] for s in strategies]
    cvars = [s["cvar"] for s in strategies]

    population_stats = {
        "median_abs_gamma": float(np.median(gammas)) if gammas else 1.0,
        "median_abs_vega": float(np.median(vegas)) if vegas else 1.0,
        "convexities": convexities,
        "cvars": cvars,
    }

    for s in strategies:
        s["alignment"] = compute_alignment(s, regime, population_stats)
```

### 4.3 Integration into `main.py`

```python
# After regime classification, after all strategies are scored:
from nvda_earnings_vol.alignment import compute_all_alignments

compute_all_alignments(ranked_strategies, snapshot["regime"])
```

### 4.4 Alignment Score Interpretation Table

| Score | Label |
|-------|-------|
| 0.75–1.00 | Strong structural match |
| 0.50–0.75 | Partial alignment |
| 0.25–0.50 | Weak alignment |
| 0.00–0.25 | Structurally opposed |

Note: `alignment_weighted` scales this by regime confidence. A 0.8 alignment score under 0.5 confidence = 0.40 weighted — equivalent to weak alignment under strong regime.

---

## 5. MODULE: `historical.py` — Additions

Add distribution shape computation alongside existing P75:

```python
def compute_distribution_shape(moves: list[float]) -> dict:
    """
    moves: list of signed percentage returns (not absolute)
    Returns skewness, kurtosis, mean/median abs move, tail probs.
    """
    import numpy as np
    from scipy import stats

    arr = np.array(moves)
    abs_arr = np.abs(arr)

    tail_thresholds = [0.05, 0.08, 0.10, 0.12, 0.15]
    tail_probs = {
        t: float(np.mean(abs_arr > t))
        for t in tail_thresholds
    }

    return {
        "mean_abs_move": float(np.mean(abs_arr)),
        "median_abs_move": float(np.median(abs_arr)),
        "skewness": float(stats.skew(arr)),
        "kurtosis": float(stats.kurtosis(arr)),   # excess kurtosis
        "tail_probs": tail_probs,
    }
```

**Interpretation guidance for report:**
- `skewness > 0.3` → historical upside bias
- `skewness < -0.3` → historical downside bias
- `kurtosis > 3.0` → fat-tailed, jump-prone
- `kurtosis < 1.0` → thin-tailed

---

## 6. MODULE: `gamma.py` — Additions

### 6.1 Gamma Flip Level

```python
def find_gamma_flip(gex_by_strike: dict) -> float | None:
    """
    gex_by_strike: {strike: gex_value} sorted by strike.
    Returns the interpolated strike where cumulative GEX crosses zero.
    Returns None if no sign change exists.
    """
    strikes = sorted(gex_by_strike.keys())
    cum_gex = []
    running = 0.0
    for k in strikes:
        running += gex_by_strike[k]
        cum_gex.append((k, running))

    # Find sign change
    for i in range(1, len(cum_gex)):
        k0, g0 = cum_gex[i - 1]
        k1, g1 = cum_gex[i]
        if g0 * g1 < 0:
            # Linear interpolation
            flip = k0 + (k1 - k0) * abs(g0) / (abs(g0) + abs(g1))
            return round(flip, 2)

    return None


def top_gamma_strikes(gex_by_strike: dict, n: int = 3) -> list[tuple]:
    """Returns top N strikes by absolute GEX value."""
    return sorted(
        gex_by_strike.items(),
        key=lambda x: abs(x[1]),
        reverse=True
    )[:n]
```

---

## 7. HTML REPORT TEMPLATE

The report is structured in 7 sections. Here is the complete section map and HTML spec.

### 7.1 Section Map

```
Section A: Market Snapshot Header
Section B: Volatility Regime Summary  ← NEW
Section C: Regime Classification Engine  ← NEW
Section D: Dealer Positioning Dashboard  ← extended
Section E: Strategy Rankings  ← extended
Section F: Strategy Trade Sheets (top 3)  ← NEW
Section G: Appendix (methodology notes)
```

---

### 7.2 Section B — Volatility Regime Summary

```html
<h2>Volatility Regime Summary</h2>

<table>
  <tr>
    <th>Spot</th><td>${{ snapshot.spot | round(2) }}</td>
    <th>Expected Move ($)</th><td>${{ (snapshot.implied_move * snapshot.spot) | round(2) }}</td>
  </tr>
  <tr>
    <th>Implied Move</th><td>{{ (snapshot.implied_move * 100) | round(2) }}%</td>
    <th>Historical P75</th><td>{{ (snapshot.historical_p75 * 100) | round(2) }}%</td>
  </tr>
  <tr>
    <th>Implied / P75</th><td>{{ snapshot.regime.vol_ratio | round(3) }}</td>
    <th>Vol Regime</th><td><strong>{{ snapshot.regime.vol_regime }}</strong></td>
  </tr>
</table>

<h4>Term Structure</h4>
<table>
  <tr>
    <th>Front IV</th><td>{{ (snapshot.front_iv * 100) | round(2) }}%</td>
    <th>Back1 IV</th><td>{{ (snapshot.back1_iv * 100) | round(2) }}%</td>
    {% if snapshot.back2_iv %}
    <th>Back2 IV</th><td>{{ (snapshot.back2_iv * 100) | round(2) }}%</td>
    {% endif %}
  </tr>
  <tr>
    <th>Front–Back Spread</th><td>{{ (snapshot.front_back_spread * 100) | round(2) }} vol pts</td>
    <th>Term Structure</th><td>{{ snapshot.regime.term_structure_regime }}</td>
  </tr>
</table>

<h4>Event Variance Attribution</h4>
<table>
  <tr>
    <th>Raw Event Var</th><td>{{ snapshot.raw_event_var | round(4) }}</td>
    <th>EventVar / TotalFrontVar</th><td>{{ (snapshot.event_variance_ratio * 100) | round(1) }}%</td>
  </tr>
  <tr>
    <th>Event Structure</th><td><strong>{{ snapshot.regime.event_regime }}</strong></td>
    <th>Interpolation</th><td>{{ snapshot.interpolation_method }}</td>
  </tr>
  {% if snapshot.negative_event_var %}
  <tr>
    <td colspan="4" style="color:red;"><strong>⚠ Negative event variance detected — term structure may be inverted or data issue present.</strong></td>
  </tr>
  {% endif %}
</table>

<h4>Historical Distribution ({{ n_historical }} earnings events)</h4>
<table>
  <tr>
    <th>Mean |Move|</th><td>{{ (snapshot.mean_abs_move * 100) | round(2) }}%</td>
    <th>Median |Move|</th><td>{{ (snapshot.median_abs_move * 100) | round(2) }}%</td>
  </tr>
  <tr>
    <th>Skewness</th><td>{{ snapshot.skewness | round(3) }}</td>
    <th>Excess Kurtosis</th><td>{{ snapshot.kurtosis | round(3) }}</td>
  </tr>
</table>

<h4>Tail Probability Table</h4>
<table>
  <tr>
    {% for threshold, prob in snapshot.tail_probs.items() %}
    <th>P(|Move| &gt; {{ (threshold * 100) | int }}%)</th>
    {% endfor %}
  </tr>
  <tr>
    {% for threshold, prob in snapshot.tail_probs.items() %}
    <td>{{ (prob * 100) | round(1) }}%</td>
    {% endfor %}
  </tr>
</table>
```

---

### 7.3 Section C — Regime Classification Engine

```html
<h2>Regime Classification Engine</h2>

<table>
  <tr>
    <th>Vol Pricing Regime</th>
    <td>{{ snapshot.regime.vol_regime }}</td>
    <th>Signal Strength</th>
    <td>{{ snapshot.regime.vol_confidence | round(2) }}</td>
  </tr>
  <tr>
    <th>Event Structure</th>
    <td>{{ snapshot.regime.event_regime }}</td>
    <th>Signal Strength</th>
    <td>{{ snapshot.regime.event_confidence | round(2) }}</td>
  </tr>
  <tr>
    <th>Term Structure</th>
    <td>{{ snapshot.regime.term_structure_regime }}</td>
    <th>—</th><td>—</td>
  </tr>
  <tr>
    <th>Dealer Gamma Regime</th>
    <td>{{ snapshot.regime.gamma_regime }}</td>
    <th>Signal Strength</th>
    <td>{{ snapshot.regime.gamma_confidence | round(2) }}</td>
  </tr>
  <tr style="background:#1a2a3a; color:white;">
    <th>Composite Regime</th>
    <td><strong>{{ snapshot.regime.composite_regime }}</strong></td>
    <th>Composite Confidence</th>
    <td><strong>{{ snapshot.regime.confidence | round(2) }}</strong></td>
  </tr>
</table>

<p><strong>Strategic Bias:</strong> {{ snapshot.regime.strategic_bias }}</p>

<p class="note">
  Regime confidence 0–1: values below 0.4 indicate mixed or transitional conditions.
  Composite confidence = 0.4 × vol_signal + 0.3 × gamma_signal + 0.3 × event_signal.
</p>
```

---

### 7.4 Section D — Dealer Positioning (Extended)

```html
<h2>Dealer Positioning & Microstructure</h2>

<table>
  <tr>
    <th>Net GEX ($)</th><td>{{ snapshot.gex_net | format_gex }}</td>
    <th>Abs GEX ($)</th><td>{{ snapshot.gex_abs | format_gex }}</td>
  </tr>
  <tr>
    <th>Gamma Regime</th><td>{{ snapshot.regime.gamma_regime }}</td>
    <th>Flip Level</th>
    <td>
      {% if snapshot.gamma_flip %}
        {{ snapshot.gamma_flip | round(2) }}
        ({{ snapshot.flip_distance_pct | round(2) }}% from spot)
      {% else %}
        No flip detected in chain
      {% endif %}
    </td>
  </tr>
  <tr>
    <th>Front-Expiry GEX</th><td>{{ snapshot.front_gex | format_gex }}</td>
    <th>Back-Expiry GEX</th><td>{{ snapshot.back_gex | format_gex }}</td>
  </tr>
</table>

<p class="note">{{ snapshot.gex_dealer_note }}</p>

<h4>Top 3 Strikes by Gamma Concentration</h4>
<table>
  <tr><th>Strike</th><th>GEX ($)</th><th>% of Abs GEX</th></tr>
  {% for strike, value in snapshot.top_gamma_strikes %}
  <tr>
    <td>{{ strike }}</td>
    <td>{{ value | format_gex }}</td>
    <td>{{ ((value | abs) / snapshot.gex_abs * 100) | round(1) }}%</td>
  </tr>
  {% endfor %}
</table>
```

---

### 7.5 Section E — Strategy Rankings (Extended)

Add columns to the existing table:

```html
<table>
  <tr>
    <th>Rank</th>
    <th>Strategy</th>
    <th>Score</th>
    <th>EV</th>
    <th>CVaR</th>
    <th>Convexity</th>
    <th>Capital Ratio</th>
    <th>Robustness</th>
    <th>Risk</th>
    <th>Alignment</th>    <!-- NEW -->
    <th>Weighted Align</th>  <!-- NEW -->
  </tr>
  {% for strat in strategies %}
  <tr>
    <td>{{ strat.rank }}</td>
    <td>{{ strat.name }}</td>
    <td>{{ strat.score | round(4) }}</td>
    <td>{{ strat.ev | round(2) }}</td>
    <td>{{ strat.cvar | round(2) }}</td>
    <td>{{ strat.convexity | round(4) }}</td>
    <td>{{ strat.capital_ratio | round(4) }}</td>
    <td>{{ strat.robustness | round(4) }}</td>
    <td>{{ strat.risk }}</td>
    <td>{{ strat.alignment.alignment_score | round(2) }}</td>
    <td>{{ strat.alignment.alignment_weighted | round(2) }}</td>
  </tr>
  {% endfor %}
</table>
```

---

### 7.6 Section F — Trade Sheets (Top 3)

This is the execution-grade section. One card per strategy.

```html
<h2>Top Strategy Trade Sheets</h2>

{% for strat in strategies[:3] %}
<div style="border:2px solid #2c5282; padding:20px; margin-bottom:40px; border-radius:6px;">

  <h3>{{ strat.rank }}. {{ strat.name | upper }}
    <span style="font-size:0.8em; color:#666;">Score: {{ strat.score | round(4) }}</span>
  </h3>

  <!-- ── Entry Structure ── -->
  <h4>Legs</h4>
  <table>
    <tr>
      <th>Side</th><th>Type</th><th>Strike</th><th>Expiry</th>
      <th>Qty</th><th>Entry $</th><th>IV</th>
      <th>Δ</th><th>Γ</th><th>Vega</th>
    </tr>
    {% for leg in strat.legs %}
    <tr>
      <td><strong>{{ leg.side }}</strong></td>
      <td>{{ leg.option_type | upper }}</td>
      <td>{{ leg.strike | round(2) }}</td>
      <td>{{ leg.expiry }}</td>
      <td>{{ leg.qty }}</td>
      <td>{{ leg.entry_price | round(2) }}</td>
      <td>{{ (leg.iv * 100) | round(1) }}%</td>
      <td>{{ leg.delta | round(3) }}</td>
      <td>{{ leg.gamma | round(5) }}</td>
      <td>{{ leg.vega | round(2) }}</td>
    </tr>
    {% endfor %}
  </table>

  <!-- ── Net Greeks ── -->
  <h4>Net Greeks at Entry</h4>
  <table>
    <tr>
      <th>Net Δ</th><th>Net Γ</th><th>Net Vega</th>
      {% if strat.net_theta is not none %}<th>Net Θ</th>{% endif %}
    </tr>
    <tr>
      <td>{{ strat.net_delta | round(4) }}</td>
      <td>{{ strat.net_gamma | round(6) }}</td>
      <td>{{ strat.net_vega | round(2) }}</td>
      {% if strat.net_theta is not none %}<td>{{ strat.net_theta | round(2) }}</td>{% endif %}
    </tr>
  </table>

  <!-- ── Risk Boundaries ── -->
  <h4>Risk Boundaries</h4>
  <table>
    <tr>
      <th>Max Loss</th><td>${{ strat.max_loss | round(2) }}</td>
      <th>Max Gain</th><td>${{ strat.max_gain | round(2) }}</td>
    </tr>
    {% if strat.lower_breakeven %}
    <tr>
      <th>Lower BE</th>
      <td>{{ strat.lower_breakeven | round(2) }} ({{ strat.lower_be_pct | round(2) }}%)</td>
      <th>Upper BE</th>
      <td>
        {% if strat.upper_breakeven %}
          {{ strat.upper_breakeven | round(2) }} ({{ strat.upper_be_pct | round(2) }}%)
        {% else %}
          Open
        {% endif %}
      </td>
    </tr>
    {% endif %}
    <tr>
      <th>Capital Required</th><td>${{ (strat.max_loss | abs) | round(2) }}</td>
      <th>Capital Efficiency</th><td>{{ strat.capital_ratio | round(4) }}</td>
    </tr>
  </table>

  <!-- ── Scenario EVs ── -->
  <h4>Scenario EV Sensitivity</h4>
  <table>
    <tr>
      {% for label in strat.scenario_evs.keys() %}
      <th>{{ label }}</th>
      {% endfor %}
    </tr>
    <tr>
      {% for ev in strat.scenario_evs.values() %}
      <td style="color: {% if ev >= 0 %}green{% else %}red{% endif %}">
        ${{ ev | round(2) }}
      </td>
      {% endfor %}
    </tr>
  </table>

  <!-- ── Regime Alignment ── -->
  <h4>Regime Alignment
    <span style="font-size:0.8em;">
      (regime: {{ snapshot.regime.composite_regime }},
       confidence: {{ snapshot.regime.confidence | round(2) }})
    </span>
  </h4>

  <!-- Heatmap row -->
  <table style="text-align:center;">
    <tr>
      {% for axis, score in strat.alignment.alignment_heatmap.items() %}
      {% set r = ((1 - score) * 220) | int %}
      {% set g = (score * 200) | int %}
      <td style="background:rgb({{ r }},{{ g }},80); padding:12px 16px; color:white; font-weight:bold;">
        {{ axis }}<br>{{ score | round(2) }}
      </td>
      {% endfor %}
    </tr>
  </table>

  <p>
    <strong>Composite Alignment:</strong> {{ strat.alignment.alignment_score | round(2) }}
    &nbsp;|&nbsp;
    <strong>Confidence-Weighted:</strong> {{ strat.alignment.alignment_weighted | round(2) }}
  </p>

</div>
{% endfor %}
```

---

## 8. SCORING TRANSPARENCY EXTENSION

### 8.1 Score Decomposition

Extend `scoring.py` to expose normalized component weights:

```python
def decompose_score(strategy: dict, normalization_stats: dict) -> dict:
    """
    Returns per-component contribution to composite score.
    normalization_stats: {field: (min, max)} for each scored field.
    """
    components = {}
    weights = SCORE_WEIGHTS  # existing dict

    for field, weight in weights.items():
        raw = strategy[field]
        lo, hi = normalization_stats[field]
        normalized = (raw - lo) / (hi - lo) if hi != lo else 0.5
        components[f"{field}_norm"] = round(normalized, 4)
        components[f"{field}_contribution"] = round(normalized * weight, 4)

    components["total"] = round(sum(
        v for k, v in components.items() if k.endswith("_contribution")
    ), 4)

    return components
```

**Add to report (per strategy row or expandable):**

```html
<details>
  <summary>Score Breakdown</summary>
  <table>
    {% for key, val in strat.score_components.items() %}
    {% if key.endswith('_contribution') %}
    <tr>
      <td>{{ key | replace('_contribution','') }}</td>
      <td>{{ val }}</td>
    </tr>
    {% endif %}
    {% endfor %}
    <tr style="font-weight:bold;">
      <td>Total</td><td>{{ strat.score_components.total }}</td>
    </tr>
  </table>
</details>
```

---

## 9. HEATMAP COLOR FORMULA

For RGB heatmap cells (0=red, 1=green, transition through yellow):

```python
# For score s in [0,1]:
# s=0.0 → rgb(220, 0, 80)   = red
# s=0.5 → rgb(110, 100, 80) = yellow-ish
# s=1.0 → rgb(0, 200, 80)   = green

r = int((1 - score) * 220)
g = int(score * 200)
b = 80  # constant blue baseline
```

In Jinja2:
```html
{% set r = ((1 - score) * 220) | int %}
{% set g = (score * 200) | int %}
<td style="background:rgb({{ r }},{{ g }},80);">
```

---

## 10. FORMATTING HELPERS

Add to template context or Jinja2 filter registry:

```python
def format_gex(value: float) -> str:
    """Format large GEX values with B/M suffix."""
    abs_val = abs(value)
    sign = "-" if value < 0 else ""
    if abs_val >= 1e9:
        return f"{sign}{abs_val/1e9:.2f}B"
    elif abs_val >= 1e6:
        return f"{sign}{abs_val/1e6:.2f}M"
    else:
        return f"{sign}{abs_val:.0f}"

# Register as Jinja filter:
env.filters["format_gex"] = format_gex
```

---

## 11. IMPLEMENTATION CHECKLIST

**Phase 1 — High Priority (affects actionability)**

- [ ] Extend `extract_event_vol()` return dict with IV and variance fields
- [ ] Add `compute_distribution_shape()` to `historical.py`
- [ ] Add `find_gamma_flip()` and `top_gamma_strikes()` to `gamma.py`
- [ ] Ensure `structures.py` / `payoff.py` expose leg-level detail at entry
- [ ] Ensure `scoring.py` exposes `scenario_evs` per strategy
- [ ] Expose `max_loss`, `max_gain`, `lower_breakeven`, `upper_breakeven`

**Phase 2 — New Modules**

- [ ] Create `regime.py` with `classify_regime()`
- [ ] Create `alignment.py` with `compute_alignment()` and `compute_all_alignments()`
- [ ] Wire both into `main.py` after diagnostics, before report

**Phase 3 — Report Template**

- [ ] Add Section B (Vol Regime Summary)
- [ ] Add Section C (Regime Classification)
- [ ] Extend Section D (Dealer Positioning)
- [ ] Extend Section E (Rankings table — alignment columns)
- [ ] Add Section F (Trade Sheets per top strategy)
- [ ] Add `format_gex` Jinja filter
- [ ] Add score decomposition `<details>` block

**Phase 4 — Testing**

- [ ] Flat term structure edge case: `event_variance_ratio` ≠ 0
- [ ] Negative event var: `negative_event_var = True` + warning block visible
- [ ] No gamma flip: `gamma_flip = None` → "No flip detected"
- [ ] Alignment neutral regime: all scores = 0.5
- [ ] Alignment pure breakout: calendar should score high gamma + vega
- [ ] Score decomposition sums to composite score ± 0.001

---

## 12. WHAT THIS ACHIEVES

After implementation:

**Before:** 
> "Calendar ranked #1, score 0.863, EV 26.05"

**After:**
> "Calendar ranked #1. Regime: Convex Breakout Setup (confidence 0.72). 
> Structure: BUY 1 190C Feb28 @ 14.20 / SELL 1 190C Mar21 @ 18.40. 
> Net Vega +0.42 — aligned with Tail Underpriced regime (vega score 0.81). 
> Scenario EVs: Base +26 / Hard Crush +18 / Expansion +44. 
> Regime alignment 0.74 → strong structural match."

The report becomes a complete, printable pre-trade brief.

---

*Spec version 2.0 — All regime logic deterministic. No ML. No optimization. Fully auditable.*
