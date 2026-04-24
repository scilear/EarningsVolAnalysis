"""Historical realized earnings move analysis."""

from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from scipy import stats

from event_vol_analysis import config

LOGGER = logging.getLogger(__name__)

DEFAULT_EVENT_DB_PATH = Path("data/options_intraday.db")


@dataclass(frozen=True)
class ConditionalExpected:
    """Conditional expected move estimate bundle for one name."""

    median: float
    trimmed_mean: float | None
    recency_weighted: float | None
    timing_method: str
    n_observations: int
    data_quality: str
    conditioning_applied: list[str]
    primary_estimate: float
    peer_conditioned: float | None = None


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

    arr = np.array(signed_moves, dtype=float)
    abs_arr = np.abs(arr)

    # Tail probability thresholds
    tail_thresholds = [0.05, 0.08, 0.10, 0.12, 0.15]
    tail_probs = {t: float(np.mean(abs_arr > t)) for t in tail_thresholds}

    skewness = float(stats.skew(arr)) if len(arr) >= 3 else 0.0
    kurtosis = float(stats.kurtosis(arr)) if len(arr) >= 4 else 0.0
    skewness = 0.0 if np.isnan(skewness) else skewness
    kurtosis = 0.0 if np.isnan(kurtosis) else kurtosis

    return {
        "mean_abs_move": float(np.mean(abs_arr)),
        "median_abs_move": float(np.median(abs_arr)),
        "skewness": skewness,
        "kurtosis": kurtosis,  # excess kurtosis
        "tail_probs": tail_probs,
    }


def calibrate_fat_tail_inputs(
    signed_moves: list[float],
) -> dict[str, float | int | bool]:
    """Calibrate fat-tail simulation inputs from historical earnings moves."""
    sample_size = len(signed_moves)
    dist_shape = compute_distribution_shape(signed_moves)
    raw_kurtosis = max(float(dist_shape["kurtosis"]), 0.0)

    if sample_size < config.FAT_TAIL_MIN_HISTORY_MOVES:
        return {
            "sample_size": sample_size,
            "raw_excess_kurtosis": raw_kurtosis,
            "target_excess_kurtosis": 0.0,
            "fat_tail_active": False,
        }

    sample_weight = min(
        1.0,
        sample_size / float(config.FAT_TAIL_CALIBRATION_FULL_SAMPLE),
    )
    target_excess_kurtosis = raw_kurtosis * sample_weight
    target_excess_kurtosis = min(
        target_excess_kurtosis,
        config.FAT_TAIL_MAX_EXCESS_KURTOSIS,
    )

    return {
        "sample_size": sample_size,
        "raw_excess_kurtosis": raw_kurtosis,
        "target_excess_kurtosis": target_excess_kurtosis,
        "fat_tail_active": target_excess_kurtosis > 0.0,
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
    _, signed_moves = extract_earnings_moves_with_dates(history, earnings_dates)
    return signed_moves


def extract_earnings_moves_with_dates(
    history: pd.DataFrame,
    earnings_dates: list[pd.Timestamp],
) -> tuple[list[pd.Timestamp], list[float]]:
    """Extract signed earnings moves with aligned event dates.

    Returns
    -------
    tuple[list[pd.Timestamp], list[float]]
        Aligned (event_dates_used, signed_moves), preserving input order
        for dates that have usable pricing windows.
    """

    if history.empty or not earnings_dates:
        return [], []

    history = history.copy()
    history["Date"] = pd.to_datetime(history["Date"]).dt.date
    close_map = history.set_index("Date")["Close"].to_dict()
    trading_days = sorted(close_map.keys())

    aligned_dates: list[pd.Timestamp] = []
    signed_moves: list[float] = []
    for earnings_dt in earnings_dates:
        event_date = _event_trading_day(trading_days, earnings_dt)
        prev_date = _prev_trading_day(trading_days, event_date)
        if event_date is None or prev_date is None:
            continue
        prev_close = close_map[prev_date]
        event_close = close_map[event_date]
        signed_moves.append(event_close / prev_close - 1.0)
        aligned_dates.append(pd.Timestamp(earnings_dt).normalize())

    return aligned_dates, signed_moves


def trimmed_mean_move(moves: Sequence[float]) -> float:
    """Compute trimmed mean of absolute moves.

    Excludes exactly one top and one bottom observation.
    Requires at least four observations after trimming.
    """

    abs_moves = _abs_moves(moves)
    if len(abs_moves) < 6:
        raise ValueError("trimmed_mean_move requires at least 6 observations.")
    trimmed = sorted(abs_moves)[1:-1]
    return float(np.mean(trimmed))


def recency_weighted_mean(
    moves: Sequence[float],
    n_recent: int = 4,
    recent_weight: float = 2.0,
) -> float:
    """Compute recency-weighted mean absolute move.

    Input ordering is assumed oldest-first.
    """

    abs_moves = _abs_moves(moves)
    if len(abs_moves) < n_recent:
        raise ValueError(
            f"recency_weighted_mean requires at least {n_recent} observations."
        )

    weights = np.ones(len(abs_moves), dtype=float)
    weights[-n_recent:] = recent_weight
    values = np.array(abs_moves, dtype=float)
    return float(np.average(values, weights=weights))


def split_by_timing(
    ticker: str,
    dates: Sequence[pd.Timestamp],
    moves: Sequence[float],
    *,
    db_path: Path | str = DEFAULT_EVENT_DB_PATH,
    allow_yfinance_fallback: bool = True,
) -> dict[str, list[float]]:
    """Split earnings moves by event timing label (amc/bmo/unknown).

    Timing is resolved from the event registry when available.
    """

    if len(dates) != len(moves):
        raise ValueError("dates and moves must be aligned and have equal length.")

    result: dict[str, list[float]] = {
        "amc": [],
        "bmo": [],
        "unknown": [],
    }
    timing_map = _load_event_timing_map(ticker, db_path=Path(db_path))
    yfinance_timing_map: dict[dt.date, str | None] | None = None

    for date_value, move in zip(dates, moves):
        event_date = pd.Timestamp(date_value).date()
        label = timing_map.get(event_date)
        if label is None and allow_yfinance_fallback:
            if yfinance_timing_map is None:
                yfinance_timing_map = _load_event_timing_map_from_yfinance(ticker)
            label = yfinance_timing_map.get(event_date)
        bucket = _timing_bucket(label)
        if bucket == "unknown":
            LOGGER.warning(
                "Timing unresolved for %s on %s; assigning to 'unknown'.",
                ticker,
                event_date,
            )
        result[bucket].append(abs(float(move)))

    return result


def conditional_expected_move(
    moves: Sequence[float],
    *,
    timing: str | None = None,
    vix_quartile: int | None = None,
    drift_sign: int | None = None,
    peer_median: float | None = None,
    conditioning_frame: pd.DataFrame | None = None,
) -> ConditionalExpected:
    """Build conditional expected move estimates with graceful degradation."""

    abs_moves = _abs_moves(moves)
    if not abs_moves:
        raise ValueError("conditional_expected_move requires at least one move.")

    selected = list(abs_moves)
    timing_method = (
        timing if timing in {"amc", "bmo", "combined", "unknown"} else "combined"
    )

    conditioning_applied: list[str] = []
    if conditioning_frame is not None and not conditioning_frame.empty:
        if len(conditioning_frame) != len(abs_moves):
            raise ValueError("conditioning_frame must align to moves length.")
        frame = conditioning_frame.copy()
        frame["abs_move"] = np.array(abs_moves, dtype=float)

        if timing in {"amc", "bmo"}:
            timing_filtered = frame[frame["timing"].astype(str).str.lower() == timing]
            if len(timing_filtered) >= 4:
                frame = timing_filtered
                selected = frame["abs_move"].tolist()
                timing_method = timing
                conditioning_applied.append(f"timing:{timing}")
            else:
                LOGGER.warning(
                    "Timing split '%s' left %d observations (<4); falling back to combined.",
                    timing,
                    len(timing_filtered),
                )
                timing_method = "combined"

        if vix_quartile is not None and "vix_quartile" in frame.columns:
            low = max(int(vix_quartile) - 1, 1)
            high = min(int(vix_quartile) + 1, 4)
            vix_filtered = frame[
                frame["vix_quartile"].astype(float).between(low, high, inclusive="both")
            ]
            if len(vix_filtered) >= 4:
                frame = vix_filtered
                selected = frame["abs_move"].tolist()
                conditioning_applied.append(f"vix_quartile:{int(vix_quartile)}")
            else:
                LOGGER.info(
                    "Skipping VIX quartile conditioning; filtered sample %d < 4.",
                    len(vix_filtered),
                )

        if drift_sign is not None and "drift_sign" in frame.columns:
            drift_filtered = frame[
                frame["drift_sign"].astype(float) == float(drift_sign)
            ]
            if len(drift_filtered) >= 4:
                frame = drift_filtered
                selected = frame["abs_move"].tolist()
                conditioning_applied.append(f"drift_sign:{int(drift_sign)}")
            else:
                LOGGER.info(
                    "Skipping drift conditioning; filtered sample %d < 4.",
                    len(drift_filtered),
                )

    median_value = float(np.median(selected))

    trimmed_value: float | None
    try:
        trimmed_value = trimmed_mean_move(selected)
    except ValueError:
        trimmed_value = None

    recency_value: float | None
    try:
        recency_value = recency_weighted_mean(selected)
    except ValueError:
        recency_value = None

    primary = recency_value if recency_value is not None else median_value
    n_observations = len(selected)
    effective_n = n_observations
    if timing_method in {"amc", "bmo"}:
        effective_n = max(1, int(np.floor(n_observations / 2)))
    data_quality = _data_quality(effective_n)

    return ConditionalExpected(
        median=median_value,
        trimmed_mean=trimmed_value,
        recency_weighted=recency_value,
        timing_method=timing_method,
        n_observations=n_observations,
        data_quality=data_quality,
        conditioning_applied=conditioning_applied,
        primary_estimate=primary,
        peer_conditioned=float(peer_median) if peer_median is not None else None,
    )


def _abs_moves(moves: Sequence[float]) -> list[float]:
    """Normalize moves to absolute-float list."""

    return [abs(float(move)) for move in moves if move is not None and pd.notna(move)]


def _data_quality(n_observations: int) -> str:
    """Map sample size to LOW/MEDIUM/HIGH quality."""

    if n_observations > 10:
        return "HIGH"
    if n_observations >= 6:
        return "MEDIUM"
    return "LOW"


def _timing_bucket(raw_label: str | None) -> str:
    """Map provider-specific timing labels to amc/bmo/unknown."""

    if raw_label is None:
        return "unknown"

    normalized = str(raw_label).strip().lower()
    amc_labels = {
        "amc",
        "ah",
        "after hours",
        "after close",
        "post-market",
        "post market",
    }
    bmo_labels = {"bmo", "am", "before open", "pre-market", "pre market"}
    if normalized in amc_labels:
        return "amc"
    if normalized in bmo_labels:
        return "bmo"
    return "unknown"


def _load_event_timing_map(
    ticker: str,
    *,
    db_path: Path,
) -> dict[dt.date, str | None]:
    """Load date->event_time_label map from local event registry."""

    if not db_path.exists():
        return {}

    query = """
        SELECT event_date, event_time_label
        FROM event_registry
        WHERE UPPER(underlying_symbol) = UPPER(?)
          AND event_family = 'earnings'
    """

    try:
        with sqlite3.connect(db_path) as conn:
            frame = pd.read_sql_query(query, conn, params=[ticker.upper()])
    except Exception as exc:  # pragma: no cover
        LOGGER.warning(
            "Could not load event timing metadata for %s from %s: %s",
            ticker,
            db_path,
            exc,
        )
        return {}

    if frame.empty:
        return {}

    frame["event_date"] = pd.to_datetime(frame["event_date"], errors="coerce").dt.date
    frame = frame.dropna(subset=["event_date"])
    if frame.empty:
        return {}

    mapping: dict[dt.date, str | None] = {}
    for _, row in frame.iterrows():
        mapping[row["event_date"]] = row["event_time_label"]
    return mapping


def _load_event_timing_map_from_yfinance(
    ticker: str,
    *,
    limit: int = 24,
) -> dict[dt.date, str | None]:
    """Load date->timing labels from yfinance earnings metadata.

    yfinance often returns dates without reliable intraday labels. When
    timestamps are date-only (00:00:00), timing remains unknown.
    """

    try:
        import yfinance as yf

        earnings = yf.Ticker(ticker).get_earnings_dates(limit=limit)
    except Exception as exc:  # pragma: no cover
        LOGGER.debug(
            "Could not fetch yfinance earnings timing for %s: %s",
            ticker,
            exc,
        )
        return {}

    if earnings is None or earnings.empty:
        return {}

    mapping: dict[dt.date, str | None] = {}
    for ts in earnings.index:
        if not isinstance(ts, pd.Timestamp):
            continue
        event_date = ts.date()
        if ts.hour == 0 and ts.minute == 0 and ts.second == 0:
            mapping[event_date] = None
        elif ts.hour >= 16:
            mapping[event_date] = "ah"
        elif ts.hour < 12:
            mapping[event_date] = "am"
        else:
            mapping[event_date] = None
    return mapping
