"""Post-earnings outcome tracking for calibration loop inputs."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from data.option_data_store import create_store


DEFAULT_DB_PATH = Path("data/options_intraday.db")
ALLOWED_PHASE1 = {
    "HELD_REPRICING",
    "POTENTIAL_OVERSHOOT",
    "NOT_ASSESSED",
}
ALLOWED_TIMING = {"AMC", "BMO", "UNKNOWN"}


@dataclass(frozen=True)
class EarningsOutcomeRecord:
    """Outcome record joining ex-ante prediction and realized post-event data."""

    id: int
    ticker: str
    event_date: dt.date
    timing: str
    analysis_timestamp: dt.datetime
    predicted_type: int
    predicted_confidence: str
    edge_ratio_label: str
    edge_ratio_value: float
    edge_ratio_confidence: str
    vol_regime_label: str
    implied_move: float
    conditional_expected_move: float
    realized_move: float | None
    realized_move_direction: str | None
    realized_vs_implied_ratio: float | None
    phase1_category: str | None
    entry_taken: bool | None
    pnl_if_entered: float | None
    outcome_complete: bool


def store_prediction(
    ticker: str,
    event_date: dt.date | str,
    type_classification: Any,
    edge_ratio: Any,
    vol_regime: Any,
    *,
    timing: str = "UNKNOWN",
    analysis_timestamp: dt.datetime | None = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> EarningsOutcomeRecord:
    """Insert one ex-ante prediction row for calibration tracking."""

    predicted_type = int(_read(type_classification, "type"))
    predicted_confidence = str(_read(type_classification, "confidence")).upper()
    edge_ratio_label = str(_read(edge_ratio, "label")).upper()
    edge_ratio_value = float(_read(edge_ratio, "ratio"))
    edge_ratio_confidence = str(_read(edge_ratio, "confidence")).upper()
    vol_regime_label = str(_read(vol_regime, "label", "vol_regime")).upper()
    implied_move = float(_read(edge_ratio, "implied"))
    conditional_expected_move = float(_read(edge_ratio, "conditional_expected_primary"))

    normalized_timing = str(timing).upper()
    if normalized_timing not in ALLOWED_TIMING:
        normalized_timing = "UNKNOWN"

    ts = analysis_timestamp or dt.datetime.now(dt.UTC)
    store = create_store(db_path)
    store.store_earnings_prediction(
        ticker=ticker,
        event_date=event_date,
        timing=normalized_timing,
        analysis_timestamp=ts,
        predicted_type=predicted_type,
        predicted_confidence=predicted_confidence,
        edge_ratio_label=edge_ratio_label,
        edge_ratio_value=edge_ratio_value,
        edge_ratio_confidence=edge_ratio_confidence,
        vol_regime_label=vol_regime_label,
        implied_move=implied_move,
        conditional_expected_move=conditional_expected_move,
    )
    return _get_record(store, ticker=ticker, event_date=event_date)


def update_outcome(
    ticker: str,
    event_date: dt.date | str,
    phase1_category: str,
    entry_taken: bool,
    pnl: float | None,
    *,
    force: bool = False,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> EarningsOutcomeRecord:
    """Update manual post-event fields (phase-1 classification + entry/PnL)."""

    normalized_phase1 = str(phase1_category).upper()
    if normalized_phase1 not in ALLOWED_PHASE1:
        allowed = ", ".join(sorted(ALLOWED_PHASE1))
        raise ValueError(f"phase1_category must be one of: {allowed}")

    store = create_store(db_path)
    store.update_earnings_outcome(
        ticker=ticker,
        event_date=event_date,
        phase1_category=normalized_phase1,
        entry_taken=bool(entry_taken),
        pnl_if_entered=pnl,
        force=force,
    )
    return _get_record(store, ticker=ticker, event_date=event_date)


def auto_populate_realized_move(
    ticker: str,
    event_date: dt.date | str,
    *,
    force: bool = False,
    db_path: Path | str = DEFAULT_DB_PATH,
    price_history: pd.DataFrame | None = None,
) -> EarningsOutcomeRecord | None:
    """Populate realized move fields from post-event price action."""

    store = create_store(db_path)
    existing = store.get_earnings_outcome(ticker, event_date)
    if existing is None:
        raise ValueError(f"No outcome row found for {ticker} {event_date}")

    timing = str(existing.get("timing") or "UNKNOWN").upper()
    history = (
        price_history
        if price_history is not None
        else _fetch_price_window(
            ticker,
            _as_date(event_date),
        )
    )
    if history is None or history.empty:
        return None

    realized_signed = _compute_realized_move(history, _as_date(event_date), timing)
    if realized_signed is None:
        return None

    realized_abs = abs(realized_signed)
    direction = "UP" if realized_signed >= 0 else "DOWN"
    implied_move = float(existing["implied_move"])
    ratio = realized_abs / implied_move if implied_move > 0 else None

    changed = store.set_earnings_realized_move(
        ticker=ticker,
        event_date=event_date,
        realized_move=realized_abs,
        realized_move_direction=direction,
        realized_vs_implied_ratio=ratio,
        force=force,
    )
    if not changed:
        return _record_from_row(existing)
    return _get_record(store, ticker=ticker, event_date=event_date)


def get_outcome_record(
    ticker: str,
    event_date: dt.date | str,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> EarningsOutcomeRecord | None:
    """Return one stored outcome record, if present."""

    store = create_store(db_path)
    row = store.get_earnings_outcome(ticker, event_date)
    if row is None:
        return None
    return _record_from_row(row)


def _fetch_price_window(ticker: str, event_date: dt.date) -> pd.DataFrame:
    """Fetch local window with Date/Open/Close around event date."""

    start = event_date - dt.timedelta(days=10)
    end = event_date + dt.timedelta(days=10)
    history = yf.Ticker(ticker).history(start=start, end=end)
    if history.empty:
        return history
    frame = history.reset_index()
    columns = [col for col in ("Date", "Open", "Close") if col in frame.columns]
    frame = frame[columns].copy()
    frame["Date"] = pd.to_datetime(frame["Date"]).dt.date
    return frame


def _compute_realized_move(
    history: pd.DataFrame,
    event_date: dt.date,
    timing: str,
) -> float | None:
    """Compute signed realized move by timing convention."""

    if history.empty or "Date" not in history.columns:
        return None

    frame = history.copy().sort_values("Date").reset_index(drop=True)
    frame["Date"] = pd.to_datetime(frame["Date"]).dt.date

    event_rows = frame[frame["Date"] == event_date]
    if event_rows.empty:
        return None
    event_idx = int(event_rows.index[0])

    normalized_timing = timing.upper()
    if normalized_timing == "BMO":
        if event_idx - 1 < 0 or "Open" not in frame.columns:
            return None
        prior_close = float(frame.iloc[event_idx - 1]["Close"])
        event_open = float(frame.iloc[event_idx]["Open"])
        if prior_close <= 0:
            return None
        return event_open / prior_close - 1.0

    # AMC and UNKNOWN default to close(event) -> close(next session)
    if event_idx + 1 >= len(frame):
        return None
    event_close = float(frame.iloc[event_idx]["Close"])
    next_close = float(frame.iloc[event_idx + 1]["Close"])
    if event_close <= 0:
        return None
    return next_close / event_close - 1.0


def _get_record(
    store: Any,
    *,
    ticker: str,
    event_date: dt.date | str,
) -> EarningsOutcomeRecord:
    """Fetch one row and convert to dataclass, raising on missing row."""

    row = store.get_earnings_outcome(ticker, event_date)
    if row is None:
        raise ValueError(f"No outcome row found for {ticker} {event_date}")
    return _record_from_row(row)


def _record_from_row(row: Any) -> EarningsOutcomeRecord:
    """Convert sqlite row/dict into EarningsOutcomeRecord."""

    if not isinstance(row, dict):
        row = dict(row)

    entry_taken = row.get("entry_taken")
    if entry_taken is not None:
        entry_taken = bool(entry_taken)

    return EarningsOutcomeRecord(
        id=int(row["id"]),
        ticker=str(row["ticker"]),
        event_date=_as_date(row["event_date"]),
        timing=str(row["timing"]),
        analysis_timestamp=pd.to_datetime(row["analysis_timestamp"]).to_pydatetime(),
        predicted_type=int(row["predicted_type"]),
        predicted_confidence=str(row["predicted_confidence"]),
        edge_ratio_label=str(row["edge_ratio_label"]),
        edge_ratio_value=float(row["edge_ratio_value"]),
        edge_ratio_confidence=str(row["edge_ratio_confidence"]),
        vol_regime_label=str(row["vol_regime_label"]),
        implied_move=float(row["implied_move"]),
        conditional_expected_move=float(row["conditional_expected_move"]),
        realized_move=(
            None if row.get("realized_move") is None else float(row["realized_move"])
        ),
        realized_move_direction=row.get("realized_move_direction"),
        realized_vs_implied_ratio=(
            None
            if row.get("realized_vs_implied_ratio") is None
            else float(row["realized_vs_implied_ratio"])
        ),
        phase1_category=row.get("phase1_category"),
        entry_taken=entry_taken,
        pnl_if_entered=(
            None if row.get("pnl_if_entered") is None else float(row["pnl_if_entered"])
        ),
        outcome_complete=bool(row["outcome_complete"]),
    )


def _read(payload: Any, *keys: str) -> Any:
    """Read first matching key from dict-like or object-like payload."""

    for key in keys:
        if isinstance(payload, dict) and key in payload:
            return payload[key]
        if hasattr(payload, key):
            return getattr(payload, key)
    joined = ", ".join(keys)
    raise KeyError(joined)


def _as_date(value: dt.date | dt.datetime | str | pd.Timestamp) -> dt.date:
    """Normalize date-like values to date."""

    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))
