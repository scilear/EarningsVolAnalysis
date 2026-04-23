"""Tests for macro binary-event outcomes store and tail-rate query."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from event_vol_analysis.macro_outcomes import (
    load_macro_event_outcomes,
    query_event_type_tail_rate,
    store_macro_event_outcome,
)


def test_store_and_load_macro_outcomes(tmp_path: Path) -> None:
    data_dir = tmp_path / "macro_event_outcomes"
    file_path = store_macro_event_outcome(
        event_type="geopolitical",
        event_date=dt.date(2026, 4, 10),
        underlying="SPY",
        implied_move_pct=0.021,
        realized_move_pct=0.035,
        vix_at_entry=28.4,
        vvix_percentile_at_entry=78.0,
        gex_zone="Strong Amplified",
        vol_crush=-0.08,
        notes="Sample seed",
        data_dir=data_dir,
    )

    assert file_path.exists()
    records = load_macro_event_outcomes(data_dir)
    assert len(records) == 1
    assert records[0].event_type == "geopolitical"
    assert records[0].underlying == "SPY"
    assert records[0].move_vs_implied_ratio == pytest.approx(0.035 / 0.021)


def test_query_event_type_tail_rate_counts_and_flag(tmp_path: Path) -> None:
    data_dir = tmp_path / "macro_event_outcomes"
    # Two tail events and one non-tail event for geopolitical.
    store_macro_event_outcome(
        event_type="geopolitical",
        event_date="2026-04-10",
        underlying="SPY",
        implied_move_pct=0.020,
        realized_move_pct=0.032,
        vix_at_entry=30.0,
        vvix_percentile_at_entry=82.0,
        gex_zone="Strong Amplified",
        vol_crush=-0.05,
        data_dir=data_dir,
    )
    store_macro_event_outcome(
        event_type="geopolitical",
        event_date="2026-04-15",
        underlying="XLE",
        implied_move_pct=0.018,
        realized_move_pct=0.016,
        vix_at_entry=26.0,
        vvix_percentile_at_entry=71.0,
        gex_zone="Uncertain",
        vol_crush=-0.03,
        data_dir=data_dir,
    )
    store_macro_event_outcome(
        event_type="geopolitical",
        event_date="2026-04-20",
        underlying="XOP",
        implied_move_pct=0.022,
        realized_move_pct=0.041,
        vix_at_entry=33.0,
        vvix_percentile_at_entry=88.0,
        gex_zone="Strong Amplified",
        vol_crush=-0.07,
        data_dir=data_dir,
    )

    summary = query_event_type_tail_rate(
        "geopolitical",
        threshold_sd=1.0,
        data_dir=data_dir,
    )

    assert summary["event_type"] == "geopolitical"
    assert summary["tail_event_count"] == 2
    assert summary["total_events"] == 3
    assert summary["has_min_2_tail_events"] is True
    assert summary["tail_rate"] == pytest.approx(2.0 / 3.0)


def test_query_event_type_tail_rate_with_vix_quartile_filter(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "macro_event_outcomes"
    store_macro_event_outcome(
        event_type="fomc",
        event_date="2026-06-12",
        underlying="SPY",
        implied_move_pct=0.014,
        realized_move_pct=0.020,
        vix_at_entry=18.0,
        vvix_percentile_at_entry=55.0,
        gex_zone="Neutral",
        vol_crush=-0.04,
        vix_quartile=2,
        data_dir=data_dir,
    )
    store_macro_event_outcome(
        event_type="fomc",
        event_date="2026-07-29",
        underlying="SPY",
        implied_move_pct=0.015,
        realized_move_pct=0.028,
        vix_at_entry=24.0,
        vvix_percentile_at_entry=72.0,
        gex_zone="Uncertain",
        vol_crush=-0.05,
        vix_quartile=3,
        data_dir=data_dir,
    )

    quartile_two = query_event_type_tail_rate(
        "fomc",
        threshold_sd=1.2,
        vix_quartile=2,
        data_dir=data_dir,
    )
    quartile_three = query_event_type_tail_rate(
        "fomc",
        threshold_sd=1.2,
        vix_quartile=3,
        data_dir=data_dir,
    )

    assert quartile_two["total_events"] == 1
    assert quartile_two["tail_event_count"] == 1
    assert quartile_three["total_events"] == 1
    assert quartile_three["tail_event_count"] == 1


def test_store_macro_outcome_rejects_invalid_event_type(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="event_type must be one of"):
        store_macro_event_outcome(
            event_type="cpi",
            event_date="2026-08-01",
            underlying="SPY",
            implied_move_pct=0.01,
            realized_move_pct=0.02,
            vix_at_entry=20.0,
            vvix_percentile_at_entry=60.0,
            gex_zone="Neutral",
            vol_crush=-0.01,
            data_dir=tmp_path,
        )


def test_store_macro_outcome_rejects_invalid_vix_quartile(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="vix_quartile"):
        store_macro_event_outcome(
            event_type="regulatory",
            event_date="2026-08-01",
            underlying="XLE",
            implied_move_pct=0.01,
            realized_move_pct=0.02,
            vix_at_entry=20.0,
            vvix_percentile_at_entry=60.0,
            gex_zone="Neutral",
            vol_crush=-0.01,
            vix_quartile=5,
            data_dir=tmp_path,
        )
