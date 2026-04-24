"""IV rank and percentile based volatility regime helpers."""

from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

LOGGER = logging.getLogger(__name__)

_CHEAP = "CHEAP"
_NEUTRAL = "NEUTRAL"
_EXPENSIVE = "EXPENSIVE"
_AMBIGUOUS = "AMBIGUOUS"

_BUCKET_STEPS = {
    _CHEAP: 0,
    _NEUTRAL: 1,
    _EXPENSIVE: 2,
}


@dataclass(frozen=True)
class VolRegimeClassification:
    """Structured output for playbook volatility classification."""

    label: str
    ivr: float
    ivp: float
    bucket_ivr: str
    bucket_ivp: str
    confidence: str
    term_structure_slope: float | None
    skew_25d: float | None
    history_points: int
    history_window_days: int

    def to_dict(self) -> dict[str, float | str | None | int]:
        """Return a serializable dictionary representation."""

        return asdict(self)


def classify_vol_regime(
    ivr: float,
    ivp: float,
    *,
    force_low_confidence: bool = False,
    term_structure_slope: float | None = None,
    skew_25d: float | None = None,
    history_points: int = 0,
    history_window_days: int = 365,
) -> VolRegimeClassification:
    """Classify IV regime using IV rank and IV percentile.

    Rules
    -----
    - Same bucket -> that label, HIGH confidence.
    - One-step disagreement -> NEUTRAL, LOW confidence.
    - Two-step disagreement -> AMBIGUOUS, LOW confidence.
    """

    bucket_ivr = _bucket(ivr)
    bucket_ivp = _bucket(ivp)
    diff = abs(_BUCKET_STEPS[bucket_ivr] - _BUCKET_STEPS[bucket_ivp])

    if diff == 0:
        label = bucket_ivr
        confidence = "HIGH"
    elif diff == 1:
        label = _NEUTRAL
        confidence = "LOW"
    else:
        label = _AMBIGUOUS
        confidence = "LOW"

    if force_low_confidence:
        confidence = "LOW"

    return VolRegimeClassification(
        label=label,
        ivr=float(ivr),
        ivp=float(ivp),
        bucket_ivr=bucket_ivr,
        bucket_ivp=bucket_ivp,
        confidence=confidence,
        term_structure_slope=term_structure_slope,
        skew_25d=skew_25d,
        history_points=int(history_points),
        history_window_days=int(history_window_days),
    )


def classify_from_iv_history(
    current_iv: float,
    iv_history: Sequence[float],
    *,
    min_history: int = 60,
    term_structure_slope: float | None = None,
    skew_25d: float | None = None,
    history_window_days: int = 365,
) -> VolRegimeClassification:
    """Compute IVR/IVP from history and classify.

    If history is shorter than ``min_history``, force conservative output:
    ``NEUTRAL`` with ``LOW`` confidence.
    """

    if current_iv is None or np.isnan(current_iv):
        raise ValueError("Current IV is required to classify volatility regime.")

    cleaned_history = [float(value) for value in iv_history if pd.notna(value)]
    ivr, degenerate_range = compute_ivr(
        current_iv=float(current_iv), iv_history=cleaned_history
    )
    ivp = compute_ivp(current_iv=float(current_iv), iv_history=cleaned_history)

    classification = classify_vol_regime(
        ivr,
        ivp,
        force_low_confidence=degenerate_range,
        term_structure_slope=term_structure_slope,
        skew_25d=skew_25d,
        history_points=len(cleaned_history),
        history_window_days=history_window_days,
    )

    if len(cleaned_history) < min_history:
        return VolRegimeClassification(
            label=_NEUTRAL,
            ivr=classification.ivr,
            ivp=classification.ivp,
            bucket_ivr=classification.bucket_ivr,
            bucket_ivp=classification.bucket_ivp,
            confidence="LOW",
            term_structure_slope=classification.term_structure_slope,
            skew_25d=classification.skew_25d,
            history_points=classification.history_points,
            history_window_days=classification.history_window_days,
        )

    return classification


def compute_ivr(
    current_iv: float,
    iv_history: Sequence[float],
) -> tuple[float, bool]:
    """Compute IV rank (0-100) and return whether range is degenerate."""

    if current_iv is None or np.isnan(current_iv):
        raise ValueError("Current IV is required for IV rank calculation.")

    if not iv_history:
        return 50.0, True

    iv_low = float(np.min(iv_history))
    iv_high = float(np.max(iv_history))

    if np.isclose(iv_high, iv_low):
        return 50.0, True

    raw = (float(current_iv) - iv_low) / (iv_high - iv_low) * 100.0
    return float(np.clip(raw, 0.0, 100.0)), False


def compute_ivp(current_iv: float, iv_history: Sequence[float]) -> float:
    """Compute IV percentile (0-100) from the supplied history."""

    if current_iv is None or np.isnan(current_iv):
        raise ValueError("Current IV is required for IV percentile calculation.")
    if not iv_history:
        return 50.0

    arr = np.array(iv_history, dtype=float)
    return float(np.mean(arr < float(current_iv)) * 100.0)


def compute_term_structure_slope(
    front_iv: float,
    back_iv: float,
) -> float | None:
    """Return normalized term-structure slope: (front-back)/back."""

    if back_iv is None or front_iv is None:
        return None
    if back_iv <= 0:
        return None
    return float((front_iv - back_iv) / back_iv)


def rr25_to_skew_25d(rr25: float | None) -> float | None:
    """Convert risk-reversal sign convention to put-minus-call skew."""

    if rr25 is None:
        return None
    return float(-rr25)


def load_atm_iv_history_from_store(
    ticker: str,
    *,
    db_path: str | Path = "data/options_intraday.db",
    as_of_date: dt.date | None = None,
    lookback_days: int = 365,
    min_dte: int = 7,
    max_dte: int = 60,
) -> list[float]:
    """Load 1-year daily ATM IV history from local options cache.

    Returns an empty list when the cache does not exist or no suitable rows
    are found.
    """

    db_file = Path(db_path)
    if not db_file.exists():
        return []

    end_date = as_of_date or dt.date.today()
    start_date = end_date - dt.timedelta(days=lookback_days)

    query = """
        SELECT
            timestamp,
            strike,
            implied_volatility,
            underlying_price,
            days_to_expiry
        FROM option_quotes
        WHERE ticker = ?
          AND timestamp >= ?
          AND timestamp <= ?
          AND data_quality = 'valid'
          AND implied_volatility IS NOT NULL
          AND underlying_price IS NOT NULL
          AND days_to_expiry BETWEEN ? AND ?
        ORDER BY timestamp ASC
    """

    try:
        with sqlite3.connect(db_file) as conn:
            frame = pd.read_sql_query(
                query,
                conn,
                params=[
                    ticker.upper(),
                    f"{start_date.isoformat()} 00:00:00",
                    f"{end_date.isoformat()} 23:59:59",
                    min_dte,
                    max_dte,
                ],
            )
    except Exception as exc:  # pragma: no cover
        LOGGER.warning(
            "Could not load ATM IV history for %s from %s: %s",
            ticker,
            db_file,
            exc,
        )
        return []

    if frame.empty:
        return []

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame = frame.dropna(
        subset=["timestamp", "strike", "implied_volatility", "underlying_price"]
    )
    if frame.empty:
        return []

    frame["distance_to_atm"] = (frame["strike"] - frame["underlying_price"]).abs()
    nearest = (
        frame.sort_values(["timestamp", "distance_to_atm"])
        .groupby("timestamp", as_index=False)
        .first()
    )
    nearest["trade_date"] = nearest["timestamp"].dt.date
    daily = (
        nearest.sort_values("timestamp").groupby("trade_date", as_index=False).tail(1)
    )

    return daily["implied_volatility"].astype(float).tolist()


def _bucket(value: float) -> str:
    if value < 30.0:
        return _CHEAP
    if value > 60.0:
        return _EXPENSIVE
    return _NEUTRAL
