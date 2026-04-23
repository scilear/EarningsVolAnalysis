"""Tests for the macro ETF event workbook summary layer."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from data.option_data_store import create_store
from event_vol_analysis.macro_outcomes import store_macro_event_outcome
from research.macro.macro_event_workbook import (
    MacroWorkbookConfig,
    build_workbook_summary,
    render_markdown,
)


def _seed_macro_sample(db_path: Path) -> None:
    store = create_store(db_path)
    event_id = "macro:cpi:QQQ:2026-06-10"
    quote_ts = datetime(2026, 6, 9, 21, 0, 0)

    store.register_event(
        event_id=event_id,
        event_family="macro",
        event_name="cpi",
        underlying_symbol="QQQ",
        proxy_symbol="TLT",
        event_date="2026-06-10",
        source_system="econ-calendar",
        event_ts_utc=datetime(2026, 6, 10, 12, 30, 0),
        event_time_label="am",
    )
    store.bind_snapshot_to_event(
        event_id=event_id,
        snapshot_label="pre_close_d0",
        timing_bucket="pre_event",
        quote_ts=quote_ts,
        ticker="QQQ",
        rel_trade_days_to_event=-1,
        selection_method="nearest_before_close",
        is_primary=True,
    )
    store.store_surface_metrics(
        event_id=event_id,
        snapshot_label="pre_close_d0",
        quote_ts=quote_ts,
        ticker="QQQ",
        metrics={
            "spot": 500.0,
            "front_expiry": "2026-06-12",
            "back_expiry": "2026-06-19",
            "front_dte": 2,
            "back_dte": 9,
            "atm_iv_front": 0.32,
            "atm_iv_back": 0.24,
            "iv_ratio": 1.33,
            "implied_move_pct": 0.025,
            "event_variance_ratio": 0.58,
        },
    )
    store.store_realized_outcome(
        event_id=event_id,
        horizon_code="h1_close",
        pre_snapshot_label="pre_close_d0",
        post_snapshot_label="post_close_d1",
        outcome={
            "spot_pre": 500.0,
            "spot_post": 512.5,
            "realized_move_signed_pct": 0.025,
            "realized_move_abs_pct": 0.025,
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
            "entry_cost": -12.5,
            "exit_value": 18.0,
            "realized_pnl": 5.5,
            "realized_pnl_pct": 0.44,
            "max_risk_at_entry": 12.5,
        },
    )


def test_build_workbook_summary_returns_macro_sections(tmp_path: Path) -> None:
    db_path = tmp_path / "macro.db"
    _seed_macro_sample(db_path)
    store_macro_event_outcome(
        event_type="fomc",
        event_date="2026-06-12",
        underlying="SPY",
        implied_move_pct=0.015,
        realized_move_pct=0.024,
        vix_at_entry=21.0,
        vvix_percentile_at_entry=66.0,
        gex_zone="Uncertain",
        vol_crush=-0.04,
        data_dir=tmp_path / "macro_event_outcomes",
    )
    store_macro_event_outcome(
        event_type="fomc",
        event_date="2026-07-29",
        underlying="SPY",
        implied_move_pct=0.014,
        realized_move_pct=0.021,
        vix_at_entry=19.0,
        vvix_percentile_at_entry=62.0,
        gex_zone="Neutral",
        vol_crush=-0.03,
        data_dir=tmp_path / "macro_event_outcomes",
    )

    summary = build_workbook_summary(
        MacroWorkbookConfig(
            db_path=str(db_path),
            event_name="cpi",
            proxy_symbol="TLT",
            macro_event_type="fomc",
            macro_outcomes_dir=str(tmp_path / "macro_event_outcomes"),
        )
    )

    assert summary["coverage"]["events"] == 1
    assert summary["event_timing"]["events_with_precise_timestamp"] == 1
    assert summary["event_timing"]["proxy_symbols"] == ["TLT"]
    assert summary["structure_outcomes"][0]["structure_code"] == "long_straddle_atm"
    assert summary["tail_rate_gate"]["event_type"] == "fomc"
    assert summary["tail_rate_gate"]["has_min_2_tail_events"] is True


def test_render_markdown_contains_expected_sections(tmp_path: Path) -> None:
    db_path = tmp_path / "macro.db"
    _seed_macro_sample(db_path)
    store_macro_event_outcome(
        event_type="fomc",
        event_date="2026-06-12",
        underlying="SPY",
        implied_move_pct=0.015,
        realized_move_pct=0.024,
        vix_at_entry=21.0,
        vvix_percentile_at_entry=66.0,
        gex_zone="Uncertain",
        vol_crush=-0.04,
        data_dir=tmp_path / "macro_event_outcomes",
    )
    store_macro_event_outcome(
        event_type="fomc",
        event_date="2026-07-29",
        underlying="SPY",
        implied_move_pct=0.014,
        realized_move_pct=0.021,
        vix_at_entry=19.0,
        vvix_percentile_at_entry=62.0,
        gex_zone="Neutral",
        vol_crush=-0.03,
        data_dir=tmp_path / "macro_event_outcomes",
    )

    markdown = render_markdown(
        build_workbook_summary(
            MacroWorkbookConfig(
                db_path=str(db_path),
                event_name="cpi",
                proxy_symbol="TLT",
                macro_event_type="fomc",
                macro_outcomes_dir=str(tmp_path / "macro_event_outcomes"),
            )
        )
    )

    assert "# Macro Event Workbook" in markdown
    assert "## Event Timing" in markdown
    assert "long_straddle_atm" in markdown
    assert "## Tail Rate Gate" in markdown
