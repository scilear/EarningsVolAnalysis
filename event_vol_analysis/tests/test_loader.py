"""Tests for loader helpers."""

import datetime as dt

import pytest

from event_vol_analysis.data import loader as loader_module
from event_vol_analysis.data.loader import (
    EventDateResolution,
    get_dividend_yield,
    get_expiries_after,
    resolve_next_earnings_date,
    select_front_expiry,
)

# ── TestGetDividendYield ────────────────────────────────────────────────────


class _MockTicker:
    def __init__(self, info: dict) -> None:
        self.info = info


class TestGetDividendYield:
    """Tests for get_dividend_yield() in data/loader.py."""

    def test_returns_yield_when_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "event_vol_analysis.data.loader.yf.Ticker",
            lambda t: _MockTicker({"dividendYield": 0.012}),
        )
        assert get_dividend_yield("AAPL") == pytest.approx(0.012)

    def test_returns_zero_for_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "event_vol_analysis.data.loader.yf.Ticker",
            lambda t: _MockTicker({"dividendYield": None}),
        )
        assert get_dividend_yield("AAPL") == 0.0

    def test_returns_zero_for_missing_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "event_vol_analysis.data.loader.yf.Ticker",
            lambda t: _MockTicker({}),
        )
        assert get_dividend_yield("AAPL") == 0.0

    def test_returns_zero_on_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _bad_ticker(t: str) -> None:
            raise RuntimeError("network error")

        monkeypatch.setattr(
            "event_vol_analysis.data.loader.yf.Ticker",
            _bad_ticker,
        )
        assert get_dividend_yield("AAPL") == 0.0

    def test_return_type_is_float(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "event_vol_analysis.data.loader.yf.Ticker",
            lambda t: _MockTicker({"dividendYield": 0.012}),
        )
        result = get_dividend_yield("AAPL")
        assert isinstance(result, float)


# ── Original tests ──────────────────────────────────────────────────────────


def test_get_expiries_after_filters() -> None:
    expiries = [
        dt.date(2026, 1, 1),
        dt.date(2026, 2, 1),
        dt.date(2026, 3, 1),
    ]
    result = get_expiries_after(expiries, dt.date(2026, 2, 1))
    assert result == [dt.date(2026, 2, 1), dt.date(2026, 3, 1)]


def test_select_front_expiry_prefers_nearest_after_event_for_unknown_timing() -> None:
    expiries = [
        dt.date(2026, 8, 21),
        dt.date(2026, 8, 28),
        dt.date(2026, 9, 18),
    ]
    out = select_front_expiry(
        expiries,
        dt.date(2026, 8, 21),
        ticker="TSLA",
        event_time_label=None,
    )
    assert out == dt.date(2026, 8, 28)


def test_select_front_expiry_bmo_still_avoids_same_day() -> None:
    expiries = [dt.date(2026, 8, 21), dt.date(2026, 8, 28)]
    out = select_front_expiry(
        expiries,
        dt.date(2026, 8, 21),
        ticker="TSLA",
        event_time_label="bmo",
    )
    assert out == dt.date(2026, 8, 28)


def test_select_front_expiry_requires_strictly_after_for_amc() -> None:
    expiries = [dt.date(2026, 8, 21), dt.date(2026, 8, 28)]
    out = select_front_expiry(
        expiries,
        dt.date(2026, 8, 21),
        ticker="TSLA",
        event_time_label="amc",
    )
    assert out == dt.date(2026, 8, 28)


class _MockEarningsTicker:
    def __init__(self, earnings_index: list) -> None:
        self._earnings_index = earnings_index

    def get_earnings_dates(self, limit: int = 8):  # noqa: ARG002
        import pandas as pd

        return pd.DataFrame(index=pd.DatetimeIndex(self._earnings_index))


class TestResolveNextEarningsDate:
    def test_resolved_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "event_vol_analysis.data.loader.yf.Ticker",
            lambda t: _MockEarningsTicker(
                [
                    dt.datetime(2026, 5, 28),
                    dt.datetime(2026, 8, 27),
                ]
            ),
        )
        result = resolve_next_earnings_date("NVDA", today=dt.date(2026, 4, 21))
        assert isinstance(result, EventDateResolution)
        assert result.status == "resolved"
        assert result.event_date == dt.date(2026, 5, 28)

    def test_missing_when_provider_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import pandas as pd

        class _EmptyTicker:
            def get_earnings_dates(self, limit: int = 8):  # noqa: ARG002
                return pd.DataFrame()

        monkeypatch.setattr(
            "event_vol_analysis.data.loader.yf.Ticker",
            lambda t: _EmptyTicker(),
        )
        result = resolve_next_earnings_date("NVDA", today=dt.date(2026, 4, 21))
        assert result.status == "missing"
        assert result.event_date is None

    def test_ambiguous_when_two_dates_close(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "event_vol_analysis.data.loader.yf.Ticker",
            lambda t: _MockEarningsTicker(
                [
                    dt.datetime(2026, 5, 28),
                    dt.datetime(2026, 6, 2),
                ]
            ),
        )
        result = resolve_next_earnings_date("NVDA", today=dt.date(2026, 4, 21))
        assert result.status == "ambiguous"
        assert result.event_date is None
        assert len(result.candidates) >= 2

    def test_stale_when_only_past_dates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "event_vol_analysis.data.loader.yf.Ticker",
            lambda t: _MockEarningsTicker(
                [
                    dt.datetime(2025, 11, 20),
                    dt.datetime(2026, 2, 20),
                ]
            ),
        )
        result = resolve_next_earnings_date("NVDA", today=dt.date(2026, 4, 21))
        assert result.status == "stale"
        assert result.event_date is None

    def test_fetch_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _bad_ticker(t: str):
            raise RuntimeError("network error")

        monkeypatch.setattr(
            "event_vol_analysis.data.loader.yf.Ticker",
            _bad_ticker,
        )
        result = resolve_next_earnings_date("NVDA", today=dt.date(2026, 4, 21))
        assert result.status == "fetch_error"
        assert result.event_date is None


def test_rate_limiter_applies_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loader_module.config, "YF_RATE_LIMIT_MS", 200)
    monkeypatch.setattr(loader_module, "_LAST_YF_REQUEST_MONOTONIC", 10.0)

    ticks = iter([10.05, 10.20])
    monkeypatch.setattr(loader_module.time, "monotonic", lambda: next(ticks))

    sleeps: list[float] = []
    monkeypatch.setattr(loader_module.time, "sleep", lambda s: sleeps.append(s))

    loader_module._throttle_yfinance()

    assert sleeps == [pytest.approx(0.15, rel=1e-6)]


def test_rate_limiter_retries_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loader_module.config, "YF_MAX_RETRIES", 3)
    monkeypatch.setattr(loader_module, "_throttle_yfinance", lambda: None)

    sleeps: list[float] = []
    monkeypatch.setattr(loader_module.time, "sleep", lambda s: sleeps.append(s))

    attempts = {"count": 0}

    def _operation() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("429 Too Many Requests")
        return "ok"

    result = loader_module._execute_yfinance_call(
        _operation,
        ticker="AAPL",
        action="history",
    )

    assert result == "ok"
    assert attempts["count"] == 3
    assert sleeps == [1.0, 2.0]
