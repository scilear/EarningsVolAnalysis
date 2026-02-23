"""Gamma exposure calculations."""

from __future__ import annotations

import pandas as pd

from nvda_earnings_vol.analytics.bsm import option_gamma
from nvda_earnings_vol.config import (
    CONTRACT_MULTIPLIER,
    DIVIDEND_YIELD,
    GEX_RANGE_PCT,
    RISK_FREE_RATE,
)


def gex_summary(
    chain: pd.DataFrame, spot: float, t: float, gex_range_pct: float = GEX_RANGE_PCT
) -> dict[str, float]:
    """Compute net and absolute gamma exposure.

    Assumes dealers are net short options.
    """
    chain = chain.copy()
    if gex_range_pct > 0:
        lower = spot * (1 - gex_range_pct)
        upper = spot * (1 + gex_range_pct)
        chain = chain[(chain["strike"] >= lower) & (chain["strike"] <= upper)].copy()
    if chain.empty:
        return {"net_gex": 0.0, "abs_gex": 0.0}
    chain["gamma"] = chain.apply(
        lambda row: option_gamma(
            spot,
            row["strike"],
            t,
            RISK_FREE_RATE,
            DIVIDEND_YIELD,
            row["impliedVolatility"],
        ),
        axis=1,
    )
    chain["gex"] = (
        chain["gamma"] * chain["openInterest"] * CONTRACT_MULTIPLIER * spot**2
    )
    net_gex = -float(chain["gex"].sum())
    abs_gex = float(chain["gex"].abs().sum())
    return {"net_gex": net_gex, "abs_gex": abs_gex}
