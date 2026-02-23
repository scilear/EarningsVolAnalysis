"""Monte Carlo simulation for earnings moves."""

from __future__ import annotations

import logging
import math

import numpy as np

from nvda_earnings_vol.config import MC_SIMULATIONS


LOGGER = logging.getLogger(__name__)


def simulate_moves(
    event_vol: float,
    simulations: int = MC_SIMULATIONS,
    seed: int | None = None,
) -> np.ndarray:
    """Simulate lognormal event moves with drift correction."""
    if event_vol <= 0:
        return np.zeros(simulations)
    sigma_1d = event_vol / math.sqrt(252.0)
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(simulations)
    moves = np.exp(-0.5 * sigma_1d**2 + sigma_1d * z) - 1.0
    _validate(moves, sigma_1d)
    return moves


def _validate(moves: np.ndarray, sigma_1d: float) -> None:
    mean = float(np.mean(moves))
    std = float(np.std(moves))
    mean_ok = abs(mean) <= 0.03 * max(abs(sigma_1d), 1e-9)
    std_ok = abs(std - sigma_1d) <= 0.03 * max(sigma_1d, 1e-9)
    if not mean_ok or not std_ok:
        LOGGER.warning(
            "Monte Carlo validation warning: mean=%.6f std=%.6f target=%.6f",
            mean,
            std,
            sigma_1d,
        )
