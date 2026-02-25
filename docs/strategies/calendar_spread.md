# Calendar Spread

**One-liner:** Short front ATM call / long back ATM call — exploits the
differential IV crush between front and back expiries.

---

## Structure

| # | Side | Type | Strike | Expiry |
|---|---|---|---|---|
| 1 | Sell | Call | `atm_strike` | front |
| 2 | Buy | Call | `atm_strike` | back |

Both legs are at the same `atm_strike`.  The front leg expires shortly after
the earnings event; the back leg expires one cycle later (the second
post-event expiry returned by `get_expiries_after()`).

**Risk classification:** defined risk.  The short front call and long back
call share the same strike.  In `_is_undefined_risk()`, the long back call
(strike = ATM) satisfies the coverage condition for the short front call
(requires long call at strike ≥ short strike), so the strategy passes as
defined risk even though the legs are on different expiries.

---

## Rationale

The calendar spread is built on the term-structure thesis: front-month IV
collapses sharply after earnings while back-month IV holds relatively stable.
The short front call captures the post-event IV crush as premium decay; the
long back call provides a hedge and retains residual value.

This is the only multi-expiry strategy in the set.  Its P&L profile is
non-monotonic: it profits most when NVDA ends near the ATM strike at expiry
(time spread at maximum width) and loses when NVDA moves far in either
direction (both legs converge toward intrinsic value or the long leg
underperforms the short leg's gain).

---

## Greeks Profile

| Greek | Sign | Comment |
|---|---|---|
| Delta | Near-zero at entry | Short-dated call delta dominates near event |
| Gamma | Negative | Short-dated gamma > long-dated gamma |
| Vega | Positive (net) | Long back vega > short front vega in absolute terms when front IV is high; reverses after crush |
| Theta | Positive (near term) | Short front theta decay accelerates near expiry |

The sign of net vega depends on the IV level difference: pre-event, front IV
is elevated, so the position is net short vol (front vega > back vega in
dollar terms).  Post-event, after front IV crushes, the position is net long
back vega.

---

## IV Scenario Behaviour

| Scenario | Front leg | Back leg | Net effect |
|---|---|---|---|
| `base_crush` | Front IV collapses to back IV level; short call gains | Back IV unchanged; long call retains value | Best case: captures maximum spread between front crush and back stability |
| `hard_crush` | Front IV −35%; short call gains further | Back IV −10%; long call loses some value | Still profitable if front crush dominates |
| `expansion` | Front IV +10%; short call loses value | Back IV +5%; long call gains | Net loss if the stock also moves away from ATM |

The calendar's edge is entirely in the `base_crush` scenario.  It is the
primary beneficiary of the `"base_crush"` IV scenario in the simulation.

---

## Exit Pricing Detail

Both legs are re-priced via BSM on the event date (`HOLD_TO_EXPIRY = False`).
Time remaining for each leg:

- **Front leg:** business days from event date to front expiry / 252.
- **Back leg:** business days from event date to back expiry / 252.

This means the back leg retains substantial time value at exit, which is the
structural source of the calendar's positive P&L under crush scenarios.

Slippage (`SLIPPAGE_PCT = 0.10`) is applied at both entry and exit for each
leg, so a two-leg structure incurs 2× the single-leg slippage cost.

---

## Assumptions

- Front-month IV will crush significantly more than back-month IV after
  earnings.
- NVDA will not make a large directional move away from ATM (which would
  cause both legs to converge toward intrinsic and destroy the spread value).
- Sufficient liquidity exists in both the front and back expiry chains.
- The back expiry has enough time remaining to hold meaningful time value
  after the event.

---

## Limitations

- **No minimum back-expiry DTE enforcement.** `config.py` defines
  `CALENDAR_LONG_MIN_DTE = 30`, but `build_strategies()` does not apply it —
  the back expiry is simply the second post-event expiry from the market data.
  If the option chain has closely spaced expiries, the back leg may have fewer
  than 30 DTE at the time of the event, significantly reducing its time-value
  retention and the strategy's edge.
- **Large-move vulnerability.** If NVDA gaps significantly in either
  direction, the short front call moves deeply ITM (short leg loss) while the
  long back call (same strike, longer expiry) gains less, producing a net
  loss.  The calendar has the worst P&L profile of all strategies under tail
  move scenarios.
- **Vega sign reversal.** Pre-event, net vega is negative (short front IV
  > long back IV in dollar terms).  If IV expands before the event or the
  simulation includes a pre-event expansion, the calendar loses money.  The
  model does not simulate pre-event dynamics; it only captures exit pricing
  after the event.
- **Two-leg slippage.** The calendar pays slippage twice (entry and exit for
  two legs), making it the highest-friction strategy in the set for a
  given contract size.
- **Same-strike coverage.** The defined-risk classification relies on the
  back-expiry long call covering the front-expiry short call at the same
  strike.  In practice, early assignment (not modelled) on the short front
  call is theoretically possible for American-style equity options.
  The BSM model assumes European exercise; early assignment risk is not
  captured.
