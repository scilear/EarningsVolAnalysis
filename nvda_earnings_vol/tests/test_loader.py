"""Tests for loader helpers."""

import datetime as dt

import pytest

from nvda_earnings_vol.data.loader import (
    get_dividend_yield,
    get_expiries_after,
)


# ── TestGetDividendYield ────────────────────────────────────────────────────


class _MockTicker:
    def __init__(self, info: dict) -> None:
        self.info = info


class TestGetDividendYield:
    """Tests for get_dividend_yield() in data/loader.py."""

    def test_returns_yield_when_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "nvda_earnings_vol.data.loader.yf.Ticker",
            lambda t: _MockTicker({"dividendYield": 0.012}),
        )
        assert get_dividend_yield("AAPL") == pytest.approx(0.012)

    def test_returns_zero_for_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "nvda_earnings_vol.data.loader.yf.Ticker",
            lambda t: _MockTicker({"dividendYield": None}),
        )
        assert get_dividend_yield("AAPL") == 0.0

    def test_returns_zero_for_missing_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "nvda_earnings_vol.data.loader.yf.Ticker",
            lambda t: _MockTicker({}),
        )
        assert get_dividend_yield("AAPL") == 0.0

    def test_returns_zero_on_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _bad_ticker(t: str) -> None:
            raise RuntimeError("network error")

        monkeypatch.setattr(
            "nvda_earnings_vol.data.loader.yf.Ticker",
            _bad_ticker,
        )
        assert get_dividend_yield("AAPL") == 0.0

    def test_return_type_is_float(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "nvda_earnings_vol.data.loader.yf.Ticker",
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
