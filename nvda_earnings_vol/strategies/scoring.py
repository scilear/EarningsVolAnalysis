"""Strategy scoring and risk metrics."""

from __future__ import annotations

import math

import numpy as np

from nvda_earnings_vol.config import CONVEXITY_CAP, CONVEXITY_EPS, SCORING_WEIGHTS
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
    return sorted(results, key=lambda row: row["score"], reverse=True)


def compute_metrics(
    strategy: Strategy,
    pnls: np.ndarray,
    implied_move: float,
    historical_p75: float,
    spot: float,
    robustness_override: float | None = None,
) -> dict:
    """Compute scoring metrics for a strategy."""
    ev = float(np.mean(pnls))
    cvar = float(np.mean(np.sort(pnls)[: max(int(0.1 * len(pnls)), 1)]))
    convexity = _convexity(pnls)
    robustness = (
        float(robustness_override)
        if robustness_override is not None
        else 1.0 / (float(np.std(pnls)) + 1e-9)
    )

    max_loss = float(np.min(pnls))
    expected_move_dollar = max(implied_move, historical_p75) * spot * 100
    capital_ratio = abs(max_loss) / max(expected_move_dollar, 1e-9)

    risk_classification = (
        "undefined_risk" if _is_undefined_risk(strategy) else "defined_risk"
    )

    return {
        "strategy": strategy.name,
        "strategy_obj": strategy,
        "ev": ev,
        "cvar": cvar,
        "convexity": convexity,
        "robustness": robustness,
        "max_loss": max_loss,
        "capital_ratio": capital_ratio,
        "risk_classification": risk_classification,
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
    short_calls = [
        leg for leg in strategy.legs if leg.option_type == "call" and leg.side == "sell"
    ]
    short_puts = [
        leg for leg in strategy.legs if leg.option_type == "put" and leg.side == "sell"
    ]
    long_calls = [
        leg for leg in strategy.legs if leg.option_type == "call" and leg.side == "buy"
    ]
    long_puts = [
        leg for leg in strategy.legs if leg.option_type == "put" and leg.side == "buy"
    ]

    for short in short_calls:
        cover_qty = sum(
            long.qty
            for long in long_calls
            if long.expiry == short.expiry and long.strike >= short.strike
        )
        if cover_qty < short.qty:
            return True

    for short in short_puts:
        cover_qty = sum(
            long.qty
            for long in long_puts
            if long.expiry == short.expiry and long.strike <= short.strike
        )
        if cover_qty < short.qty:
            return True

    return False
