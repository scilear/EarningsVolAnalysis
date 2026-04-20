"""Tests for multi-ticker batch mode in main CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from nvda_earnings_vol import main as main_module


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
        seed=42,
        test_data=True,
        test_scenario="baseline",
        test_data_dir=None,
        save_test_data=None,
        batch_output_dir="reports/batch",
        batch_summary_json="reports/batch_summary.json",
    )


def test_run_batch_mode_writes_summary_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    args = _base_args()
    args.batch_output_dir = str(tmp_path / "batch")
    args.batch_summary_json = str(tmp_path / "batch" / "summary.json")

    commands: list[list[str]] = []

    class _Result:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    def _fake_run(command: list[str], check: bool = False):  # noqa: ARG001
        commands.append(command)
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
