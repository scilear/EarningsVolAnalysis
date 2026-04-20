"""Monte Carlo simulation for earnings moves."""

from __future__ import annotations

import logging
import math

import numpy as np
from scipy import stats

from event_vol_analysis.config import (
    FAT_TAIL_MAX_DF,
    FAT_TAIL_MAX_EXCESS_KURTOSIS,
    FAT_TAIL_MIN_DF,
    FAT_TAILS_ENABLED,
    MC_SIMULATIONS,
)


LOGGER = logging.getLogger(__name__)


def simulate_moves(
    event_vol: float,
    simulations: int = MC_SIMULATIONS,
    seed: int | None = None,
    target_excess_kurtosis: float | None = None,
) -> np.ndarray:
    """Simulate event moves with optional fat-tailed innovations."""
    if event_vol <= 0:
        return np.zeros(simulations)
    sigma_1d = event_vol / math.sqrt(252.0)
    rng = np.random.default_rng(seed)
    z = _sample_innovations(
        rng,
        simulations,
        target_excess_kurtosis=target_excess_kurtosis,
    )
    moves = np.exp(-0.5 * sigma_1d**2 + sigma_1d * z) - 1.0
    _validate(moves, sigma_1d)
    return moves


def _sample_innovations(
    rng: np.random.Generator,
    simulations: int,
    *,
    target_excess_kurtosis: float | None,
) -> np.ndarray:
    """Sample standardized innovations from normal or Student-t."""
    if not FAT_TAILS_ENABLED or target_excess_kurtosis is None:
        return rng.standard_normal(simulations)

    if target_excess_kurtosis <= 0:
        return rng.standard_normal(simulations)

    clipped_kurtosis = min(
        float(target_excess_kurtosis),
        FAT_TAIL_MAX_EXCESS_KURTOSIS,
    )
    nu = 4.0 + (6.0 / clipped_kurtosis)
    nu = min(max(nu, FAT_TAIL_MIN_DF), FAT_TAIL_MAX_DF)

    t_samples = stats.t.rvs(df=nu, size=simulations, random_state=rng)
    scale = math.sqrt(nu / (nu - 2.0))
    return t_samples / scale


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
