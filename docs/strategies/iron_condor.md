# Iron Condor

**One-liner:** Short OTM strangle with wing hedges — range-bound premium
harvest; profits from low realised vol and IV crush.

---

## Structure

| # | Side | Type | Strike | Expiry |
|---|---|---|---|---|
| 1 | Sell | Call | `otm_call` | front |
| 2 | Buy | Call | `wing_call` | front |
| 3 | Sell | Put | `otm_put` | front |
| 4 | Buy | Put | `wing_put` | front |

`wing_call` = nearest call strike to `otm_call × 1.05` (5% above short call)
`wing_put` = nearest put strike to `otm_put × 0.95` (5% below short put)

The wing distance is **not** configurable via `config.py`; it is hardcoded at
5% of the short strike in `build_strategies()`.

**Risk classification:** defined risk.  Each short leg is covered by a long
wing on the same side, so `_is_undefined_risk()` returns False.

---

## Rationale

The iron condor collects net premium by selling the OTM strangle (short call
and short put) and hedging the unlimited-loss risk with OTM wings.  It is the
only strategy in the set with a short-vega, short-gamma profile.

At earnings, the iron condor bets that:
1. NVDA will not move beyond the short strikes (range-bound outcome).
2. Front IV will crush after the event, allowing the short options to decay in
   value.

This makes it the natural complement of the long-vol structures: it is the
best performer when the implied move significantly overstates the realised
move (i.e., when vol is "Tail Overpriced").

---

## Greeks Profile

| Greek | Sign | Comment |
|---|---|---|
| Delta | Near-zero | Symmetric short strangle; small residual delta from asymmetric chain |
| Gamma | Negative | Maximum loss if a large move is realised |
| Vega | Negative | Profits from IV crush; penalised by expansion |
| Theta | Positive | Primary positive-carry contribution |

---

## IV Scenario Behaviour

| Scenario | Effect |
|---|---|
| `base_crush` | Short legs gain significantly as front IV collapses; this is the best scenario for the iron condor |
| `hard_crush` | Further gains as IV falls harder; even better, provided price stays inside the short strikes |
| `expansion` | Short legs lose value; can turn profitable positions into losses if the move also approaches the short strikes |

The iron condor has the highest EV in the base-crush and hard-crush scenarios
among range-bound outcomes.  Under expansion, it is the worst performer.

---

## Assumptions

- NVDA will remain between `otm_put` and `otm_call` at exit.
- Front IV will decrease post-earnings (IV crush).
- The premium collected from the short strangle will exceed the cost of the
  wings.

---

## Limitations

- The iron condor is the **only strategy in the set that loses money on large
  moves**, which are precisely the outcome earnings events can produce.
  Historical NVDA earnings have included multi-sigma gaps.
- Wing strikes are hardcoded at 5% outside the short strikes.  This is not
  calibrated to the option chain's liquidity or the expected tail distribution.
  Wider wings require smaller premium outlay for less downside protection;
  narrower wings cap the loss but reduce collected premium.
- Maximum loss = spread width × 100 − net premium collected.  With 5% wing
  offsets and a typical 15–20% earnings move, the wings are very unlikely to
  be reached, meaning the max-loss exposure is essentially unconstrained for
  realistic move scenarios.
- The strategy scores well on robustness (low scenario EV std) and CVaR when
  vol is overpriced, but can have a large negative CVaR if the distribution
  includes tail scenarios.  The 5% worst paths in the MC simulation correspond
  to the largest earnings moves, where both short legs are deeply ITM.
- Scoring context: under `base_crush`, the iron condor typically generates
  high EV and low CVaR relative to the long-vol structures, which may give it
  a high composite score.  Users should verify the regime classification
  before treating a high-scoring iron condor as actionable — it is only
  appropriate in overpriced-vol, low-expected-move environments.
