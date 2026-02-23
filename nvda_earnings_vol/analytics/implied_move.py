"""Implied move calculation from ATM straddle."""

from __future__ import annotations

import logging

import pandas as pd

from nvda_earnings_vol.config import IMPLIED_MOVE_MAX_SPREAD_PCT
from nvda_earnings_vol.data.filters import execution_price


LOGGER = logging.getLogger(__name__)


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
    _warn_wide_spread(call_row, put_row)
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


def _warn_wide_spread(call_row: pd.Series, put_row: pd.Series) -> None:
    call_mid = float(call_row["mid"])
    call_spread = float(call_row["spread"])
    put_mid = float(put_row["mid"])
    put_spread = float(put_row["spread"])

    call_pct = call_spread / call_mid if call_mid > 0 else float("inf")
    put_pct = put_spread / put_mid if put_mid > 0 else float("inf")

    if call_pct > IMPLIED_MOVE_MAX_SPREAD_PCT or put_pct > IMPLIED_MOVE_MAX_SPREAD_PCT:
        LOGGER.warning(
            "ATM spread exceeds %.2f%% of mid (call=%.2f%%, put=%.2f%%)",
            IMPLIED_MOVE_MAX_SPREAD_PCT * 100,
            call_pct * 100,
            put_pct * 100,
        )
