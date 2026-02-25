# Call Spread (Bull Call Spread)

**One-liner:** Long ATM call / short OTM call — capped bullish bet at lower
net premium.

---

## Structure

| # | Side | Type | Strike | Expiry |
|---|---|---|---|---|
| 1 | Buy | Call | `atm_strike` | front |
| 2 | Sell | Call | `otm_call` | front |

`otm_call` = nearest call strike to `spot + implied_move × 0.8`.

Both legs expire on the same front expiry, making this a vertical spread.

**Risk classification:** defined risk.  The short call is covered by the long
call at a lower strike (ATM ≤ OTM), so the coverage check in
`_is_undefined_risk()` passes.

---

## Rationale

The call spread finances the long ATM call by selling away the upside beyond
the OTM strike.  This reduces the net debit and therefore reduces the
required move to break even.  In exchange, maximum profit is capped at the
spread width minus the net premium paid.

At earnings, the call spread behaves better than a naked call when the stock
moves moderately upward: the short call partially offsets IV crush on the
long leg, while the limited-width spread does not sacrifice much upside for
typical earnings moves.

---

## Greeks Profile

| Greek | Sign | Comment |
|---|---|---|
| Delta | Positive, < naked call | Short OTM call reduces net delta |
| Gamma | Positive but lower | Short call offsets some gamma |
| Vega | Positive but lower | Short call partially hedges IV crush — structural advantage over naked long call |
| Theta | Negative but lower | Short call reduces net theta bleed |

The reduced vega is a meaningful advantage: the short call partially offsets
the IV-crush damage that destroys value in a naked long call.

---

## IV Scenario Behaviour

| Scenario | Effect |
|---|---|
| `base_crush` | Both legs crushed proportionally; net P&L better than naked long call because short leg profits partially offset long leg loss |
| `hard_crush` | Short call gains significantly; net loss reduced compared to long call alone |
| `expansion` | Long call gains; short call loses; net gain dampened relative to naked long call |

The vega hedge from the short leg makes the call spread more robust to
`base_crush` and `hard_crush` than any pure long-vol structure.

---

## Assumptions

- NVDA will make a moderate-to-large upside move.
- The move will land at or above `otm_call` (the spread's max-profit zone).
- Front IV will not expand so dramatically that the short call causes a
  significant loss.

---

## Limitations

- Maximum profit is capped at the spread width minus net premium; a very
  large upside move above `otm_call` produces the same P&L as an
  at-the-money outcome above the short strike.
- The strategy requires directional accuracy: a neutral or downside move
  produces a near-total loss of net premium.
- The short strike is at `otm_call = spot + implied_move × 0.8`, so the
  profit zone begins approximately at the market's own implied move.  The
  structure requires NVDA to exceed what is already priced in.
- Strike resolution uses `_nearest_strike(front_chain, target,
  option_type="call")`.  If the nearest call strike above `otm_call` is not
  at a clean spread width, the max gain and breakeven may differ from a
  textbook spread.
