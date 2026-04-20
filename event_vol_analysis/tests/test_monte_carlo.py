"""Tests for Monte Carlo simulation."""

import numpy as np

from event_vol_analysis.simulation.monte_carlo import simulate_moves


def test_simulate_moves_length() -> None:
    moves = simulate_moves(0.5, simulations=1000)
    assert len(moves) == 1000


def test_simulate_moves_returns_zero_for_non_positive_vol() -> None:
    moves = simulate_moves(0.0, simulations=128)
    assert np.allclose(moves, 0.0)


def test_fat_tails_increase_tail_probability() -> None:
    normal_like = simulate_moves(
        0.5,
        simulations=50_000,
        seed=123,
        target_excess_kurtosis=0.0,
    )
    fat_tailed = simulate_moves(
        0.5,
        simulations=50_000,
        seed=123,
        target_excess_kurtosis=4.0,
    )

    normal_tail = float(np.mean(np.abs(normal_like) > 0.06))
    fat_tail = float(np.mean(np.abs(fat_tailed) > 0.06))
    assert fat_tail > normal_tail
