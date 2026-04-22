"""Tests for historical move stats and conditional expected move helpers."""

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from event_vol_analysis.analytics.historical import (
    calibrate_fat_tail_inputs,
    conditional_expected_move,
    compute_distribution_shape,
    earnings_move_p75,
    extract_earnings_moves,
    extract_earnings_moves_with_dates,
    recency_weighted_mean,
    split_by_timing,
    trimmed_mean_move,
)


def test_earnings_move_p75() -> None:
    data = pd.DataFrame(
        {
            "Date": [
                dt.date(2024, 1, 2),
                dt.date(2024, 1, 3),
                dt.date(2024, 1, 4),
                dt.date(2024, 1, 5),
            ],
            "Close": [100.0, 110.0, 105.0, 120.0],
        }
    )
    earnings_dates = [pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-05")]
    p75 = earnings_move_p75(data, earnings_dates)
    assert 0.1 < p75 < 0.15


def test_compute_distribution_shape_handles_small_sample_without_nan() -> None:
    stats = compute_distribution_shape([0.01, -0.02])
    assert stats["skewness"] == 0.0
    assert stats["kurtosis"] == 0.0


def test_calibrate_fat_tail_inputs_disables_when_sample_too_small() -> None:
    out = calibrate_fat_tail_inputs([0.01, -0.02, 0.015])
    assert out["sample_size"] == 3
    assert out["target_excess_kurtosis"] == 0.0
    assert out["fat_tail_active"] is False


def test_calibrate_fat_tail_inputs_scales_with_sample_size() -> None:
    moves_small = [-0.20, 0.20, -0.05, 0.05, -0.02, 0.02]
    moves_large = [
        -0.20,
        0.20,
        -0.15,
        0.15,
        -0.10,
        0.10,
        -0.06,
        0.06,
        -0.04,
        0.04,
        -0.02,
        0.02,
    ]

    small = calibrate_fat_tail_inputs(moves_small)
    large = calibrate_fat_tail_inputs(moves_large)

    assert small["fat_tail_active"] == (small["target_excess_kurtosis"] > 0.0)
    assert large["fat_tail_active"] == (large["target_excess_kurtosis"] > 0.0)
    assert large["target_excess_kurtosis"] >= small["target_excess_kurtosis"]


def test_trimmed_mean_move_normal() -> None:
    moves = [0.02, 0.06, 0.03, 0.04, 0.20, 0.01]
    out = trimmed_mean_move(moves)
    assert out == pytest.approx((0.02 + 0.03 + 0.04 + 0.06) / 4)


def test_trimmed_mean_move_too_few_raises() -> None:
    with pytest.raises(ValueError):
        trimmed_mean_move([0.01, 0.02, 0.03, 0.04, 0.05])


def test_trimmed_mean_move_at_six_obs_returns_middle_four() -> None:
    out = trimmed_mean_move([0.01, 0.02, 0.03, 0.04, 0.06, 0.20])
    assert out == pytest.approx((0.02 + 0.03 + 0.04 + 0.06) / 4)


def test_recency_weighted_mean_normal() -> None:
    moves = [0.01, 0.02, 0.03, 0.04, 0.10, 0.10, 0.10, 0.10]
    out = recency_weighted_mean(moves, n_recent=4, recent_weight=2.0)
    expected = (0.01 + 0.02 + 0.03 + 0.04 + 2 * (0.10 + 0.10 + 0.10 + 0.10)) / (4 + 8)
    assert out == pytest.approx(expected)


def test_recency_weighted_mean_too_few_raises() -> None:
    with pytest.raises(ValueError):
        recency_weighted_mean([0.01, 0.02, 0.03], n_recent=4)


def test_split_by_timing_amc_bmo_mix(tmp_path: Path) -> None:
    db_path = tmp_path / "events.db"
    from data.option_data_store import create_store

    store = create_store(db_path)
    store.register_event(
        event_id="earnings:test:NVDA:2026-01-10",
        event_family="earnings",
        event_name="test",
        underlying_symbol="NVDA",
        event_date=dt.date(2026, 1, 10),
        source_system="test",
        event_time_label="ah",
    )
    store.register_event(
        event_id="earnings:test:NVDA:2026-04-10",
        event_family="earnings",
        event_name="test",
        underlying_symbol="NVDA",
        event_date=dt.date(2026, 4, 10),
        source_system="test",
        event_time_label="am",
    )

    dates = [
        pd.Timestamp("2026-01-10"),
        pd.Timestamp("2026-04-10"),
        pd.Timestamp("2026-07-10"),
    ]
    moves = [0.08, -0.05, 0.03]
    out = split_by_timing(
        "NVDA",
        dates,
        moves,
        db_path=db_path,
        allow_yfinance_fallback=False,
    )

    assert out["amc"] == [0.08]
    assert out["bmo"] == [0.05]
    assert out["unknown"] == [0.03]


def test_conditional_expected_prefers_recency_weighted_primary() -> None:
    moves = [0.02, 0.03, 0.01, 0.02, 0.06, 0.07, 0.06, 0.08]
    out = conditional_expected_move(moves, timing="combined")
    assert out.recency_weighted is not None
    assert out.primary_estimate == out.recency_weighted
    assert out.data_quality == "MEDIUM"


def test_conditional_expected_low_quality() -> None:
    moves = [0.02, 0.03, 0.01, 0.02]
    out = conditional_expected_move(moves, timing="combined")
    assert out.data_quality == "LOW"


def test_extract_earnings_moves_with_dates_aligns_lengths() -> None:
    data = pd.DataFrame(
        {
            "Date": [
                dt.date(2024, 1, 2),
                dt.date(2024, 1, 3),
                dt.date(2024, 1, 4),
                dt.date(2024, 1, 5),
                dt.date(2024, 1, 8),
            ],
            "Close": [100.0, 110.0, 105.0, 120.0, 118.0],
        }
    )
    earnings_dates = [pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-05")]

    aligned_dates, signed_moves = extract_earnings_moves_with_dates(
        data, earnings_dates
    )
    plain_moves = extract_earnings_moves(data, earnings_dates)

    assert len(aligned_dates) == len(signed_moves) == len(plain_moves)
    assert signed_moves == plain_moves
