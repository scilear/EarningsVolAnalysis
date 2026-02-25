# Long Strangle

**One-liner:** Long OTM call + OTM put — cheaper direction-neutral vol bet
requiring a larger move than the straddle.

---

## Structure

| # | Side | Type | Strike | Expiry |
|---|---|---|---|---|
| 1 | Buy | Call | `otm_call` | front |
| 2 | Buy | Put | `otm_put` | front |

`otm_call` = nearest call strike to `spot + move`
`otm_put` = nearest put strike to `spot − move`
where `move = spot × strangle_offset_pct` and `strangle_offset_pct =
implied_move × 0.8` (set dynamically in `main.py`).

**Important:** the offset is **not** the static `STRANGLE_OFFSET_PCT = 0.05`
from `config.py`.  It is tied to the current implied move at runtime, so the
OTM distance widens when the market prices in a larger event.

**Risk classification:** defined risk (no short legs).

---

## Rationale

The strangle lowers premium outlay versus the straddle by moving both strikes
OTM.  The trade-off is that a larger absolute move is required to reach
breakeven.  The offset is calibrated to ~80% of the current implied move, so
the strikes sit meaningfully inside the tails but not so far out that the
options are illiquid.

The strangle is the preferred long-vol structure when the straddle is
overpriced relative to historical realised moves, or when the trader wants
exposure to a large move with lower upfront cost and more tolerance for a
moderate, range-bound outcome.

---

## Greeks Profile

| Greek | Sign | Comment |
|---|---|---|
| Delta | Near-zero (OTM, but slightly directional at entry) | Becomes strongly directional once either wing is ITM |
| Gamma | Positive | Lower than straddle; options are OTM |
| Vega | Positive | Lower than straddle; cheaper to hold |
| Theta | Negative | Lower absolute theta than straddle |

---

## IV Scenario Behaviour

| Scenario | Effect |
|---|---|
| `base_crush` | Both OTM options lose most of their extrinsic value; OTM options are proportionally more sensitive to IV crush than ATM |
| `hard_crush` | Severe; OTM options may approach near-zero value on the losing wing |
| `expansion` | Helps, but OTM options start with lower vega so absolute gain is smaller than for the straddle |

Because the legs are OTM, their IV (from the chain) may differ from ATM IV.
The post-event IV scaling in `_post_iv()` applies proportionally relative to
the ATM IV of the relevant expiry, so OTM skew is frozen but its absolute
level scales with the ATM shift.

---

## Assumptions

- A large move will occur in either direction, exceeding the combined
  out-of-the-money premium.
- The strangle offset (≈0.8× implied move) is a reasonable proxy for where
  the market expects the move to cluster.
- Sufficient liquidity exists at the chosen OTM strikes.

---

## Limitations

- Requires a larger absolute move than the straddle to profit, because both
  strikes are OTM.
- OTM options are proportionally more sensitive to IV crush: a large
  percentage of their value is extrinsic.
- The 0.8× implied-move offset is fixed at construction time.  If the
  implied move changes significantly before the event, the strikes may become
  stale.
- Strike resolution uses `_nearest_strike(front_chain, target,
  option_type=...)`, which filters by option type.  If the nearest put strike
  and nearest call strike are not symmetric around spot (uneven chain), the
  strangle may have a residual delta bias.
- `STRANGLE_OFFSET_PCT` in `config.py` is defined as a default but is
  overridden by `main.py`; any code that calls `build_strategies()` directly
  without passing `strangle_offset_pct` will use the config default (0.05),
  not the implied-move-based value.
