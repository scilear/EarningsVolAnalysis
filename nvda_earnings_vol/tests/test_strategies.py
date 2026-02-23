"""Tests for strategy construction."""

import pandas as pd

from nvda_earnings_vol.strategies.structures import build_strategies


def _chain(expiry: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "strike": [95.0, 100.0, 105.0],
            "option_type": ["call", "call", "call"],
            "expiry": [pd.Timestamp(expiry)] * 3,
        }
    )


def test_build_strategies_count() -> None:
    front = _chain("2030-01-01")
    back = _chain("2030-02-01")
    strategies = build_strategies(front, back, 100.0)
    assert len(strategies) >= 8
