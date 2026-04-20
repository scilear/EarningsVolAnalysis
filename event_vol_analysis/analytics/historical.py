"""Historical realized earnings move analysis."""

from __future__ import annotations

import datetime as dt
import logging

import numpy as np
import pandas as pd
from scipy import stats


LOGGER = logging.getLogger(__name__)


def compute_distribution_shape(signed_moves: list[float]) -> dict:
    """
    Compute distribution shape statistics from historical earnings moves.
    
    Parameters
    ----------
    signed_moves : list of float
        List of signed percentage returns (not absolute values)
    
    Returns
    -------
    dict with distribution statistics:
        - mean_abs_move: mean of absolute moves
        - median_abs_move: median of absolute moves
        - skewness: skewness of signed moves
        - kurtosis: excess kurtosis of signed moves
        - tail_probs: dict of P(|Move| > threshold) for various thresholds
    """
    if not signed_moves:
        return {
            "mean_abs_move": 0.0,
            "median_abs_move": 0.0,
            "skewness": 0.0,
            "kurtosis": 0.0,
            "tail_probs": {},
        }
    
    arr = np.array(signed_moves)
    abs_arr = np.abs(arr)
    
    # Tail probability thresholds
    tail_thresholds = [0.05, 0.08, 0.10, 0.12, 0.15]
    tail_probs = {
        t: float(np.mean(abs_arr > t))
        for t in tail_thresholds
    }
    
    return {
        "mean_abs_move": float(np.mean(abs_arr)),
        "median_abs_move": float(np.median(abs_arr)),
        "skewness": float(stats.skew(arr)),
        "kurtosis": float(stats.kurtosis(arr)),  # excess kurtosis
        "tail_probs": tail_probs,
    }


def earnings_move_p75(
    history: pd.DataFrame,
    earnings_dates: list[pd.Timestamp],
) -> float:
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
        event_date = _event_trading_day(trading_days, earnings_dt)
        prev_date = _prev_trading_day(trading_days, event_date)
        if event_date is None or prev_date is None:
            continue
        prev_close = close_map[prev_date]
        event_close = close_map[event_date]
        abs_moves.append(abs(event_close / prev_close - 1.0))

    if len(abs_moves) < 2:
        raise ValueError("Insufficient earnings moves to compute P75.")
    if len(abs_moves) < 6:
        LOGGER.warning("Limited earnings move sample size: %d", len(abs_moves))
    return float(np.percentile(np.array(abs_moves), 75))


def _event_trading_day(
    trading_days: list[dt.date], earnings_dt: pd.Timestamp
) -> dt.date | None:
    local_dt = earnings_dt.to_pydatetime()
    is_after_close = local_dt.time() >= dt.time(16, 0)
    target_date = local_dt.date()
    if is_after_close:
        next_day_target = target_date + dt.timedelta(days=1)
        return _next_trading_day(trading_days, next_day_target)
    return _next_trading_day(trading_days, target_date)


def _next_trading_day(
    trading_days: list[dt.date],
    target: dt.date,
) -> dt.date | None:
    for day in trading_days:
        if day >= target:
            return day
    return None


def _prev_trading_day(
    trading_days: list[dt.date],
    target: dt.date | None,
) -> dt.date | None:
    if target is None:
        return None
    prev = None
    for day in trading_days:
        if day >= target:
            return prev
        prev = day
    return prev


def extract_earnings_moves(
    history: pd.DataFrame,
    earnings_dates: list[pd.Timestamp],
) -> list[float]:
    """
    Extract signed earnings gap moves from price history.
    
    Parameters
    ----------
    history : pd.DataFrame
        Price history with 'Date' and 'Close' columns
    earnings_dates : list of pd.Timestamp
        Earnings announcement dates
    
    Returns
    -------
    list of float
        Signed percentage moves (event_close / prev_close - 1.0)
    """
    if history.empty or not earnings_dates:
        return []
    
    history = history.copy()
    history["Date"] = pd.to_datetime(history["Date"]).dt.date
    close_map = history.set_index("Date")["Close"].to_dict()
    trading_days = sorted(close_map.keys())
    
    signed_moves = []
    for earnings_dt in earnings_dates:
        event_date = _event_trading_day(trading_days, earnings_dt)
        prev_date = _prev_trading_day(trading_days, event_date)
        if event_date is None or prev_date is None:
            continue
        prev_close = close_map[prev_date]
        event_close = close_map[event_date]
        signed_moves.append(event_close / prev_close - 1.0)
    
    return signed_moves
