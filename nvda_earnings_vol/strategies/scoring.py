"""Strategy scoring and risk metrics."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from nvda_earnings_vol.config import (
    CONVEXITY_CAP,
    CONVEXITY_EPS,
    SCORING_WEIGHTS,
)
from nvda_earnings_vol.strategies.structures import Strategy


def score_strategies(results: list[dict]) -> list[dict]:
    """Score strategies based on EV, convexity, CVaR, and robustness."""
    metrics = {
        "ev": [item["ev"] for item in results],
        "convexity": [item["convexity"] for item in results],
        "cvar": [item["cvar"] for item in results],
        "robustness": [item["robustness"] for item in results],
    }
    norm = {key: _normalize(values) for key, values in metrics.items()}
    
    # Compute normalization stats for score decomposition
    normalization_stats = {
        key: (min(values), max(values)) for key, values in metrics.items()
    }

    for idx, item in enumerate(results):
        score = 0.0
        for key, weight in SCORING_WEIGHTS.items():
            score += weight * norm[key][idx]
        if item["risk_classification"] == "undefined_risk":
            score *= 0.9
            item["risk_penalty_applied"] = True
        else:
            item["risk_penalty_applied"] = False
        item["score"] = score
        
        # Add rank and score decomposition
        item["rank"] = idx + 1
        item["score_components"] = decompose_score(item, normalization_stats)
    
    return sorted(results, key=lambda row: row["score"], reverse=True)


def decompose_score(strategy: dict, normalization_stats: dict) -> dict:
    """
    Returns per-component contribution to composite score.
    
    Parameters
    ----------
    strategy : dict
        Strategy with ev, convexity, cvar, robustness fields
    normalization_stats : dict
        {field: (min, max)} for each scored field
    
    Returns
    -------
    dict with normalized components and weighted contributions
    """
    components = {}
    weights = SCORING_WEIGHTS

    for field, weight in weights.items():
        raw = strategy[field]
        lo, hi = normalization_stats[field]
        normalized = (raw - lo) / (hi - lo) if hi != lo else 0.5
        components[f"{field}_norm"] = round(normalized, 4)
        components[f"{field}_contribution"] = round(normalized * weight, 4)

    components["total"] = round(sum(
        v for k, v in components.items() if k.endswith("_contribution")
    ), 4)

    return components


def compute_metrics(
    strategy: Strategy,
    pnls: np.ndarray,
    implied_move: float,
    historical_p75: float,
    spot: float,
    robustness_override: float | None = None,
    scenario_evs: dict[str, float] | None = None,
    net_greeks: dict[str, float] | None = None,
    breakevens: dict[str, float | None] | None = None,
    capital: dict[str, float] | None = None,
) -> dict:
    """Compute scoring metrics for a strategy with enhanced fields."""
    ev = float(np.mean(pnls))
    cvar = float(
        np.mean(np.sort(pnls)[: max(int(0.05 * len(pnls)), 1)])
    )
    convexity = _convexity(pnls)
    if robustness_override is None:
        raise ValueError(
            "robustness_override is required. Standalone P&L std is not a "
            "valid robustness metric."
        )
    robustness = float(robustness_override)

    max_loss = float(np.min(pnls))
    expected_move_dollar = max(implied_move, historical_p75) * spot * 100
    capital_ratio = abs(max_loss) / max(expected_move_dollar, 1e-9)

    risk_classification = (
        "undefined_risk" if _is_undefined_risk(strategy) else "defined_risk"
    )
    
    # Build legs dict for reporting
    legs = [leg.to_dict() for leg in strategy.legs]

    return {
        "strategy": strategy.name,
        "strategy_obj": strategy,
        "name": strategy.name.upper(),
        "legs": legs,
        "ev": ev,
        "cvar": cvar,
        "convexity": convexity,
        "robustness": robustness,
        "max_loss": max_loss,
        "max_gain": capital.get("max_gain", 0.0) if capital else 0.0,
        "capital_ratio": capital_ratio,
        "capital_required": capital.get("capital_required", abs(max_loss)) if capital else abs(max_loss),
        "capital_efficiency": capital.get("capital_efficiency", capital_ratio) if capital else capital_ratio,
        "risk_classification": risk_classification,
        "undefined_risk": risk_classification == "undefined_risk",
        "scenario_evs": scenario_evs or {},
        "net_delta": net_greeks.get("delta", 0.0) if net_greeks else 0.0,
        "net_gamma": net_greeks.get("gamma", 0.0) if net_greeks else 0.0,
        "net_vega": net_greeks.get("vega", 0.0) if net_greeks else 0.0,
        "net_theta": net_greeks.get("theta", 0.0) if net_greeks else None,
        "lower_breakeven": breakevens.get("lower") if breakevens else None,
        "upper_breakeven": breakevens.get("upper") if breakevens else None,
        "lower_be_pct": ((breakevens.get("lower") - spot) / spot * 100) if breakevens and breakevens.get("lower") else None,
        "upper_be_pct": ((breakevens.get("upper") - spot) / spot * 100) if breakevens and breakevens.get("upper") else None,
    }


def _convexity(pnls: np.ndarray) -> float:
    tail = max(int(0.1 * len(pnls)), 1)
    top = float(np.mean(np.sort(pnls)[-tail:]))
    bottom = float(np.mean(np.sort(pnls)[:tail]))
    if abs(bottom) < CONVEXITY_EPS:
        return CONVEXITY_CAP
    value = top / abs(bottom)
    return min(value, CONVEXITY_CAP)


def _normalize(values: list[float]) -> list[float]:
    min_val = min(values)
    max_val = max(values)
    if math.isclose(min_val, max_val):
        return [0.5 for _ in values]
    return [(val - min_val) / (max_val - min_val) for val in values]


def _is_undefined_risk(strategy: Strategy) -> bool:
    """Return True if any short leg is uncovered.

    Coverage rules:
    - Short call is covered by a long call with strike >= short strike.
    - Short put is covered by a long put with strike <= short strike.
    - Time spreads (calendars/diagonals) are defined risk.
    """
    short_calls = [
        leg
        for leg in strategy.legs
        if leg.option_type == "call" and leg.side == "sell"
    ]
    short_puts = [
        leg
        for leg in strategy.legs
        if leg.option_type == "put" and leg.side == "sell"
    ]
    long_calls = [
        leg
        for leg in strategy.legs
        if leg.option_type == "call" and leg.side == "buy"
    ]
    long_puts = [
        leg
        for leg in strategy.legs
        if leg.option_type == "put" and leg.side == "buy"
    ]

    for short in short_calls:
        cover_qty = sum(
            long.qty for long in long_calls if long.strike >= short.strike
        )
        if cover_qty < short.qty:
            return True

    for short in short_puts:
        cover_qty = sum(
            long.qty for long in long_puts if long.strike <= short.strike
        )
        if cover_qty < short.qty:
            return True

    return False
