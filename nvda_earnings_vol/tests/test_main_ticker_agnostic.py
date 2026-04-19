"""Regression coverage for ticker-agnostic main-path behavior."""

from __future__ import annotations

import argparse
from pathlib import Path

from nvda_earnings_vol import main as main_module


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
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", lambda self: args)
    monkeypatch.setattr(main_module, "write_report", _capture_report)
    monkeypatch.setattr(main_module, "plot_move_comparison", lambda *a, **k: "move-plot")
    monkeypatch.setattr(main_module, "plot_pnl_distribution", lambda *a, **k: "pnl-plot")
    monkeypatch.setattr(main_module, "_print_console_snapshot", lambda *a, **k: None)

    main_module.main()

    assert captured["context"]["ticker"] == "TSLA"
    assert captured["context"]["generic_event"]["underlying"] == "TSLA"
    assert captured["path"] == Path("reports/tsla_earnings_report.html")
