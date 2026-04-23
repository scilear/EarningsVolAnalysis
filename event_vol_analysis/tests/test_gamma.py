"""Tests for GEX calculations."""

import pandas as pd

from event_vol_analysis.analytics.gamma import (
    compute_charm_exposure,
    compute_vanna_exposure,
    gex_summary,
    identify_pin_strikes,
)


def test_gex_outputs() -> None:
    chain = pd.DataFrame(
        {
            "strike": [100.0, 100.0],
            "option_type": ["call", "put"],
            "impliedVolatility": [0.2, 0.2],
            "openInterest": [100, 100],
        }
    )
    output = gex_summary(chain, 100.0, 0.1)
    assert "net_gex" in output
    assert "abs_gex" in output
    assert "vanna_net" in output
    assert "charm_net" in output
    assert "gex_by_strike" in output
    assert "pin_strikes" in output


def test_identify_pin_strikes_detects_concentration() -> None:
    gex_by_strike = {
        95.0: 100.0,
        100.0: 2000.0,
        105.0: -150.0,
    }
    pins = identify_pin_strikes(gex_by_strike, threshold_pct=0.50)
    assert len(pins) == 1
    assert pins[0]["strike"] == 100.0


def test_vanna_and_charm_exposure_are_numeric() -> None:
    chain = pd.DataFrame(
        {
            "strike": [95.0, 100.0, 105.0, 95.0, 100.0, 105.0],
            "option_type": ["call", "call", "call", "put", "put", "put"],
            "impliedVolatility": [0.20, 0.21, 0.23, 0.20, 0.21, 0.23],
            "openInterest": [150, 300, 120, 180, 260, 140],
        }
    )
    vanna = compute_vanna_exposure(chain, spot=100.0, t=30 / 365.0)
    charm = compute_charm_exposure(chain, spot=100.0, t=30 / 365.0)
    assert isinstance(vanna, float)
    assert isinstance(charm, float)
