"""Event variance extraction from term structure."""

from __future__ import annotations

import datetime as dt
import logging

import pandas as pd

from nvda_earnings_vol.config import TIME_EPSILON


LOGGER = logging.getLogger(__name__)


def _business_days(start: dt.date, end: dt.date) -> int:
    if end <= start:
        return 0
    return pd.bdate_range(start, end).size - 1


def _atm_iv(chain: pd.DataFrame, spot: float) -> float:
    chain = chain.copy()
    chain["distance"] = (chain["strike"] - spot).abs()
    atm_strike = chain.sort_values("distance").iloc[0]["strike"]
    atm = chain[chain["strike"] == atm_strike]
    ivs = atm["impliedVolatility"].dropna()
    if ivs.empty:
        raise ValueError("ATM IV not available.")
    return float(ivs.mean())


def event_variance(
    front_chain: pd.DataFrame,
    back1_chain: pd.DataFrame,
    back2_chain: pd.DataFrame | None,
    spot: float,
    event_date: dt.date,
    front_expiry: dt.date,
    back1_expiry: dt.date,
    back2_expiry: dt.date | None,
) -> dict[str, float | str | None]:
    """Compute event variance and diagnostics using total variance interpolation."""
    front_iv = _atm_iv(front_chain, spot)
    back1_iv = _atm_iv(back1_chain, spot)

    t_front = max(_business_days(dt.date.today(), front_expiry) / 252.0, TIME_EPSILON)
    t_back1 = max(_business_days(dt.date.today(), back1_expiry) / 252.0, TIME_EPSILON)
    dt_event = max(_business_days(event_date, front_expiry) / 252.0, TIME_EPSILON)

    if back2_chain is not None and back2_expiry is not None:
        back2_iv = _atm_iv(back2_chain, spot)
        t_back2 = max(_business_days(dt.date.today(), back2_expiry) / 252.0, TIME_EPSILON)
        tv_pre = _linear_interp(
            t_back1,
            t_back1 * back1_iv**2,
            t_back2,
            t_back2 * back2_iv**2,
            max(t_front - dt_event, TIME_EPSILON),
        )
        assumption = "term_structure_interpolation"
    else:
        tv_pre = max(t_front - dt_event, TIME_EPSILON) * back1_iv**2
        assumption = "single_point"

    raw_event_var = (t_front * front_iv**2 - tv_pre) / dt_event
    ratio = abs(raw_event_var) / max(front_iv**2, TIME_EPSILON)
    warning_level = None
    if raw_event_var < 0:
        warning_level = "mild" if ratio < 0.25 else "severe"
        LOGGER.warning("Negative event variance detected: %.6f", raw_event_var)

    event_var = max(raw_event_var, 0.0)
    return {
        "front_iv": front_iv,
        "back_iv": back1_iv,
        "event_var": event_var,
        "raw_event_var": raw_event_var,
        "ratio": ratio,
        "warning_level": warning_level,
        "assumption": assumption,
        "dt_event": dt_event,
    }


def _linear_interp(
    x1: float, y1: float, x2: float, y2: float, x_target: float
) -> float:
    if x2 == x1:
        return y1
    weight = (x_target - x1) / (x2 - x1)
    return y1 + weight * (y2 - y1)
