"""Gamma exposure calculations."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from event_vol_analysis.analytics.bsm import delta as option_delta
from event_vol_analysis.analytics.bsm import gamma as option_gamma
from event_vol_analysis.config import (
    CONTRACT_MULTIPLIER,
    DIVIDEND_YIELD,
    GEX_RANGE_PCT,
    RISK_FREE_RATE,
)


ONE_DAY_IN_YEARS = 1.0 / 365.0
IV_BUMP = 0.01


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


def identify_pin_strikes(
    gex_by_strike: Mapping[float, float],
    threshold_pct: float = 0.15,
) -> list[dict[str, float]]:
    """Identify strikes where |GEX| exceeds threshold share of abs GEX.

    Args:
        gex_by_strike: Mapping of strike to net strike-level GEX.
        threshold_pct: Minimum |GEX| share of total absolute GEX.

    Returns:
        List of pin-strike rows sorted by |GEX| descending.
    """
    if not gex_by_strike:
        return []

    total_abs = sum(abs(float(value)) for value in gex_by_strike.values())
    if total_abs <= 0.0:
        return []

    pins: list[dict[str, float]] = []
    for strike, value in gex_by_strike.items():
        abs_pct = abs(float(value)) / total_abs
        if abs_pct >= threshold_pct:
            pins.append(
                {
                    "strike": float(strike),
                    "gex": float(value),
                    "abs_pct": float(abs_pct),
                }
            )

    pins.sort(key=lambda row: abs(row["gex"]), reverse=True)
    return pins


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
        reverse=True,
    )[:n]


def compute_vanna_exposure(
    chain: pd.DataFrame,
    spot: float,
    t: float,
    *,
    div_yield: float = DIVIDEND_YIELD,
    iv_bump: float = IV_BUMP,
) -> float:
    """Estimate net vanna exposure in dollar terms.

    Vanna is approximated via finite-difference of delta with respect to IV:
    d(delta)/d(iv). Exposure is signed by option type under the same dealer
    convention used for GEX (calls negative, puts positive), and scaled by
    OI * contract multiplier * spot.
    """
    if chain.empty or t <= 0:
        return 0.0

    exposure = 0.0
    for row in chain.itertuples(index=False):
        iv = float(getattr(row, "impliedVolatility", 0.0) or 0.0)
        strike = float(getattr(row, "strike", 0.0) or 0.0)
        oi = float(getattr(row, "openInterest", 0.0) or 0.0)
        option_type = str(getattr(row, "option_type", "")).lower()
        if iv <= 0.0 or strike <= 0.0 or oi <= 0.0:
            continue
        if option_type not in {"call", "put"}:
            continue

        lower_iv = max(iv - iv_bump, 1e-4)
        upper_iv = iv + iv_bump
        if upper_iv <= lower_iv:
            continue

        delta_up = option_delta(
            spot,
            strike,
            t,
            RISK_FREE_RATE,
            div_yield,
            upper_iv,
            option_type,
        )
        delta_down = option_delta(
            spot,
            strike,
            t,
            RISK_FREE_RATE,
            div_yield,
            lower_iv,
            option_type,
        )
        vanna = (delta_up - delta_down) / (upper_iv - lower_iv)
        sign = -1.0 if option_type == "call" else 1.0
        exposure += sign * vanna * oi * CONTRACT_MULTIPLIER * spot

    return float(exposure)


def compute_charm_exposure(
    chain: pd.DataFrame,
    spot: float,
    t: float,
    *,
    div_yield: float = DIVIDEND_YIELD,
    day_step: float = ONE_DAY_IN_YEARS,
) -> float:
    """Estimate net charm exposure as delta change per day.

    Charm is approximated by repricing delta one calendar day closer to expiry.
    Returned value is net delta-per-day in shares (scaled by OI and contract
    multiplier), signed by the same dealer convention used for GEX.
    """
    if chain.empty or t <= day_step:
        return 0.0

    t_next = max(t - day_step, 1e-6)
    exposure = 0.0
    for row in chain.itertuples(index=False):
        iv = float(getattr(row, "impliedVolatility", 0.0) or 0.0)
        strike = float(getattr(row, "strike", 0.0) or 0.0)
        oi = float(getattr(row, "openInterest", 0.0) or 0.0)
        option_type = str(getattr(row, "option_type", "")).lower()
        if iv <= 0.0 or strike <= 0.0 or oi <= 0.0:
            continue
        if option_type not in {"call", "put"}:
            continue

        delta_now = option_delta(
            spot,
            strike,
            t,
            RISK_FREE_RATE,
            div_yield,
            iv,
            option_type,
        )
        delta_next = option_delta(
            spot,
            strike,
            t_next,
            RISK_FREE_RATE,
            div_yield,
            iv,
            option_type,
        )
        charm_per_day = delta_next - delta_now
        sign = -1.0 if option_type == "call" else 1.0
        exposure += sign * charm_per_day * oi * CONTRACT_MULTIPLIER

    return float(exposure)


def gex_summary(
    chain: pd.DataFrame,
    spot: float,
    t: float,
    gex_range_pct: float = GEX_RANGE_PCT,
    div_yield: float = DIVIDEND_YIELD,
) -> dict[str, float | None | list]:
    """Compute net and absolute gamma exposure.

    Applies sign convention: calls contribute negative GEX
    (dealers short calls), puts contribute positive GEX
    (dealers short puts). This enables positive
    net GEX when put-heavy positioning dominates.
    """
    chain = chain.copy()
    if gex_range_pct > 0:
        lower = spot * (1 - gex_range_pct)
        upper = spot * (1 + gex_range_pct)
        mask = (chain["strike"] >= lower) & (chain["strike"] <= upper)
        chain = chain[mask].copy()

    if chain.empty:
        return {
            "net_gex": 0.0,
            "abs_gex": 0.0,
            "gamma_flip": None,
            "flip_distance_pct": None,
            "top_gamma_strikes": [],
            "gex_by_strike": [],
            "pin_strikes": [],
            "vanna_net": 0.0,
            "charm_net": 0.0,
        }

    chain["gamma"] = chain.apply(
        lambda row: option_gamma(
            spot,
            row["strike"],
            t,
            RISK_FREE_RATE,
            div_yield,
            row["impliedVolatility"],
            row["option_type"],  # call or put
        ),
        axis=1,
    )
    # Apply sign convention:
    # calls = negative GEX (dealers short), puts = positive GEX.
    chain["gex"] = chain.apply(
        lambda row: (
            (-1.0 if row["option_type"] == "call" else 1.0)
            * row["gamma"]
            * row["openInterest"]
            * CONTRACT_MULTIPLIER
            * spot**2
        ),
        axis=1,
    )

    # Aggregate by strike
    gex_by_strike = chain.groupby("strike")["gex"].sum().to_dict()

    net_gex = float(chain["gex"].sum())
    abs_gex = float(chain["gex"].abs().sum())

    vanna_net = compute_vanna_exposure(chain, spot, t, div_yield=div_yield)
    charm_net = compute_charm_exposure(chain, spot, t, div_yield=div_yield)

    # Find gamma flip
    gamma_flip = find_gamma_flip(gex_by_strike)
    flip_distance_pct = None
    if gamma_flip is not None:
        flip_distance_pct = (gamma_flip - spot) / spot * 100

    # Top gamma strikes
    top_strikes = top_gamma_strikes(gex_by_strike, n=3)
    pin_strikes = identify_pin_strikes(gex_by_strike)
    by_strike = sorted(gex_by_strike.items(), key=lambda row: float(row[0]))

    return {
        "net_gex": net_gex,
        "abs_gex": abs_gex,
        "gamma_flip": gamma_flip,
        "flip_distance_pct": flip_distance_pct,
        "top_gamma_strikes": top_strikes,
        "gex_by_strike": by_strike,
        "pin_strikes": pin_strikes,
        "vanna_net": vanna_net,
        "charm_net": charm_net,
    }
