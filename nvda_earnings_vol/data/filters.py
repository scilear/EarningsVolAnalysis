"""Option chain filtering and slippage utilities."""

from __future__ import annotations

import numpy as np
import pandas as pd


def filter_by_moneyness(
    chain: pd.DataFrame, spot: float, low: float, high: float
) -> pd.DataFrame:
    """Filter options by strike moneyness range."""
    min_strike = spot * low
    max_strike = spot * high
    mask = (chain["strike"] >= min_strike) & (chain["strike"] <= max_strike)
    return chain.loc[mask].copy()


def filter_by_liquidity(
    chain: pd.DataFrame, min_oi: int, max_spread_pct: float
) -> pd.DataFrame:
    """Filter by open interest and spread percentage."""
    chain = chain.copy()
    chain["spread_pct"] = chain["spread"] / chain["mid"].replace(0.0, pd.NA)
    mask = (
        (chain["openInterest"] >= min_oi)
        & (chain["spread_pct"] <= max_spread_pct)
    )
    return chain.loc[mask].dropna(subset=["spread_pct"]).copy()


def execution_price(
    mid: float, spread: float, side: str, slippage_pct: float
) -> float:
    """Return execution price adjusted by slippage.

    Slippage crosses slippage_pct of half-spread.
    """
    half_spread = 0.5 * spread
    adjustment = half_spread * slippage_pct
    if side == "buy":
        return mid + adjustment
    if side == "sell":
        return mid - adjustment
    raise ValueError("side must be 'buy' or 'sell'")


def execution_price_vec(
    mid_arr: np.ndarray, spread: float, side: str, slippage_pct: float
) -> np.ndarray:
    """Vectorized execution price adjusted by slippage.

    Args:
        mid_arr: Array of mid prices (shape: (N,))
        spread: Spread (scalar, from option lookup)
        side: 'buy' or 'sell'
        slippage_pct: Slippage percentage to cross

    Returns:
        Array of execution prices (shape: (N,))
    """
    mid_arr = np.asarray(mid_arr, dtype=np.float64)
    half_spread_cost = 0.5 * spread * slippage_pct
    if side == "buy":
        return mid_arr + half_spread_cost
    if side == "sell":
        return mid_arr - half_spread_cost
    raise ValueError("side must be 'buy' or 'sell'")
