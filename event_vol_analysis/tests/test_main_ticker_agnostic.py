"""Regression coverage for ticker-agnostic main-path behavior."""

from __future__ import annotations

import argparse
from pathlib import Path

from event_vol_analysis import main as main_module


def test_main_uses_explicit_non_nvda_ticker_in_test_data_mode(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict = {}

    def _capture_report(path: Path, context: dict) -> None:
        captured["path"] = path
        captured["context"] = context

    args = argparse.Namespace(
        ticker="TSLA",
        tickers=None,
        ticker_file=None,
        event_date=None,
        output=None,
        cache_dir="data/cache",
        use_cache=False,
        refresh_cache=False,
        seed=42,
        move_model="lognormal",
        test_data=True,
        test_scenario="baseline",
        test_data_dir=None,
        save_test_data=None,
        batch_output_dir="reports/batch",
        batch_summary_json=None,
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", lambda self: args)
    monkeypatch.setattr(main_module, "write_report", _capture_report)
    monkeypatch.setattr(
        main_module, "plot_move_comparison", lambda *a, **k: "move-plot"
    )
    monkeypatch.setattr(
        main_module, "plot_pnl_distribution", lambda *a, **k: "pnl-plot"
    )
    monkeypatch.setattr(main_module, "_print_console_snapshot", lambda *a, **k: None)

    main_module.main()

    assert captured["context"]["ticker"] == "TSLA"
    assert captured["context"]["generic_event"]["underlying"] == "TSLA"
    assert captured["path"] == Path("reports/tsla_earnings_report.html")
    assert "conditional_expected" in captured["context"]["snapshot"]
    assert "timing_splits" in captured["context"]["snapshot"]
    assert "edge_ratio" in captured["context"]["snapshot"]
    assert "positioning" in captured["context"]["snapshot"]
    assert "signal_graph" in captured["context"]["snapshot"]
    assert "trust_metrics" in captured["context"]["snapshot"]
    assert captured["context"]["snapshot"]["trust_metrics"]["status"] in {
        "PASS",
        "WARN",
        "FAIL",
    }
    assert "type_classification" in captured["context"]["snapshot"]
    assert "vanna_net" in captured["context"]["snapshot"]
    assert "charm_net" in captured["context"]["snapshot"]
    assert "pin_strikes" in captured["context"]["snapshot"]
    assert "gex_by_strike_top" in captured["context"]["snapshot"]
    assert "ivr" in captured["context"]["regime"]
    assert "ivp" in captured["context"]["regime"]
    assert "vanna_net" in captured["context"]["regime"]
    assert "charm_net" in captured["context"]["regime"]
    assert "macro_vehicle_class" in captured["context"]["regime"]
    assert "macro_vehicle_supported" in captured["context"]["regime"]
    assert "macro_requires_forward_model" in captured["context"]["regime"]


def test_load_tickers_from_file_supports_csv_and_newlines(tmp_path: Path) -> None:
    ticker_file = tmp_path / "tickers.txt"
    ticker_file.write_text("nvda, tsla\nmsft\n", encoding="utf-8")

    loaded = main_module._load_tickers_from_file(str(ticker_file))

    assert loaded == ["NVDA", "TSLA", "MSFT"]


def test_main_uses_default_move_model_when_missing_from_args(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict = {}

    def _capture_report(path: Path, context: dict) -> None:
        captured["path"] = path
        captured["context"] = context

    args = argparse.Namespace(
        ticker="TSLA",
        tickers=None,
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
        batch_summary_json=None,
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", lambda self: args)
    monkeypatch.setattr(main_module, "write_report", _capture_report)
    monkeypatch.setattr(
        main_module, "plot_move_comparison", lambda *a, **k: "move-plot"
    )
    monkeypatch.setattr(
        main_module, "plot_pnl_distribution", lambda *a, **k: "pnl-plot"
    )
    monkeypatch.setattr(main_module, "_print_console_snapshot", lambda *a, **k: None)

    main_module.main()

    assert captured["context"]["snapshot"]["move_model_selected"] == "fat_tailed"
