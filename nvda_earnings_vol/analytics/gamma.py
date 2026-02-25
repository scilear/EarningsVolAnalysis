"""Gamma exposure calculations."""

from __future__ import annotations

import pandas as pd

from nvda_earnings_vol.analytics.bsm import gamma as option_gamma
from nvda_earnings_vol.config import (
    CONTRACT_MULTIPLIER,
    DIVIDEND_YIELD,
    GEX_RANGE_PCT,
    RISK_FREE_RATE,
)


def find_gamma_flip(gex_by_strike: dict) -> float | None:
    """
    Find the strike where cumulative GEX crosses zero.
    
    Parameters
    ----------
    gex_by_strike : dict
        {strike: gex_value} mapping
    
    Returns
    -------
    float | None
        Interpolated strike where net gamma flips sign, or None if no crossing
    """
    if not gex_by_strike:
        return None
    
    strikes = sorted(gex_by_strike.keys())
    cum_gex = []
    running = 0.0
    
    for k in strikes:
        running += gex_by_strike[k]
        cum_gex.append((k, running))
    
    # Find sign change
    for i in range(1, len(cum_gex)):
        k0, g0 = cum_gex[i - 1]
        k1, g1 = cum_gex[i]
        if g0 * g1 < 0:
            # Linear interpolation
            flip = k0 + (k1 - k0) * abs(g0) / (abs(g0) + abs(g1))
            return round(flip, 2)
    
    return None


def top_gamma_strikes(gex_by_strike: dict, n: int = 3) -> list[tuple]:
    """
    Return top N strikes by absolute GEX value.
    
    Parameters
    ----------
    gex_by_strike : dict
        {strike: gex_value} mapping
    n : int
        Number of top strikes to return
    
    Returns
    -------
    list of tuples
        [(strike, gex_value), ...] sorted by |gex| descending
    """
    if not gex_by_strike:
        return []
    
    return sorted(
        gex_by_strike.items(),
        key=lambda x: abs(x[1]),
        reverse=True
    )[:n]


def gex_summary(
    chain: pd.DataFrame,
    spot: float,
    t: float,
    gex_range_pct: float = GEX_RANGE_PCT,
) -> dict[str, float | None | list]:
    """Compute net and absolute gamma exposure.

    Applies sign convention: calls contribute negative GEX (dealers short calls),
    puts contribute positive GEX (dealers short puts). This enables positive
    net GEX when put-heavy positioning dominates.
    """
    chain = chain.copy()
    if gex_range_pct > 0:
        lower = spot * (1 - gex_range_pct)
        upper = spot * (1 + gex_range_pct)
        chain = chain[
            (chain["strike"] >= lower) & (chain["strike"] <= upper)
        ].copy()
    
    if chain.empty:
        return {
            "net_gex": 0.0,
            "abs_gex": 0.0,
            "gamma_flip": None,
            "flip_distance_pct": None,
            "top_gamma_strikes": [],
        }
    
    chain["gamma"] = chain.apply(
        lambda row: option_gamma(
            spot,
            row["strike"],
            t,
            RISK_FREE_RATE,
            DIVIDEND_YIELD,
            row["impliedVolatility"],
            row["option_type"],  # call or put
        ),
        axis=1,
    )
    # Apply sign convention: calls = negative GEX (dealers short), puts = positive GEX
    chain["gex"] = chain.apply(
        lambda row: (
            -1.0 if row["option_type"] == "call" else 1.0
        ) * row["gamma"] * row["openInterest"] * CONTRACT_MULTIPLIER * spot**2,
        axis=1,
    )

    # Aggregate by strike
    gex_by_strike = chain.groupby("strike")["gex"].sum().to_dict()

    net_gex = float(chain["gex"].sum())  # Remove negative sign, already applied per option type
    abs_gex = float(chain["gex"].abs().sum())
    
    # Find gamma flip
    gamma_flip = find_gamma_flip(gex_by_strike)
    flip_distance_pct = None
    if gamma_flip is not None:
        flip_distance_pct = (gamma_flip - spot) / spot * 100
    
    # Top gamma strikes
    top_strikes = top_gamma_strikes(gex_by_strike, n=3)
    
    return {
        "net_gex": net_gex,
        "abs_gex": abs_gex,
        "gamma_flip": gamma_flip,
        "flip_distance_pct": flip_distance_pct,
        "top_gamma_strikes": top_strikes,
    }
