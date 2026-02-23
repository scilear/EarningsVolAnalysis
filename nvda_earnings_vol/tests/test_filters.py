"""Tests for filter utilities."""

import pandas as pd

from nvda_earnings_vol.data.filters import filter_by_liquidity


def test_filter_by_liquidity_empty() -> None:
    chain = pd.DataFrame(
        {
            "openInterest": [0, 0],
            "spread": [1.0, 1.0],
            "mid": [10.0, 10.0],
        }
    )
    filtered = filter_by_liquidity(chain, min_oi=10, max_spread_pct=0.1)
    assert filtered.empty
