# Long Straddle

**One-liner:** Long ATM call + put on the front expiry — direction-neutral,
bets on a large move in either direction.

---

## Structure

| # | Side | Type | Strike | Expiry |
|---|---|---|---|---|
| 1 | Buy | Call | `atm_strike` | front |
| 2 | Buy | Put | `atm_strike` | front |

Both legs share the same `atm_strike` (nearest strike to spot in the front
chain) and the same front expiry.

**Risk classification:** defined risk (no short legs).

---

## Rationale

The straddle is the purest expression of a long-volatility view: it profits
from a large move in either direction.  Because the strike is ATM, the
position starts delta-neutral.  It carries the highest premium of any
long-vol structure in the set, but also the lowest required move to break
even for a given vega exposure.

At earnings, the primary question is whether the actual realised move exceeds
the combined premium — i.e., whether realised vol exceeds the implied vol
baked into the straddle price.  The position is fully exposed to IV crush: if
front IV collapses to back-month levels without a commensurate price move,
the straddle is unprofitable.

---

## Greeks Profile

| Greek | Sign | Comment |
|---|---|---|
| Delta | ~0 (ATM) | Becomes directional quickly as spot moves |
| Gamma | Positive (2×) | Highest gamma of any single-expiry structure in the set |
| Vega | Positive (2×) | Highest vega; most sensitive to IV crush |
| Theta | Negative (2×) | Highest theta cost |

---

## IV Scenario Behaviour

| Scenario | Effect |
|---|---|
| `base_crush` | Both legs repriced with front IV collapsed to back level; large extrinsic loss on both legs simultaneously |
| `hard_crush` | Front IV −35%; worst case for the straddle as vol collapses further |
| `expansion` | Front IV +10%; helps both legs; best scenario for the straddle if combined with a neutral price move |

The straddle is the structure most sensitive to the `base_crush` and
`hard_crush` scenarios.  The combined vega is 2× a single option, so every
point of IV collapse costs twice as much.

---

## Assumptions

- A large move will occur in either direction.
- The realised move exceeds the combined premium paid (i.e., realised vol
  beats implied vol).
- Front IV will not crush so severely that the vol loss overwhelms the move.

---

## Limitations

- Most expensive structure in the set: requires the largest absolute P&L move
  to generate positive EV under IV-crush scenarios.
- Double vega exposure makes the straddle the most penalised by `hard_crush`.
- Both legs share the same single ATM strike; a gap to either side is
  required.  A small move near strike produces a near-total premium loss.
- Under `base_crush` with a moderate move, the straddle typically
  underperforms the strangle and spread structures.
- Scoring: tends to rank lower than defined-risk spread structures under
  base-crush assumptions because high CVaR (two-leg full loss) weighs against
  the convexity advantage.
