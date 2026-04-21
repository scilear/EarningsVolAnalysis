"""Tests for historical move stats."""

import datetime as dt

import pandas as pd

from event_vol_analysis.analytics.historical import (
    calibrate_fat_tail_inputs,
    compute_distribution_shape,
    earnings_move_p75,
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
