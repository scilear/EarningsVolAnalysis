"""Helpers to register workbook-ready event samples from a manifest."""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yfinance as yf

from data.option_data_store import OptionsDataStore, create_store
from event_vol_analysis import config


LOGGER = logging.getLogger(__name__)
_LAST_YF_REQUEST_MONOTONIC: float | None = None


def _is_yf_rate_limited(exc: Exception) -> bool:
    """Return True when the exception resembles an HTTP 429 rate limit."""
    message = str(exc).lower()
    return "429" in message or "too many requests" in message


def _throttle_yfinance() -> None:
    """Throttle yfinance calls with configured inter-request delay."""
    global _LAST_YF_REQUEST_MONOTONIC
    delay_seconds = max(float(config.YF_RATE_LIMIT_MS), 0.0) / 1000.0
    if delay_seconds <= 0.0:
        return

    now = time.monotonic()
    if _LAST_YF_REQUEST_MONOTONIC is not None:
        elapsed = now - _LAST_YF_REQUEST_MONOTONIC
        if elapsed < delay_seconds:
            sleep_for = delay_seconds - elapsed
            LOGGER.info("yfinance throttle sleep %.3fs", sleep_for)
            time.sleep(sleep_for)
    _LAST_YF_REQUEST_MONOTONIC = time.monotonic()


def _fetch_earnings_dates_with_backoff(ticker: str, limit: int):
    """Fetch earnings dates with exponential backoff on 429 responses."""
    attempts = max(int(config.YF_MAX_RETRIES), 1)
    yf_ticker = yf.Ticker(ticker)

    for attempt in range(1, attempts + 1):
        _throttle_yfinance()
        try:
            return yf_ticker.get_earnings_dates(limit=limit)
        except Exception as exc:
            retryable = _is_yf_rate_limited(exc)
            if (not retryable) or attempt >= attempts:
                raise
            backoff_seconds = float(2 ** (attempt - 1))
            LOGGER.warning(
                "Earnings backfill rate-limited for %s "
                "(attempt %d/%d), retrying in %.1fs: %s",
                ticker,
                attempt,
                attempts,
                backoff_seconds,
                exc,
            )
            time.sleep(backoff_seconds)


def build_event_id(
    event_family: str,
    event_name: str,
    underlying_symbol: str,
    event_date: str,
) -> str:
    """Build a stable event identifier used across replay and workbook layers."""

    return (
        f"{event_family.lower()}:{event_name.lower()}:"
        f"{underlying_symbol.upper()}:{event_date}"
    )


def load_event_manifest(manifest_path: str | Path) -> list[dict[str, Any]]:
    """Load a JSON manifest describing event rows to backfill."""

    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        events = payload.get("events", [])
    else:
        events = payload
    if not isinstance(events, list):
        raise ValueError(
            "Manifest must be a list of events or an object with an 'events' list."
        )
    return events


def backfill_event_manifest(
    manifest_path: str | Path,
    *,
    db_path: str = "data/options_intraday.db",
) -> dict[str, Any]:
    """Backfill one manifest into the additive event store."""

    store = create_store(db_path)
    return backfill_event_records(store, load_event_manifest(manifest_path))


def auto_ingest_earnings_calendar_db(
    tickers: list[str],
    *,
    db_path: str = "data/options_intraday.db",
    limit: int = 8,
    on_or_after: date | None = None,
) -> dict[str, Any]:
    """Fetch upcoming earnings dates and upsert them into event_registry."""

    store = create_store(db_path)
    return auto_ingest_earnings_calendar(
        store,
        tickers,
        limit=limit,
        on_or_after=on_or_after,
    )


def auto_ingest_earnings_calendar(
    store: OptionsDataStore,
    tickers: list[str],
    *,
    limit: int = 8,
    on_or_after: date | None = None,
) -> dict[str, Any]:
    """Fetch upcoming earnings dates and upsert them into event_registry."""

    normalized_tickers = sorted(
        {str(ticker).upper() for ticker in tickers if str(ticker).strip()}
    )
    cutoff = on_or_after or date.today()
    summary: dict[str, Any] = {
        "tickers_requested": len(normalized_tickers),
        "tickers_processed": 0,
        "events_created": 0,
        "events_updated": 0,
        "events_skipped_past": 0,
        "fetch_errors": [],
        "event_ids": [],
    }

    for ticker in normalized_tickers:
        try:
            earnings = _fetch_earnings_dates_with_backoff(ticker, limit)
        except Exception as exc:
            summary["fetch_errors"].append({"ticker": ticker, "error": str(exc)})
            continue

        summary["tickers_processed"] += 1
        if earnings is None or len(getattr(earnings, "index", [])) == 0:
            continue

        seen_dates: set[date] = set()
        for raw_ts in earnings.index:
            event_date = _coerce_event_date(raw_ts)
            if event_date is None:
                continue
            if event_date in seen_dates:
                continue
            seen_dates.add(event_date)

            if event_date < cutoff:
                summary["events_skipped_past"] += 1
                continue

            event_date_str = event_date.isoformat()
            event_name = f"{ticker.lower()}_earnings_{event_date_str}"
            event_id = build_event_id(
                event_family="earnings",
                event_name=event_name,
                underlying_symbol=ticker,
                event_date=event_date_str,
            )
            existing = not store.get_event_registry(event_id).empty

            store.register_event(
                event_id=event_id,
                event_family="earnings",
                event_name=event_name,
                underlying_symbol=ticker,
                event_date=event_date,
                event_ts_utc=_coerce_event_timestamp(raw_ts),
                event_time_label=None,
                source_system="yfinance-earnings-calendar",
                source_ref=f"yfinance:get_earnings_dates:{ticker}:{limit}",
                event_status="scheduled",
            )

            summary["event_ids"].append(event_id)
            if existing:
                summary["events_updated"] += 1
            else:
                summary["events_created"] += 1

    return summary


def backfill_event_records(
    store: OptionsDataStore,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Register event rows, bindings, metrics, outcomes, and replay rows."""

    summary = {
        "events_processed": 0,
        "snapshot_bindings": 0,
        "surface_metrics": 0,
        "realized_outcomes": 0,
        "structure_replays": 0,
        "event_ids": [],
    }

    for event in events:
        event_date = str(event["event_date"])
        event_id = str(
            event.get("event_id")
            or build_event_id(
                event_family=str(event["event_family"]),
                event_name=str(event["event_name"]),
                underlying_symbol=str(event["underlying_symbol"]),
                event_date=event_date,
            )
        )
        store.register_event(
            event_id=event_id,
            event_family=str(event["event_family"]),
            event_name=str(event["event_name"]),
            underlying_symbol=str(event["underlying_symbol"]),
            proxy_symbol=event.get("proxy_symbol"),
            event_date=event_date,
            event_ts_utc=_optional_datetime(event.get("event_ts_utc")),
            event_time_label=event.get("event_time_label"),
            source_system=str(event["source_system"]),
            source_ref=event.get("source_ref"),
            event_status=str(event.get("event_status", "scheduled")),
        )
        summary["events_processed"] += 1
        summary["event_ids"].append(event_id)

        for binding in event.get("snapshot_bindings", []):
            quote_ts = _required_datetime(binding["quote_ts"])
            ticker = str(binding.get("ticker") or event["underlying_symbol"]).upper()
            _validate_snapshot_exists(store, ticker=ticker, quote_ts=quote_ts)
            store.bind_snapshot_to_event(
                event_id=event_id,
                snapshot_label=str(binding["snapshot_label"]),
                timing_bucket=str(binding["timing_bucket"]),
                quote_ts=quote_ts,
                ticker=ticker,
                rel_trade_days_to_event=int(binding["rel_trade_days_to_event"]),
                selection_method=str(binding["selection_method"]),
                is_primary=bool(binding.get("is_primary", False)),
            )
            summary["snapshot_bindings"] += 1

        for metric in event.get("surface_metrics", []):
            store.store_surface_metrics(
                event_id=event_id,
                snapshot_label=str(metric["snapshot_label"]),
                quote_ts=_required_datetime(metric["quote_ts"]),
                ticker=str(metric.get("ticker") or event["underlying_symbol"]).upper(),
                metrics=dict(metric["metrics"]),
                metric_version=str(metric.get("metric_version", "v1")),
            )
            summary["surface_metrics"] += 1

        for outcome in event.get("realized_outcomes", []):
            store.store_realized_outcome(
                event_id=event_id,
                horizon_code=str(outcome["horizon_code"]),
                pre_snapshot_label=str(outcome["pre_snapshot_label"]),
                post_snapshot_label=str(outcome["post_snapshot_label"]),
                outcome=dict(outcome["outcome"]),
                outcome_version=str(outcome.get("outcome_version", "v1")),
            )
            summary["realized_outcomes"] += 1

        for replay in event.get("structure_replays", []):
            store.store_structure_replay_outcome(
                event_id=event_id,
                structure_code=str(replay["structure_code"]),
                entry_snapshot_label=str(replay["entry_snapshot_label"]),
                exit_horizon_code=str(replay["exit_horizon_code"]),
                replay=dict(replay["replay"]),
            )
            summary["structure_replays"] += 1

    return summary


def _validate_snapshot_exists(
    store: OptionsDataStore,
    *,
    ticker: str,
    quote_ts: datetime,
) -> None:
    """Ensure one referenced snapshot already exists in the option quote store."""

    chain = store.query_chain(ticker=ticker, timestamp=quote_ts, min_quality="valid")
    if chain.empty:
        raise ValueError(
            f"No stored option chain found for ticker '{ticker}' at '{quote_ts.isoformat()}'."
        )


def _required_datetime(value: Any) -> datetime:
    """Normalize one manifest datetime field."""

    normalized = _optional_datetime(value)
    if normalized is None:
        raise ValueError("Expected a datetime-compatible value, got null.")
    return normalized


def _optional_datetime(value: Any) -> datetime | None:
    """Normalize one optional manifest datetime field."""

    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"Unsupported datetime value: {value!r}")


def _coerce_event_date(value: Any) -> date | None:
    """Coerce one date-like earnings index value to datetime.date."""

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value).date()
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime().date()
    return None


def _coerce_event_timestamp(value: Any) -> datetime | None:
    """Coerce one earnings index value to datetime, if meaningful."""

    timestamp: datetime | None
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, str):
        timestamp = datetime.fromisoformat(value)
    elif hasattr(value, "to_pydatetime"):
        timestamp = value.to_pydatetime()
    else:
        return None

    if (
        timestamp.hour == 0
        and timestamp.minute == 0
        and timestamp.second == 0
        and timestamp.microsecond == 0
    ):
        return None
    return timestamp
