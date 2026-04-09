"""Helpers to register workbook-ready event samples from a manifest."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from data.option_data_store import OptionsDataStore, create_store


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
        raise ValueError("Manifest must be a list of events or an object with an 'events' list.")
    return events


def backfill_event_manifest(
    manifest_path: str | Path,
    *,
    db_path: str = "data/options_intraday.db",
) -> dict[str, Any]:
    """Backfill one manifest into the additive event store."""

    store = create_store(db_path)
    return backfill_event_records(store, load_event_manifest(manifest_path))


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
