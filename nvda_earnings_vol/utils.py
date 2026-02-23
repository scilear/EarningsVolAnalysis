"""Shared utility functions."""

from __future__ import annotations

import datetime as dt

import pandas as pd


def business_days(start: dt.date, end: dt.date) -> int:
    """Return number of business days between start and end."""
    if end <= start:
        return 0
    return pd.bdate_range(start, end).size - 1


def atm_iv(chain: pd.DataFrame, spot: float) -> float:
    """Return mean IV of the ATM strike in chain."""
    chain = chain.copy()
    chain["distance"] = (chain["strike"] - spot).abs()
    atm_strike = chain.sort_values("distance").iloc[0]["strike"]
    atm = chain[chain["strike"] == atm_strike]
    ivs = atm["impliedVolatility"].dropna()
    if ivs.empty:
        raise ValueError("ATM IV not available.")
    return float(ivs.mean())
