"""Tests for regime-structure alignment behavior."""

from event_vol_analysis.alignment import compute_alignment


def _population() -> dict:
    return {
        "median_abs_gamma": 2.0,
        "median_abs_vega": 1.0,
        "convexities": [0.5, 1.0, 1.5],
        "cvars": [-2.0, -1.0, -0.5],
    }


def _base_regime() -> dict:
    return {
        "vol_regime": "Fairly Priced",
        "composite_regime": "Mixed / Transitional Setup",
        "confidence": 1.0,
    }


def test_gamma_alignment_prefers_long_gamma_in_amplified_move_regime() -> None:
    long_gamma = compute_alignment(
        {"net_gamma": 2.0, "net_vega": 0.0, "convexity": 1.0, "cvar": -1.0},
        {**_base_regime(), "gamma_regime": "Amplified Move Regime"},
        _population(),
    )
    short_gamma = compute_alignment(
        {"net_gamma": -2.0, "net_vega": 0.0, "convexity": 1.0, "cvar": -1.0},
        {**_base_regime(), "gamma_regime": "Amplified Move Regime"},
        _population(),
    )

    assert long_gamma["alignment_breakdown"]["gamma_alignment"] == 1.0
    assert short_gamma["alignment_breakdown"]["gamma_alignment"] == 0.0


def test_gamma_alignment_prefers_short_gamma_in_pin_risk_regime() -> None:
    short_gamma = compute_alignment(
        {"net_gamma": -2.0, "net_vega": 0.0, "convexity": 1.0, "cvar": -1.0},
        {**_base_regime(), "gamma_regime": "Pin Risk Regime"},
        _population(),
    )
    long_gamma = compute_alignment(
        {"net_gamma": 2.0, "net_vega": 0.0, "convexity": 1.0, "cvar": -1.0},
        {**_base_regime(), "gamma_regime": "Pin Risk Regime"},
        _population(),
    )

    assert short_gamma["alignment_breakdown"]["gamma_alignment"] == 1.0
    assert long_gamma["alignment_breakdown"]["gamma_alignment"] == 0.0


def test_gamma_alignment_is_neutral_in_neutral_gamma_regime() -> None:
    result = compute_alignment(
        {"net_gamma": 2.0, "net_vega": 0.0, "convexity": 1.0, "cvar": -1.0},
        {**_base_regime(), "gamma_regime": "Neutral Gamma"},
        _population(),
    )

    assert result["alignment_breakdown"]["gamma_alignment"] == 0.5
