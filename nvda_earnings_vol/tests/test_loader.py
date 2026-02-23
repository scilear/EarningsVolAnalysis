"""Tests for loader helpers."""

import datetime as dt

from nvda_earnings_vol.data.loader import get_expiries_after


def test_get_expiries_after_filters() -> None:
    expiries = [
        dt.date(2026, 1, 1),
        dt.date(2026, 2, 1),
        dt.date(2026, 3, 1),
    ]
    result = get_expiries_after(expiries, dt.date(2026, 2, 1))
    assert result == [dt.date(2026, 2, 1), dt.date(2026, 3, 1)]
