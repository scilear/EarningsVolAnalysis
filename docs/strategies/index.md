# Strategies Index

Eight strategies are constructed by `build_strategies()` in
`nvda_earnings_vol/strategies/structures.py` and evaluated through the full
Monte Carlo / scoring pipeline in `main.py`.

| Strategy | One-liner |
|---|---|
| [Long Call](long_call.md) | Long front-expiry ATM call — pure bullish delta bet |
| [Long Put](long_put.md) | Long front-expiry ATM put — pure bearish delta bet |
| [Long Straddle](long_straddle.md) | Long ATM call + put — direction-neutral, bets on a large move |
| [Long Strangle](long_strangle.md) | Long OTM call + put at ~0.8× implied-move offset — cheaper vol bet requiring a bigger move |
| [Call Spread](call_spread.md) | Long ATM call / short OTM call — capped bullish bet at lower cost |
| [Put Spread](put_spread.md) | Long ATM put / short OTM put — capped bearish bet at lower cost |
| [Iron Condor](iron_condor.md) | Short OTM strangle + wing hedges — range-bound premium harvest |
| [Calendar Spread](calendar_spread.md) | Short front ATM call / long back ATM call — bets on post-earnings front-IV crush |

---

## Strike Construction

All strikes are resolved to the nearest available strike in the chain via
`_nearest_strike()`. The key reference points are:

| Variable | Definition |
|---|---|
| `atm_strike` | Nearest strike to `spot` |
| `move` | `spot × strangle_offset_pct` (passed from `main.py` as `implied_move × 0.8`) |
| `otm_call` | Nearest call strike to `spot + move` |
| `otm_put` | Nearest put strike to `spot − move` |
| `wing_call` | Nearest call strike to `otm_call × 1.05` |
| `wing_put` | Nearest put strike to `otm_put × 0.95` |

The strangle offset is **not** the static `STRANGLE_OFFSET_PCT = 0.05` from
`config.py`; it is computed dynamically in `main.py` as `implied_move × 0.8`.

---

## Payoff Computation

Default mode is `HOLD_TO_EXPIRY = False`.  Positions are priced at exit via
BSM on the event date, with time remaining computed as business days from
event date to each leg's expiry divided by 252.  Slippage (`SLIPPAGE_PCT =
0.10`) is applied at both entry and exit.  P&L is in dollars (price ×
`CONTRACT_MULTIPLIER = 100`).

When `HOLD_TO_EXPIRY = True` (non-default), exit values reduce to intrinsic
only (no time value, no IV scenario effect).

---

## IV Scenarios

Three scenarios are applied to re-price each leg at exit.

| Scenario | Front expiry | Back expiry |
|---|---|---|
| `base_crush` | Collapses to back ATM IV | Unchanged |
| `hard_crush` | −35% | −10% |
| `expansion` | +10% | +5% |

IV is scaled proportionally per strike: `leg_iv × (target_atm / atm_iv)`.
The skew shape (risk reversal, butterfly) is **frozen** — no smile-level shift
is applied (v3 spec §4.5).

---

## Scoring

Each strategy is scored across 100 000 Monte Carlo paths under `base_crush`
and ranked by composite score (weights from `config.SCORING_WEIGHTS`):

| Metric | Weight | Definition |
|---|---|---|
| EV | 0.40 | Mean P&L |
| Convexity | 0.30 | Mean(top 10% P&Ls) / \|mean(bottom 10% P&Ls)\|, capped at 10.0 |
| CVaR | 0.20 | Mean of worst 5% P&Ls |
| Robustness | 0.10 | 1 / std(EVs across 3 scenarios × 5 vol shocks) |

All four metrics are min-max normalised across the strategy set before
weighting.  Strategies classified as **undefined risk** receive a ×0.90
score penalty.

**Risk classification** (`_is_undefined_risk` in `scoring.py`): a strategy
is undefined risk if any short call is not covered by a long call at an
equal-or-higher strike, or any short put is not covered by a long put at an
equal-or-lower strike, *counting legs across all expiries*.  The calendar's
short front call is covered by the long back call at the same strike, so it
is classified as defined risk.

---

## Regime Alignment

After ranking, `compute_all_alignments()` in `alignment.py` scores each
strategy's structural fit against the classified regime on four axes (each
normalised to [0, 1]):

| Axis | Signal |
|---|---|
| Gamma | Long gamma preferred in `gamma_bias = "long_gamma"`; short gamma in `"short_gamma"`; 0.5 if neutral |
| Vega | Long vega preferred when vol is `"Tail Underpriced"`; short vega when `"Tail Overpriced"`; 0.5 otherwise |
| Convexity | High-convexity percentile rank preferred in `"Convex Breakout Setup"`; inverted in `"Premium Harvest Setup"` |
| Tail Risk | Lower CVaR percentile rank preferred when vol is `"Tail Underpriced"`; 0.5 otherwise |

The composite alignment score is the mean of the four axes, weighted by
overall regime confidence.

**Known limitation:** `compute_alignment()` reads `regime.get("gamma_bias",
"neutral")`, but `classify_regime()` (in `regime.py`) does not emit a
`gamma_bias` key — it emits `gamma_regime`.  As a result, the gamma alignment
axis always defaults to 0.5 in the current codebase, regardless of the
detected gamma regime.

---

## Global Assumptions and Limitations

- **BSM pricing everywhere.** Entry prices come from mid-market chain data;
  exit prices are re-priced with BSM under the chosen IV scenario.  BSM
  assumptions (constant vol, no jumps, European exercise) are not met in
  practice around an earnings event.
- **Single-contract sizing.** All strategies are built with `qty = 1` per
  leg.  P&L figures are not normalised by capital.
- **No intraday path.** The Monte Carlo draws a single end-of-event move; the
  P&L path between entry and the event is not modelled.
- **Frozen skew.** Post-event RR and butterfly are held constant.  Skew
  dynamics during crush or expansion are not modelled.
- **Log-normal move distribution.** `simulate_moves()` draws from a
  log-normal distribution (drift-corrected).  Empirical earnings distributions
  show heavier tails and gap-risk not captured by log-normal.
- **Data source.** Live data relies on `yfinance`.  Bid/ask spreads, open
  interest, and implied volatilities may be stale or unreliable for illiquid
  strikes.
