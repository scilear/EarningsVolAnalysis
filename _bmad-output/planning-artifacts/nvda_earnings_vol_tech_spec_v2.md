# Tech-Spec: NVDA Earnings Volatility & Options Structure Analysis Engine (v2)

Created: 2026-02-23
Status: Updated for implementation
Target: NVDA (hardcoded MVP), parameterized event date

---

## 1. Overview

### Problem Statement

Options traders need a quantitative engine that isolates pure earnings event volatility, compares implied vs realized moves, and ranks option structures by risk-adjusted expected value, not just probability of profit. Existing tools either oversimplify (ignoring IV regime uncertainty, skew distortion, tail risk) or require expensive platforms.

### Solution

A self-contained Python CLI application that fetches live options/price data via yfinance, runs a full analytical pipeline (event vol extraction, skew analysis, GEX, Monte Carlo simulation under multiple IV regimes), scores 8 option structures on a composite metric, and outputs a self-contained HTML report with embedded plots.

### Scope

In Scope (MVP):
- NVDA only (hardcoded ticker)
- CLI with --event-date param (default: next earnings)
- All 12 spec sections implemented
- HTML report with embedded base64 plots
- Basic unit tests per module
- Print-level debug output

Out of Scope (Post-MVP):
- Multi-ticker support
- PDF report generation
- Real-time streaming
- Web UI
- SABR or stochastic vol models
- Broker API integration

---

## 2. Project Structure

nvda_earnings_vol/
├── __init__.py
├── config.py
├── main.py
├── data/
│   ├── __init__.py
│   ├── loader.py
│   └── filters.py
├── analytics/
│   ├── __init__.py
│   ├── bsm.py
│   ├── implied_move.py
│   ├── event_vol.py
│   ├── historical.py
│   ├── skew.py
│   └── gamma.py
├── simulation/
│   ├── __init__.py
│   └── monte_carlo.py
├── strategies/
│   ├── __init__.py
│   ├── structures.py
│   ├── payoff.py
│   └── scoring.py
├── viz/
│   ├── __init__.py
│   └── plots.py
├── reports/
│   ├── __init__.py
│   ├── reporter.py
│   └── figures/
├── tests/
│   ├── __init__.py
│   ├── test_loader.py
│   ├── test_bsm.py
│   ├── test_implied_move.py
│   ├── test_event_vol.py
│   ├── test_historical.py
│   ├── test_skew.py
│   ├── test_gamma.py
│   ├── test_monte_carlo.py
│   ├── test_strategies.py
│   └── test_scoring.py
└── requirements.txt

---

## 3. Dependencies

yfinance>=0.2.31
pandas>=2.0
numpy>=1.24
scipy>=1.11
matplotlib>=3.7
seaborn>=0.12
jinja2>=3.1
pytest>=7.0
flake8>=6.0

No QuantLib. No py_vollib. BSM is implemented inline.

---

## 4. Module Specifications (Updated)

### 4.1 config.py — Central Configuration

TICKER: str = "NVDA"
HISTORY_YEARS: int = 5
MC_SIMULATIONS: int = 100_000

# Strike filtering
MONEYNESS_LOW: float = 0.80
MONEYNESS_HIGH: float = 1.20

# Liquidity filters
MIN_OI: int = 100
MAX_SPREAD_PCT: float = 0.05

# Slippage
SLIPPAGE_PCT: float = 0.10

# Calendar strategy
CALENDAR_LONG_MIN_DTE: int = 30

# Holding behavior
HOLD_TO_EXPIRY: bool = False

# IV scenarios
IV_SCENARIOS: dict = {
    "base_crush": "collapse_to_back",
    "hard_crush": 0.35,
    "expansion": -0.10,
}

# Vol-of-vol shocks
VOL_SHOCKS: list = [-10, -5, 5, 10]

# Scoring weights
SCORING_WEIGHTS: dict = {
    "ev": 0.4,
    "convexity": 0.3,
    "cvar": 0.2,
    "robustness": 0.1,
}

# GEX
GEX_RANGE_PCT: float = 0.05

# Risk-free rate
RISK_FREE_RATE: float = 0.05

# Dividend yield
DIVIDEND_YIELD: float = 0.0003

---

### 4.2 data/filters.py — Data Cleaning & Filtering (Updated Slippage)

apply_slippage(chain, slippage_pct=0.10)

execution_price = mid ± (0.5 * spread * slippage_pct)

This crosses slippage_pct of half-spread, not the full spread.

---

### 4.3 analytics/event_vol.py — Event Variance Extraction (Upgraded)

Goal: isolate pure event variance using a pre-event variance proxy.

If two back expiries are available (back1, back2):

1) Compute t_front, t_back1, t_back2 in years (busdays/252).
2) Interpolate back1/back2 variance to match (t_front - dt) maturity.

pre_event_var_proxy = linear_interpolation(
    x1=t_back1, y1=back1_iv^2,
    x2=t_back2, y2=back2_iv^2,
    x_target=(t_front - dt)
)

event_var = (t_front * front_iv^2 - (t_front - dt) * pre_event_var_proxy) / dt

If only one back expiry is available:
- Use current single-point formula with back_iv
- Flag: "Single-point term structure assumption"

If event_var < 0: clamp to 0 and warn.

---

### 4.4 simulation/monte_carlo.py — Lognormal Simulation (Corrected)

Corrected lognormal drift:

Z ~ N(0,1)
sigma_1d = event_vol / sqrt(252)
move = exp(-0.5 * sigma_1d^2 + sigma_1d * Z) - 1

Ensures E[S_T] = S_0.

Add Monte Carlo sanity check:
- mean of simulated moves approx 0
- std approx target sigma_1d
- log warning if deviation > 3%

---

### 4.5 strategies/payoff.py — Holding Behavior (Global Toggle)

Global config flag:

HOLD_TO_EXPIRY = False (default)

If False:
- All strategies reprice using post-event IV
- Remaining T = time from post-earnings open to expiry
- Use strategy_payoff_with_iv for all structures

If True:
- Use payoff at expiry

---

### 4.6 analytics/gamma.py — GEX Outputs (Dual)

Compute both:
- net_gex (signed, assumes dealer short options)
- abs_gex (sum of absolute gex by strike)

Reporting logic:

If abs_gex large and net_gex near zero:
"Positioning concentrated but direction uncertain"

Retain regime classification but include ambiguity warning.

---

### 4.7 strategies/scoring.py — Convexity Metric (Upgraded)

Replace prior convexity definition with:

Convexity =
E[P&L | top 10% outcomes] / |E[P&L | bottom 10% outcomes]|

This captures right-tail asymmetry directly.

---

### 4.8 strategies/scoring.py — Capital Inefficiency Flag (New)

Before ranking, compute:

capital_ratio = max_loss / expected_move_dollar

expected_move_dollar = implied_move * spot * 100

If capital_ratio > 2:
flag strategy as "capital inefficient"

Add a column in ranked output for this flag.

---

### 4.9 main.py — Console Snapshot (Updated)

Add to console summary:

ImpliedMove / P75 historical

---

## 5. Additional Changes Summary (Nine Upgrades)

1) Event vol uses interpolated pre-event variance proxy when two back expiries exist.
2) Lognormal simulation includes drift correction to preserve mean.
3) Global HOLD_TO_EXPIRY toggle; default is False and all strategies reprice post-event.
4) GEX reports net and absolute values; flags ambiguity.
5) Convexity metric redefined using top/bottom 10% outcomes.
6) Slippage model crosses slippage_pct of half-spread, not full spread.
7) Console snapshot includes implied move / P75 historical.
8) Capital inefficiency flag based on max loss vs expected move dollar.
9) Monte Carlo sanity check: warn if mean/std deviate > 3%.

---

## 6. Acceptance Criteria (Updated)

- [ ] Event vol uses interpolation when two back expiries available; single-point assumption flagged otherwise.
- [ ] Lognormal simulation uses drift correction.
- [ ] HOLD_TO_EXPIRY default False; all strategies reprice using post-event IV.
- [ ] GEX reports both net and absolute; ambiguity warning included.
- [ ] Convexity metric uses top/bottom 10% outcomes ratio.
- [ ] Slippage uses half-spread adjustment.
- [ ] Console snapshot prints implied move / P75 historical.
- [ ] Capital inefficiency flag present in ranked strategies.
- [ ] Monte Carlo sanity check logs warning if mean/std off by > 3%.

All other acceptance criteria remain as in v1.
