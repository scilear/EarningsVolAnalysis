"""Volatility regime classification engine.

Classifies the current market environment into structured regimes:
- Vol Pricing Regime (IVR/IVP dual classifier)
- Event Variance Regime
- Term Structure Regime
- Dealer Gamma Regime
- Composite Event Regime
"""

from __future__ import annotations

import numpy as np
from typing import Dict, Any

from event_vol_analysis.analytics.vol_regime import (
    classify_from_iv_history,
    compute_term_structure_slope,
    load_atm_iv_history_from_store,
    rr25_to_skew_25d,
)


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

    implied_move = float(snapshot.get("implied_move", 0.0))
    historical_p75 = float(snapshot.get("historical_p75", 0.0))
    ratio_p75 = implied_move / historical_p75 if historical_p75 > 0 else 0.0

    front_iv = float(snapshot.get("front_iv", 0.0) or 0.0)
    back_iv = float(snapshot.get("back_iv", 0.0) or 0.0)
    term_structure_slope = compute_term_structure_slope(front_iv, back_iv)
    rr25_raw = _as_optional_float(snapshot.get("rr25_raw", snapshot.get("rr25")))
    skew_25d = rr25_to_skew_25d(rr25_raw)

    iv_history = snapshot.get("atm_iv_history")
    if iv_history is None:
        ticker = snapshot.get("ticker")
        iv_history = load_atm_iv_history_from_store(str(ticker)) if ticker else []
    if iv_history is None:
        iv_history = []

    vol = classify_from_iv_history(
        current_iv=front_iv,
        iv_history=iv_history,
        term_structure_slope=term_structure_slope,
        skew_25d=skew_25d,
    )
    vol_label = vol.label
    legacy_vol_label = _legacy_vol_label(vol_label)

    # Event Variance Regime
    ev_ratio = snapshot["event_variance_ratio"]
    if ev_ratio > 0.70:
        event_label = "Pure Binary Event"
    elif ev_ratio > 0.50:
        event_label = "Event-Dominant"
    else:
        event_label = "Distributed Volatility"

    # Term Structure Regime
    spread = front_iv - back_iv
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
    if vol_label == "CHEAP" and gamma_label.startswith("Amplified") and ev_ratio > 0.6:
        composite = "Convex Breakout Setup"
    elif vol_label == "EXPENSIVE" and gamma_label.startswith("Pin"):
        composite = "Premium Harvest Setup"
    else:
        composite = "Mixed / Transitional Setup"

    # Confidence Scores
    vol_conf = 1.0 if vol.confidence == "HIGH" else 0.35
    gamma_conf = min(abs(gex_net) / gex_abs, 1.0) if gex_abs > 0 else 0
    event_conf = min(ev_ratio / 0.8, 1.0)
    regime_confidence = 0.4 * vol_conf + 0.3 * gamma_conf + 0.3 * event_conf

    return {
        "vol_regime": vol_label,
        "vol_label": vol_label,
        "vol_regime_legacy": legacy_vol_label,
        "vol_confidence_label": vol.confidence,
        "vol_ambiguous": vol_label == "AMBIGUOUS",
        "ivr": vol.ivr,
        "ivp": vol.ivp,
        "bucket_ivr": vol.bucket_ivr,
        "bucket_ivp": vol.bucket_ivp,
        "term_structure_slope": vol.term_structure_slope,
        "skew_25d": vol.skew_25d,
        "iv_history_points": vol.history_points,
        "iv_history_window_days": vol.history_window_days,
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


def _legacy_vol_label(vol_label: str) -> str:
    """Map playbook IVR/IVP labels to legacy alignment labels."""

    if vol_label == "CHEAP":
        return "Tail Underpriced"
    if vol_label == "EXPENSIVE":
        return "Tail Overpriced"
    return "Fairly Priced"


def _as_optional_float(value: Any) -> float | None:
    """Convert optional numeric-like values to float."""

    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.upper() == "N/A":
            return None
        return float(stripped)
    return float(value)


# NOTE:
# compute_alignment_score is intentionally commented out for now.
# The active and tested alignment implementation is
# event_vol_analysis.alignment.compute_alignment.
#
# Keeping this legacy scorer active risks semantic drift because it diverges
# from the canonical alignment logic used by the main pipeline.
