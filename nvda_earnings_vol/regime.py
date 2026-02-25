"""
Volatility regime classification engine.

Classifies the current market environment into structured regimes:
- Vol Pricing Regime
- Event Variance Regime
- Term Structure Regime
- Dealer Gamma Regime
- Composite Event Regime
"""

from __future__ import annotations

import numpy as np
from typing import Dict, Any


def classify_regime(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify the current market regime into structured categories.
    
    Args:
        snapshot: Dictionary containing market data:
            - implied_move: float (implied move as decimal)
            - historical_p75: float (historical P75 move as decimal)
            - historical_p90: float (historical P90 move as decimal, optional)
            - event_variance_ratio: float (event variance / total front variance)
            - front_iv: float (front expiry ATM IV as decimal)
            - back_iv: float (back1 expiry ATM IV as decimal)
            - back2_iv: float (back2 expiry ATM IV as decimal, optional)
            - gex_net: float (net dealer gamma exposure in $)
            - gex_abs: float (absolute dealer gamma exposure in $)
            - spot: float (current spot price)
            - mean_abs_move: float (mean absolute historical move as decimal)
            - median_abs_move: float (median absolute historical move as decimal)
            - skewness: float (skewness of signed moves)
            - kurtosis: float (kurtosis of signed moves)
    
    Returns:
        Dictionary with regime classifications and confidence scores
    """
    
    # Vol Pricing Regime
    ratio_p75 = snapshot["implied_move"] / snapshot["historical_p75"]
    if ratio_p75 < 0.85:
        vol_label = "Tail Underpriced"
    elif ratio_p75 > 1.10:
        vol_label = "Tail Overpriced"
    else:
        vol_label = "Fairly Priced"
    
    # Event Variance Regime
    ev_ratio = snapshot["event_variance_ratio"]
    if ev_ratio > 0.70:
        event_label = "Pure Binary Event"
    elif ev_ratio > 0.50:
        event_label = "Event-Dominant"
    else:
        event_label = "Distributed Volatility"
    
    # Term Structure Regime
    spread = snapshot["front_iv"] - snapshot["back_iv"]
    if spread > 0.20:
        term_label = "Extreme Front Premium"
    elif spread > 0.10:
        term_label = "Elevated Front Premium"
    elif spread < -0.05:
        term_label = "Inverted Structure"
    else:
        term_label = "Normal Structure"
    
    # Dealer Gamma Regime
    gex_net = snapshot["gex_net"]
    gex_abs = snapshot["gex_abs"]
    gex_ratio = abs(gex_net) / gex_abs if gex_abs > 0 else 0
    
    if gex_net < 0 and gex_ratio > 0.7:
        gamma_label = "Amplified Move Regime"
    elif gex_net > 0 and gex_ratio > 0.7:
        gamma_label = "Pin Risk Regime"
    else:
        gamma_label = "Neutral Gamma"
    
    # Composite Event Regime
    if (
        vol_label == "Tail Underpriced"
        and gamma_label.startswith("Amplified")
        and ev_ratio > 0.6
    ):
        composite = "Convex Breakout Setup"
    elif (
        vol_label == "Tail Overpriced"
        and gamma_label.startswith("Pin")
    ):
        composite = "Premium Harvest Setup"
    else:
        composite = "Mixed / Transitional Setup"
    
    # Confidence Scores
    vol_conf = min(abs(ratio_p75 - 1.0) / 0.20, 1.0)
    gamma_conf = min(abs(gex_net) / gex_abs, 1.0) if gex_abs > 0 else 0
    event_conf = min(ev_ratio / 0.8, 1.0)
    regime_confidence = (
        0.4 * vol_conf +
        0.3 * gamma_conf +
        0.3 * event_conf
    )
    
    return {
        "vol_regime": vol_label,
        "event_regime": event_label,
        "term_structure_regime": term_label,
        "gamma_regime": gamma_label,
        "composite_regime": composite,
        "vol_ratio": ratio_p75,
        "gex_ratio": gex_ratio,
        "vol_confidence": vol_conf,
        "gamma_confidence": gamma_conf,
        "event_confidence": event_conf,
        "confidence": regime_confidence,
    }


def compute_alignment_score(strategy: Dict[str, Any], regime: Dict[str, Any], population: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute how well a strategy's structural exposures match the detected regime.
    
    Args:
        strategy: Dictionary containing strategy metrics:
            - net_gamma: float
            - net_vega: float
            - convexity: float
            - cvar_95: float
            - undefined_risk: bool
        regime: Dictionary from classify_regime()
        population: Population statistics:
            - median_convexity: float
            - median_cvar: float
            - median_abs_gamma: float
            - median_abs_vega: float
            - convexities: list of floats
            - cvars: list of floats
    
    Returns:
        Dictionary with alignment scores and breakdown
    """
    
    def scaled_sign_alignment(value: float, desired_positive: bool, scale: float) -> float:
        """Scale signed exposure to 0-1 alignment."""
        if scale == 0:
            return 0.5
        
        normalized = value / scale
        normalized = max(min(normalized, 1), -1)
        
        if desired_positive:
            return (normalized + 1) / 2
        else:
            return (1 - normalized) / 2
    
    def percentile_rank(value: float, population: list) -> float:
        """Compute percentile rank of value in population."""
        if not population:
            return 0.5
        return sum(1 for x in population if x < value) / len(population)
    
    # Gamma Alignment
    gamma_score = scaled_sign_alignment(
        strategy["net_gamma"],
        desired_positive=(regime["gamma_regime"] == "Amplified Move Regime"),
        scale=population["median_abs_gamma"]
    )
    
    # Vega Alignment
    vega_score = scaled_sign_alignment(
        strategy["net_vega"],
        desired_positive=(regime["vol_regime"] == "Tail Underpriced"),
        scale=population["median_abs_vega"]
    )
    
    # Convexity Alignment
    convexity = strategy["convexity"]
    median_conv = population["median_convexity"]
    comp = regime["composite_regime"]
    
    if comp == "Convex Breakout Setup":
        conv_score = 1.0 if convexity >= median_conv else 0.0
    elif comp == "Premium Harvest Setup":
        conv_score = 1.0 if convexity < median_conv else 0.0
    else:
        conv_score = 0.5
    
    # Tail Risk Alignment
    cvar = strategy["cvar_95"]
    median_cvar = population["median_cvar"]
    vol_regime = regime["vol_regime"]
    
    if vol_regime == "Tail Underpriced":
        tail_score = 1.0 if cvar <= median_cvar else 0.0
    elif vol_regime == "Tail Overpriced":
        tail_score = 0.5
    else:
        tail_score = 0.5
    
    # Weighted Alignment
    alignment_score = (gamma_score + vega_score + conv_score + tail_score) / 4.0
    weighted_alignment = alignment_score * regime["confidence"]
    
    return {
        "alignment_score": alignment_score,
        "alignment_weighted": weighted_alignment,
        "alignment_breakdown": {
            "gamma_alignment": gamma_score,
            "vega_alignment": vega_score,
            "convexity_alignment": conv_score,
            "tail_alignment": tail_score,
        },
        "alignment_heatmap": {
            "Gamma": gamma_score,
            "Vega": vega_score,
            "Convexity": conv_score,
            "Tail": tail_score,
        }
    }