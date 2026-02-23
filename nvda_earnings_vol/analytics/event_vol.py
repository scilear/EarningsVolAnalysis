"""Event variance extraction from term structure."""

from __future__ import annotations

import datetime as dt
import logging

import pandas as pd

from nvda_earnings_vol.config import TIME_EPSILON
from nvda_earnings_vol.utils import atm_iv, business_days


LOGGER = logging.getLogger(__name__)


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
    """Compute event variance using total-variance interpolation."""
    front_iv = atm_iv(front_chain, spot)
    back1_iv = atm_iv(back1_chain, spot)

    t_front = max(
        business_days(dt.date.today(), front_expiry) / 252.0,
        TIME_EPSILON,
    )
    t_back1 = max(
        business_days(dt.date.today(), back1_expiry) / 252.0,
        TIME_EPSILON,
    )
    dt_event = max(
        business_days(event_date, front_expiry) / 252.0,
        TIME_EPSILON,
    )

    if back2_chain is not None and back2_expiry is not None:
        back2_iv = atm_iv(back2_chain, spot)
        t_back2 = max(
            business_days(dt.date.today(), back2_expiry) / 252.0,
            TIME_EPSILON,
        )
        # tv_pre is already total variance (T * IV^2); no extra scaling.
        tv_pre = _linear_interp(
            t_back1,
            t_back1 * back1_iv**2,
            t_back2,
            t_back2 * back2_iv**2,
            max(t_front - dt_event, TIME_EPSILON),
        )
        assumption = "Term structure interpolation"
    else:
        tv_pre = max(t_front - dt_event, TIME_EPSILON) * back1_iv**2
        assumption = "Single-point term structure assumption"

    raw_event_var = (t_front * front_iv**2 - tv_pre) / dt_event
    ratio = abs(raw_event_var) / max(front_iv**2, TIME_EPSILON)
    warning_level = None
    if raw_event_var < 0:
        warning_level = "severe" if ratio > 0.10 else "mild"
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
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    x_target: float,
) -> float:
    if x2 == x1:
        return y1
    weight = (x_target - x1) / (x2 - x1)
    return y1 + weight * (y2 - y1)
