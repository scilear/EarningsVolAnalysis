"""Tests for additive event-storage extensions in the option data store."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from data.option_data_store import create_store


def test_store_initializes_event_extension_tables(tmp_path: Path) -> None:
    store = create_store(tmp_path / "options.db")
    registry = store.get_event_registry()
    assert registry.empty


def test_register_event_and_bind_snapshot(tmp_path: Path) -> None:
    store = create_store(tmp_path / "options.db")
    event_id = "earnings:nvda_q1:NVDA:2026-05-28"
    quote_ts = datetime(2026, 5, 27, 21, 0, 0)

    store.register_event(
        event_id=event_id,
        event_family="earnings",
        event_name="nvda_q1",
        underlying_symbol="NVDA",
        event_date=date(2026, 5, 28),
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

    registry = store.get_event_registry(event_id)
    bindings = store.get_event_snapshot_bindings(event_id)

    assert len(registry) == 1
    assert registry.iloc[0]["event_name"] == "nvda_q1"
    assert len(bindings) == 1
    assert bindings.iloc[0]["snapshot_label"] == "pre_close_d0"
    assert int(bindings.iloc[0]["is_primary"]) == 1


def test_store_surface_metrics_realized_outcome_and_replay(tmp_path: Path) -> None:
    store = create_store(tmp_path / "options.db")
    event_id = "macro:cpi:QQQ:2026-06-10"
    quote_ts = datetime(2026, 6, 9, 21, 0, 0)

    store.register_event(
        event_id=event_id,
        event_family="macro",
        event_name="cpi",
        underlying_symbol="QQQ",
        proxy_symbol="QQQ",
        event_date="2026-06-10",
        source_system="econ-calendar",
        event_ts_utc=datetime(2026, 6, 10, 12, 30, 0),
        event_time_label="am",
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
            "skew_25d_rr": -0.01,
            "skew_25d_bf": 0.02,
            "gex_proxy": 1500000.0,
            "liquidity_score": 0.82,
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
            "iv_front_pre": 0.32,
            "iv_front_post": 0.25,
            "iv_change_abs": -0.07,
            "iv_change_pct": -0.21875,
            "iv_crush_abs": 0.07,
            "iv_crush_pct": 0.21875,
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

    with store._get_connection() as conn:
        metrics = conn.execute(
            "SELECT * FROM event_surface_metrics WHERE event_id = ?",
            (event_id,),
        ).fetchall()
        outcomes = conn.execute(
            "SELECT * FROM event_realized_outcome WHERE event_id = ?",
            (event_id,),
        ).fetchall()
        replays = conn.execute(
            "SELECT * FROM structure_replay_outcome WHERE event_id = ?",
            (event_id,),
        ).fetchall()
        horizons = conn.execute(
            "SELECT horizon_code FROM event_evaluation_horizon ORDER BY horizon_code"
        ).fetchall()

    assert len(metrics) == 1
    assert len(outcomes) == 1
    assert len(replays) == 1
    assert {row[0] for row in horizons} >= {"h0_close", "h1_close", "h3_close"}
