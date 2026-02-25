"""
Regime-strategy structural alignment scoring.

Orthogonal to ranking. Fully deterministic.
Provides visual heatmap data for report rendering.
"""

from __future__ import annotations

from typing import List

import numpy as np


def _percentile_rank(value: float, population: List[float]) -> float:
    """Returns 0-1 rank of value within population."""
    if len(population) == 0:
        return 0.5
    return sum(1 for x in population if x <= value) / len(population)


def _scaled_sign(value: float, desired_positive: bool, scale: float) -> float:
    """
    Maps value onto [0,1] relative to scale.
    
    Args:
        value: The exposure value (gamma or vega)
        desired_positive: True if long exposure preferred
        scale: Median absolute exposure across strategies for normalization
    
    Returns:
        Score in [0, 1] where 1 = fully aligned, 0 = opposed, 0.5 = neutral
    """
    if scale == 0:
        return 0.5
    
    normalized = max(min(value / scale, 1.0), -1.0)
    
    if desired_positive:
        return (normalized + 1.0) / 2.0
    else:
        return (1.0 - normalized) / 2.0


def compute_alignment(strategy: dict, regime: dict, population_stats: dict) -> dict:
    """
    Compute how well a strategy's structural exposures match the detected regime.
    
    Parameters
    ----------
    strategy : dict
        Must contain: net_gamma, net_vega, convexity, cvar (negative number)
    regime : dict
        Must contain: gamma_bias, vol_regime, composite_regime, confidence
    population_stats : dict
        Must contain: median_abs_gamma, median_abs_vega, convexities (list),
                      cvars (list of negative numbers)
    
    Returns
    -------
    dict with alignment_score, alignment_weighted, alignment_breakdown,
    and alignment_heatmap for visualization.
    """
    
    # ─── Axis 1: Gamma ────────────────────────────────────────────────────
    gamma_bias = regime.get("gamma_bias", "neutral")
    desired_long_gamma = (gamma_bias == "long_gamma")
    desired_short_gamma = (gamma_bias == "short_gamma")
    
    if gamma_bias == "neutral":
        gamma_score = 0.5
    elif desired_long_gamma:
        gamma_score = _scaled_sign(
            strategy.get("net_gamma", 0.0),
            desired_positive=True,
            scale=population_stats.get("median_abs_gamma", 1.0)
        )
    else:  # desired_short_gamma
        gamma_score = _scaled_sign(
            strategy.get("net_gamma", 0.0),
            desired_positive=False,
            scale=population_stats.get("median_abs_gamma", 1.0)
        )
    
    # ─── Axis 2: Vega ─────────────────────────────────────────────────────
    vol_regime = regime.get("vol_regime", "Fairly Priced")
    
    if vol_regime == "Tail Underpriced":
        vega_score = _scaled_sign(
            strategy.get("net_vega", 0.0),
            desired_positive=True,
            scale=population_stats.get("median_abs_vega", 1.0)
        )
    elif vol_regime == "Tail Overpriced":
        vega_score = _scaled_sign(
            strategy.get("net_vega", 0.0),
            desired_positive=False,
            scale=population_stats.get("median_abs_vega", 1.0)
        )
    else:
        vega_score = 0.5
    
    # ─── Axis 3: Convexity ────────────────────────────────────────────────
    composite = regime.get("composite_regime", "Mixed / Transitional Setup")
    conv_rank = _percentile_rank(
        strategy.get("convexity", 0.0),
        population_stats.get("convexities", [])
    )
    
    if composite == "Convex Breakout Setup":
        convexity_score = conv_rank  # high convexity aligned
    elif composite == "Premium Harvest Setup":
        convexity_score = 1.0 - conv_rank  # low convexity aligned
    else:
        convexity_score = 0.5
    
    # ─── Axis 4: Tail Risk (CVaR) ─────────────────────────────────────────
    # CVaR is a negative number - more negative = heavier tail loss
    # percentile rank of cvar: 0 = best (least negative), 1 = worst
    cvar_rank = _percentile_rank(
        strategy.get("cvar", 0.0),
        population_stats.get("cvars", [])
    )
    
    # For tail underpriced: prefer strategies with less severe CVaR (low rank)
    if vol_regime == "Tail Underpriced":
        tail_score = 1.0 - cvar_rank
    else:
        tail_score = 0.5
    
    # ─── Composite ────────────────────────────────────────────────────────
    alignment_score = (gamma_score + vega_score + convexity_score + tail_score) / 4.0
    alignment_weighted = alignment_score * regime.get("confidence", 0.5)
    
    return {
        "alignment_score": round(alignment_score, 3),
        "alignment_weighted": round(alignment_weighted, 3),
        "alignment_breakdown": {
            "gamma_alignment": round(gamma_score, 3),
            "vega_alignment": round(vega_score, 3),
            "convexity_alignment": round(convexity_score, 3),
            "tail_alignment": round(tail_score, 3),
        },
        # Raw values for heatmap cells (same as breakdown)
        "alignment_heatmap": {
            "Gamma": round(gamma_score, 3),
            "Vega": round(vega_score, 3),
            "Convexity": round(convexity_score, 3),
            "Tail Risk": round(tail_score, 3),
        }
    }


def compute_all_alignments(strategies: list, regime: dict) -> None:
    """
    Mutates each strategy dict in-place.
    Computes population stats first, then scores per strategy.
    
    Parameters
    ----------
    strategies : list of dict
        Each strategy must have: net_gamma, net_vega, convexity, cvar
    regime : dict
        From classify_regime(), must have gamma_bias, vol_regime, etc.
    """
    # Extract population statistics
    gammas = [abs(s.get("net_gamma", 0.0)) for s in strategies]
    vegas = [abs(s.get("net_vega", 0.0)) for s in strategies]
    convexities = [s.get("convexity", 0.0) for s in strategies]
    cvars = [s.get("cvar", 0.0) for s in strategies]
    
    population_stats = {
        "median_abs_gamma": float(np.median(gammas)) if gammas else 1.0,
        "median_abs_vega": float(np.median(vegas)) if vegas else 1.0,
        "convexities": convexities,
        "cvars": cvars,
    }
    
    # Compute alignment for each strategy and mutate in-place
    for s in strategies:
        s["alignment"] = compute_alignment(s, regime, population_stats)
