# Long Call

**One-liner:** Long front-expiry ATM call — pure bullish delta bet.

---

## Structure

| # | Side | Type | Strike | Expiry |
|---|---|---|---|---|
| 1 | Buy | Call | `atm_strike` | front |

`atm_strike` is the nearest available strike to spot in the front-expiry
chain (`_nearest_strike(front_chain, spot)`).

**Risk classification:** defined risk (no short legs).

---

## Rationale

The long call profits when NVDA rises enough post-earnings to overcome the
premium paid.  It is the most directionally leveraged structure in the set:
maximum loss is capped at the premium, while upside is unlimited.

The strategy relies entirely on delta; it is also long gamma and long vega,
so a surprise vol expansion helps, but the primary driver is price direction.

---

## Greeks Profile

| Greek | Sign | Comment |
|---|---|---|
| Delta | Positive (~0.5 ATM) | Primary driver |
| Gamma | Positive | Accelerates delta as spot rises |
| Vega | Positive | Benefits from any residual vol before expiry |
| Theta | Negative | Time decay works against the position |

---

## IV Scenario Behaviour

Exit pricing assumes `HOLD_TO_EXPIRY = False` (default).  The position is
re-priced via BSM on the event date using the remaining time to front expiry.

| Scenario | Effect |
|---|---|
| `base_crush` | Front IV collapses to back IV level; significant value destruction regardless of move |
| `hard_crush` | Front IV drops 35%; heavier additional loss on top of base_crush |
| `expansion` | Front IV rises 10%; small offset to time-value loss; rarely enough to rescue a wrong-direction bet |

IV crush is the dominant P&L driver in the base scenario.  A long call needs
a sufficiently large upside move to overcome the simultaneous collapse in
implied vol.

---

## Assumptions

- NVDA will make a substantial upside move post-earnings.
- The move will be large enough to compensate for front-month IV crush.
- The chain contains a liquid strike near spot.

---

## Limitations

- IV crush is the rule, not the exception, post-earnings.  Under
  `base_crush`, an ATM call loses most of its extrinsic value even if the
  stock moves up moderately.
- A neutral-to-small move produces a near-total loss of premium.
- Convexity is moderate: the position's upside is unbounded in theory, but
  the BSM exit at a single post-event IV snapshot does not capture intraday
  path convexity.
- Single-leg exposure means no hedge against directional error.
