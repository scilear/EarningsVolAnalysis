"""Tests for Monte Carlo simulation."""

from nvda_earnings_vol.simulation.monte_carlo import simulate_moves


def test_simulate_moves_length() -> None:
    moves = simulate_moves(0.5, simulations=1000)
    assert len(moves) == 1000
