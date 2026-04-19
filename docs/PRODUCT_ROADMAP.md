# EarningsVolAnalysis — Product Roadmap & Feedback Log

Owner: Fab (Vol Specialist)
Last updated: 2026-04-19

This file is the single source of truth for product direction, open tasks, and accumulated feedback
on the EarningsVolAnalysis tool. It is maintained across sessions.

---

## Product Vision

An earnings-season workflow tool that:
1. Classifies the vol regime for any name before I touch the options chain
2. Surfaces the right structure universe given that regime (not a static menu)
3. Scores structures on a risk-adjusted basis so the ranking is actionable
4. Runs as a batch scan across a watchlist, not just one name at a time
5. Stores event history so workbook statistics accumulate and improve over time

Current state: useful regime classifier + strategy screener. Not yet an execution-ready playbook.

---

## Known Bugs (fix before trusting output)

### BUG-01 — Gamma alignment axis is permanently broken
- **File:** `nvda_earnings_vol/alignment.py`
- **Issue:** `compute_alignment()` reads `regime.get("gamma_bias", "neutral")` but
  `regime.py → classify_regime()` emits `gamma_regime`, not `gamma_bias`.
  The gamma alignment axis always returns 0.5 regardless of detected gamma regime.
- **Impact:** Alignment heatmap is misleading. The most important regime axis is silent.
- **Fix:** Map `gamma_regime` → `gamma_bias` in the bridge, or rename the key consistently.
- **Priority:** P0 — fix before using alignment scores in any decision

### BUG-02 — TICKER config is hardcoded to NVDA
- **File:** `nvda_earnings_vol/config.py` line 6: `TICKER: str = "NVDA"`
- **Issue:** Default ticker is NVDA. The CLI accepts `--ticker` but several internal defaults
  and calibration paths still assume NVDA.
- **Impact:** Running on other names (TSLA, MSFT, GOOGL) may produce NVDA-shaped assumptions.
- **Fix:** Audit `calibrate_ticker_params()` and test data generators to confirm they are
  ticker-agnostic or parametrized correctly.
- **Priority:** P0 for multi-name earnings season use

---

## Missing Structures (by priority)

### STRUCT-01 — Symmetric Butterfly [P0]
**Use case:** Regime = "Tail Overpriced" + I believe the stock pins near ATM post-event.
The iron condor is a weaker substitute — higher gamma exposure, no directional pin thesis.

Structure: BUY 1 ATM, SELL 2 at ±implied-move width, BUY 1 wing (calls or puts)
Entry gate: implied_move / historical_p75 > 1.10 (overpriced move)
Scoring difference vs IC: lower CVaR, lower gamma, lower capital efficiency — worth modeling separately.

### STRUCT-02 — Broken-Wing Butterfly (skip-strike) [P1]
**Use case:** Overpriced move + 55/45 directional lean. Collect a small credit in the high-
conviction direction, define risk on the other side.

Structure: Asymmetric butterfly — skip one strike on the wing side of your lean.
Example: Stock at 100, lean bullish, sell 2× 105, buy 100 + buy 115 (skip 110).
Result: credit on downside, small max loss on massive upside, profits in the 100–110 range.

### STRUCT-03 — Diagonal Spread [P1]
**Use case:** Directional thesis + want IV crush on front leg to finance the back.
Most useful in Pure Binary regime with extreme front premium (IV ratio > 1.6).

Structure: SELL front-month ATM or slightly OTM, BUY back-month ATM or same strike.
Distinct from calendar: the strikes differ (calendar is same-strike by definition).
Entry gate: event_variance_ratio > 0.70 AND iv_ratio > 1.40

### STRUCT-04 — Risk Reversal [P2]
**Use case:** Skew trade. When put skew is rich and I have a bullish directional thesis,
sell the OTM put, buy the OTM call. Lower vega than naked call.

Structure: SELL OTM put (delta ~0.25), BUY OTM call (delta ~0.25)
Entry gate: requires skew metric (25Δ RR) in the snapshot — not currently computed.
Blocker: need to add 25Δ risk reversal to the surface metrics pipeline.

### STRUCT-05 — Jade Lizard [P2]
**Use case:** High put skew name, no conviction on direction, but put premium is rich enough
to sell. No upside risk by construction.

Structure: SELL OTM put + SELL OTM call spread (e.g., sell 105c / buy 110c)
Credit received > width of call spread → no upside risk.
Entry gate: put_premium > call_spread_width (requires live chain data to verify at construction time)

### STRUCT-06 — 1×2 Ratio Spread (sell more) [P3]
**Use case:** Limited-move regime, collect premium. Opposite of backspread.
BUY 1 ATM, SELL 2 OTM. Credit at entry, tail risk if stock gaps hard.
Entry gate: implied_move / historical_p75 < 0.85 AND vol regime = Elevated (you want the premium)
Must flag as undefined risk.

---

## Modeling Improvements (by priority)

### MODEL-01 — Fat-tailed move distribution [P1]
**Current:** Log-normal MC (100k paths).
**Issue:** Earnings moves have gap risk and fatter tails than log-normal. EV calculations for
straddles, butterflies, and OTM structures are systematically distorted.
**Fix:** Replace log-normal with Laplace or a jump-diffusion mixture calibrated to historical
earnings move distribution for the name. The historical move data is already in the pipeline.

### MODEL-02 — Capital-normalize the EV ranking [P1]
**Current:** Single-contract EV. $50 EV on a $200 straddle vs $50 EV on a $15 call spread
are treated identically in the ranking table.
**Fix:** Add EV/premium_paid and EV/max_loss columns. Rank on capital-adjusted basis,
not raw dollar EV.

### MODEL-03 — Skew dynamics in IV scenarios [P2]
**Current:** Frozen skew across all IV scenarios (RR and butterfly constant post-event).
**Issue:** Post-event crush is not proportional across the smile. Put skew often normalizes
faster than call skew for beaten-down names. Broken-wing butterflies and risk reversals
are mispriced without this.
**Fix:** Add skew compression factors per scenario (similar to how `CALENDAR_BACK3_POST_EVENT_IV_FACTOR`
handles term structure compression).

### MODEL-04 — American option exercise / early assignment flag [P3]
**Current:** BSM everywhere (European exercise assumption).
**Issue:** For ITM short puts post-event, early assignment risk is real. Not modeled.
**Fix:** Flag positions where early assignment risk is non-trivial (deep ITM short puts,
short calls on high-dividend names). Do not need full American pricing — just a warning.

---

## Workflow / Infrastructure Improvements

### INFRA-01 — Multi-ticker batch mode [P1]
**Current:** One name at a time.
**Need:** Earnings season watchlist scan. Feed a CSV of tickers + event dates, get a regime
summary table + top structure per name.
**Reference:** `multi_ticker_todo.md` already exists — needs implementation.

### INFRA-02 — Earnings calendar auto-ingestion [P1]
**Current:** Event date must be specified manually via `--event-date`.
**Risk:** Manual date entry → wrong date → stale approval enters different vol regime.
This is the exact failure mode behind the XOP position (wrong vol environment, not caught
at gate).
**Fix:** Integrate an earnings calendar source (yfinance `calendar`, or Nasdaq API)
so the tool self-discovers the next event date for a given ticker.

### INFRA-03 — Portfolio notional limit enforcement [P2]
**Current:** No check. 15% options notional limit is a manual step.
**Fix:** Accept `--portfolio-value` flag. Compute proposed notional per structure at 1-contract
sizing. Flag which structures are within the 15% limit for a given portfolio size. This removes
a manual gate that can be forgotten.

### INFRA-04 — Automated realized-outcome backfill [P3]
**Current:** The event store is powerful but requires manual manifest seeding. No automated
post-event outcome capture.
**Fix:** After event date passes, automatically pull post-event close, compute realized move,
IV crush (from stored pre-event snapshot), and write to `realized_outcomes` table.

---

## What Works Well — Do Not Break

- Regime classification framework (vol pricing × event structure × term structure × gamma)
- IV scenario stress testing (base_crush / hard_crush / expansion) — maps to real vol outcomes
- Backspread entry conditions — 5-gate discipline is sound and matches actual criteria
- Post-event calendar — correctly uses a different IV compression factor than pre-event calendar
- HTML report structure — executive summary → regime → diagnostics → rankings → trade sheets

---

## Session Notes

### 2026-04-19 — Initial product review + TSLA test run (Fab)
- First pass assessment completed. Tool is useful as regime classifier + strategy screener.
- Test mode ran cleanly on TSLA (--ticker TSLA --test-data). Multi-ticker CLI works.
- BUG-01 (gamma alignment) confirmed: all alignment scores show 0.50 across every strategy.
- BUG-02 (NVDA hardcode) confirmed via config.py TICKER constant.
- All structure gaps (STRUCT-01 through STRUCT-06) identified from live options workflow perspective.

**TSLA test run output (baseline synthetic scenario):**
- Spot: 130.00 | Event: 2026-04-26 | Front exp: 2026-05-03 | Back exp: 2026-05-31
- Regime: Fairly Priced / Event-Dominant / Normal Structure / Neutral Gamma → Mixed/Transitional (confidence 0.38)
- ImpliedMove 10.15% vs historical P75 9.41% → ratio 1.08 (fairly priced)

| Rank | Strategy | Score | EV | CVaR | Convexity | Capital Ratio | Alignment |
|---|---|---|---|---|---|---|---|
| 1 | CALENDAR | 0.998 | +$195 | +$192 | 1.02 | 0.14 | 0.50 |
| 2 | IRON_CONDOR | 0.911 | +$160 | +$156 | 1.03 | 0.11 | 0.50 |
| 3 | CALL_SPREAD | 0.483 | -$69 | -$97 | -0.49 | 0.09 | 0.50 |
| 4 | PUT_SPREAD | 0.437 | -$92 | -$119 | -0.59 | 0.11 | 0.50 |
| 5 | LONG_PUT | 0.269 | -$281 | -$317 | -0.79 | 0.26 | 0.50 |
| 6 | LONG_CALL | 0.257 | -$295 | -$335 | -0.79 | 0.28 | 0.50 |
| 7 | LONG_STRANGLE | 0.139 | -$417 | -$419 | -0.99 | 0.32 | 0.50 |
| 8 | LONG_STRADDLE | 0.000 | -$576 | -$577 | -0.99 | 0.44 | 0.50 |

Conditional: CALL/PUT_BACKSPREAD not activated (IV ratio 1.14 < 1.40 gate, implied move > P75×0.90)

**Observations from this run:**
1. Alignment column is 0.50 across the board — BUG-01 confirmed visually.
2. Long vol structures score near zero in baseline scenario — expected with fairly priced vol in normal term structure.
3. Capital Ratio column is useful — calendar at 0.14 vs straddle at 0.44, good for sizing context. But this needs normalizing vs actual $ risk, not just premium/spot ratio.
4. The butterfly is conspicuously absent — in this regime (fairly priced, mixed) a butterfly would rank between the IC and calendar.
5. Backspread gate logging is clean and informative — "IV ratio 1.14 < P75×0.9 (overpriced)" is exactly the right message.

- Priority order confirmed: P0 bugs first, then STRUCT-01 (butterfly) + INFRA-01 (batch mode) in parallel.
