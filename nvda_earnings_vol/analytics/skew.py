"""Skew metrics from option chain."""

from __future__ import annotations

import logging

import pandas as pd

from nvda_earnings_vol.analytics.bsm import option_delta
from nvda_earnings_vol.config import DIVIDEND_YIELD, RISK_FREE_RATE


LOGGER = logging.getLogger(__name__)


def skew_metrics(chain: pd.DataFrame, spot: float, t: float) -> dict[str, float | None]:
    """Compute 25d risk reversal and butterfly from chain IVs."""
    calls = chain[chain["option_type"] == "call"].copy()
    puts = chain[chain["option_type"] == "put"].copy()

    calls["delta"] = calls.apply(
        lambda row: option_delta(
            spot,
            row["strike"],
            t,
            RISK_FREE_RATE,
            DIVIDEND_YIELD,
            row["impliedVolatility"],
            "call",
        ),
        axis=1,
    )
    puts["delta"] = puts.apply(
        lambda row: option_delta(
            spot,
            row["strike"],
            t,
            RISK_FREE_RATE,
            DIVIDEND_YIELD,
            row["impliedVolatility"],
            "put",
        ),
        axis=1,
    )

    call_25 = _closest_delta(calls, 0.25)
    put_25 = _closest_delta(puts, -0.25)
    atm_iv = _atm_iv(chain, spot)

    if call_25 is None or put_25 is None:
        LOGGER.warning("25d skew strikes not found.")
        return {"rr25": None, "bf25": None}

    rr25 = call_25 - put_25
    bf25 = 0.5 * (call_25 + put_25) - atm_iv
    return {"rr25": rr25, "bf25": bf25}


def _closest_delta(frame: pd.DataFrame, target: float) -> float | None:
    if frame.empty:
        return None
    frame = frame.copy()
    frame["dist"] = (frame["delta"] - target).abs()
    iv = frame.sort_values("dist").iloc[0]["impliedVolatility"]
    return float(iv) if pd.notna(iv) else None


def _atm_iv(chain: pd.DataFrame, spot: float) -> float:
    chain = chain.copy()
    chain["distance"] = (chain["strike"] - spot).abs()
    atm_strike = chain.sort_values("distance").iloc[0]["strike"]
    atm = chain[chain["strike"] == atm_strike]
    ivs = atm["impliedVolatility"].dropna()
    if ivs.empty:
        return 0.0
    return float(ivs.mean())
