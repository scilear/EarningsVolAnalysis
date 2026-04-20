"""Tests for scripts.backfill_event_history CLI modes."""

from __future__ import annotations

import argparse
import json

import pytest

from scripts import backfill_event_history


def test_cli_auto_earnings_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    captured: dict = {}

    args = argparse.Namespace(
        manifest=None,
        db="data/options_intraday.db",
        auto_earnings=True,
        tickers="NVDA,TSLA",
        limit=5,
        on_or_after="2026-01-01",
    )

    def _fake_ingest(
        tickers: list[str],
        *,
        db_path: str,
        limit: int,
        on_or_after,
    ) -> dict:
        captured["tickers"] = tickers
        captured["db_path"] = db_path
        captured["limit"] = limit
        captured["on_or_after"] = on_or_after
        return {"events_created": 2}

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", lambda self: args)
    monkeypatch.setattr(
        backfill_event_history,
        "auto_ingest_earnings_calendar_db",
        _fake_ingest,
    )

    backfill_event_history.main()
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert payload["events_created"] == 2
    assert captured["tickers"] == ["NVDA", "TSLA"]
    assert captured["db_path"] == "data/options_intraday.db"
    assert captured["limit"] == 5
    assert captured["on_or_after"].isoformat() == "2026-01-01"


def test_cli_manifest_mode_requires_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = argparse.Namespace(
        manifest=None,
        db="data/options_intraday.db",
        auto_earnings=False,
        tickers="NVDA",
        limit=8,
        on_or_after=None,
    )
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", lambda self: args)

    with pytest.raises(ValueError, match="manifest is required"):
        backfill_event_history.main()
