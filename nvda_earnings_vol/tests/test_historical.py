"""Tests for historical move stats."""

import pandas as pd

from nvda_earnings_vol.analytics.historical import historical_p75


def test_historical_p75() -> None:
    data = pd.DataFrame(
        {"Close": [100.0, 101.0, 99.0, 100.5, 98.0]}
    )
    p75 = historical_p75(data)
    assert p75 > 0
