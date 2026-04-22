"""Tests for post-earnings outcome tracking workflow (T030)."""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from event_vol_analysis.outcomes import (
    auto_populate_realized_move,
    get_outcome_record,
    store_prediction,
    update_outcome,
)


def _inputs() -> tuple[dict, dict, dict]:
    type_classification = {
        "type": 1,
        "confidence": "HIGH",
    }
    edge_ratio = {
        "label": "CHEAP",
        "ratio": 0.82,
        "confidence": "MEDIUM",
        "implied": 0.05,
        "conditional_expected_primary": 0.061,
    }
    vol_regime = {
        "label": "CHEAP",
    }
    return type_classification, edge_ratio, vol_regime


def _amc_history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": [
                dt.date(2026, 5, 1),
                dt.date(2026, 5, 4),
            ],
            "Open": [100.0, 109.0],
            "Close": [100.0, 110.0],
        }
    )


def _bmo_history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": [
                dt.date(2026, 4, 30),
                dt.date(2026, 5, 1),
            ],
            "Open": [101.0, 95.0],
            "Close": [100.0, 94.0],
        }
    )


def test_store_prediction_inserts_record(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"
    type_classification, edge_ratio, vol_regime = _inputs()

    record = store_prediction(
        "NVDA",
        "2026-05-01",
        type_classification,
        edge_ratio,
        vol_regime,
        timing="AMC",
        db_path=db_path,
    )

    assert record.ticker == "NVDA"
    assert record.event_date == dt.date(2026, 5, 1)
    assert record.predicted_type == 1
    assert record.edge_ratio_label == "CHEAP"
    assert record.outcome_complete is False


def test_store_prediction_duplicate_raises(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"
    type_classification, edge_ratio, vol_regime = _inputs()

    store_prediction(
        "NVDA",
        "2026-05-01",
        type_classification,
        edge_ratio,
        vol_regime,
        timing="AMC",
        db_path=db_path,
    )

    with pytest.raises(ValueError, match="already exists"):
        store_prediction(
            "NVDA",
            "2026-05-01",
            type_classification,
            edge_ratio,
            vol_regime,
            timing="AMC",
            db_path=db_path,
        )


def test_update_outcome_sets_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"
    type_classification, edge_ratio, vol_regime = _inputs()
    store_prediction(
        "NVDA",
        "2026-05-01",
        type_classification,
        edge_ratio,
        vol_regime,
        timing="AMC",
        db_path=db_path,
    )

    record = update_outcome(
        "NVDA",
        "2026-05-01",
        phase1_category="HELD_REPRICING",
        entry_taken=True,
        pnl=1.25,
        db_path=db_path,
    )

    assert record.phase1_category == "HELD_REPRICING"
    assert record.entry_taken is True
    assert record.pnl_if_entered == pytest.approx(1.25)


def test_update_outcome_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"
    type_classification, edge_ratio, vol_regime = _inputs()
    store_prediction(
        "NVDA",
        "2026-05-01",
        type_classification,
        edge_ratio,
        vol_regime,
        timing="AMC",
        db_path=db_path,
    )

    first = update_outcome(
        "NVDA",
        "2026-05-01",
        phase1_category="HELD_REPRICING",
        entry_taken=False,
        pnl=None,
        db_path=db_path,
    )
    second = update_outcome(
        "NVDA",
        "2026-05-01",
        phase1_category="HELD_REPRICING",
        entry_taken=False,
        pnl=None,
        db_path=db_path,
    )

    assert first.phase1_category == second.phase1_category
    assert first.entry_taken == second.entry_taken


def test_auto_populate_amc_day_pair(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"
    type_classification, edge_ratio, vol_regime = _inputs()
    store_prediction(
        "NVDA",
        "2026-05-01",
        type_classification,
        edge_ratio,
        vol_regime,
        timing="AMC",
        db_path=db_path,
    )

    record = auto_populate_realized_move(
        "NVDA",
        "2026-05-01",
        db_path=db_path,
        price_history=_amc_history(),
    )
    assert record is not None
    assert record.realized_move == pytest.approx(0.10)
    assert record.realized_move_direction == "UP"


def test_auto_populate_bmo_day_pair(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"
    type_classification, edge_ratio, vol_regime = _inputs()
    store_prediction(
        "NVDA",
        "2026-05-01",
        type_classification,
        edge_ratio,
        vol_regime,
        timing="BMO",
        db_path=db_path,
    )

    record = auto_populate_realized_move(
        "NVDA",
        "2026-05-01",
        db_path=db_path,
        price_history=_bmo_history(),
    )
    assert record is not None
    assert record.realized_move == pytest.approx(0.05)
    assert record.realized_move_direction == "DOWN"


def test_outcome_complete_flag_false_when_partial(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"
    type_classification, edge_ratio, vol_regime = _inputs()
    store_prediction(
        "NVDA",
        "2026-05-01",
        type_classification,
        edge_ratio,
        vol_regime,
        timing="AMC",
        db_path=db_path,
    )

    record = auto_populate_realized_move(
        "NVDA",
        "2026-05-01",
        db_path=db_path,
        price_history=_amc_history(),
    )
    assert record is not None
    assert record.outcome_complete is False


def test_outcome_complete_flag_true_when_both_set(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"
    type_classification, edge_ratio, vol_regime = _inputs()
    store_prediction(
        "NVDA",
        "2026-05-01",
        type_classification,
        edge_ratio,
        vol_regime,
        timing="AMC",
        db_path=db_path,
    )
    auto_populate_realized_move(
        "NVDA",
        "2026-05-01",
        db_path=db_path,
        price_history=_amc_history(),
    )

    updated = update_outcome(
        "NVDA",
        "2026-05-01",
        phase1_category="HELD_REPRICING",
        entry_taken=False,
        pnl=None,
        db_path=db_path,
    )
    assert updated.outcome_complete is True


def test_realized_vs_implied_ratio_calculation(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"
    type_classification, edge_ratio, vol_regime = _inputs()
    store_prediction(
        "NVDA",
        "2026-05-01",
        type_classification,
        edge_ratio,
        vol_regime,
        timing="AMC",
        db_path=db_path,
    )

    record = auto_populate_realized_move(
        "NVDA",
        "2026-05-01",
        db_path=db_path,
        price_history=_amc_history(),
    )
    assert record is not None
    assert record.realized_vs_implied_ratio == pytest.approx(2.0)


def test_full_flow_store_auto_update_query(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"
    type_classification, edge_ratio, vol_regime = _inputs()

    store_prediction(
        "NVDA",
        "2026-05-01",
        type_classification,
        edge_ratio,
        vol_regime,
        timing="AMC",
        db_path=db_path,
    )
    auto_populate_realized_move(
        "NVDA",
        "2026-05-01",
        db_path=db_path,
        price_history=_amc_history(),
    )
    update_outcome(
        "NVDA",
        "2026-05-01",
        phase1_category="POTENTIAL_OVERSHOOT",
        entry_taken=True,
        pnl=3.0,
        db_path=db_path,
    )

    row = get_outcome_record("NVDA", "2026-05-01", db_path=db_path)
    assert row is not None
    assert row.outcome_complete is True
    assert row.phase1_category == "POTENTIAL_OVERSHOOT"


def test_update_script_runs_and_updates_record(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"
    script_path = Path("scripts/update_earnings_outcome.py")
    type_classification, edge_ratio, vol_regime = _inputs()
    store_prediction(
        "NVDA",
        "2026-05-01",
        type_classification,
        edge_ratio,
        vol_regime,
        timing="AMC",
        db_path=db_path,
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--ticker",
            "NVDA",
            "--event-date",
            "2026-05-01",
            "--phase1",
            "HELD_REPRICING",
            "--entry",
            "yes",
            "--pnl",
            "2.5",
            "--db",
            str(db_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Updated outcome record" in completed.stdout
