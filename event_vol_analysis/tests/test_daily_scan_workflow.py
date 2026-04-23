"""Tests for daily earnings workflow orchestration (T032)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd
import pytest

from event_vol_analysis.reports.playbook_scan import (
    PlaybookScanResult,
    PlaybookScanRow,
)
from event_vol_analysis.workflow import daily_scan


def _row(
    ticker: str,
    *,
    type_: int,
    confidence: str = "HIGH",
    action: str = "Action",
    ratio: float = 1.25,
    edge_label: str = "CHEAP",
    phase2: list[str] | None = None,
) -> PlaybookScanRow:
    """Build one synthetic scan row for workflow tests."""

    return PlaybookScanRow(
        ticker=ticker,
        earnings_date="2026-05-30",
        vol_regime="CHEAP",
        edge_ratio=f"{edge_label} (MEDIUM)",
        positioning="BALANCED",
        signal="No signal",
        type_=type_,
        confidence=confidence,
        action=action,
        edge_ratio_detail={"ratio": ratio, "label": edge_label},
        phase2_checklist=phase2,
    )


def test_telegram_alert_format_type1() -> None:
    row = _row("NVDA", type_=1, action="Buy straddle")

    message = daily_scan._format_telegram_alert(row, dt.date(2026, 5, 1))
    assert "[EARNINGS SCAN] 2026-05-01" in message
    assert "NVDA | TYPE 1 | HIGH confidence" in message
    assert "Action: Buy straddle" in message
    assert "PHASE 2" not in message


def test_telegram_alert_format_type4_includes_checklist_note() -> None:
    row = _row(
        "AAPL",
        type_=4,
        action="Potential fade candidate",
        phase2=["Confirm reversal"],
    )

    message = daily_scan._format_telegram_alert(row, dt.date(2026, 5, 1))
    assert "AAPL | TYPE 4" in message
    assert "[PHASE 2 CHECKLIST - see report]" in message


def test_pre_market_alert_format_single_line() -> None:
    row = _row("GLD", type_=2, edge_label="FAIR")

    message = daily_scan._format_telegram_alert(
        row,
        dt.date(2026, 5, 1),
        mode="pre-market",
    )
    assert message.startswith("[PRE-MARKET EARNINGS SCAN]")
    assert "GLD: TYPE 2" in message
    assert "IV Regime:" in message
    assert "Edge Ratio:" in message


def test_pre_market_summary_message_title() -> None:
    message = daily_scan._summary_message(
        dt.date(2026, 5, 1),
        universe=5,
        filtered=1,
        actionable=2,
        report_path=Path("reports/pre-market/2026-05-01_pre_market_scan.html"),
        mode="pre-market",
    )
    assert "[PRE-MARKET EARNINGS SCAN COMPLETE]" in message


def test_telegram_summary_message(tmp_path: Path) -> None:
    report = tmp_path / "daily" / "2026-05-01_playbook_scan.html"
    message = daily_scan._summary_message(
        dt.date(2026, 5, 1),
        universe=12,
        filtered=3,
        actionable=4,
        report_path=report,
    )
    assert "[EARNINGS SCAN COMPLETE] 2026-05-01" in message
    assert "Universe: 12 names | Filtered: 3 | Actionable: 4 non-TYPE-5" in message
    assert str(report) in message


def test_no_alerts_when_all_type5(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(daily_scan, "LOG_PATH", tmp_path / "daily_scan.log")
    monkeypatch.setattr(
        daily_scan,
        "_fetch_upcoming_earnings_events",
        lambda cfg: [
            {"ticker": "NVDA", "event_date": dt.date(2026, 5, 2)},
            {"ticker": "AAPL", "event_date": dt.date(2026, 5, 3)},
        ],
    )
    monkeypatch.setattr(
        daily_scan,
        "_apply_hard_filters",
        lambda cfg, events: (events, []),
    )
    monkeypatch.setattr(
        daily_scan,
        "_run_playbook_scan_rows",
        lambda cfg, events: (
            [_row("NVDA", type_=5), _row("AAPL", type_=5)],
            [],
        ),
    )

    sent: list[str] = []
    monkeypatch.setattr(
        daily_scan,
        "_notify",
        lambda message, dry_run, mode="full-window": sent.append(message),
    )

    rc = daily_scan.run(
        [
            "--dry-run",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert rc == 0
    assert len(sent) == 1
    assert "Actionable: 0 non-TYPE-5" in sent[0]


def test_telegram_unavailable_falls_back_to_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(
        daily_scan,
        "_send_telegram_message",
        lambda token, chat_id, text: (_ for _ in ()).throw(RuntimeError("down")),
    )

    infos: list[str] = []

    def _capture_info(msg: str, *args: object) -> None:
        infos.append(msg % args if args else msg)

    monkeypatch.setattr(daily_scan.LOGGER, "info", _capture_info)
    monkeypatch.setattr(
        daily_scan.LOGGER,
        "error",
        lambda *args, **kwargs: None,
    )

    daily_scan._notify("hello", dry_run=False)
    assert any("ALERT (fallback)" in line for line in infos)


def test_dry_run_suppresses_telegram(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    called = {"value": False}

    def _send(_token: str, _chat: str, _text: str) -> None:
        called["value"] = True

    monkeypatch.setattr(daily_scan, "_send_telegram_message", _send)
    daily_scan._notify("dry-run-message", dry_run=True)
    out = capsys.readouterr().out

    assert "dry-run-message" in out
    assert called["value"] is False


def test_notify_pre_market_uses_telegram_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, object] = {"ran": False, "cmd": None}

    monkeypatch.setattr(
        daily_scan.shutil, "which", lambda name: "/usr/bin/telegram-send"
    )

    def _fake_run(command, check=False, capture_output=True, text=True):
        called["ran"] = True
        called["cmd"] = command

        class _Result:
            returncode = 0
            stderr = ""

        return _Result()

    monkeypatch.setattr(daily_scan.subprocess, "run", _fake_run)
    daily_scan._notify("hello", dry_run=False, mode="pre-market")
    assert called["ran"] is True
    assert called["cmd"] == ["/usr/bin/telegram-send", "hello"]


def test_notify_pre_market_fallback_when_cli_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(daily_scan.shutil, "which", lambda name: None)
    captured: list[str] = []
    monkeypatch.setattr(
        daily_scan.LOGGER,
        "info",
        lambda msg, *args: captured.append(msg % args if args else msg),
    )
    monkeypatch.setattr(daily_scan.LOGGER, "warning", lambda *args, **kwargs: None)

    daily_scan._notify("fallback-msg", dry_run=False, mode="pre-market")
    assert any("ALERT (fallback)" in line for line in captured)


def test_resolve_output_dir_by_mode() -> None:
    assert daily_scan._resolve_output_dir(None, "full-window") == Path("reports/daily")
    assert daily_scan._resolve_output_dir(None, "pre-market") == Path(
        "reports/pre-market"
    )
    assert daily_scan._resolve_output_dir("x/y", "pre-market") == Path("x/y")


def test_resolve_scan_date_invalid() -> None:
    with pytest.raises(ValueError):
        daily_scan._resolve_scan_date("2026/05/01")


def test_fetch_upcoming_events_pre_market_exact_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Store:
        def get_event_registry(self):
            return pd.DataFrame(
                [
                    {
                        "event_family": "earnings",
                        "event_status": "scheduled",
                        "event_date": dt.date(2026, 5, 1),
                        "underlying_symbol": "AAPL",
                    },
                    {
                        "event_family": "earnings",
                        "event_status": "scheduled",
                        "event_date": dt.date(2026, 5, 2),
                        "underlying_symbol": "MSFT",
                    },
                ]
            )

    monkeypatch.setattr(daily_scan, "create_store", lambda path: _Store())
    monkeypatch.setattr(
        daily_scan,
        "auto_ingest_earnings_calendar_db",
        lambda *args, **kwargs: {
            "tickers_processed": 1,
            "events_created": 0,
            "events_updated": 0,
            "fetch_errors": [],
        },
    )

    cfg = daily_scan.ScanConfig(
        tickers=["AAPL"],
        db_path="data/options_intraday.db",
        output_dir=Path("reports/pre-market"),
        mode="pre-market",
        scan_date=dt.date(2026, 5, 1),
        days_ahead=14,
        limit_per_ticker=8,
        dry_run=True,
    )
    events = daily_scan._fetch_upcoming_earnings_events(cfg)
    assert len(events) == 1
    assert events[0]["ticker"] == "AAPL"


def test_safe_save_report_pre_market_filename(
    tmp_path: Path,
) -> None:
    result = PlaybookScanResult(
        rows=[_row("NVDA", type_=1)],
        filtered_out=[],
        frequency_warning_fired=False,
    )
    result.compute_summary()

    path = daily_scan._safe_save_report(
        result,
        output_dir=tmp_path / "reports" / "pre-market",
        mode="pre-market",
        scan_date=dt.date(2026, 5, 1),
    )
    assert path is not None
    assert path.name == "2026-05-01_pre_market_scan.html"


def test_log_entry_appended(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_path = tmp_path / "daily_scan.log"
    monkeypatch.setattr(daily_scan, "LOG_PATH", log_path)

    daily_scan._append_run_log({"scan_date": "2026-05-01", "actionable": 2})
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    payload = json.loads(lines[-1])

    assert payload["scan_date"] == "2026-05-01"
    assert payload["actionable"] == 2


def test_integration_dry_run_5_name_universe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(daily_scan, "LOG_PATH", tmp_path / "daily_scan.log")

    events = [
        {"ticker": "NVDA", "event_date": dt.date(2026, 5, 2)},
        {"ticker": "AAPL", "event_date": dt.date(2026, 5, 3)},
        {"ticker": "MSFT", "event_date": dt.date(2026, 5, 4)},
        {"ticker": "AMZN", "event_date": dt.date(2026, 5, 5)},
        {"ticker": "META", "event_date": dt.date(2026, 5, 6)},
    ]
    monkeypatch.setattr(
        daily_scan,
        "_fetch_upcoming_earnings_events",
        lambda cfg: events,
    )
    monkeypatch.setattr(
        daily_scan,
        "_apply_hard_filters",
        lambda cfg, incoming: (incoming, []),
    )
    monkeypatch.setattr(
        daily_scan,
        "_run_playbook_scan_rows",
        lambda cfg, incoming: (
            [
                _row("NVDA", type_=1, action="Buy straddle"),
                _row("AAPL", type_=4, action="Potential fade"),
                _row("MSFT", type_=5),
                _row("AMZN", type_=5),
                _row("META", type_=5),
            ],
            [],
        ),
    )

    telegram_called = {"value": False}
    monkeypatch.setattr(
        daily_scan,
        "_send_telegram_message",
        lambda token, chat_id, text: telegram_called.__setitem__(
            "value",
            True,
        ),
    )

    output_dir = tmp_path / "reports" / "daily"
    rc = daily_scan.run(["--dry-run", "--output-dir", str(output_dir)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "[EARNINGS SCAN]" in out
    assert "[EARNINGS SCAN COMPLETE]" in out
    assert telegram_called["value"] is False

    iso = dt.date.today().isoformat()
    report_path = output_dir / f"{iso}_playbook_scan.html"
    assert report_path.exists()
