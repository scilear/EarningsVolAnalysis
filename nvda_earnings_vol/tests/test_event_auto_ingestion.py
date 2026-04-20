"""Tests for earnings calendar auto-ingestion."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from data.option_data_store import create_store
from event_option_playbook.backfill import auto_ingest_earnings_calendar


class _MockTicker:
    def __init__(self, earnings_index: list[pd.Timestamp]) -> None:
        self._earnings_index = earnings_index

    def get_earnings_dates(self, limit: int = 8) -> pd.DataFrame:  # noqa: ARG002
        return pd.DataFrame(index=pd.DatetimeIndex(self._earnings_index))


def test_auto_ingest_creates_registry_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = create_store(tmp_path / "events.db")
    monkeypatch.setattr(
        "event_option_playbook.backfill.yf.Ticker",
        lambda ticker: _MockTicker(
            [
                pd.Timestamp("2026-05-28"),
                pd.Timestamp("2026-08-27"),
            ]
        ),
    )

    summary = auto_ingest_earnings_calendar(
        store,
        ["NVDA"],
        limit=4,
        on_or_after=date(2026, 1, 1),
    )
    registry = store.get_event_registry()

    assert summary["events_created"] == 2
    assert summary["events_updated"] == 0
    assert summary["events_skipped_past"] == 0
    assert summary["fetch_errors"] == []
    assert len(summary["event_ids"]) == 2
    assert len(registry) == 2
    assert set(registry["source_system"]) == {"yfinance-earnings-calendar"}
    assert set(registry["event_family"]) == {"earnings"}


def test_auto_ingest_updates_existing_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = create_store(tmp_path / "events.db")
    event_id = "earnings:nvda_earnings_2026-05-28:NVDA:2026-05-28"
    store.register_event(
        event_id=event_id,
        event_family="earnings",
        event_name="nvda_earnings_2026-05-28",
        underlying_symbol="NVDA",
        event_date=date(2026, 5, 28),
        source_system="manual",
    )
    monkeypatch.setattr(
        "event_option_playbook.backfill.yf.Ticker",
        lambda ticker: _MockTicker([pd.Timestamp("2026-05-28")]),
    )

    summary = auto_ingest_earnings_calendar(
        store,
        ["NVDA"],
        on_or_after=date(2026, 1, 1),
    )
    registry = store.get_event_registry(event_id)

    assert summary["events_created"] == 0
    assert summary["events_updated"] == 1
    assert len(registry) == 1
    assert registry.iloc[0]["source_system"] == "yfinance-earnings-calendar"


def test_auto_ingest_skips_past_dates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = create_store(tmp_path / "events.db")
    monkeypatch.setattr(
        "event_option_playbook.backfill.yf.Ticker",
        lambda ticker: _MockTicker(
            [
                pd.Timestamp("2025-02-01"),
                pd.Timestamp("2026-06-01"),
            ]
        ),
    )

    summary = auto_ingest_earnings_calendar(
        store,
        ["NVDA"],
        on_or_after=date(2026, 1, 1),
    )

    assert summary["events_created"] == 1
    assert summary["events_skipped_past"] == 1


def test_auto_ingest_collects_fetch_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = create_store(tmp_path / "events.db")

    def _raise(ticker: str):
        raise RuntimeError(f"boom: {ticker}")

    monkeypatch.setattr("event_option_playbook.backfill.yf.Ticker", _raise)
    summary = auto_ingest_earnings_calendar(
        store,
        ["NVDA", "TSLA"],
        on_or_after=date(2026, 1, 1),
    )

    assert summary["events_created"] == 0
    assert len(summary["fetch_errors"]) == 2
