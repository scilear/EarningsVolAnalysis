"""Tests for calibration.py and related data-input validation.

Covers:
- _atm_region, _min_oi, _max_spread_pct, _wing_width_pct, _gex_large_abs
- calibrate_ticker_params (public integration)
- calibrate_iv_scenarios (formula, EVR clamping, dict mutation)
- div_yield propagation: skew_metrics, gex_summary, strategy_pnl_vec
- wing_width_pct propagation: build_call/put_backspread
"""

from __future__ import annotations

import copy
import datetime as dt
import math

import numpy as np
import pandas as pd
import pytest

from event_vol_analysis import config
from event_vol_analysis.calibration import (
    _atm_region,
    _gex_large_abs,
    _max_spread_pct,
    _min_oi,
    _wing_width_pct,
    calibrate_iv_scenarios,
    calibrate_ticker_params,
)


# ── Shared helpers ──────────────────────────────────────────────────────────


class _MockTicker:
    def __init__(self, info: dict) -> None:
        self.info = info


def _make_raw_chain(
    spot: float = 100.0,
    n_strikes: int = 21,
    step: float = 2.5,
    base_oi: int = 500,
    base_spread_pct: float = 0.04,
) -> pd.DataFrame:
    """Build a minimal raw chain DataFrame for calibration tests.

    Produces both calls and puts for each strike, with columns:
    strike, bid, ask, impliedVolatility, openInterest,
    option_type, expiry.
    """
    centre = round(spot / step) * step
    strikes = [centre + (i - n_strikes // 2) * step for i in range(n_strikes)]
    rows = []
    for i, s in enumerate(strikes):
        exponent = -0.5 * ((s - spot) / (spot * 0.10)) ** 2
        mid = max(0.50, 10.0 * math.exp(exponent))
        half_spread = mid * base_spread_pct / 2.0
        oi = max(10, base_oi - i * 20)
        for ot in ("call", "put"):
            rows.append(
                {
                    "strike": s,
                    "bid": max(0.01, mid - half_spread),
                    "ask": mid + half_spread,
                    "impliedVolatility": 0.45,
                    "openInterest": oi,
                    "option_type": ot,
                    "expiry": pd.Timestamp("2026-04-17"),
                }
            )
    return pd.DataFrame(rows)


def _make_chain_with_oi(
    spot: float,
    strikes: list[float],
    oi_vals: list[int],
) -> pd.DataFrame:
    """Chain where each strike has a specific OI, in the ATM region."""
    rows = []
    for s, oi in zip(strikes, oi_vals):
        rows.append(
            {
                "strike": s,
                "bid": 1.0,
                "ask": 1.1,
                "impliedVolatility": 0.40,
                "openInterest": oi,
                "option_type": "call",
                "expiry": pd.Timestamp("2026-04-17"),
            }
        )
    return pd.DataFrame(rows)


# ── Fixture for IV scenario isolation ───────────────────────────────────────


@pytest.fixture()
def restore_iv_scenarios():
    """Save and restore config.IV_SCENARIOS around each test."""
    original = copy.deepcopy(config.IV_SCENARIOS)
    yield
    config.IV_SCENARIOS.clear()
    config.IV_SCENARIOS.update(original)


# ── TestAtmRegion ───────────────────────────────────────────────────────────


class TestAtmRegion:
    """Tests for _atm_region(chain, spot, width=0.15)."""

    def _make_chain(self, strikes: list[float]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "strike": strikes,
                "option_type": ["call"] * len(strikes),
            }
        )

    def test_includes_atm_strikes(self) -> None:
        # Use strikes clearly inside ±15% (not on boundary)
        chain = self._make_chain([90.0, 100.0, 110.0])
        result = _atm_region(chain, spot=100.0, width=0.15)
        assert set(result["strike"]) == {90.0, 100.0, 110.0}

    def test_excludes_far_otm(self) -> None:
        chain = self._make_chain([50.0, 200.0])
        result = _atm_region(chain, spot=100.0, width=0.15)
        assert result.empty

    def test_custom_width(self) -> None:
        chain = self._make_chain([90.0, 100.0, 110.0])
        result = _atm_region(chain, spot=100.0, width=0.05)
        assert list(result["strike"]) == [100.0]

    def test_empty_chain(self) -> None:
        chain = pd.DataFrame({"strike": [], "option_type": []})
        result = _atm_region(chain, spot=100.0)
        assert result.empty


# ── TestMinOi ───────────────────────────────────────────────────────────────


class TestMinOi:
    """Tests for _min_oi(chain, spot)."""

    _SPOT = 100.0
    # 10 strikes all clearly within ±14% of spot=100
    # (avoiding the ±15% boundary to prevent float-precision edge cases)
    _STRIKES = [
        88.0, 91.0, 94.0, 97.0, 100.0,
        103.0, 106.0, 109.0, 112.0, 114.0,
    ]

    def _chain(self, oi_vals: list[int]) -> pd.DataFrame:
        return _make_chain_with_oi(self._SPOT, self._STRIKES, oi_vals)

    def test_returns_20th_percentile(self) -> None:
        oi_vals = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000]
        chain = self._chain(oi_vals)
        expected = int(pd.Series(oi_vals).quantile(0.20))
        result = _min_oi(chain, self._SPOT)
        assert result == expected

    def test_clamps_floor(self) -> None:
        chain = self._chain([1] * 10)
        assert _min_oi(chain, self._SPOT) == 10

    def test_clamps_ceiling(self) -> None:
        chain = self._chain([50_000] * 10)
        assert _min_oi(chain, self._SPOT) == 200

    def test_fallback_empty_chain(self) -> None:
        chain = pd.DataFrame(
            {"strike": [], "openInterest": [], "option_type": []}
        )
        assert _min_oi(chain, self._SPOT) == config.MIN_OI

    def test_fallback_no_oi_column(self) -> None:
        n = len(self._STRIKES)
        chain = pd.DataFrame(
            {"strike": self._STRIKES, "option_type": ["call"] * n}
        )
        assert _min_oi(chain, self._SPOT) == config.MIN_OI

    def test_fallback_all_zero_oi(self) -> None:
        chain = self._chain([0] * 10)
        assert _min_oi(chain, self._SPOT) == config.MIN_OI


# ── TestMaxSpreadPct ─────────────────────────────────────────────────────────


class TestMaxSpreadPct:
    """Tests for _max_spread_pct(chain, spot)."""

    _SPOT = 100.0
    _STRIKES = [
        90.0, 92.5, 95.0, 97.5, 100.0,
        102.5, 105.0, 107.5, 110.0, 112.5,
    ]

    def _chain_from_spread_pcts(
        self, spread_pcts: list[float]
    ) -> pd.DataFrame:
        rows = []
        mid = 10.0
        for s, sp in zip(self._STRIKES, spread_pcts):
            rows.append(
                {
                    "strike": s,
                    "bid": mid * (1 - sp / 2),
                    "ask": mid * (1 + sp / 2),
                    "option_type": "call",
                    "expiry": pd.Timestamp("2026-04-17"),
                }
            )
        return pd.DataFrame(rows)

    def test_returns_65th_percentile(self) -> None:
        spread_pcts = [
            0.01, 0.02, 0.03, 0.04, 0.05,
            0.06, 0.07, 0.08, 0.09, 0.10,
        ]
        chain = self._chain_from_spread_pcts(spread_pcts)
        expected = float(pd.Series(spread_pcts).quantile(0.65))
        result = _max_spread_pct(chain, self._SPOT)
        assert result == pytest.approx(expected, rel=1e-4)

    def test_clamps_floor(self) -> None:
        spread_pcts = [0.001] * 10
        chain = self._chain_from_spread_pcts(spread_pcts)
        assert _max_spread_pct(chain, self._SPOT) == pytest.approx(0.03)

    def test_clamps_ceiling(self) -> None:
        spread_pcts = [0.50] * 10
        chain = self._chain_from_spread_pcts(spread_pcts)
        assert _max_spread_pct(chain, self._SPOT) == pytest.approx(0.20)

    def test_fallback_empty_chain(self) -> None:
        chain = pd.DataFrame(
            {"strike": [], "bid": [], "ask": [], "option_type": []}
        )
        assert _max_spread_pct(chain, self._SPOT) == config.MAX_SPREAD_PCT

    def test_fallback_zero_mid(self) -> None:
        chain = pd.DataFrame(
            {
                "strike": self._STRIKES,
                "bid": [0.0] * 10,
                "ask": [0.0] * 10,
                "option_type": ["call"] * 10,
            }
        )
        assert _max_spread_pct(chain, self._SPOT) == config.MAX_SPREAD_PCT


# ── TestWingWidthPct ─────────────────────────────────────────────────────────


class TestWingWidthPct:
    """Tests for _wing_width_pct(chain, spot)."""

    def _chain(self, strikes: list[float]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "strike": strikes,
                "option_type": ["call"] * len(strikes),
            }
        )

    def test_returns_min_spacing_over_spot(self) -> None:
        chain = self._chain([97.5, 100.0, 102.5, 105.0])
        result = _wing_width_pct(chain, spot=100.0)
        assert result == pytest.approx(2.5 / 100.0)

    def test_mixed_spacing_picks_minimum(self) -> None:
        # Spacings: 5, 2.5, 2.5, 10 — minimum is 2.5
        chain = self._chain([90.0, 95.0, 97.5, 100.0, 110.0])
        result = _wing_width_pct(chain, spot=100.0)
        assert result == pytest.approx(2.5 / 100.0)

    def test_clamps_floor(self) -> None:
        # spacing=0.1, 0.1/100=0.001 < floor 0.005
        chain = self._chain([99.9, 100.0, 100.1])
        result = _wing_width_pct(chain, spot=100.0)
        assert result == pytest.approx(0.005)

    def test_clamps_ceiling(self) -> None:
        # spacing=10, 10/100=0.10 > ceiling 0.05
        chain = self._chain([90.0, 100.0, 110.0])
        result = _wing_width_pct(chain, spot=100.0)
        assert result == pytest.approx(0.05)

    def test_fallback_empty_chain(self) -> None:
        chain = pd.DataFrame({"strike": [], "option_type": []})
        assert (
            _wing_width_pct(chain, spot=100.0)
            == config.BACKSPREAD_MIN_WING_WIDTH_PCT
        )

    def test_fallback_single_strike(self) -> None:
        chain = self._chain([100.0])
        assert (
            _wing_width_pct(chain, spot=100.0)
            == config.BACKSPREAD_MIN_WING_WIDTH_PCT
        )


# ── TestGexLargeAbs ──────────────────────────────────────────────────────────


class TestGexLargeAbs:
    """Tests for _gex_large_abs(ticker)."""

    def test_half_pct_of_market_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "event_vol_analysis.calibration.yf.Ticker",
            lambda t: _MockTicker({"marketCap": 2e12}),
        )
        assert _gex_large_abs("AAPL") == pytest.approx(2e12 * 0.005)

    def test_fallback_missing_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "event_vol_analysis.calibration.yf.Ticker",
            lambda t: _MockTicker({}),
        )
        assert _gex_large_abs("AAPL") == config.GEX_LARGE_ABS

    def test_fallback_zero_market_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "event_vol_analysis.calibration.yf.Ticker",
            lambda t: _MockTicker({"marketCap": 0}),
        )
        assert _gex_large_abs("AAPL") == config.GEX_LARGE_ABS

    def test_fallback_on_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _bad(t: str) -> None:
            raise RuntimeError("timeout")

        monkeypatch.setattr(
            "event_vol_analysis.calibration.yf.Ticker", _bad
        )
        assert _gex_large_abs("AAPL") == config.GEX_LARGE_ABS


# ── TestCalibrateTickerParams ────────────────────────────────────────────────


class TestCalibrateTickerParams:
    """Integration tests for calibrate_ticker_params()."""

    _SPOT = 175.0
    _REQUIRED_KEYS = {
        "min_oi",
        "max_spread_pct",
        "backspread_min_wing_width_pct",
        "gex_large_abs",
    }

    @pytest.fixture()
    def chain_and_mock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> pd.DataFrame:
        monkeypatch.setattr(
            "event_vol_analysis.calibration.yf.Ticker",
            lambda t: _MockTicker({"marketCap": 1e12}),
        )
        return _make_raw_chain(spot=self._SPOT)

    def test_returns_all_required_keys(
        self, chain_and_mock: pd.DataFrame
    ) -> None:
        result = calibrate_ticker_params("TEST", chain_and_mock, self._SPOT)
        assert set(result.keys()) == self._REQUIRED_KEYS

    def test_min_oi_in_valid_range(
        self, chain_and_mock: pd.DataFrame
    ) -> None:
        result = calibrate_ticker_params("TEST", chain_and_mock, self._SPOT)
        assert 10 <= result["min_oi"] <= 200

    def test_max_spread_pct_in_valid_range(
        self, chain_and_mock: pd.DataFrame
    ) -> None:
        result = calibrate_ticker_params("TEST", chain_and_mock, self._SPOT)
        assert 0.03 <= result["max_spread_pct"] <= 0.20

    def test_wing_width_pct_in_valid_range(
        self, chain_and_mock: pd.DataFrame
    ) -> None:
        result = calibrate_ticker_params("TEST", chain_and_mock, self._SPOT)
        assert 0.005 <= result["backspread_min_wing_width_pct"] <= 0.05

    def test_gex_large_abs_matches_market_cap(
        self, chain_and_mock: pd.DataFrame
    ) -> None:
        result = calibrate_ticker_params("TEST", chain_and_mock, self._SPOT)
        assert result["gex_large_abs"] == pytest.approx(1e12 * 0.005)

    def test_min_oi_is_int(self, chain_and_mock: pd.DataFrame) -> None:
        result = calibrate_ticker_params("TEST", chain_and_mock, self._SPOT)
        assert isinstance(result["min_oi"], int)

    def test_all_fallback_on_empty_chain(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "event_vol_analysis.calibration.yf.Ticker",
            lambda t: _MockTicker({}),
        )
        empty = pd.DataFrame(
            {
                "strike": [],
                "bid": [],
                "ask": [],
                "openInterest": [],
                "option_type": [],
            }
        )
        result = calibrate_ticker_params("TEST", empty, self._SPOT)
        assert result["min_oi"] == config.MIN_OI
        assert result["max_spread_pct"] == config.MAX_SPREAD_PCT
        assert (
            result["backspread_min_wing_width_pct"]
            == config.BACKSPREAD_MIN_WING_WIDTH_PCT
        )
        assert result["gex_large_abs"] == config.GEX_LARGE_ABS


# ── TestCalibrateIvScenarios ────────────────────────────────────────────────


@pytest.mark.usefixtures("restore_iv_scenarios")
class TestCalibrateIvScenarios:
    """Tests for calibrate_iv_scenarios().

    The fixture restore_iv_scenarios saves/restores config.IV_SCENARIOS
    around every test so mutations don't bleed between tests.
    """

    def test_evr_zero_no_event_component(self) -> None:
        calibrate_iv_scenarios(0.50, 0.30, 0.0)
        assert config.IV_SCENARIOS["hard_crush"]["front"] == pytest.approx(
            0.0, abs=1e-4
        )
        assert config.IV_SCENARIOS["expansion"]["front"] == pytest.approx(
            0.13, abs=1e-4
        )

    def test_evr_half_formula(self) -> None:
        calibrate_iv_scenarios(0.50, 0.30, 0.5)
        expected_front = math.sqrt(0.5) - 1.0  # ≈ -0.2929
        assert config.IV_SCENARIOS["hard_crush"]["front"] == pytest.approx(
            expected_front, abs=1e-4
        )
        assert config.IV_SCENARIOS["hard_crush"]["back"] == pytest.approx(
            -0.06, abs=1e-4
        )
        assert config.IV_SCENARIOS["expansion"]["front"] == pytest.approx(
            0.09, abs=1e-4
        )
        assert config.IV_SCENARIOS["expansion"]["back"] == pytest.approx(
            0.045, abs=1e-4
        )

    def test_evr_one_full_event(self) -> None:
        calibrate_iv_scenarios(0.50, 0.30, 1.0)
        assert config.IV_SCENARIOS["hard_crush"]["front"] == pytest.approx(
            -1.0, abs=1e-4
        )
        assert config.IV_SCENARIOS["hard_crush"]["back"] == pytest.approx(
            -0.12, abs=1e-4
        )
        assert config.IV_SCENARIOS["expansion"]["front"] == pytest.approx(
            0.05, abs=1e-4
        )
        assert config.IV_SCENARIOS["expansion"]["back"] == pytest.approx(
            0.03, abs=1e-4
        )

    def test_hard_crush_front_always_nonpositive(self) -> None:
        for evr in [0.0, 0.3, 0.6, 1.0]:
            calibrate_iv_scenarios(0.50, 0.30, evr)
            assert config.IV_SCENARIOS["hard_crush"]["front"] <= 0.0

    def test_expansion_front_always_positive(self) -> None:
        for evr in [0.0, 0.5, 1.0]:
            calibrate_iv_scenarios(0.50, 0.30, evr)
            assert config.IV_SCENARIOS["expansion"]["front"] > 0.0

    def test_evr_clamped_below(self) -> None:
        calibrate_iv_scenarios(0.50, 0.30, -0.5)
        # treated as evr=0
        assert config.IV_SCENARIOS["hard_crush"]["front"] == pytest.approx(
            0.0, abs=1e-4
        )
        assert config.IV_SCENARIOS["expansion"]["front"] == pytest.approx(
            0.13, abs=1e-4
        )

    def test_evr_clamped_above(self) -> None:
        calibrate_iv_scenarios(0.50, 0.30, 1.5)
        # treated as evr=1
        assert config.IV_SCENARIOS["hard_crush"]["front"] == pytest.approx(
            -1.0, abs=1e-4
        )
        assert config.IV_SCENARIOS["expansion"]["front"] == pytest.approx(
            0.05, abs=1e-4
        )

    def test_base_crush_unchanged(self) -> None:
        original_base = copy.deepcopy(config.IV_SCENARIOS["base_crush"])
        calibrate_iv_scenarios(0.50, 0.30, 0.7)
        assert config.IV_SCENARIOS["base_crush"] == original_base

    def test_mutates_hard_crush_in_config(self) -> None:
        calibrate_iv_scenarios(0.50, 0.30, 0.5)
        # hard_crush front must differ from the default -0.35
        assert config.IV_SCENARIOS["hard_crush"]["front"] != -0.35

    def test_mutation_visible_via_same_reference(self) -> None:
        from event_vol_analysis.config import IV_SCENARIOS  # same object

        calibrate_iv_scenarios(0.50, 0.30, 0.5)
        expected = math.sqrt(0.5) - 1.0
        assert IV_SCENARIOS["hard_crush"]["front"] == pytest.approx(
            expected, abs=1e-4
        )


# ── TestDivYieldPropagation ──────────────────────────────────────────────────


def _make_minimal_chain(
    spot: float = 100.0,
    expiry: str = "2026-04-17",
    iv: float = 0.40,
) -> pd.DataFrame:
    """Minimal chain for skew/gex/payoff propagation tests.

    Strikes span ±25% of spot in steps of 5.  Includes ``mid`` and
    ``spread`` columns required by ``payoff._build_lookup``.
    """
    step = 5.0
    strikes = [spot + i * step for i in range(-5, 6)]
    rows = []
    for s in strikes:
        mid = 2.0
        spread = 0.20
        for ot in ("call", "put"):
            rows.append(
                {
                    "strike": s,
                    "bid": mid - spread / 2,
                    "ask": mid + spread / 2,
                    "mid": mid,
                    "spread": spread,
                    "impliedVolatility": iv,
                    "openInterest": 500,
                    "option_type": ot,
                    "expiry": pd.Timestamp(expiry),
                }
            )
    return pd.DataFrame(rows)


class TestDivYieldPropagation:
    """Verify div_yield kwarg is forwarded to BSM, not silently dropped."""

    _SPOT = 100.0
    _T = 30 / 365.0

    def test_skew_metrics_uses_div_yield(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import event_vol_analysis.analytics.skew as skew_mod
        from event_vol_analysis.analytics.bsm import delta as real_delta

        recorded_q: list[float] = []

        def _recording_delta(S, K, t, r, q, sigma, option_type):
            recorded_q.append(q)
            return real_delta(S, K, t, r, q, sigma, option_type)

        monkeypatch.setattr(skew_mod, "option_delta", _recording_delta)

        from event_vol_analysis.analytics.skew import skew_metrics

        chain = _make_minimal_chain(self._SPOT)
        skew_metrics(chain, self._SPOT, self._T, div_yield=0.07)
        assert recorded_q, "option_delta was never called"
        assert all(q == pytest.approx(0.07) for q in recorded_q), (
            "div_yield not forwarded to option_delta"
        )

    def test_gex_summary_uses_div_yield(self) -> None:
        from event_vol_analysis.analytics.gamma import gex_summary

        chain = _make_minimal_chain(self._SPOT)
        r0 = gex_summary(chain, self._SPOT, self._T, div_yield=0.0)
        r5 = gex_summary(chain, self._SPOT, self._T, div_yield=0.05)
        assert (
            r0["net_gex"] != r5["net_gex"]
            or r0["abs_gex"] != r5["abs_gex"]
        ), "gex_summary did not propagate div_yield to BSM gamma"

    def test_strategy_pnl_vec_uses_div_yield(self) -> None:
        from event_vol_analysis.strategies.payoff import strategy_pnl_vec
        from event_vol_analysis.strategies.structures import (
            OptionLeg,
            Strategy,
        )

        chain = _make_minimal_chain(self._SPOT)
        expiry = dt.date(2026, 4, 17)
        strategy = Strategy(
            name="test_call",
            legs=(
                OptionLeg(
                    option_type="call",
                    strike=self._SPOT,
                    qty=1,
                    side="buy",
                    expiry=pd.Timestamp(expiry),
                ),
            ),
        )
        rng = np.random.default_rng(42)
        moves = rng.normal(0.0, 0.05, size=1000)
        kwargs = dict(
            strategy=strategy,
            chain=chain,
            spot=self._SPOT,
            moves=moves,
            front_expiry=expiry,
            back_expiry=expiry,
            event_date=dt.date(2026, 3, 19),
            front_iv=0.40,
            back_iv=0.35,
            slippage_pct=0.0,
            scenario="hard_crush",
        )
        pnl0 = strategy_pnl_vec(**kwargs, div_yield=0.0)
        pnl5 = strategy_pnl_vec(**kwargs, div_yield=0.05)
        assert not np.allclose(pnl0.mean(), pnl5.mean()), (
            "strategy_pnl_vec did not propagate div_yield to BSM pricing"
        )


# ── TestBackspreadWingWidthPct ───────────────────────────────────────────────


class TestBackspreadWingWidthPct:
    """Verify wing_width_pct controls strike selection in backspreads."""

    _SPOT = 195.0
    _EXPIRY = pd.Timestamp("2026-04-17")

    def _chain(self) -> pd.DataFrame:
        """Strikes spaced 2.5 apart, centred on 195."""
        strikes = [192.5, 195.0, 197.5, 200.0, 202.5, 205.0, 207.5, 210.0]
        rows = []
        for s in strikes:
            for ot in ("call", "put"):
                rows.append(
                    {
                        "strike": s,
                        "bid": 2.0,
                        "ask": 2.2,
                        "impliedVolatility": 0.45,
                        "openInterest": 500,
                        "option_type": ot,
                        "expiry": self._EXPIRY,
                    }
                )
        return pd.DataFrame(rows)

    def test_tight_wing_allows_adjacent_strike(self) -> None:
        from event_vol_analysis.strategies.backspreads import (
            build_call_backspread,
        )

        chain = self._chain()
        strategy = build_call_backspread(
            chain, self._SPOT, self._EXPIRY, wing_width_pct=0.005
        )
        assert strategy is not None
        long_leg = strategy.legs[1]
        # 0.5% of 195 = $0.975; adjacent strike at $2.5 qualifies
        assert long_leg.strike == pytest.approx(197.5)

    def test_wide_wing_skips_adjacent_strike(self) -> None:
        from event_vol_analysis.strategies.backspreads import (
            build_call_backspread,
        )

        chain = self._chain()
        strategy = build_call_backspread(
            chain, self._SPOT, self._EXPIRY, wing_width_pct=0.02
        )
        assert strategy is not None
        long_leg = strategy.legs[1]
        # 2% of 195 = $3.90; 197.5 is only $2.5 away → skipped
        assert long_leg.strike > 197.5

    def test_impossible_wing_returns_none(self) -> None:
        from event_vol_analysis.strategies.backspreads import (
            build_call_backspread,
        )

        chain = self._chain()
        strategy = build_call_backspread(
            chain, self._SPOT, self._EXPIRY, wing_width_pct=0.20
        )
        # 20% of 195 = $39; no strike that far OTM in the chain
        assert strategy is None

    def test_put_wing_mirrors_call_wing(self) -> None:
        from event_vol_analysis.strategies.backspreads import (
            build_put_backspread,
        )

        chain = self._chain()
        # 1% of 195 = $1.95; 192.5 is $2.5 below ATM → qualifies
        strategy = build_put_backspread(
            chain, self._SPOT, self._EXPIRY, wing_width_pct=0.01
        )
        assert strategy is not None
        long_leg = strategy.legs[1]
        # Put long strike must be below the short (ATM) strike
        assert long_leg.strike < self._SPOT
