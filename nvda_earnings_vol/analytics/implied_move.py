"""Implied move calculation from ATM straddle."""

from __future__ import annotations

import pandas as pd


def implied_move_from_chain(chain: pd.DataFrame, spot: float) -> float:
    """Compute implied move as ATM straddle price divided by spot."""
    chain = chain.copy()
    chain["distance"] = (chain["strike"] - spot).abs()
    atm_strike = chain.sort_values("distance").iloc[0]["strike"]
    atm = chain[chain["strike"] == atm_strike]

    calls = atm[atm["option_type"] == "call"]
    puts = atm[atm["option_type"] == "put"]
    if calls.empty or puts.empty:
        raise ValueError("ATM straddle not found in chain.")

    call_mid = float(calls.iloc[0]["mid"])
    put_mid = float(puts.iloc[0]["mid"])
    straddle = call_mid + put_mid
    return straddle / spot
