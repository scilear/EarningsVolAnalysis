"""Tests for manifest-driven event backfill helpers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from data.option_data_store import create_store
from event_option_playbook.backfill import backfill_event_manifest


def _store_chain_snapshot(db_path: Path, quote_ts: datetime) -> None:
    store = create_store(db_path)
    chain = pd.DataFrame(
        [
            {
                "strike": 100.0,
                "optionType": "call",
                "bid": 4.0,
                "ask": 4.4,
                "volume": 25,
                "openInterest": 100,
                "impliedVolatility": 0.35,
                "expiration": "2026-06-19",
            }
        ]
    )
    store.store_chain("NVDA", quote_ts, chain, underlying_price=101.0)


def test_backfill_event_manifest_registers_workbook_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "events.db"
    quote_ts = datetime(2026, 5, 27, 21, 0, 0)
    _store_chain_snapshot(db_path, quote_ts)

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "event_family": "earnings",
                        "event_name": "nvda_q1",
                        "underlying_symbol": "NVDA",
                        "event_date": "2026-05-28",
                        "source_system": "manual",
                        "event_time_label": "ah",
                        "snapshot_bindings": [
                            {
                                "snapshot_label": "pre_close_d0",
                                "timing_bucket": "pre_event",
                                "quote_ts": quote_ts.isoformat(),
                                "ticker": "NVDA",
                                "rel_trade_days_to_event": -1,
                                "selection_method": "nearest_before_close",
                                "is_primary": True,
                            }
                        ],
                        "surface_metrics": [
                            {
                                "snapshot_label": "pre_close_d0",
                                "quote_ts": quote_ts.isoformat(),
                                "ticker": "NVDA",
                                "metrics": {
                                    "spot": 101.0,
                                    "front_expiry": "2026-06-19",
                                    "back_expiry": "2026-06-26",
                                    "front_dte": 22,
                                    "back_dte": 29,
                                    "atm_iv_front": 0.35,
                                    "atm_iv_back": 0.31,
                                    "iv_ratio": 1.13,
                                    "implied_move_pct": 0.05,
                                    "event_variance_ratio": 0.5,
                                },
                            }
                        ],
                        "realized_outcomes": [
                            {
                                "horizon_code": "h1_close",
                                "pre_snapshot_label": "pre_close_d0",
                                "post_snapshot_label": "post_close_d1",
                                "outcome": {
                                    "spot_pre": 101.0,
                                    "spot_post": 106.0,
                                    "realized_move_signed_pct": 0.0495,
                                    "realized_move_abs_pct": 0.0495,
                                },
                            }
                        ],
                        "structure_replays": [
                            {
                                "structure_code": "long_straddle_atm",
                                "entry_snapshot_label": "pre_close_d0",
                                "exit_horizon_code": "h1_close",
                                "replay": {
                                    "assumptions_version": "v1",
                                    "pricing_model_version": "midmark_v1",
                                    "entry_cost": -8.0,
                                    "exit_value": 10.5,
                                    "realized_pnl": 2.5,
                                    "realized_pnl_pct": 0.3125,
                                    "max_risk_at_entry": 8.0,
                                },
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    summary = backfill_event_manifest(manifest_path, db_path=str(db_path))
    store = create_store(db_path)

    assert summary["events_processed"] == 1
    assert summary["snapshot_bindings"] == 1
    assert summary["surface_metrics"] == 1
    assert summary["realized_outcomes"] == 1
    assert summary["structure_replays"] == 1
    assert not store.get_event_registry(summary["event_ids"][0]).empty


def test_backfill_event_manifest_rejects_missing_snapshot(tmp_path: Path) -> None:
    db_path = tmp_path / "events.db"
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "event_family": "earnings",
                        "event_name": "nvda_q1",
                        "underlying_symbol": "NVDA",
                        "event_date": "2026-05-28",
                        "source_system": "manual",
                        "snapshot_bindings": [
                            {
                                "snapshot_label": "pre_close_d0",
                                "timing_bucket": "pre_event",
                                "quote_ts": "2026-05-27T21:00:00",
                                "ticker": "NVDA",
                                "rel_trade_days_to_event": -1,
                                "selection_method": "nearest_before_close",
                                "is_primary": True,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="No stored option chain found"):
        backfill_event_manifest(manifest_path, db_path=str(db_path))
