"""Define and build option structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from nvda_earnings_vol.config import STRANGLE_OFFSET_PCT


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
    
    def is_defined_risk(self) -> bool:
        """Return True if this is a defined risk strategy."""
        # Short strategies with uncovered legs are undefined
        has_short_call = any(
            leg.option_type == "call" and leg.side == "sell"
            for leg in self.legs
        )
        has_short_put = any(
            leg.option_type == "put" and leg.side == "sell"
            for leg in self.legs
        )
        
        # If no shorts, it's defined risk
        if not has_short_call and not has_short_put:
            return True
        
        # Check for covered positions
        long_call_strikes = [
            leg.strike for leg in self.legs
            if leg.option_type == "call" and leg.side == "buy"
        ]
        short_call_strikes = [
            leg.strike for leg in self.legs
            if leg.option_type == "call" and leg.side == "sell"
        ]
        
        long_put_strikes = [
            leg.strike for leg in self.legs
            if leg.option_type == "put" and leg.side == "buy"
        ]
        short_put_strikes = [
            leg.strike for leg in self.legs
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

    return [
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
