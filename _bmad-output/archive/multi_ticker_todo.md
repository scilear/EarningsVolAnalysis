# Multi-Ticker Calibration Checklist

The pipeline now accepts `--ticker <SYMBOL>` (default: `NVDA`).
Most analytics are market-data-relative and transfer to any liquid single-name
with weekly options.  The items below require per-ticker review before trusting
the output.

---

## 1. `DIVIDEND_YIELD` — ✅ **auto-fetched**

**Location:** `data/loader.py: get_dividend_yield()`
Fetched live from `yf.Ticker(ticker).info["dividendYield"]`; falls back
to 0.0 for non-payers.  Threaded as `div_yield` kwarg through all BSM
calls (skew, gamma, payoff, post-event calendar, Greek enrichment).

---

## 2. `POST_EVENT_CALENDAR_LONG_IV_COMPRESSION` — **empirically NVDA-derived**

**Location:** `config.py`
**Current value:** `0.97` (3% further crush after event settlement)
**Comment in code:** "conservative estimate from NVDA historical surfaces"

This parameter governs how much the back-leg IV compresses during the
post-event holding period.  High-beta / high-vol names (e.g., SMCI, MSTR)
may retain more IV; mega-cap defensives may crush faster.

**Action:** Back-test on 4–6 earnings cycles for each new ticker before
using this strategy.  The parameter is straightforward to override once
you have historical surface data.

---

## 3. `GEX_LARGE_ABS` — ✅ **auto-calibrated**

**Location:** `calibration.py: _gex_large_abs()`
Set to 0.5% of market cap via `yf.Ticker(ticker).info["marketCap"]`.
Falls back to `config.GEX_LARGE_ABS` if fetch fails.

---

## 4. `BACKSPREAD_MIN_WING_WIDTH_PCT` — ✅ **auto-calibrated**

**Location:** `calibration.py: _wing_width_pct()`
Derived from the minimum strike spacing in the raw ATM-region chain
divided by spot, clamped to [0.005, 0.05].  Passed as `wing_width_pct`
kwarg to `build_call/put_backspread()`.  Falls back to
`config.BACKSPREAD_MIN_WING_WIDTH_PCT` on failure.

---

## 5. `CALENDAR_BACK3_POST_EVENT_IV_FACTOR` and `CALENDAR_BACK1_POST_EVENT_IV_FACTOR`

**Location:** `config.py`
**Current values:** `0.92` / `0.85`

These simulate post-event IV crush on the short (front) leg of a calendar.
The crush magnitude depends on how much of the back-leg vol is "event premium"
vs. structural vol.  Names with smaller earnings surprise distributions
(e.g., large-cap defensives) tend to crush harder; speculative names less so.

**Action:** Low priority — these factors affect scenario P&L magnitude but
not strategy selection.  Review if the post-event calendar appears
systematically over- or under-valued.

---

## 6. `IV_SCENARIOS` — ✅ **auto-calibrated (hard_crush and expansion)**

**Location:** `calibration.py: calibrate_iv_scenarios()`
`hard_crush` front derived as `sqrt(1 - evr) - 1` (removes the event
variance component from front IV); back scales with `max(0.03, evr×0.12)`.
`expansion` scales inversely with event dominance.  `base_crush` is
unchanged (already market-data-relative).  Mutates `config.IV_SCENARIOS`
in-place so `payoff.py` picks up the updated values without API changes.

---

## 7. `HISTORY_YEARS` — earnings history depth

**Location:** `config.py`
**Current value:** `5` years

NVDA has 20+ earnings observations in 5 years (quarterly).  Newly public
companies, spinoffs, or names that changed business model may have fewer
relevant observations.

**Action:** Consider reducing to `3` for tickers with limited relevant
history.  Also check that `get_earnings_dates()` returns enough dates to
compute a meaningful P75 — the pipeline warns if fewer than 4 are found.

---

## 8. Liquidity filters — ✅ **auto-calibrated**

**Location:** `calibration.py: _min_oi()` and `_max_spread_pct()`
`min_oi` = 20th-pct OI in ATM ±15% region, clamped [10, 200].
`max_spread_pct` = 65th-pct bid-ask spread% in ATM ±15%, clamped [0.03, 0.20].
Both derived from the raw (pre-filter) front chain and passed to
`_load_filtered_chain()` for all expiries.  Fall back to config defaults.

---

## 9. Package name `event_vol_analysis`

The Python package is still named `event_vol_analysis/`.  This is purely
cosmetic but worth renaming to something generic (e.g., `earnings_vol`) if
the tool will be used regularly for multiple tickers.  All internal imports
use the full dotted path, so a rename requires a global search-and-replace.

---

## What does NOT need recalibration

The following are market-data-relative and transfer without modification:

- Strike moneyness filter (±20% of spot)
- All BSM formulas and Greeks
- Event variance extraction logic
- Implied move computation
- Regime classification axes
- Backspread entry gates (IV ratio, event variance ratio, implied move vs P75)
- Post-event calendar entry gate (days after event, IV ratio, min short DTE)
- Strategy scoring weights (EV, CVaR, convexity, robustness)
- Monte Carlo simulation
- DTE windows for back1, back3 selection (21–45 days)
