"""Load market data using yfinance."""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import yfinance as yf

from event_vol_analysis.config import BACK3_DTE_MIN, BACK3_DTE_MAX


LOGGER = logging.getLogger(__name__)
DEFAULT_CACHE_DB_PATH = Path("data/options_intraday.db")


@dataclass(frozen=True)
class EventDateResolution:
    """Resolution result for one auto-discovered earnings event date."""

    status: str
    event_date: dt.date | None
    message: str
    candidates: list[dt.date]


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
    parsed = [dt.datetime.strptime(exp, "%Y-%m-%d").date() for exp in expiries]
    return sorted(set(parsed))


def _normalize_chain_from_db(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize chain from option_quotes table."""
    if frame.empty:
        return frame

    output = frame.rename(
        columns={
            "implied_volatility": "impliedVolatility",
            "open_interest": "openInterest",
        }
    ).copy()

    if "expiry" in output.columns:
        output["expiry"] = pd.to_datetime(output["expiry"])

    if "mid" not in output.columns:
        output["mid"] = (output["bid"] + output["ask"]) / 2.0
    if "spread" not in output.columns:
        output["spread"] = (output["ask"] - output["bid"]).clip(lower=0.0)

    required = {
        "strike",
        "bid",
        "ask",
        "impliedVolatility",
        "openInterest",
        "option_type",
        "expiry",
    }
    missing = required.difference(output.columns)
    if missing:
        LOGGER.warning("EOD cache missing columns for %s: %s", missing)
        return pd.DataFrame()

    return output


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
    cache_db_path: Path | None = DEFAULT_CACHE_DB_PATH,
    cache_only: bool = False,
) -> pd.DataFrame:
    """Fetch options chain for a given expiry and return combined frame."""
    cache_path = None
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        stamp = dt.date.today().strftime("%Y%m%d")
        cache_name = f"{ticker}_{expiry.strftime('%Y%m%d')}_{stamp}.csv"
        cache_path = cache_dir / cache_name

    if use_cache and not refresh_cache:
        db_cached = _load_chain_from_database_cache(
            ticker,
            expiry,
            cache_db_path,
        )
        if db_cached is not None:
            return db_cached

    if (
        use_cache
        and cache_path is not None
        and cache_path.exists()
        and not refresh_cache
    ):
        LOGGER.info("Loading options chain from cache: %s", cache_path)
        chain = pd.read_csv(cache_path, parse_dates=["expiry"])
        if "expiry" not in chain.columns:
            raise ValueError("Cached options chain missing expiry column.")
        _raise_if_market_closed(chain)
        return chain

    if cache_only:
        raise ValueError(
            "No cached options chain available (cache-only mode, live fetch disabled)."
        )

    yf_ticker = yf.Ticker(ticker)
    chain = yf_ticker.option_chain(expiry.strftime("%Y-%m-%d"))

    calls = _normalize_chain_frame(chain.calls, "call", expiry)
    puts = _normalize_chain_frame(chain.puts, "put", expiry)
    combined = pd.concat([calls, puts], ignore_index=True)
    _raise_if_market_closed(combined)

    if cache_path is not None:
        if _is_cache_data_valid(combined):
            combined.to_csv(cache_path, index=False)
            LOGGER.info("Saved options chain to cache: %s", cache_path)
        else:
            LOGGER.warning("Skipping cache save: data contains invalid (zero) prices")

    return combined


def _load_chain_from_database_cache(
    ticker: str,
    expiry: dt.date,
    db_path: Path | None,
) -> pd.DataFrame | None:
    """Load one chain snapshot from SQLite cache when available."""
    if db_path is None:
        return None

    path = Path(db_path)
    if not path.exists():
        return None

    try:
        from data.option_data_store import create_store

        store = create_store(path)
        chain = store.query_chain(
            ticker=ticker,
            expiry=expiry,
            min_quality="valid",
        )
    except Exception as exc:  # pragma: no cover
        LOGGER.warning(
            "Database cache lookup failed for %s %s (%s): %s",
            ticker,
            expiry,
            path,
            exc,
        )
        return None

    if chain.empty:
        return None

    normalized = chain.rename(
        columns={
            "implied_volatility": "impliedVolatility",
            "open_interest": "openInterest",
        }
    ).copy()

    if "expiry" in normalized.columns:
        normalized["expiry"] = pd.to_datetime(normalized["expiry"])

    if "mid" not in normalized.columns:
        normalized["mid"] = (normalized["bid"] + normalized["ask"]) / 2.0
    if "spread" not in normalized.columns:
        normalized["spread"] = (normalized["ask"] - normalized["bid"]).clip(lower=0.0)

    required = {
        "strike",
        "bid",
        "ask",
        "impliedVolatility",
        "openInterest",
        "option_type",
        "expiry",
    }
    missing = required.difference(normalized.columns)
    if missing:
        LOGGER.warning(
            "Database cache missing required columns for %s %s: %s",
            ticker,
            expiry,
            sorted(missing),
        )
        return None

    _raise_if_market_closed(normalized)
    LOGGER.info(
        "Loading options chain from database cache: %s (%s %s, rows=%d)",
        path,
        ticker,
        expiry,
        len(normalized),
    )
    return normalized


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
    resolution = resolve_next_earnings_date(ticker)
    if resolution.status == "resolved":
        return resolution.event_date
    return None


def resolve_next_earnings_date(
    ticker: str,
    *,
    today: dt.date | None = None,
    limit: int = 8,
    ambiguity_window_days: int = 7,
    max_days_ahead: int = 220,
) -> EventDateResolution:
    """Resolve one actionable next earnings date with ambiguity checks.

    Returns a structured result so callers can fail with explicit operator
    guidance instead of silently defaulting.
    """
    as_of = today or dt.date.today()
    try:
        earnings = yf.Ticker(ticker).get_earnings_dates(limit=limit)
    except Exception as exc:
        return EventDateResolution(
            status="fetch_error",
            event_date=None,
            message=(
                "Earnings calendar fetch failed from yfinance. "
                "Provide --event-date YYYY-MM-DD or retry later. "
                f"Provider error: {exc}"
            ),
            candidates=[],
        )

    if earnings is None or len(getattr(earnings, "index", [])) == 0:
        return EventDateResolution(
            status="missing",
            event_date=None,
            message=(
                "No earnings dates were returned by yfinance. "
                "Provide --event-date YYYY-MM-DD."
            ),
            candidates=[],
        )

    all_dates = sorted(
        {ts.date() for ts in earnings.index if isinstance(ts, pd.Timestamp)}
    )
    if not all_dates:
        return EventDateResolution(
            status="missing",
            event_date=None,
            message=(
                "Earnings calendar response had no parseable timestamps. "
                "Provide --event-date YYYY-MM-DD."
            ),
            candidates=[],
        )

    upcoming = [event_date for event_date in all_dates if event_date >= as_of]
    if not upcoming:
        latest = all_dates[-1]
        return EventDateResolution(
            status="stale",
            event_date=None,
            message=(
                "Earnings calendar appears stale (only past dates). "
                f"Latest returned date: {latest}. "
                "Provide --event-date YYYY-MM-DD."
            ),
            candidates=all_dates,
        )

    next_date = upcoming[0]
    days_ahead = (next_date - as_of).days
    if days_ahead > max_days_ahead:
        return EventDateResolution(
            status="stale",
            event_date=None,
            message=(
                "Auto-discovered date is too far in the future to trust as "
                f"next earnings ({next_date}, {days_ahead} days ahead). "
                "Provide --event-date YYYY-MM-DD."
            ),
            candidates=upcoming,
        )

    if len(upcoming) >= 2:
        second = upcoming[1]
        if (second - next_date).days <= ambiguity_window_days:
            return EventDateResolution(
                status="ambiguous",
                event_date=None,
                message=(
                    "Multiple nearby candidate earnings dates were returned "
                    f"({next_date}, {second}). "
                    "Provide --event-date YYYY-MM-DD."
                ),
                candidates=upcoming,
            )

    return EventDateResolution(
        status="resolved",
        event_date=next_date,
        message=(f"Auto-discovered earnings date from yfinance: {next_date}"),
        candidates=upcoming,
    )


def get_dividend_yield(ticker: str) -> float:
    """Return the trailing annual dividend yield for *ticker* as a decimal.

    Reads ``dividendYield`` from yfinance ``.info``.  Falls back to 0.0 if
    the field is absent or ``None`` (e.g. non-dividend-paying stocks).

    Args:
        ticker: Underlying ticker symbol.

    Returns:
        Dividend yield as a decimal (e.g. 0.012 for 1.2%).
    """
    try:
        info = yf.Ticker(ticker).info
        yield_val = info.get("dividendYield")
        if yield_val is not None:
            return float(yield_val)
    except Exception as exc:
        LOGGER.warning("Dividend yield fetch failed for %s: %s", ticker, exc)
    LOGGER.info("No dividend yield found for %s; defaulting to 0.0", ticker)
    return 0.0


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


def select_front_expiry(
    expiries: Iterable[dt.date],
    event_date: dt.date,
    *,
    ticker: str | None = None,
    event_time_label: str | None = None,
) -> dt.date:
    """Select the nearest valid front expiry around the earnings event.

    Timing policy: require strictly after event date to avoid accidental
    same-day 0DTE selection.
    """
    ordered = sorted(set(expiries))
    if not ordered:
        name = ticker or "ticker"
        raise ValueError(f"No option expiries available for {name}.")

    candidates = [exp for exp in ordered if exp > event_date]

    if not candidates:
        name = ticker or "ticker"
        timing_label = (
            f" (event_time_label={event_time_label})"
            if event_time_label is not None
            else ""
        )
        raise ValueError(
            "No valid front expiry found after event date "
            f"{event_date} for {name}{timing_label}."
        )
    return candidates[0]


def _select_back3_expiry(
    available_expiries: Iterable[dt.date],
    back2_expiry: dt.date,
    as_of_date: dt.date,
) -> dt.date | None:
    """Return the first expiry after back2 that falls within the back3 window.

    DTE bounds are read from config (``BACK3_DTE_MIN``, ``BACK3_DTE_MAX``),
    which are the single source of truth shared with the backspread builder
    and calendar builder. Changing the config automatically propagates here.

    Args:
        available_expiries: All available option expiry dates.
        back2_expiry: The back2 expiry; back3 must be strictly after this.
        as_of_date: The reference date for computing DTE.

    Returns:
        The first qualifying back3 expiry, or ``None`` if none found.
    """
    for expiry in sorted(available_expiries):
        if expiry <= back2_expiry:
            continue
        dte = (expiry - as_of_date).days
        if BACK3_DTE_MIN <= dte <= BACK3_DTE_MAX:
            return expiry
    return None


def _raise_if_market_closed(chain: pd.DataFrame) -> None:
    if chain.empty:
        return
    bids = chain["bid"].fillna(0.0)
    asks = chain["ask"].fillna(0.0)
    if (bids == 0).all() and (asks == 0).all():
        raise ValueError(
            "Options bid/ask are all 0.00; market appears closed or data unavailable."
        )


def load_cached_chain_at_date(
    ticker: str,
    expiry: dt.date,
    db_path: Path | None,
    as_of_date: dt.date,
    min_quality: str = "valid",
) -> pd.DataFrame | None:
    """Load the most recent valid chain snapshot for a ticker/expiry as of a date.

    Args:
        ticker: Stock ticker symbol
        expiry: Specific expiry to load
        db_path: Path to options_intraday.db
        as_of_date: Load snapshot captured on or before this date
        min_quality: Minimum quality tag ('valid', 'partial', 'all')

    Returns:
        Chain DataFrame or None if no valid snapshot found
    """
    if db_path is None:
        return None

    path = Path(db_path)
    if not path.exists():
        return None

    try:
        from data.option_data_store import create_store

        store = create_store(path)
        snapshot = store.query_eod_snapshot(ticker.upper(), as_of_date, min_quality)

        # Fallback: if no snapshot metadata, try latest from option_quotes directly
        if snapshot is None:
            ts = store.get_latest_timestamp(ticker.upper())
            if ts is not None:
                LOGGER.info(
                    "Falling back to latest quote for %s at %s",
                    ticker,
                    ts,
                )
                chain = store.query_chain(
                    ticker=ticker,
                    timestamp=ts,
                    expiry=expiry,
                    min_quality="all",
                )
                if not chain.empty:
                    return _normalize_chain_from_db(chain)
            return None

        ts = snapshot.get("timestamp")
        if ts is None:
            return None

        chain = store.query_chain(
            ticker=ticker,
            timestamp=ts,
            expiry=expiry,
            min_quality="valid",
        )
    except Exception as exc:  # pragma: no cover
        LOGGER.warning(
            "EOD cache lookup failed for %s %s (%s): %s",
            ticker,
            expiry,
            path,
            exc,
        )
        return None

    if chain.empty:
        return None

    normalized = chain.rename(
        columns={
            "implied_volatility": "impliedVolatility",
            "open_interest": "openInterest",
        }
    ).copy()

    if "expiry" in normalized.columns:
        normalized["expiry"] = pd.to_datetime(normalized["expiry"])

    if "mid" not in normalized.columns:
        normalized["mid"] = (normalized["bid"] + normalized["ask"]) / 2.0
    if "spread" not in normalized.columns:
        normalized["spread"] = (normalized["ask"] - normalized["bid"]).clip(lower=0.0)

    required = {
        "strike",
        "bid",
        "ask",
        "impliedVolatility",
        "openInterest",
        "option_type",
        "expiry",
    }
    missing = required.difference(normalized.columns)
    if missing:
        LOGGER.warning(
            "EOD cache missing required columns for %s %s: %s",
            ticker,
            expiry,
            sorted(missing),
        )
        return None

    LOGGER.info(
        "Loaded EOD cache: %s %s from %s (%d rows, quality=%s)",
        ticker,
        expiry,
        ts,
        len(normalized),
        snapshot.get("quality_tag", "unknown"),
    )
    return normalized


def _is_cache_data_valid(chain: pd.DataFrame) -> bool:
    """Return False if chain has invalid prices (all zeros or NaN)."""
    if chain.empty:
        return False
    bids = chain["bid"].fillna(0.0)
    asks = chain["ask"].fillna(0.0)
    # Check if all prices are zero (invalid data)
    if (bids == 0).all() and (asks == 0).all():
        return False
    # Check if spot prices (implied by mid) are reasonable
    mids = (bids + asks) / 2.0
    if (mids == 0).all():
        return False
    return True
