"""Historical realized earnings move analysis."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd


def earnings_move_p75(history: pd.DataFrame, earnings_dates: list[pd.Timestamp]) -> float:
    """Return 75th percentile of absolute earnings gap moves."""
    if history.empty:
        raise ValueError("No price history available.")
    if not earnings_dates:
        raise ValueError("No earnings dates available for historical moves.")

    history = history.copy()
    history["Date"] = pd.to_datetime(history["Date"]).dt.date
    close_map = history.set_index("Date")["Close"].to_dict()
    trading_days = sorted(close_map.keys())

    abs_moves = []
    for earnings_dt in earnings_dates:
        target_date = earnings_dt.date()
        event_date = _next_trading_day(trading_days, target_date)
        prev_date = _prev_trading_day(trading_days, event_date)
        if event_date is None or prev_date is None:
            continue
        prev_close = close_map[prev_date]
        event_close = close_map[event_date]
        abs_moves.append(abs(event_close / prev_close - 1.0))

    if len(abs_moves) < 2:
        raise ValueError("Insufficient earnings moves to compute P75.")
    return float(np.percentile(np.array(abs_moves), 75))


def _next_trading_day(trading_days: list[dt.date], target: dt.date) -> dt.date | None:
    for day in trading_days:
        if day >= target:
            return day
    return None


def _prev_trading_day(trading_days: list[dt.date], target: dt.date | None) -> dt.date | None:
    if target is None:
        return None
    prev = None
    for day in trading_days:
        if day >= target:
            return prev
        prev = day
    return prev
