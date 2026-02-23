"""Tests for historical move stats."""

import datetime as dt

import pandas as pd

from nvda_earnings_vol.analytics.historical import earnings_move_p75


def test_earnings_move_p75() -> None:
    data = pd.DataFrame(
        {
            "Date": [
                dt.date(2024, 1, 2),
                dt.date(2024, 1, 3),
                dt.date(2024, 1, 4),
                dt.date(2024, 1, 5),
            ],
            "Close": [100.0, 110.0, 105.0, 120.0],
        }
    )
    earnings_dates = [pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-05")]
    p75 = earnings_move_p75(data, earnings_dates)
    assert 0.1 < p75 < 0.15
