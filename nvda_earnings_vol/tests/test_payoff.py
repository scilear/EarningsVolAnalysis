"""Tests for payoff time remaining logic."""

import datetime as dt

import pandas as pd

from nvda_earnings_vol.config import TIME_EPSILON
from nvda_earnings_vol.strategies import payoff


def test_time_remaining_uses_single_day_offset() -> None:
    event_date = dt.date(2026, 1, 5)
    expiry = dt.date(2026, 1, 7)
    business_days = pd.bdate_range(event_date, expiry).size
    expected = max((business_days - 1) / 252.0, TIME_EPSILON)

    assert payoff._time_remaining(event_date, expiry) == expected
