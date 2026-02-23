"""Implied move calculation from ATM straddle."""

from __future__ import annotations

import pandas as pd

from nvda_earnings_vol.data.filters import execution_price


def implied_move_from_chain(
    chain: pd.DataFrame, spot: float, slippage_pct: float
) -> float:
    """Compute implied move as slippage-adjusted ATM straddle price / spot."""
    chain = chain.copy()
    chain["distance"] = (chain["strike"] - spot).abs()
    atm_strike = chain.sort_values("distance").iloc[0]["strike"]
    atm = chain[chain["strike"] == atm_strike]

    calls = atm[atm["option_type"] == "call"]
    puts = atm[atm["option_type"] == "put"]
    if calls.empty or puts.empty:
        raise ValueError("ATM straddle not found in chain.")

    call_row = calls.iloc[0]
    put_row = puts.iloc[0]
    call_price = execution_price(
        float(call_row["mid"]),
        float(call_row["spread"]),
        "buy",
        slippage_pct,
    )
    put_price = execution_price(
        float(put_row["mid"]),
        float(put_row["spread"]),
        "buy",
        slippage_pct,
    )
    straddle = call_price + put_price
    return straddle / spot
