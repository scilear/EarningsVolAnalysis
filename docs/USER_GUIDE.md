# NVDA Earnings Volatility Analysis - User Guide

> **Quick Start:** `python -m nvda_earnings_vol.main --test-data --output reports/my_report.html`

---

## Overview

**NVDA Earnings Volatility Analysis** is an institutional-grade options analytics tool designed to help traders make informed decisions around earnings events. It analyzes implied volatility, historical price moves, dealer positioning, and term structure to generate actionable trading recommendations.

### What It Does
- **Extracts event-implied volatility** from option term structure
- **Classifies market regime** (vol pricing, gamma exposure, term structure)
- **Scores trading strategies** based on EV, convexity, tail risk, and robustness
- **Generates comprehensive HTML reports** with regime analysis and trade recommendations

---

## Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [Command Line Options](#command-line-options)
4. [Understanding the Report](#understanding-the-report)
5. [Regime Classification](#regime-classification)
6. [Strategy Recommendations](#strategy-recommendations)
7. [Test Data Mode](#test-data-mode)
8. [Configuration](#configuration)
9. [Troubleshooting](#troubleshooting)

---

## Installation

### Prerequisites
- Python 3.10+
- pip or conda

### Setup

```bash
# Clone or navigate to the project
cd EarningsVolAnalysis

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or: .venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### Dependencies
- `yfinance` - Market data
- `pandas` - Data manipulation
- `numpy` - Numerical computations
- `scipy` - Statistical functions
- `jinja2` - Report templating
- `matplotlib` - Visualization

---

## Quick Start

### Option 1: Test Mode (No Market Data Required)

Generate a report using synthetic test data:

```bash
python -m nvda_earnings_vol.main --test-data --output reports/test_report.html
```

This generates a complete report with realistic synthetic data, useful for:
- Validating the pipeline without market access
- Understanding report structure
- Testing different market scenarios

### Option 2: Live Mode (Requires Market Data)

Generate a report with live market data:

```bash
python -m nvda_earnings_vol.main --event-date 2026-03-15 --output reports/nvda_report.html
```

**Note:** Run during market hours for best results. Pre/post-market data may have stale quotes.

---

## Command Line Options

### Core Options

| Option | Description | Default |
|--------|-------------|---------|
| `--event-date` | Earnings event date (YYYY-MM-DD) | Auto-detect from yfinance |
| `--output` | Output HTML report path | `reports/nvda_earnings_report.html` |
| `--cache-dir` | Directory for cached option chains | `data/cache` |
| `--use-cache` | Use cached option chains when available | `false` |
| `--refresh-cache` | Force refresh of cached data | `false` |
| `--seed` | Random seed for Monte Carlo | `none` |

### Test Data Options

| Option | Description | Default |
|--------|-------------|---------|
| `--test-data` | Use synthetic test data instead of live | `false` |
| `--test-scenario` | Test scenario to use | `baseline` |
| `--test-data-dir` | Load test data from directory | `none` |
| `--save-test-data` | Save generated test data to directory | `none` |

### Examples

```bash
# Basic live report
python -m nvda_earnings_vol.main --event-date 2026-03-15

# Use cached data (faster, but may be stale)
python -m nvda_earnings_vol.main --use-cache --event-date 2026-03-15

# Test high volatility scenario
python -m nvda_earnings_vol.main --test-data --test-scenario high_vol

# Generate reproducible results
python -m nvda_earnings_vol.main --test-data --seed 42

# Save test data for later analysis
python -m nvda_earnings_vol.main --test-data --save-test-data data/test_sets/baseline
```

---

## Understanding the Report

The HTML report contains several key sections:

### 1. Executive Summary
- **Spot Price**: Current NVDA price
- **Event Date**: Target earnings date
- **Expiries**: Front and back month options used
- **Key Metrics**: Implied move, historical P75, event volatility

### 2. Regime Classification Header
Displays the composite market regime with confidence score.

### 3. Volatility Diagnostics Table

| Metric | Description |
|--------|-------------|
| Implied Move | Market's expected move (from ATM straddle) |
| Historical P75 | 75th percentile of historical earnings moves |
| Event Vol | Isolated event-implied volatility |
| Event Vol / Front IV | Ratio indicating event premium |

### 4. Term Structure Analysis

| Metric | Description |
|--------|-------------|
| Front IV / Back IV | Term structure slope |
| Event Variance Ratio | % of front variance attributed to event |
| Interpolation Method | How term structure was calculated |

### 5. Dealer Positioning (Gamma)

| Metric | Description |
|--------|-------------|
| Net GEX | Net dealer gamma exposure (positive = long gamma) |
| Abs GEX | Total gamma exposure magnitude |
| Gamma Flip | Price level where dealers flip from long to short gamma |
| Top Gamma Strikes | Strikes with highest gamma concentration |

### 6. Historical Distribution Shape

| Metric | Description |
|--------|-------------|
| Mean Abs Move | Average absolute earnings move |
| Median Abs Move | Median absolute earnings move |
| Skewness | Asymmetry of return distribution |
| Kurtosis | Tail fatness (>3 = fat tails) |

### 7. Strategy Rankings

Table of strategies ranked by composite score:

| Column | Description |
|--------|-------------|
| Strategy | Strategy name (long_call, iron_condor, etc.) |
| EV | Expected value across Monte Carlo simulations |
| Convexity | Upside potential ratio (95th/50th percentile) |
| CVaR | Conditional value at risk (average of worst 5%) |
| Robustness | Strategy stability across IV scenarios |
| Score | Weighted composite score |

### 8. Strategy Trade Sheets

For top strategies, detailed execution information:
- **Legs**: Exact strikes, expiries, quantities
- **Entry Prices**: Mid-market prices
- **Greeks**: Delta, gamma, vega, theta per leg
- **Breakevens**: Upper and lower breakeven points
- **Capital**: Max loss, max gain, capital required

### 9. Alignment Heatmap

Visual representation of how well each strategy aligns with the current regime across four axes:
- **Gamma Alignment**: Directional gamma vs regime
- **Vega Alignment**: Volatility exposure vs regime
- **Convexity Alignment**: Tail benefit vs regime
- **Risk Alignment**: Defined vs undefined risk preference

---

## Regime Classification

The system classifies market conditions into structured regimes:

### Vol Pricing Regime

| Classification | Condition | Interpretation |
|----------------|-----------|----------------|
| Tail Underpriced | Implied Move / P75 < 0.85 | Options are cheap relative to history |
| Fairly Priced | 0.85 ≤ Ratio ≤ 1.10 | Options fairly valued |
| Tail Overpriced | Ratio > 1.10 | Options are expensive |

### Event Structure Regime

| Classification | Event Variance Ratio | Interpretation |
|----------------|---------------------|----------------|
| Pure Binary Event | > 70% | Most front-month variance is event-driven |
| Event-Dominant | 50-70% | Significant event component |
| Distributed Volatility | < 50% | Volatility spread across time |

### Term Structure Regime

| Classification | Front IV - Back IV | Interpretation |
|----------------|-------------------|----------------|
| Extreme Front Premium | > 20% | Severe event pricing |
| Elevated Front Premium | 10-20% | Notable event premium |
| Normal Structure | -5% to 10% | Typical term structure |
| Inverted Structure | < -5% | Back month more expensive |

### Gamma Regime

| Classification | Condition | Interpretation |
|----------------|-----------|----------------|
| Amplified Move Regime | Net GEX < 0, |GEX/GEX| > 0.7 | Dealers short gamma → volatility amplification |
| Pin Risk Regime | Net GEX > 0, |GEX/GEX| > 0.7 | Dealers long gamma → price suppression |
| Neutral Gamma | Otherwise | No strong gamma effects |

### Composite Regime

| Composite | Conditions | Trading Implication |
|-----------|------------|---------------------|
| Convex Breakout Setup | Tail Underpriced + Amplified Gamma + High EV Ratio | Favor long volatility |
| Premium Harvest Setup | Tail Overpriced + Pin Risk | Favor short volatility |
| Mixed / Transitional | Otherwise | No strong directional bias |

---

## Strategy Recommendations

### Strategies Analyzed

| Strategy | Type | Risk Profile |
|----------|------|--------------|
| Long Call | Directional | Unlimited upside, limited downside |
| Long Put | Directional | Limited upside, limited downside |
| Long Straddle | Long Vol | Unlimited upside both directions |
| Long Strangle | Long Vol | Lower cost, wider breakevens |
| Bull Put Spread | Income | Defined risk, neutral-to-bullish |
| Iron Condor | Income | Defined risk, range-bound |
| Calendar Spread | Time Decay | Defined risk, flat-to-bullish |

### Scoring Methodology

Each strategy receives a composite score (0-1) based on:

| Component | Weight | Description |
|-----------|--------|-------------|
| Expected Value | 40% | Mean P&L across simulations |
| Convexity | 30% | Upside potential ratio |
| CVaR | 20% | Tail risk (worst 5% average) |
| Robustness | 10% | Stability across IV scenarios |

**Risk Penalty:** Undefined-risk strategies receive a 10% score reduction.

---

## Test Data Mode

### Available Scenarios

| Scenario | Description | Use Case |
|----------|-------------|----------|
| `baseline` | Balanced market with normal vol structure | Default testing |
| `high_vol` | Elevated vol with pronounced skew | Stress testing |
| `low_vol` | Complacent market with flat skew | Low-vol environment |
| `gamma_unbalanced` | Strong positive gamma positioning | Pin risk analysis |
| `term_inverted` | Inverted term structure | Unusual conditions |

### Using Test Data

```bash
# Generate baseline report
python -m nvda_earnings_vol.main --test-data

# Test high volatility scenario
python -m nvda_earnings_vol.main --test-data --test-scenario high_vol

# Save test data for reuse
python -m nvda_earnings_vol.main --test-data --save-test-data data/test_sets/scenario1

# Load previously saved test data
python -m nvda_earnings_vol.main --test-data-dir data/test_sets/scenario1
```

---

## Configuration

Key parameters in `nvda_earnings_vol/config.py`:

### Filters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MONEYNESS_LOW` | 0.80 | Minimum strike/spot ratio |
| `MONEYNESS_HIGH` | 1.20 | Maximum strike/spot ratio |
| `MIN_OI` | 100 | Minimum open interest |
| `MAX_SPREAD_PCT` | 0.05 | Maximum bid-ask spread % |

### Simulation

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MC_SIMULATIONS` | 100,000 | Monte Carlo paths |
| `HISTORY_YEARS` | 5 | Years of historical data |

### Scoring

| Parameter | Default | Description |
|-----------|---------|-------------|
| `SCORING_WEIGHTS` | See below | Component weights |

```python
SCORING_WEIGHTS = {
    "ev": 0.4,
    "convexity": 0.3,
    "cvar": 0.2,
    "robustness": 0.1,
}
```

---

## Troubleshooting

### Common Errors

#### "Market appears closed or data unavailable"
- **Cause:** Running outside market hours
- **Solution:** Run during market hours (9:30 AM - 4:00 PM ET) or use `--test-data`

#### "Insufficient expiries after event date"
- **Cause:** No liquid options expiring after earnings
- **Solution:** Check that earnings date is correct and options exist

#### "No options remain after filtering"
- **Cause:** Filters too strict for current data
- **Solution:** Relax `MIN_OI` or `MAX_SPREAD_PCT` in config

#### "Event date must be in the future"
- **Cause:** Using past event date in live mode
- **Solution:** Use a future date or use `--test-data`

### Cache Issues

#### Stale Cache Data
```bash
# Force refresh
python -m nvda_earnings_vol.main --use-cache --refresh-cache
```

#### Clear Cache
```bash
rm -rf data/cache/*
```

### Performance Tips

1. **Use caching** when running multiple times:
   ```bash
   python -m nvda_earnings_vol.main --use-cache
   ```

2. **Reduce simulations** for faster results:
   ```python
   # In config.py
   MC_SIMULATIONS = 50_000
   ```

3. **Use test mode** for development/testing:
   ```bash
   python -m nvda_earnings_vol.main --test-data
   ```

---

## Interpreting Results

### Good Setup Indicators

- **High EV + High Convexity** → Favorable risk/reward
- **Tail Underpriced + Amplified Gamma** → Long vol opportunity
- **High Alignment Score** → Strategy matches regime

### Warning Signs

- **Negative Event Variance** → Term structure anomaly
- **Low Robustness** → Strategy sensitive to IV changes
- **High Slippage Sensitivity** → Execution matters greatly

### Decision Framework

1. **Check Regime** → Is vol cheap/fair/expensive?
2. **Review Term Structure** → How much event premium?
3. **Analyze Gamma** → Will dealers amplify or suppress?
4. **Compare Strategies** → Which has best risk-adjusted return?
5. **Verify Alignment** → Does strategy fit the regime?

---

## Support

For issues or questions:
1. Check this documentation
2. Review the technical reference
3. Examine log output for errors
4. Use `--test-data` mode to isolate issues

---

*Last updated: February 2026*
