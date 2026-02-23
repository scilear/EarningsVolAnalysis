"""Tests for skew metrics."""

import pandas as pd

from nvda_earnings_vol.analytics.skew import skew_metrics


def test_skew_handles_missing_25d() -> None:
    chain = pd.DataFrame(
        {
            "strike": [100.0, 100.0],
            "option_type": ["call", "put"],
            "impliedVolatility": [0.2, 0.2],
        }
    )
    output = skew_metrics(chain, 100.0, 0.1)
    assert "rr25" in output
