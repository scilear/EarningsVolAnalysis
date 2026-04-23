"""Tests for options chain caching and market-closed checks."""

import datetime as dt
import tempfile
from pathlib import Path

import pandas as pd

from event_vol_analysis.data.loader import (
    _raise_if_market_closed,
    get_options_chain,
)


def test_cache_load_parses_expiry() -> None:
    expiry = dt.date(2030, 1, 17)
    stamp = dt.date.today().strftime("%Y%m%d")
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_dir = Path(temp_dir)
        cache_name = f"NVDA_{expiry.strftime('%Y%m%d')}_{stamp}.csv"
        cache_path = cache_dir / cache_name
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
            cache_db_path=None,
        )

        assert pd.api.types.is_datetime64_any_dtype(loaded["expiry"])


def test_use_cache_loads_from_database_before_network(
    monkeypatch,
    tmp_path: Path,
) -> None:
    expiry = dt.date(2030, 1, 17)

    class _MockStore:
        def query_chain(self, ticker: str, expiry: dt.date, min_quality: str):
            assert ticker == "NVDA"
            assert expiry == dt.date(2030, 1, 17)
            assert min_quality == "valid"
            return pd.DataFrame(
                {
                    "strike": [100.0],
                    "bid": [1.0],
                    "ask": [1.2],
                    "implied_volatility": [0.2],
                    "open_interest": [100],
                    "option_type": ["call"],
                    "expiry": [expiry],
                    "mid": [1.1],
                    "spread": [0.2],
                }
            )

    monkeypatch.setattr(
        "data.option_data_store.create_store",
        lambda db_path: _MockStore(),
    )

    class _NoNetworkTicker:
        def option_chain(self, expiry_label: str):  # noqa: ARG002
            raise AssertionError("Network should not be called when DB cache exists")

    monkeypatch.setattr(
        "event_vol_analysis.data.loader.yf.Ticker",
        lambda ticker: _NoNetworkTicker(),
    )

    db_path = tmp_path / "options_intraday.db"
    db_path.write_text("placeholder", encoding="utf-8")

    loaded = get_options_chain(
        "NVDA",
        expiry,
        cache_dir=tmp_path,
        use_cache=True,
        cache_db_path=db_path,
    )

    assert len(loaded) == 1
    assert "impliedVolatility" in loaded.columns
    assert "openInterest" in loaded.columns


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


def test_cache_only_raises_when_no_cache(monkeypatch) -> None:
    expiry = dt.date(2030, 1, 17)

    class _NoNetworkTicker:
        def option_chain(self, expiry_label: str):  # noqa: ARG002
            raise AssertionError("Network should not be called in cache-only mode")

    monkeypatch.setattr(
        "event_vol_analysis.data.loader.yf.Ticker",
        lambda ticker: _NoNetworkTicker(),
    )

    try:
        get_options_chain(
            "NVDA",
            expiry,
            cache_dir=None,
            use_cache=True,
            cache_db_path=None,
            cache_only=True,
        )
    except ValueError as exc:
        assert "cache-only mode" in str(exc).lower()
    else:
        raise AssertionError("Expected ValueError for missing cache-only data")
