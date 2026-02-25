# Put Spread (Bear Put Spread)

**One-liner:** Long ATM put / short OTM put — capped bearish bet at lower net
premium.

---

## Structure

| # | Side | Type | Strike | Expiry |
|---|---|---|---|---|
| 1 | Buy | Put | `atm_strike` | front |
| 2 | Sell | Put | `otm_put` | front |

`otm_put` = nearest put strike to `spot − implied_move × 0.8`.

Both legs expire on the same front expiry (vertical spread).

**Risk classification:** defined risk.  The short put is covered by the long
put at a higher strike (ATM ≥ OTM), so `_is_undefined_risk()` returns False.

---

## Rationale

The put spread is the bearish mirror of the call spread.  Selling the OTM put
reduces the net debit and the required downside move to break even, at the
cost of capping maximum profit at the spread width.

In an earnings context, the short put partially hedges IV crush on the long
leg, making the structure more resilient to a post-event vol collapse than a
naked long put — particularly if the stock ends up flat or moves modestly.

---

## Greeks Profile

| Greek | Sign | Comment |
|---|---|---|
| Delta | Negative, less than naked put | Short OTM put reduces net delta |
| Gamma | Positive but lower | Short put offsets some gamma |
| Vega | Positive but lower | Short put partially hedges IV crush |
| Theta | Negative but lower | Short put reduces net theta bleed |

---

## IV Scenario Behaviour

| Scenario | Effect |
|---|---|
| `base_crush` | Both legs crushed; net P&L better than naked long put because short leg profit partially offsets long leg loss |
| `hard_crush` | Short put gains; net loss reduced versus naked long put |
| `expansion` | Long put gains; short put loses; net gain dampened |

The reduced vega makes the put spread more resilient to crush scenarios than
a naked long put.

---

## Assumptions

- NVDA will make a moderate-to-large downside move post-earnings.
- The move will reach at or below `otm_put` (the spread's max-profit zone).
- Front IV will not expand so sharply that the short put causes a significant
  mark-to-market loss before expiry.

---

## Limitations

- Maximum profit is capped at spread width minus net premium; an extreme
  downside move beyond `otm_put` yields the same result as one that just
  reaches it.
- A flat or upside move produces a near-total loss of net premium.
- The short strike is at `otm_put = spot − implied_move × 0.8`, so the
  full-profit zone requires a downside move that exceeds what the market
  already prices in.
- Skew: OTM puts typically have higher implied volatility (put skew) than ATM
  options.  The short OTM put is sold at elevated IV, which is a mild
  structural advantage; however, the `_post_iv()` function freezes skew
  shape (proportional scaling), so skew dynamics are not modelled.
- Historical NVDA earnings show positive skewness (more large upside than
  downside) — the empirical probability of reaching the max-profit zone may
  be lower than for the call spread.
