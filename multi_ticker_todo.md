# Multi-Ticker Calibration Checklist

The pipeline now accepts `--ticker <SYMBOL>` (default: `NVDA`).
Most analytics are market-data-relative and transfer to any liquid single-name
with weekly options.  The items below require per-ticker review before trusting
the output.

---

## 1. `DIVIDEND_YIELD` — **must review per ticker**

**Location:** `config.py`
**Current value:** `0.0003` (~0.03% — NVDA's actual yield as of early 2026)

Dividend yield enters BSM pricing and all Greeks.  Errors here create
systematic mispricing of puts relative to calls.

| Example ticker | Approx yield |
|---|---|
| NVDA | ~0.03% |
| AMZN, META, GOOG | ~0% |
| MSFT, AAPL | ~0.6–0.9% |
| SPY | ~1.3% |
| XOM | ~3–4% |

**Action:** Add a `--div-yield` CLI flag, or build a small lookup table in
config keyed by ticker.  Consider fetching it automatically from
`yf.Ticker(ticker).info["dividendYield"]`.

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

## 3. `GEX_LARGE_ABS` — **OI-scale dependent**

**Location:** `config.py`
**Current value:** `1e9` ($1 billion)
**Comment in code:** "calibrate to OI scale if needed"

The GEX "large gamma" threshold is used in regime classification.  NVDA has
one of the largest OI footprints in the options market.  A $1B threshold
will never trigger for a mid-cap name.

**Action:** Either make this a percentage of market-cap or of total-chain OI,
or set it per-ticker.  A reasonable heuristic: ~0.5% of market cap.

---

## 4. `BACKSPREAD_MIN_WING_WIDTH_PCT` — **converted; verify for low-priced tickers**

**Location:** `config.py`
**Current value:** `0.014` (1.4% of spot — derived from $2.50 / $175 NVDA)

Already converted from a dollar amount to a percentage of spot, so it
scales automatically.  However, on tickers whose option chain has wide
strike spacing relative to spot (e.g., a $30 stock with $2.50-wide strikes),
the 1.4% threshold may exclude all viable long strikes.

**Action:** Verify that at least one long strike is found in the backspread
builder for new tickers before concluding the strategy is structurally
unavailable.  Reduce to `0.005`–`0.010` if the chain is coarsely spaced.

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

## 6. `IV_SCENARIOS` — scenario magnitudes

**Location:** `config.py`
**Current values:** `hard_crush: front=-0.35, back=-0.10`; `expansion: front=+0.10, back=+0.05`

These shock sizes are representative of NVDA-class earnings events.  Very
high-vol names (IV > 150% pre-event) or low-vol names (IV < 30%) may see
larger or smaller realized crushes.

**Action:** Low priority for strategy ranking (the `base_crush` scenario
dominates); review if you want realistic P&L estimates in the output.

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

## 8. Liquidity filters — `MIN_OI` and `MAX_SPREAD_PCT`

**Location:** `config.py`
**Current values:** `MIN_OI = 100`, `MAX_SPREAD_PCT = 0.05` (5%)

NVDA is extremely liquid.  For less-liquid names, these thresholds may
filter out the entire chain.

**Action:** Reduce `MIN_OI` to `10–50` and loosen `MAX_SPREAD_PCT` to
`0.10–0.15` for mid-cap names.  Consider making these CLI flags.

---

## 9. Package name `nvda_earnings_vol`

The Python package is still named `nvda_earnings_vol/`.  This is purely
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
