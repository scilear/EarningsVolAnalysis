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

    # Initialize back2 values
    back2_iv: float | None = None
    t_back2: float | None = None
    
    if back2_chain is not None and back2_expiry is not None:
        back2_iv_value = atm_iv(back2_chain, spot)
        t_back2_value = max(
            business_days(dt.date.today(), back2_expiry) / 252.0,
            TIME_EPSILON,
        )
        back2_iv = back2_iv_value
        t_back2 = t_back2_value
        # tv_pre is already total variance (T * IV^2); no extra scaling.
        tv_pre = _linear_interp(
            t_back1,
            t_back1 * back1_iv**2,
            t_back2_value,
            t_back2_value * back2_iv_value**2,
            max(t_front - dt_event, TIME_EPSILON),
        )
        assumption = "Term structure interpolation"
    else:
        # Use two-point interpolation with back1 when available
        tv_pre = max(t_front - dt_event, TIME_EPSILON) * back1_iv**2
        assumption = "Two-point term structure interpolation"

    raw_event_var_annualized = (t_front * front_iv**2 - tv_pre) / dt_event
    event_var_daily = raw_event_var_annualized / 252.0  # Scale to 1-day variance
    ratio = abs(event_var_daily) / max(front_iv**2 / 252.0, TIME_EPSILON)
    warning_level = None
    if raw_event_var_annualized < 0:
        warning_level = "severe" if ratio > 0.10 else "mild"
        LOGGER.warning("Negative event variance detected: %.6f", raw_event_var_annualized)

    event_var = max(event_var_daily, 0.0)

    # Compute additional fields for enhanced reporting
    total_front_var = t_front * front_iv ** 2 / 252.0  # Daily front variance
    raw_event_var = event_var_daily  # Store daily variance for ratio
    event_variance_ratio = raw_event_var / total_front_var if total_front_var > 0 else 0.0
    front_back_spread = front_iv - back1_iv
    back_slope = (back1_iv - back2_iv) if back2_iv is not None else None
    
    # Determine interpolation method
    if back2_chain is not None and back2_expiry is not None:
        interpolation_method = "Three-point total variance interpolation"
    elif back1_iv is not None:
        interpolation_method = "Two-point term structure interpolation"
    else:
        interpolation_method = "Single-point assumption"
    
    # Term structure note
    term_structure_note = None
    if front_iv < back1_iv:
        term_structure_note = "Front IV below back IV; term structure inversion."
    
    return {
        # Original fields
        "front_iv": front_iv,
        "back_iv": back1_iv,
        "event_var": event_var,
        "raw_event_var": raw_event_var,
        "ratio": ratio,
        "warning_level": warning_level,
        "assumption": assumption,
        "dt_event": dt_event,
        
        # NEW — Term Structure fields
        "back2_iv": back2_iv,
        "front_back_spread": front_back_spread,
        "back_slope": back_slope,
        
        # NEW — Time values
        "t_front": t_front,
        "t_back1": t_back1,
        "t_back2": t_back2 if back2_expiry is not None else None,
        
        # NEW — Variance attribution
        "event_variance_ratio": event_variance_ratio,
        "interpolation_method": interpolation_method,
        "negative_event_var": raw_event_var < 0,
        "term_structure_note": term_structure_note,
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
