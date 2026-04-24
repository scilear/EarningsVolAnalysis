"""Tests for the QuantConnect replay scaffold export."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from data.option_data_store import create_store
from research.quantconnect.quantconnect_replay_scaffold import (
    QCScaffoldConfig,
    build_qc_scaffold,
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


def test_build_qc_scaffold_exports_event_payload_and_stub(tmp_path: Path) -> None:
    db_path = tmp_path / "qc.db"
    _seed_event_sample(db_path)

    scaffold = build_qc_scaffold(
        QCScaffoldConfig(
            db_path=str(db_path),
            event_family="earnings",
            underlying_symbol="NVDA",
        )
    )

    assert scaffold["coverage"]["events"] == 1
    assert scaffold["events"][0]["primary_pre_event_snapshot"] == "pre_close_d0"
    assert (
        scaffold["events"][0]["top_structure"]["structure_code"] == "long_straddle_atm"
    )
    assert (
        scaffold["events"][0]["structures"][0]["structure_code"] == "long_straddle_atm"
    )
    assert 'self.symbol = self.AddEquity("NVDA"' in scaffold["algorithm_stub"]
    assert 'payload_path = "event_replay_payload.json"' in scaffold["research_template"]
    assert "qb = QuantBook()" in scaffold["research_template"]
