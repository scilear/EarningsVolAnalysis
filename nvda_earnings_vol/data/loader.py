"""Load market data using yfinance."""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Iterable

import pandas as pd
import yfinance as yf


LOGGER = logging.getLogger(__name__)


def get_spot_price(ticker: str) -> float:
    """Fetch the latest close price for a ticker."""
    yf_ticker = yf.Ticker(ticker)
    history = yf_ticker.history(period="5d")
    if history.empty:
        raise ValueError("No price history returned for ticker.")
    return float(history["Close"].iloc[-1])


def get_option_expiries(ticker: str) -> list[dt.date]:
    """Return available option expiry dates as date objects."""
    yf_ticker = yf.Ticker(ticker)
    expiries = yf_ticker.options
    if not expiries:
        raise ValueError("No option expiries available for ticker.")
    return [dt.datetime.strptime(exp, "%Y-%m-%d").date() for exp in expiries]


def _normalize_chain_frame(
    frame: pd.DataFrame,
    option_type: str,
    expiry: dt.date,
) -> pd.DataFrame:
    required = ["strike", "bid", "ask", "impliedVolatility", "openInterest"]
    missing = [col for col in required if col not in frame.columns]
    if missing:
        raise ValueError(f"Missing option fields: {missing}")

    output = frame.copy()
    output["option_type"] = option_type
    output["expiry"] = pd.to_datetime(expiry)
    output["mid"] = (output["bid"] + output["ask"]) / 2.0
    output["spread"] = (output["ask"] - output["bid"]).clip(lower=0.0)
    return output


def get_options_chain(
    ticker: str,
    expiry: dt.date,
    cache_dir: Path | None = None,
    use_cache: bool = False,
    refresh_cache: bool = False,
) -> pd.DataFrame:
    """Fetch options chain for a given expiry and return combined frame."""
    cache_path = None
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        stamp = dt.date.today().strftime("%Y%m%d")
        cache_name = f"{ticker}_{expiry.strftime('%Y%m%d')}_{stamp}.csv"
        cache_path = cache_dir / cache_name

    if use_cache and cache_path is not None and cache_path.exists() and not refresh_cache:
        LOGGER.info("Loading options chain from cache: %s", cache_path)
        chain = pd.read_csv(cache_path, parse_dates=["expiry"])
        if "expiry" not in chain.columns:
            raise ValueError("Cached options chain missing expiry column.")
        _raise_if_market_closed(chain)
        return chain

    yf_ticker = yf.Ticker(ticker)
    chain = yf_ticker.option_chain(expiry.strftime("%Y-%m-%d"))

    calls = _normalize_chain_frame(chain.calls, "call", expiry)
    puts = _normalize_chain_frame(chain.puts, "put", expiry)
    combined = pd.concat([calls, puts], ignore_index=True)
    _raise_if_market_closed(combined)

    if cache_path is not None:
        combined.to_csv(cache_path, index=False)
        LOGGER.info("Saved options chain to cache: %s", cache_path)

    return combined


def get_price_history(ticker: str, years: int) -> pd.DataFrame:
    """Return historical daily close prices for the given number of years."""
    yf_ticker = yf.Ticker(ticker)
    end = dt.date.today()
    start = end - dt.timedelta(days=int(years * 365.25))
    history = yf_ticker.history(start=start, end=end)
    if history.empty:
        raise ValueError("No historical price data returned.")
    history = history.reset_index()
    return history[["Date", "Close"]]


def get_next_earnings_date(ticker: str) -> dt.date | None:
    """Attempt to fetch the next earnings date from yfinance."""
    yf_ticker = yf.Ticker(ticker)
    try:
        earnings = yf_ticker.get_earnings_dates(limit=1)
    except Exception as exc:
        LOGGER.warning("Earnings date fetch failed: %s", exc)
        return None
    if earnings is None or earnings.empty:
        return None
    next_date = earnings.index[0]
    if isinstance(next_date, pd.Timestamp):
        return next_date.date()
    return None


def get_earnings_dates(ticker: str, limit: int = 12) -> list[pd.Timestamp]:
    """Fetch recent earnings dates using yfinance."""
    yf_ticker = yf.Ticker(ticker)
    try:
        earnings = yf_ticker.get_earnings_dates(limit=limit)
    except Exception as exc:
        LOGGER.warning("Earnings dates fetch failed: %s", exc)
        return []
    if earnings is None or earnings.empty:
        return []
    return [ts for ts in earnings.index if isinstance(ts, pd.Timestamp)]


def get_expiries_after(
    expiries: Iterable[dt.date], target_date: dt.date
) -> list[dt.date]:
    """Filter expiries that are on or after a target date."""
    return sorted([exp for exp in expiries if exp >= target_date])


def _raise_if_market_closed(chain: pd.DataFrame) -> None:
    if chain.empty:
        return
    bids = chain["bid"].fillna(0.0)
    asks = chain["ask"].fillna(0.0)
    if (bids == 0).all() and (asks == 0).all():
        raise ValueError(
            "Options bid/ask are all 0.00; market appears closed or data unavailable."
        )
