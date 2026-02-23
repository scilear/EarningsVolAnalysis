# Tech-Spec: NVDA Earnings Volatility & Options Structure Analysis Engine (v3)

Created: 2026-02-23
Status: Completed
Target: NVDA (hardcoded MVP), parameterized event date

---

## 1. Overview

### Problem Statement

Options traders need a quantitative engine that isolates pure earnings event
volatility, compares implied vs realized moves, and ranks option structures by
risk-adjusted expected value, not just probability of profit. Existing tools
either oversimplify (ignoring IV regime uncertainty, skew distortion, tail
risk) or require expensive platforms.

### Solution

A self-contained Python CLI application that fetches live options/price data via
yfinance, runs a full analytical pipeline (event vol extraction, skew analysis,
GEX, Monte Carlo simulation under multiple IV regimes), scores 8 option
structures on a composite metric, and outputs a self-contained HTML report with
embedded plots.

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

## 2.5 Implementation Tasks

- [x] Create package structure and config constants
- [x] Implement data loaders and filtering utilities
- [x] Build analytics modules (BSM, implied move, event vol, skew, GEX)
- [x] Add Monte Carlo simulation with validation
- [x] Implement strategy construction, payoff, and scoring
- [x] Generate plots and HTML report output
- [x] Add CLI entrypoint and console diagnostics
- [x] Write unit tests for core modules and edge cases

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

## 4. Module Specifications (Updated for v3)

### 4.1 config.py -- Central Configuration

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

# Convexity guard
CONVEXITY_CAP: float = 10.0
CONVEXITY_EPS: float = 1e-6

# GEX
GEX_RANGE_PCT: float = 0.05

# Risk-free rate
RISK_FREE_RATE: float = 0.05

# Dividend yield
DIVIDEND_YIELD: float = 0.0003

---

### 4.2 data/filters.py -- Data Cleaning & Filtering (Slippage)

apply_slippage(chain, slippage_pct=0.10)

execution_price = mid +- (0.5 * spread * slippage_pct)

This crosses slippage_pct of half-spread, not the full spread.

---

### 4.3 analytics/event_vol.py -- Event Variance Extraction (Structurally Correct)

Goal: isolate pure event variance using a pre-event variance proxy.

If two back expiries are available (back1, back2):

1) Compute t_front, t_back1, t_back2 in years (busdays/252).
2) Interpolate total variance (not IV^2) to match (t_front - dt).

TV = T * IV^2

Important: TV_pre represents total variance (T * IV^2). It is not an
annualized variance rate. Do not multiply it again by maturity in the
subtraction formula.

TV_pre = linear_interpolation(
    x1=t_back1, y1=t_back1 * back1_iv^2,
    x2=t_back2, y2=t_back2 * back2_iv^2,
    x_target=(t_front - dt)
)

event_var = (t_front * front_iv^2 - TV_pre) / dt

If only one back expiry is available:
- Use current single-point formula with back_iv
- Flag: "Single-point term structure assumption"

Negative event variance handling:

If event_var < 0:
- Store raw_event_var
- Compute ratio = abs(raw_event_var) / front_iv^2
- Add to report: raw_event_var, ratio, warning level (mild/severe)
- Clamp to 0 for simulation only

---

### 4.4 simulation/monte_carlo.py -- Lognormal Simulation (Validated)

Corrected lognormal drift:

Z ~ N(0,1)
sigma_1d = event_vol / sqrt(252)
move = exp(-0.5 * sigma_1d^2 + sigma_1d * Z) - 1

Ensures E[S_T] = S_0.

Validation layer:
- mean of simulated moves approx 0
- std approx target sigma_1d
- if student-t used: skew sign matches fitted skew
- warn if any violation > 3% tolerance

Do not increase simulation count.

If any validation fails: log warning, continue execution, do not abort.

---

### 4.5 strategies/payoff.py -- Holding Behavior & Repricing Rules

Global config flag:

HOLD_TO_EXPIRY = False (default)

If False:
- All strategies reprice using post-event IV
- Remaining T = max((busdays(expiry) - 1) / 252, epsilon)
- Use strategy_payoff_with_iv for all structures
- Apply exit slippage using same model as entry

epsilon = 1e-6

If True:
- Use payoff at expiry

Leg-level IV repricing rules by expiry:

Base Crush
- Front expiry legs -> back_iv
- Back expiry legs -> unchanged

Hard Crush
- Front expiry -> front_iv * (1 - 0.35)
- Back expiry -> back_iv * (1 - 0.10)

Expansion
- Front expiry -> front_iv * 1.10
- Back expiry -> back_iv * 1.05

Do not apply flat IV shift across all legs.
Post-event skew is frozen. 25d Risk Reversal (RR) and 25d Butterfly (BF) are
assumed unchanged. IV adjustments are parallel level shifts applied per expiry,
not skew re-shaping. Do not recompute skew, shift wings differently than ATM,
or re-solve for new 25d strikes.

IV scenario application (explicit leg logic):

```python
for leg in strategy.legs:

    if leg.expiry == front_expiry:
        if scenario == "base_crush":
            post_iv = back_iv
        elif scenario == "hard_crush":
            post_iv = front_iv * (1 - 0.35)
        elif scenario == "expansion":
            post_iv = front_iv * 1.10

    else:  # back expiry leg
        if scenario == "base_crush":
            post_iv = back_iv
        elif scenario == "hard_crush":
            post_iv = back_iv * (1 - 0.10)
        elif scenario == "expansion":
            post_iv = back_iv * 1.05
```

---

### 4.6 analytics/gamma.py -- GEX Outputs (Dual)

Compute both:
- net_gex (signed, assumes dealer short options)
- abs_gex (sum of absolute gex by strike)

Reporting logic:
- Include note: "GEX sign assumes dealers net short options. Interpret regime
  directionally."
- If abs_gex large and net_gex near zero: "Positioning concentrated but
  direction uncertain"

Do not infer dealer positioning beyond this assumption.

---

### 4.7 strategies/scoring.py -- Convexity Metric (Stabilized)

Convexity =
E[P&L | top 10% outcomes] / |E[P&L | bottom 10% outcomes]|

Guard:
- If denominator < CONVEXITY_EPS, cap convexity at CONVEXITY_CAP
- Log stabilization event

---

### 4.8 strategies/scoring.py -- Capital Efficiency (Risk-Aware)

Compute:

expected_move_dollar = max(implied_move, historical_p75) * spot * 100

capital_ratio = max_loss / expected_move_dollar

Add classification:
- defined_risk
- undefined_risk

If undefined_risk:
- Automatic inefficiency flag
- Score penalty (subtract 10 percent of normalized score)

Undefined risk is defined as:
- max_gain is finite AND
- max_loss is None or infinite

Remove hard threshold of 2x. Rank relative capital ratios across strategies.

---

### 4.9 main.py -- Console Snapshot (Updated)

Add to console summary:
- Vol Diagnostics group:
  - ImpliedMove
  - Historical P75
  - ImpliedMove / P75
  - EventVol
  - EventVol / FrontIV
- Microstructure Diagnostics group:
  - Slippage sensitivity (EV delta)
  - GEX regime

---

### 4.10 reports/reporter.py -- Slippage Sensitivity & Event Vol Diagnostics

Add report sections:
- Event variance diagnostics: raw_event_var, ratio, warning level
- EV under base slippage and 2x slippage

Compute EV_2x by recomputing entry/exit pricing with slippage_pct * 2. Do not
re-run full Monte Carlo for this sensitivity.

---

## 5. Additional Changes Summary (v3)

1) Event vol uses interpolated total variance when two back expiries exist.
2) Negative event variance diagnostics included and reported.
3) Repricing rules applied by expiry and leg; T_remaining subtracts 1 day.
4) Exit slippage applied when HOLD_TO_EXPIRY is False.
5) Convexity metric stabilized with denominator guard and cap.
6) Capital efficiency is risk-aware and relative, with undefined-risk penalty.
7) GEX reporting clarifies short-option assumption, no dealer inference.
8) Slippage sensitivity included (base and 2x).
9) Monte Carlo validation layer added with 3% tolerance checks.
10) Post-event skew assumed unchanged; only level shifts applied.
11) Snapshot adds EventVol / FrontIV ratio.
12) Expanded edge case tests.

---

## 6. Edge Case Tests (Expanded)

Add tests for:
- event_var negative
- missing second back expiry
- zero liquidity after filtering
- IV = 0
- no 25d strike found
- front expiry = 0 DTE edge case
- undefined-risk strategy detection
- convexity denominator near zero

---

## 7. Acceptance Criteria (Updated)

- [ ] Event vol uses total variance interpolation when two back expiries exist;
      single-point assumption flagged otherwise.
- [ ] Negative event variance diagnostics logged and reported; clamped for
      simulation only.
- [ ] Lognormal simulation uses drift correction and validation checks.
- [ ] Monte Carlo validation failures log warning and continue execution.
- [ ] HOLD_TO_EXPIRY default False; all strategies reprice using post-event IV.
- [ ] Time remaining uses max((busdays(expiry) - 1) / 252, epsilon).
- [ ] Exit slippage applied when HOLD_TO_EXPIRY is False.
- [ ] Repricing uses expiry-specific base/hard/expansion rules.
- [ ] Post-event skew (RR, BF) assumed unchanged; level shifts only.
- [ ] GEX reports both net and absolute; assumption note included.
- [ ] Convexity metric uses top/bottom 10% outcomes and CONVEXITY_CAP/EPS.
- [ ] Capital efficiency uses expected_move_dollar with undefined-risk penalty.
- [ ] Slippage sensitivity EV reported at base and 2x slippage (no re-run MC).
- [ ] Console snapshot prints implied move / P75 historical and EventVol /
      FrontIV.
- [ ] Edge case tests implemented for v3 list.

All other acceptance criteria remain as in v1.

---

## 8. Explicit Exclusions (Stage-Appropriate)

- No dynamic skew modeling
- No stochastic vol
- No historical replay backtesting
- No dynamic slippage microstructure model
- No 500k simulation escalation
- No SABR
- No broker API
- No rate curve fetch

(End of file)

## Review Notes
- Adversarial review completed
- Findings: 10 total, 10 fixed, 0 skipped
- Resolution approach: auto-fix
