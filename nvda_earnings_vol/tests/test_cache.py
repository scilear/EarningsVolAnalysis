"""Tests for options chain caching and market-closed checks."""

import datetime as dt
import tempfile
from pathlib import Path

import pandas as pd

from nvda_earnings_vol.data.loader import get_options_chain, _raise_if_market_closed


def test_cache_load_parses_expiry() -> None:
    expiry = dt.date(2030, 1, 17)
    stamp = dt.date.today().strftime("%Y%m%d")
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_dir = Path(temp_dir)
        cache_path = cache_dir / f"NVDA_{expiry.strftime('%Y%m%d')}_{stamp}.csv"
        chain = pd.DataFrame(
            {
                "strike": [100.0],
                "bid": [1.0],
                "ask": [1.2],
                "impliedVolatility": [0.2],
                "openInterest": [100],
                "option_type": ["call"],
                "expiry": [expiry.strftime("%Y-%m-%d")],
                "mid": [1.1],
                "spread": [0.2],
            }
        )
        chain.to_csv(cache_path, index=False)

        loaded = get_options_chain(
            "NVDA",
            expiry,
            cache_dir=cache_dir,
            use_cache=True,
        )

        assert pd.api.types.is_datetime64_any_dtype(loaded["expiry"])


def test_market_closed_detection() -> None:
    chain = pd.DataFrame(
        {
            "bid": [0.0, 0.0],
            "ask": [0.0, 0.0],
        }
    )
    try:
        _raise_if_market_closed(chain)
    except ValueError as exc:
        assert "market appears closed" in str(exc).lower()
    else:
        raise AssertionError("Expected ValueError for closed market")
