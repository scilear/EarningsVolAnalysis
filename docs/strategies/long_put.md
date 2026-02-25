# Long Put

**One-liner:** Long front-expiry ATM put — pure bearish delta bet.

---

## Structure

| # | Side | Type | Strike | Expiry |
|---|---|---|---|---|
| 1 | Buy | Put | `atm_strike` | front |

`atm_strike` is the nearest available strike to spot in the front-expiry chain.

**Risk classification:** defined risk (no short legs).

---

## Rationale

The long put is the bearish mirror of the long call.  It profits when NVDA
falls enough post-earnings to overcome the premium paid.  Maximum loss is
capped at the premium; profit grows as spot falls toward zero.

Like the long call, the strategy is directionally leveraged.  Long gamma and
long vega mean both a larger-than-expected move and any residual vol
expansion will help, but the primary requirement is a significant downside
move.

---

## Greeks Profile

| Greek | Sign | Comment |
|---|---|---|
| Delta | Negative (~−0.5 ATM) | Primary driver |
| Gamma | Positive | Accelerates delta magnitude as spot falls |
| Vega | Positive | Benefits from any residual vol before expiry |
| Theta | Negative | Time decay works against the position |

---

## IV Scenario Behaviour

Exit pricing assumes `HOLD_TO_EXPIRY = False` (default).

| Scenario | Effect |
|---|---|
| `base_crush` | Front IV collapses to back IV level; significant value loss regardless of direction |
| `hard_crush` | Front IV drops 35%; accelerates extrinsic value destruction |
| `expansion` | Front IV rises 10%; modest offset; rarely compensates for a wrong-direction outcome |

As with the long call, IV crush dominates in the base case.  A sufficiently
large downside move is required to produce a net positive P&L.

---

## Assumptions

- NVDA will make a substantial downside move post-earnings.
- The move will be large enough to compensate for front-month IV crush.
- The chain contains a liquid put strike near spot.

---

## Limitations

- Identical IV-crush vulnerability as the long call: the base scenario
  destroys most extrinsic value even on a moderately bearish outcome.
- A neutral or small upside move results in a near-total loss of premium.
- No directional hedge; a wrong-direction move produces maximum loss.
- Historical NVDA earnings have skewed positive (positive kurtosis and
  historical skew), so the a priori probability of a large downside move may
  be lower than for a large upside move.
