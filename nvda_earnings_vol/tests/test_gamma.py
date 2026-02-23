"""Tests for GEX calculations."""

import pandas as pd

from nvda_earnings_vol.analytics.gamma import gex_summary


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
