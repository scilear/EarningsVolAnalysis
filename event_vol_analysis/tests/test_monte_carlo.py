"""Tests for Monte Carlo simulation."""

import numpy as np
import pytest

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
        model="lognormal",
    )
    fat_tailed = simulate_moves(
        0.5,
        simulations=50_000,
        seed=123,
        model="fat_tailed",
        target_excess_kurtosis=4.0,
        historical_sample_size=16,
    )

    normal_tail = float(np.mean(np.abs(normal_like) > 0.06))
    fat_tail = float(np.mean(np.abs(fat_tailed) > 0.06))
    assert fat_tail > normal_tail


def test_simulate_moves_rejects_unknown_model() -> None:
    with pytest.raises(ValueError, match="Unsupported move model"):
        simulate_moves(0.5, simulations=128, model="unknown_model")


def test_fat_tailed_model_seed_is_reproducible() -> None:
    moves_a = simulate_moves(
        0.5,
        simulations=5000,
        seed=77,
        model="fat_tailed",
        target_excess_kurtosis=4.0,
        historical_sample_size=16,
    )
    moves_b = simulate_moves(
        0.5,
        simulations=5000,
        seed=77,
        model="fat_tailed",
        target_excess_kurtosis=4.0,
        historical_sample_size=16,
    )
    assert np.array_equal(moves_a, moves_b)


def test_fat_tailed_model_with_insufficient_history_falls_back_to_lognormal() -> None:
    lognormal_moves = simulate_moves(
        0.5,
        simulations=5000,
        seed=99,
        model="lognormal",
    )
    fat_tail_moves = simulate_moves(
        0.5,
        simulations=5000,
        seed=99,
        model="fat_tailed",
        target_excess_kurtosis=4.0,
        historical_sample_size=3,
    )
    assert np.array_equal(lognormal_moves, fat_tail_moves)
