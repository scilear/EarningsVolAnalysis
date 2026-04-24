"""Tests for multi-ticker batch mode in main CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from event_vol_analysis import main as main_module


def _base_args() -> argparse.Namespace:
    return argparse.Namespace(
        ticker="NVDA",
        tickers=["NVDA", "TSLA"],
        ticker_file=None,
        event_date=None,
        output=None,
        cache_dir="data/cache",
        use_cache=False,
        refresh_cache=False,
        cache_only=False,
        cache_spot=None,
        cache_front_expiry=None,
        cache_back1_expiry=None,
        cache_back2_expiry=None,
        seed=42,
        move_model="lognormal",
        test_data=True,
        test_scenario="baseline",
        test_data_dir=None,
        save_test_data=None,
        batch_output_dir="reports/batch",
        batch_summary_json="reports/batch_summary.json",
        analysis_summary_json=None,
    )


def test_run_batch_mode_writes_summary_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    args = _base_args()
    args.batch_output_dir = str(tmp_path / "batch")
    args.batch_summary_json = str(tmp_path / "batch" / "summary.json")

    commands: list[list[str]] = []

    analysis_payloads = {
        "NVDA": {
            "event_date": "2026-05-28",
            "regime": "Mixed / Transitional Setup",
            "top_structure": "CALENDAR",
            "score": 0.8123,
            "trust_metrics": {"status": "PASS", "mismatch_ratio": 1.2},
            "blocking_warnings": [],
        },
        "TSLA": {
            "event_date": "2026-05-02",
            "regime": "Convex Breakout Setup",
            "top_structure": "LONG_STRADDLE",
            "score": 0.7012,
            "trust_metrics": {"status": "FAIL", "mismatch_ratio": 2.5},
            "blocking_warnings": ["negative_event_var", "trust_gate_failed"],
        },
    }

    class _Result:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    def _fake_run(
        command: list[str],
        check: bool = False,  # noqa: ARG001
        capture_output: bool = False,  # noqa: ARG001
        text: bool = False,  # noqa: ARG001
    ):
        commands.append(command)
        ticker = command[command.index("--ticker") + 1]
        summary_path = Path(command[command.index("--analysis-summary-json") + 1])
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(analysis_payloads[ticker]),
            encoding="utf-8",
        )
        return _Result(0)

    monkeypatch.setattr(main_module.subprocess, "run", _fake_run)

    ok = main_module._run_batch_mode(args, ["NVDA", "TSLA"])
    summary_path = Path(args.batch_summary_json)

    assert ok
    assert len(commands) == 2
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["tickers_succeeded"] == 2
    assert summary["tickers_failed"] == 0
    assert summary["results"][0]["event_date"] == "2026-05-28"
    assert summary["results"][0]["regime"] == "Mixed / Transitional Setup"
    assert summary["results"][0]["top_structure"] == "CALENDAR"
    assert summary["results"][0]["score"] == pytest.approx(0.8123)
    assert summary["results"][1]["blocking_warnings"] == [
        "negative_event_var",
        "trust_gate_failed",
    ]


def test_main_exits_with_code_2_when_auto_event_date_is_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _base_args()
    args.tickers = None
    args.ticker = "NVDA"
    args.test_data = False
    args.output = "reports/nvda.html"

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", lambda self: args)

    class _Resolution:
        status = "ambiguous"
        event_date = None
        message = "Multiple nearby candidate earnings dates were returned"

    monkeypatch.setattr(
        main_module,
        "resolve_next_earnings_date",
        lambda ticker: _Resolution(),
    )

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()
    assert exc_info.value.code == 2


def test_main_batch_mode_exits_nonzero_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _base_args()

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", lambda self: args)
    monkeypatch.setattr(main_module, "_run_batch_mode", lambda a, t: False)

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()
    assert exc_info.value.code == 1


def test_main_batch_mode_uses_ticker_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _base_args()
    args.tickers = None
    args.ticker_file = "tickers.txt"

    captured: dict = {}

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", lambda self: args)
    monkeypatch.setattr(
        main_module, "_load_tickers_from_file", lambda p: ["AAPL", "MSFT"]
    )

    def _capture_run(a: argparse.Namespace, tickers: list[str]) -> bool:
        captured["tickers"] = tickers
        return True

    monkeypatch.setattr(main_module, "_run_batch_mode", _capture_run)

    main_module.main()
    assert captured["tickers"] == ["AAPL", "MSFT"]


def test_batch_command_includes_move_model() -> None:
    args = _base_args()
    args.move_model = "fat_tailed"

    command = main_module._batch_command_for_ticker(
        args,
        ticker="NVDA",
        output_path=Path("reports/nvda_earnings_report.html"),
    )

    move_model_index = command.index("--move-model")
    assert command[move_model_index + 1] == "fat_tailed"


def test_batch_command_includes_cache_only_overrides() -> None:
    args = _base_args()
    args.cache_only = True
    args.cache_spot = 123.45
    args.cache_front_expiry = "2026-05-15"
    args.cache_back1_expiry = "2026-05-22"
    args.cache_back2_expiry = "2026-06-19"

    command = main_module._batch_command_for_ticker(
        args,
        ticker="NVDA",
        output_path=Path("reports/nvda_earnings_report.html"),
    )

    assert "--cache-only" in command
    assert "--cache-spot" in command
    assert "--cache-front-expiry" in command
    assert "--cache-back1-expiry" in command
    assert "--cache-back2-expiry" in command
