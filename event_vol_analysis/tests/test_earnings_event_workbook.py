"""Tests for the earnings event workbook summary layer."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from data.option_data_store import create_store
from research.earnings.earnings_event_workbook import (
    WorkbookConfig,
    build_workbook_summary,
    render_markdown,
)


def _seed_event_sample(db_path: Path) -> None:
    store = create_store(db_path)
    event_id = "earnings:nvda_q1:NVDA:2026-05-28"
    quote_ts = datetime(2026, 5, 27, 21, 0, 0)

    store.register_event(
        event_id=event_id,
        event_family="earnings",
        event_name="nvda_q1",
        underlying_symbol="NVDA",
        event_date="2026-05-28",
        source_system="manual",
        event_time_label="ah",
    )
    store.bind_snapshot_to_event(
        event_id=event_id,
        snapshot_label="pre_close_d0",
        timing_bucket="pre_event",
        quote_ts=quote_ts,
        ticker="NVDA",
        rel_trade_days_to_event=-1,
        selection_method="nearest_before_close",
        is_primary=True,
    )
    store.store_surface_metrics(
        event_id=event_id,
        snapshot_label="pre_close_d0",
        quote_ts=quote_ts,
        ticker="NVDA",
        metrics={
            "spot": 100.0,
            "front_expiry": "2026-06-19",
            "back_expiry": "2026-06-26",
            "front_dte": 22,
            "back_dte": 29,
            "atm_iv_front": 0.4,
            "atm_iv_back": 0.35,
            "iv_ratio": 1.14,
            "implied_move_pct": 0.06,
            "event_variance_ratio": 0.55,
        },
    )
    store.store_realized_outcome(
        event_id=event_id,
        horizon_code="h1_close",
        pre_snapshot_label="pre_close_d0",
        post_snapshot_label="post_close_d1",
        outcome={
            "spot_pre": 100.0,
            "spot_post": 108.0,
            "realized_move_signed_pct": 0.08,
            "realized_move_abs_pct": 0.08,
            "iv_front_pre": 0.4,
            "iv_front_post": 0.3,
            "iv_change_abs": -0.1,
            "iv_change_pct": -0.25,
            "iv_crush_abs": 0.1,
            "iv_crush_pct": 0.25,
        },
    )
    store.store_structure_replay_outcome(
        event_id=event_id,
        structure_code="long_straddle_atm",
        entry_snapshot_label="pre_close_d0",
        exit_horizon_code="h1_close",
        replay={
            "assumptions_version": "v1",
            "pricing_model_version": "midmark_v1",
            "entry_cost": -12.0,
            "exit_value": 18.5,
            "realized_pnl": 6.5,
            "realized_pnl_pct": 0.5417,
            "max_risk_at_entry": 12.0,
        },
    )


def test_build_workbook_summary_returns_coverage_and_sections(tmp_path: Path) -> None:
    db_path = tmp_path / "earnings.db"
    _seed_event_sample(db_path)

    summary = build_workbook_summary(
        WorkbookConfig(db_path=str(db_path), ticker="NVDA")
    )

    assert summary["coverage"]["events"] == 1
    assert summary["coverage"]["outcomes"] == 1
    assert summary["realized_moves"]["sample_size"] == 1
    assert summary["iv_crush"]["sample_size"] == 1
    assert summary["structure_outcomes"][0]["structure_code"] == "long_straddle_atm"


def test_render_markdown_contains_expected_sections(tmp_path: Path) -> None:
    db_path = tmp_path / "earnings.db"
    _seed_event_sample(db_path)

    markdown = render_markdown(
        build_workbook_summary(WorkbookConfig(db_path=str(db_path), ticker="NVDA"))
    )

    assert "# Earnings Event Workbook" in markdown
    assert "## Realized Moves" in markdown
    assert "long_straddle_atm" in markdown
