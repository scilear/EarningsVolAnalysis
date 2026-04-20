"""Tests for foundational event replay context assembly."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from data.option_data_store import create_store
from event_option_playbook.replay import (
    ReplayAssumptions,
    load_event_replay_context,
    replay_selection_summary,
)


def _seed_chain_snapshot(
    store,
    ticker: str,
    timestamp: datetime,
) -> None:
    chain = pd.DataFrame(
        [
            {
                "strike": 100.0,
                "optionType": "call",
                "bid": 5.0,
                "ask": 5.5,
                "volume": 100,
                "openInterest": 200,
                "impliedVolatility": 0.4,
                "expiration": "2026-06-19",
            },
            {
                "strike": 100.0,
                "optionType": "put",
                "bid": 4.8,
                "ask": 5.3,
                "volume": 120,
                "openInterest": 210,
                "impliedVolatility": 0.41,
                "expiration": "2026-06-19",
            },
        ]
    )
    store.store_chain(
        ticker=ticker,
        timestamp=timestamp,
        chain_df=chain,
        underlying_price=100.0,
    )


def test_load_event_replay_context_resolves_event_state(tmp_path: Path) -> None:
    store = create_store(tmp_path / "options.db")
    event_id = "earnings:nvda_q1:NVDA:2026-05-28"
    quote_ts = datetime(2026, 5, 27, 21, 0, 0)

    _seed_chain_snapshot(store, "NVDA", quote_ts)
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
        },
    )

    context = load_event_replay_context(
        store,
        event_id,
        assumptions=ReplayAssumptions(entry_snapshot_label="pre_close_d0"),
    )

    assert context.event_id == event_id
    assert context.primary_pre_event_binding()["snapshot_label"] == "pre_close_d0"
    assert context.outcome_for_horizon("h1_close")["spot_post"] == 108.0
    assert len(context.snapshot_chain(store, "pre_close_d0")) == 2


def test_replay_selection_summary_exposes_available_horizons(tmp_path: Path) -> None:
    store = create_store(tmp_path / "options.db")
    event_id = "macro:cpi:QQQ:2026-06-10"
    quote_ts = datetime(2026, 6, 9, 21, 0, 0)

    _seed_chain_snapshot(store, "QQQ", quote_ts)
    store.register_event(
        event_id=event_id,
        event_family="macro",
        event_name="cpi",
        underlying_symbol="QQQ",
        proxy_symbol="QQQ",
        event_date="2026-06-10",
        source_system="econ-calendar",
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

    summary = replay_selection_summary(load_event_replay_context(store, event_id))

    assert summary["event_id"] == event_id
    assert "pre_close_d0" in summary["available_snapshot_labels"]
    assert {"h0_close", "h1_close", "h3_close"} <= set(summary["available_horizons"])
