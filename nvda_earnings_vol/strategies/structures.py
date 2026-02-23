"""Define and build option structures."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class OptionLeg:
    """Single option leg."""

    option_type: str
    strike: float
    qty: int
    side: str
    expiry: pd.Timestamp


@dataclass(frozen=True)
class Strategy:
    """Strategy definition."""

    name: str
    legs: tuple[OptionLeg, ...]


def build_strategies(
    front_chain: pd.DataFrame,
    back_chain: pd.DataFrame,
    spot: float,
) -> list[Strategy]:
    """Construct a core set of strategies."""
    atm_strike = _nearest_strike(front_chain, spot)
    move = spot * 0.05
    otm_call = _nearest_strike(front_chain, spot + move)
    otm_put = _nearest_strike(front_chain, spot - move)
    wing_call = _nearest_strike(front_chain, otm_call * 1.05)
    wing_put = _nearest_strike(front_chain, otm_put * 0.95)

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


def _nearest_strike(chain: pd.DataFrame, target: float) -> float:
    chain = chain.copy()
    chain["dist"] = (chain["strike"] - target).abs()
    return float(chain.sort_values("dist").iloc[0]["strike"])
