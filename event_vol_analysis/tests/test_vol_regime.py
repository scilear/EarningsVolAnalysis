"""Tests for IVR/IVP volatility regime classification."""

from __future__ import annotations

import pytest

from event_vol_analysis.analytics.vol_regime import (
    classify_from_iv_history,
    classify_vol_regime,
    compute_ivr,
    compute_ivp,
    compute_term_structure_slope,
    rr25_to_skew_25d,
)
from event_vol_analysis.regime import classify_regime


def test_compute_ivr_normal() -> None:
    ivr, degenerate = compute_ivr(current_iv=0.40, iv_history=[0.20, 0.30, 0.50, 0.60])
    assert degenerate is False
    assert ivr == pytest.approx(50.0)


def test_compute_ivp_normal() -> None:
    ivp = compute_ivp(current_iv=0.40, iv_history=[0.20, 0.30, 0.50, 0.60])
    assert ivp == 50.0


def test_bucket_cheap_high_confidence() -> None:
    out = classify_vol_regime(ivr=20.0, ivp=25.0)
    assert out.label == "CHEAP"
    assert out.confidence == "HIGH"


def test_bucket_expensive_high_confidence() -> None:
    out = classify_vol_regime(ivr=70.0, ivp=75.0)
    assert out.label == "EXPENSIVE"
    assert out.confidence == "HIGH"


def test_bucket_ambiguous_low_confidence() -> None:
    out = classify_vol_regime(ivr=20.0, ivp=75.0)
    assert out.label == "AMBIGUOUS"
    assert out.confidence == "LOW"


def test_bucket_one_step_disagreement_is_neutral_low() -> None:
    out = classify_vol_regime(ivr=28.0, ivp=35.0)
    assert out.label == "NEUTRAL"
    assert out.confidence == "LOW"


def test_degenerate_flat_iv_history_forces_ivr_50_and_low() -> None:
    out = classify_from_iv_history(
        current_iv=0.40,
        iv_history=[0.40, 0.40, 0.40, 0.40, 0.40, 0.40],
        min_history=1,
    )
    assert out.ivr == 50.0
    assert out.confidence == "LOW"


def test_short_history_forces_neutral_low() -> None:
    out = classify_from_iv_history(
        current_iv=0.40,
        iv_history=[0.30, 0.35, 0.45, 0.50],
        min_history=60,
    )
    assert out.label == "NEUTRAL"
    assert out.confidence == "LOW"


def test_term_structure_slope_contango() -> None:
    slope = compute_term_structure_slope(front_iv=0.40, back_iv=0.50)
    assert slope is not None
    assert slope < 0.0


def test_term_structure_slope_backwardation() -> None:
    slope = compute_term_structure_slope(front_iv=0.60, back_iv=0.50)
    assert slope is not None
    assert slope > 0.0


def test_rr25_to_skew_25d_convention() -> None:
    assert rr25_to_skew_25d(-0.10) == 0.10


def test_classify_regime_surfaces_dual_fields() -> None:
    snapshot = {
        "implied_move": 0.08,
        "historical_p75": 0.07,
        "event_variance_ratio": 0.65,
        "front_iv": 0.60,
        "back_iv": 0.45,
        "gex_net": -1.0,
        "gex_abs": 1.0,
        "vanna_net": 125000.0,
        "charm_net": -840.0,
        "pin_strikes": [
            {"strike": 100.0, "gex": 1.5e6, "abs_pct": 0.32},
        ],
        "gex_by_strike": [(95.0, -2.0e5), (100.0, 1.5e6), (105.0, 1.0e5)],
        "rr25_raw": -0.05,
        "atm_iv_history": [
            0.25,
            0.28,
            0.30,
            0.31,
            0.33,
            0.35,
            0.37,
            0.38,
            0.39,
            0.40,
            0.42,
            0.44,
            0.46,
            0.48,
            0.50,
            0.52,
            0.53,
            0.54,
            0.55,
            0.56,
            0.57,
            0.58,
            0.59,
            0.60,
            0.61,
            0.62,
            0.63,
            0.64,
            0.65,
            0.66,
            0.67,
            0.68,
            0.69,
            0.70,
            0.71,
            0.72,
            0.73,
            0.74,
            0.75,
            0.76,
            0.77,
            0.78,
            0.79,
            0.80,
            0.81,
            0.82,
            0.83,
            0.84,
            0.85,
            0.86,
            0.87,
            0.88,
            0.89,
            0.90,
            0.91,
            0.92,
            0.93,
            0.94,
            0.95,
            0.96,
            0.97,
            0.98,
            0.99,
        ],
    }

    regime = classify_regime(snapshot)
    assert "ivr" in regime
    assert "ivp" in regime
    assert "bucket_ivr" in regime
    assert "bucket_ivp" in regime
    assert "term_structure_slope" in regime
    assert "skew_25d" in regime
    assert regime["skew_25d"] == 0.05
    assert regime["vanna_net"] == pytest.approx(125000.0)
    assert regime["charm_net"] == pytest.approx(-840.0)
    assert len(regime["pin_strikes"]) == 1
    assert regime["gex_by_strike_top"][0][0] == pytest.approx(100.0)
    assert regime["macro_vehicle_class"] in {
        "macro_etf",
        "vol_index_proxy",
        "other",
        "unknown",
    }
