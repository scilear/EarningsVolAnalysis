"""Define and build option structures."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from event_vol_analysis.config import STRANGLE_OFFSET_PCT


@dataclass(frozen=True)
class OptionLeg:
    """Single option leg with detailed greeks."""

    option_type: str  # "call" or "put"
    strike: float
    qty: int
    side: str  # "buy" or "sell"
    expiry: pd.Timestamp

    # Optional fields for detailed reporting
    entry_price: float | None = None
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    vega: float | None = None
    theta: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert leg to dictionary for report serialization."""
        return {
            "side": self.side.upper(),
            "option_type": self.option_type,
            "strike": self.strike,
            "expiry": self.expiry.strftime("%Y-%m-%d"),
            "qty": self.qty,
            "entry_price": self.entry_price,
            "iv": self.iv,
            "delta": self.delta,
            "gamma": self.gamma,
            "vega": self.vega,
            "theta": self.theta,
        }


@dataclass(frozen=True)
class Strategy:
    """Strategy definition with risk metrics."""

    name: str
    legs: tuple[OptionLeg, ...]

    # Risk metrics (populated during scoring)
    net_delta: float = field(default=0.0, compare=False)
    net_gamma: float = field(default=0.0, compare=False)
    net_vega: float = field(default=0.0, compare=False)
    net_theta: float = field(default=0.0, compare=False)

    # Breakevens
    lower_breakeven: float | None = field(default=None, compare=False)
    upper_breakeven: float | None = field(default=None, compare=False)

    # Capital at risk
    max_loss: float = field(default=0.0, compare=False)
    max_gain: float = field(default=0.0, compare=False)
    capital_required: float = field(default=0.0, compare=False)
    capital_efficiency: float = field(default=0.0, compare=False)
    requires_naked_short_approval: bool = field(default=False, compare=False)
    requires_existing_long: bool = field(default=False, compare=False)
    notes: str | None = field(default=None, compare=False)

    def is_defined_risk(self) -> bool:
        """Return True if this is a defined risk strategy."""
        # Short strategies with uncovered legs are undefined
        has_short_call = any(
            leg.option_type == "call" and leg.side == "sell" for leg in self.legs
        )
        has_short_put = any(
            leg.option_type == "put" and leg.side == "sell" for leg in self.legs
        )

        # If no shorts, it's defined risk
        if not has_short_call and not has_short_put:
            return True

        # Check for covered positions
        long_call_strikes = [
            leg.strike
            for leg in self.legs
            if leg.option_type == "call" and leg.side == "buy"
        ]
        short_call_strikes = [
            leg.strike
            for leg in self.legs
            if leg.option_type == "call" and leg.side == "sell"
        ]

        long_put_strikes = [
            leg.strike
            for leg in self.legs
            if leg.option_type == "put" and leg.side == "buy"
        ]
        short_put_strikes = [
            leg.strike
            for leg in self.legs
            if leg.option_type == "put" and leg.side == "sell"
        ]

        # Short calls must be covered by long calls at higher strikes
        for short_strike in short_call_strikes:
            cover = sum(1 for s in long_call_strikes if s >= short_strike)
            if cover == 0:
                return False

        # Short puts must be covered by long puts at lower strikes
        for short_strike in short_put_strikes:
            cover = sum(1 for s in long_put_strikes if s <= short_strike)
            if cover == 0:
                return False

        return True


def build_strategies(
    front_chain: pd.DataFrame,
    back_chain: pd.DataFrame,
    spot: float,
    strangle_offset_pct: float = STRANGLE_OFFSET_PCT,
) -> list[Strategy]:
    """Construct a core set of strategies."""
    if not (0.0 < strangle_offset_pct < 0.5):
        raise ValueError(
            "STRANGLE_OFFSET_PCT must be between 0 and 0.5, got "
            f"{strangle_offset_pct}. Typical range: 0.05-0.15."
        )
    atm_strike = _nearest_strike(front_chain, spot)
    move = spot * strangle_offset_pct
    otm_call = _nearest_strike(front_chain, spot + move, option_type="call")
    otm_put = _nearest_strike(front_chain, spot - move, option_type="put")
    wing_call = _nearest_strike(front_chain, otm_call * 1.05, option_type="call")
    wing_put = _nearest_strike(front_chain, otm_put * 0.95, option_type="put")

    front_expiry = front_chain["expiry"].iloc[0]
    back_expiry = back_chain["expiry"].iloc[0]

    strategies = [
        Strategy(
            name="long_call",
            legs=(OptionLeg("call", atm_strike, 1, "buy", front_expiry),),
        ),
        Strategy(
            name="long_put",
            legs=(OptionLeg("put", atm_strike, 1, "buy", front_expiry),),
        ),
        Strategy(
            name="long_straddle",
            legs=(
                OptionLeg("call", atm_strike, 1, "buy", front_expiry),
                OptionLeg("put", atm_strike, 1, "buy", front_expiry),
            ),
        ),
        Strategy(
            name="long_strangle",
            legs=(
                OptionLeg("call", otm_call, 1, "buy", front_expiry),
                OptionLeg("put", otm_put, 1, "buy", front_expiry),
            ),
        ),
        Strategy(
            name="call_spread",
            legs=(
                OptionLeg("call", atm_strike, 1, "buy", front_expiry),
                OptionLeg("call", otm_call, 1, "sell", front_expiry),
            ),
        ),
        Strategy(
            name="put_spread",
            legs=(
                OptionLeg("put", atm_strike, 1, "buy", front_expiry),
                OptionLeg("put", otm_put, 1, "sell", front_expiry),
            ),
        ),
        Strategy(
            name="iron_condor",
            legs=(
                OptionLeg("call", otm_call, 1, "sell", front_expiry),
                OptionLeg("call", wing_call, 1, "buy", front_expiry),
                OptionLeg("put", otm_put, 1, "sell", front_expiry),
                OptionLeg("put", wing_put, 1, "buy", front_expiry),
            ),
        ),
        Strategy(
            name="calendar",
            legs=(
                OptionLeg("call", atm_strike, 1, "sell", front_expiry),
                OptionLeg("call", atm_strike, 1, "buy", back_expiry),
            ),
        ),
    ]

    butterfly = _build_symmetric_call_butterfly(
        front_chain,
        spot,
        front_expiry,
    )
    if butterfly is not None:
        strategies.append(butterfly)

    return strategies


def _build_symmetric_call_butterfly(
    chain: pd.DataFrame,
    spot: float,
    expiry: pd.Timestamp,
) -> Strategy | None:
    """Build a symmetric 1-2-1 call butterfly centered near spot."""
    calls = chain[chain["option_type"] == "call"]
    strikes = sorted(float(x) for x in calls["strike"].dropna().unique())
    if len(strikes) < 3:
        return None

    middle = _nearest_strike(chain, spot, option_type="call")
    lower_candidates = [strike for strike in strikes if strike < middle]
    upper_candidates = [strike for strike in strikes if strike > middle]
    if not lower_candidates or not upper_candidates:
        return None

    best_lower = None
    best_upper = None
    best_key = None
    for lower in lower_candidates:
        target_upper = middle + (middle - lower)
        upper = min(
            upper_candidates,
            key=lambda strike: abs(strike - target_upper),
        )
        lower_width = middle - lower
        upper_width = upper - middle
        key = (
            abs(upper_width - lower_width),
            lower_width + upper_width,
        )
        if best_key is None or key < best_key:
            best_key = key
            best_lower = lower
            best_upper = upper

    if best_lower is None or best_upper is None:
        return None

    return Strategy(
        name="symmetric_butterfly",
        legs=(
            OptionLeg("call", best_lower, 1, "buy", expiry),
            OptionLeg("call", middle, 1, "sell", expiry),
            OptionLeg("call", middle, 1, "sell", expiry),
            OptionLeg("call", best_upper, 1, "buy", expiry),
        ),
    )


def _nearest_strike(
    chain: pd.DataFrame,
    target: float,
    option_type: str | None = None,
) -> float:
    """Find the nearest strike to target, optionally filtered by option type."""
    chain = chain.copy()
    if option_type is not None:
        chain = chain[chain["option_type"] == option_type]
    if chain.empty:
        raise ValueError(f"No strikes available for option_type={option_type}")
    chain["dist"] = (chain["strike"] - target).abs()
    return float(chain.sort_values("dist").iloc[0]["strike"])


def _snap_to_strike(target: float, strike_step: float = 1.0) -> float:
    """Round a theoretical strike to a tradable strike grid."""
    if strike_step <= 0:
        raise ValueError("strike_step must be positive")
    return round(target / strike_step) * strike_step


def make_long_put(
    expiry: dt.date | pd.Timestamp,
    strike: float,
) -> Strategy:
    """Create a long put structure."""
    return Strategy(
        name="long_put",
        legs=(OptionLeg("put", float(strike), 1, "buy", pd.Timestamp(expiry)),),
    )


def make_long_call(
    expiry: dt.date | pd.Timestamp,
    strike: float,
) -> Strategy:
    """Create a long call structure."""
    return Strategy(
        name="long_call",
        legs=(OptionLeg("call", float(strike), 1, "buy", pd.Timestamp(expiry)),),
    )


def make_put_spread(
    expiry: dt.date | pd.Timestamp,
    long_strike: float,
    short_strike: float,
) -> Strategy:
    """Create a debit put spread."""
    return Strategy(
        name="put_spread",
        legs=(
            OptionLeg("put", float(long_strike), 1, "buy", pd.Timestamp(expiry)),
            OptionLeg("put", float(short_strike), 1, "sell", pd.Timestamp(expiry)),
        ),
    )


def make_call_spread(
    expiry: dt.date | pd.Timestamp,
    long_strike: float,
    short_strike: float,
) -> Strategy:
    """Create a debit call spread."""
    return Strategy(
        name="call_spread",
        legs=(
            OptionLeg("call", float(long_strike), 1, "buy", pd.Timestamp(expiry)),
            OptionLeg("call", float(short_strike), 1, "sell", pd.Timestamp(expiry)),
        ),
    )


def make_long_straddle(
    expiry: dt.date | pd.Timestamp,
    strike: float,
) -> Strategy:
    """Create a long straddle."""
    expiry_ts = pd.Timestamp(expiry)
    strike_val = float(strike)
    return Strategy(
        name="long_straddle",
        legs=(
            OptionLeg("call", strike_val, 1, "buy", expiry_ts),
            OptionLeg("put", strike_val, 1, "buy", expiry_ts),
        ),
    )


def make_long_strangle(
    expiry: dt.date | pd.Timestamp,
    call_strike: float,
    put_strike: float,
) -> Strategy:
    """Create a long strangle."""
    expiry_ts = pd.Timestamp(expiry)
    return Strategy(
        name="long_strangle",
        legs=(
            OptionLeg("call", float(call_strike), 1, "buy", expiry_ts),
            OptionLeg("put", float(put_strike), 1, "buy", expiry_ts),
        ),
    )


def make_short_straddle(
    expiry: dt.date | pd.Timestamp,
    strike: float,
) -> Strategy:
    """Create a short straddle (charter-blocked unless approved)."""
    expiry_ts = pd.Timestamp(expiry)
    strike_val = float(strike)
    return Strategy(
        name="short_straddle",
        legs=(
            OptionLeg("call", strike_val, 1, "sell", expiry_ts),
            OptionLeg("put", strike_val, 1, "sell", expiry_ts),
        ),
        requires_naked_short_approval=True,
    )


def make_short_strangle(
    expiry: dt.date | pd.Timestamp,
    call_strike: float,
    put_strike: float,
) -> Strategy:
    """Create a short strangle (charter-blocked unless approved)."""
    expiry_ts = pd.Timestamp(expiry)
    return Strategy(
        name="short_strangle",
        legs=(
            OptionLeg("call", float(call_strike), 1, "sell", expiry_ts),
            OptionLeg("put", float(put_strike), 1, "sell", expiry_ts),
        ),
        requires_naked_short_approval=True,
    )


def make_covered_call(
    expiry: dt.date | pd.Timestamp,
    call_strike: float,
) -> Strategy:
    """Create a covered-call placeholder requiring existing long stock."""
    expiry_ts = pd.Timestamp(expiry)
    return Strategy(
        name="covered_call",
        legs=(OptionLeg("call", float(call_strike), 1, "sell", expiry_ts),),
        requires_existing_long=True,
    )


def make_diagonal_put_backspread(
    short_expiry: dt.date | pd.Timestamp,
    long_expiry: dt.date | pd.Timestamp,
    short_strike: float,
    long_strike: float,
    ratio: int = 2,
) -> Strategy:
    """Create a short-near/long-far diagonal put 1x2 backspread."""
    if ratio < 1:
        raise ValueError("ratio must be >= 1")
    return Strategy(
        name="diagonal_put_backspread",
        legs=(
            OptionLeg(
                "put",
                float(short_strike),
                1,
                "sell",
                pd.Timestamp(short_expiry),
            ),
            OptionLeg(
                "put",
                float(long_strike),
                int(ratio),
                "buy",
                pd.Timestamp(long_expiry),
            ),
        ),
        notes=(
            "Conditional loss zone between short and long strikes around near "
            "expiry if short leg is assigned."
        ),
    )


def make_risk_reversal(
    expiry: dt.date | pd.Timestamp,
    put_strike: float,
    call_strike: float,
    direction: str = "bullish",
) -> Strategy:
    """Create a risk-reversal structure."""
    normalized_direction = direction.strip().lower()
    expiry_ts = pd.Timestamp(expiry)
    if normalized_direction == "bullish":
        legs = (
            OptionLeg("put", float(put_strike), 1, "sell", expiry_ts),
            OptionLeg("call", float(call_strike), 1, "buy", expiry_ts),
        )
    elif normalized_direction == "bearish":
        legs = (
            OptionLeg("call", float(call_strike), 1, "sell", expiry_ts),
            OptionLeg("put", float(put_strike), 1, "buy", expiry_ts),
        )
    else:
        raise ValueError("direction must be 'bullish' or 'bearish'")

    return Strategy(
        name=f"risk_reversal_{normalized_direction}",
        legs=legs,
    )
