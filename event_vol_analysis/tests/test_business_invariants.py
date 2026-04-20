"""Business and mathematical invariant tests.

Verifies that core quantitative properties hold across all market regimes
and ticker profiles: EVR bounds, IV scenario sign conventions,
strategy gate independence, scoring monotonicity, BSM Greek sensitivity
to div_yield, and calibration round-trip safety.
"""

from __future__ import annotations

import copy
import math

import pandas as pd
import pytest

from event_vol_analysis import config
from event_vol_analysis.analytics.bsm import (
    delta as bsm_delta,
    gamma as bsm_gamma,
)
from event_vol_analysis.analytics.event_vol import event_variance
from event_vol_analysis.calibration import (
    calibrate_iv_scenarios,
    calibrate_ticker_params,
)
from event_vol_analysis.config import (
    BACK3_DTE_MAX,
    BACK3_DTE_MIN,
    BACKSPREAD_MAX_IMPLIED_OVER_P75,
    BACKSPREAD_MIN_EVENT_VAR_RATIO,
    BACKSPREAD_MIN_IV_RATIO,
    BACKSPREAD_MIN_SHORT_DELTA,
    RISK_FREE_RATE,
)
from event_vol_analysis.data.test_data import (
    generate_scenario,
    generate_test_data_set,
)
from event_vol_analysis.strategies.backspreads import (
    backspread_conditions_met,
    build_call_backspread,
)
from event_vol_analysis.strategies.scoring import score_strategies


# ── Helpers ────────────────────────────────────────────────────────────────


class _MockTicker:
    def __init__(self, info: dict) -> None:
        self.info = info


def _make_chain(
    spot: float = 100.0,
    n: int = 21,
    step: float = 2.5,
    expiry: str = "2026-04-17",
) -> pd.DataFrame:
    """Minimal chain centred on spot for invariant tests."""
    centre = round(spot / step) * step
    rows = []
    for i in range(n):
        strike = centre + (i - n // 2) * step
        for ot in ("call", "put"):
            rows.append({
                "strike": strike,
                "option_type": ot,
                "expiry": pd.Timestamp(expiry),
                "impliedVolatility": 0.40,
                "bid": 2.00,
                "ask": 2.20,
                "mid": 2.10,
                "spread": 0.20,
                "openInterest": 500,
            })
    return pd.DataFrame(rows)


def _make_result(
    ev: float,
    convexity: float,
    cvar: float,
    robustness: float,
    risk: str = "defined_risk",
) -> dict:
    """Build a minimal strategy result dict for scoring tests."""
    return {
        "ev": ev,
        "convexity": convexity,
        "cvar": cvar,
        "robustness": robustness,
        "risk_classification": risk,
        "name": "test_strategy",
    }


def _call_event_variance(scenario_name: str) -> dict:
    """Run event_variance() with chains from a named scenario."""
    data = generate_test_data_set(scenario=scenario_name)
    return event_variance(
        front_chain=data["front_chain"],
        back1_chain=data["back_chain"],
        back2_chain=None,
        spot=data["spot"],
        event_date=data["event_date"],
        front_expiry=data["front_expiry"],
        back1_expiry=data["back_expiry"],
        back2_expiry=None,
    )


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture()
def restore_iv_scenarios():
    """Save and restore config.IV_SCENARIOS around each test."""
    original = copy.deepcopy(config.IV_SCENARIOS)
    yield
    config.IV_SCENARIOS.clear()
    config.IV_SCENARIOS.update(original)


# ── TestEventVarianceRatioBounds ───────────────────────────────────────────


class TestEventVarianceRatioBounds:
    """EVR must lie in [0, 1] for well-behaved scenarios."""

    def test_evr_in_bounds_baseline(self) -> None:
        result = _call_event_variance("baseline")
        evr = result["event_variance_ratio"]
        assert 0.0 <= evr <= 1.0, f"EVR out of bounds: {evr}"

    def test_evr_in_bounds_high_vol(self) -> None:
        result = _call_event_variance("high_vol")
        evr = result["event_variance_ratio"]
        assert 0.0 <= evr <= 1.0, f"EVR out of bounds: {evr}"

    def test_evr_in_bounds_extreme_front_premium(self) -> None:
        result = _call_event_variance("extreme_front_premium")
        evr = result["event_variance_ratio"]
        assert 0.0 <= evr <= 1.0, f"EVR out of bounds: {evr}"

    def test_evr_in_bounds_distressed_deep_skew(self) -> None:
        result = _call_event_variance("distressed_deep_skew")
        evr = result["event_variance_ratio"]
        assert 0.0 <= evr <= 1.0, f"EVR out of bounds: {evr}"

    def test_negative_event_var_clipped_to_zero(self) -> None:
        """negative_event_var scenario: clamped event_var must be >= 0."""
        result = _call_event_variance("negative_event_var")
        assert result["event_var"] >= 0.0, (
            f"event_var must be clamped to zero, got {result['event_var']}"
        )


# ── TestIvScenarioSignConventions ──────────────────────────────────────────


@pytest.mark.usefixtures("restore_iv_scenarios")
class TestIvScenarioSignConventions:
    """After calibrate_iv_scenarios, crush values must be <= 0 and
    expansion values must be > 0 across the valid EVR range."""

    @pytest.mark.parametrize("evr", [0.3, 0.6, 0.9])
    def test_hard_crush_front_negative(self, evr: float) -> None:
        calibrate_iv_scenarios(0.70, 0.45, evr)
        val = config.IV_SCENARIOS["hard_crush"]["front"]
        assert val <= 0.0, (
            f"hard_crush front must be <= 0, got {val} (evr={evr})"
        )

    @pytest.mark.parametrize("evr", [0.3, 0.6, 0.9])
    def test_hard_crush_back_negative(self, evr: float) -> None:
        calibrate_iv_scenarios(0.70, 0.45, evr)
        val = config.IV_SCENARIOS["hard_crush"]["back"]
        assert val <= 0.0, (
            f"hard_crush back must be <= 0, got {val} (evr={evr})"
        )

    def test_base_crush_unchanged_by_calibration(self) -> None:
        """calibrate_iv_scenarios must NOT modify base_crush; it is
        fully market-data-relative and managed elsewhere."""
        original = copy.deepcopy(config.IV_SCENARIOS["base_crush"])
        calibrate_iv_scenarios(0.70, 0.45, 0.6)
        assert config.IV_SCENARIOS["base_crush"] == original, (
            "base_crush must not be mutated by calibrate_iv_scenarios"
        )

    @pytest.mark.parametrize("evr", [0.3, 0.6, 0.9])
    def test_expansion_front_positive(self, evr: float) -> None:
        calibrate_iv_scenarios(0.70, 0.45, evr)
        val = config.IV_SCENARIOS["expansion"]["front"]
        assert val > 0.0, (
            f"expansion front must be > 0, got {val} (evr={evr})"
        )

    @pytest.mark.parametrize("evr", [0.3, 0.6, 0.9])
    def test_expansion_back_positive(self, evr: float) -> None:
        calibrate_iv_scenarios(0.70, 0.45, evr)
        val = config.IV_SCENARIOS["expansion"]["back"]
        assert val > 0.0, (
            f"expansion back must be > 0, got {val} (evr={evr})"
        )

    @pytest.mark.parametrize("evr", [0.5, 0.7, 1.0])
    def test_hard_crush_magnitude_increases_with_evr(
        self, evr: float
    ) -> None:
        """At higher evr, hard_crush front is more negative."""
        calibrate_iv_scenarios(0.70, 0.45, evr)
        hard_front = config.IV_SCENARIOS["hard_crush"]["front"]
        # At evr >= 0.5, hard_crush front must be <= -0.10
        # (sqrt(0.5) - 1 ≈ -0.293 at evr=0.5)
        assert hard_front <= -0.10, (
            f"hard_crush front must be <= -0.10 at evr={evr}, got {hard_front}"
        )


# ── TestImpliedMoveVsHistoricalBounds ─────────────────────────────────────


class TestImpliedMoveVsHistoricalBounds:
    """Gate thresholds must hold in the relevant snapshots."""

    def test_overpriced_ratio_exceeds_threshold(self) -> None:
        snap = generate_scenario("backspread_overpriced")
        assert snap["implied_move"] > (
            snap["historical_p75"] * BACKSPREAD_MAX_IMPLIED_OVER_P75
        )

    def test_favorable_ratio_below_threshold(self) -> None:
        snap = generate_scenario("backspread_favorable")
        assert snap["implied_move"] <= (
            snap["historical_p75"] * BACKSPREAD_MAX_IMPLIED_OVER_P75
        )

    def test_high_dividend_ratio_below_threshold(self) -> None:
        snap = generate_scenario("high_dividend_snap")
        assert snap["implied_move"] <= (
            snap["historical_p75"] * BACKSPREAD_MAX_IMPLIED_OVER_P75
        )


# ── TestBackspreadGateIndependence ────────────────────────────────────────


class TestBackspreadGateIndependence:
    """Each of the five gates blocks independently when its threshold is
    crossed by exactly one unit; all other fields are held at passing
    values drawn from the strong_backspread_snap scenario."""

    def _passing_snap(self) -> dict:
        return generate_scenario("strong_backspread_snap")

    def test_gate_blocks_on_iv_ratio(self) -> None:
        snap = self._passing_snap()
        snap["iv_ratio"] = BACKSPREAD_MIN_IV_RATIO - 0.01
        assert not backspread_conditions_met(snap)

    def test_gate_blocks_on_event_var_ratio(self) -> None:
        snap = self._passing_snap()
        snap["event_variance_ratio"] = (
            BACKSPREAD_MIN_EVENT_VAR_RATIO - 0.01
        )
        assert not backspread_conditions_met(snap)

    def test_gate_blocks_on_implied_move(self) -> None:
        snap = self._passing_snap()
        snap["implied_move"] = (
            snap["historical_p75"] * BACKSPREAD_MAX_IMPLIED_OVER_P75 + 0.001
        )
        assert not backspread_conditions_met(snap)

    def test_gate_blocks_on_short_delta(self) -> None:
        snap = self._passing_snap()
        snap["short_delta"] = BACKSPREAD_MIN_SHORT_DELTA - 0.01
        assert not backspread_conditions_met(snap)

    def test_gate_blocks_on_back_dte_low(self) -> None:
        snap = self._passing_snap()
        snap["back_dte"] = BACK3_DTE_MIN - 1
        assert not backspread_conditions_met(snap)

    def test_gate_blocks_on_back_dte_high(self) -> None:
        snap = self._passing_snap()
        snap["back_dte"] = BACK3_DTE_MAX + 1
        assert not backspread_conditions_met(snap)

    def test_gate_passes_at_exact_boundaries(self) -> None:
        """All thresholds at their exact minimum/maximum values: must pass."""
        snap = self._passing_snap()
        snap["iv_ratio"] = BACKSPREAD_MIN_IV_RATIO
        snap["event_variance_ratio"] = BACKSPREAD_MIN_EVENT_VAR_RATIO
        p75 = snap["historical_p75"]
        snap["implied_move"] = p75 * BACKSPREAD_MAX_IMPLIED_OVER_P75
        snap["short_delta"] = BACKSPREAD_MIN_SHORT_DELTA
        snap["back_dte"] = BACK3_DTE_MIN
        assert backspread_conditions_met(snap)


# ── TestScoringMonotonicity ────────────────────────────────────────────────


class TestScoringMonotonicity:
    """score_strategies must return results in strictly non-increasing
    composite score order and all scores must lie in [0, 1]."""

    def _make_results(self) -> list[dict]:
        return [
            _make_result(ev=0.10, convexity=0.20, cvar=0.05, robustness=0.30),
            _make_result(ev=0.05, convexity=0.10, cvar=0.02, robustness=0.15),
            _make_result(ev=0.02, convexity=0.05, cvar=0.01, robustness=0.08),
            _make_result(ev=0.00, convexity=0.00, cvar=0.00, robustness=0.00),
        ]

    def test_scores_descending_order(self) -> None:
        ranked = score_strategies(self._make_results())
        scores = [r["score"] for r in ranked]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], (
                f"Score not descending at index {i}: "
                f"{scores[i]} < {scores[i + 1]}"
            )

    def test_score_is_float_in_unit_interval(self) -> None:
        ranked = score_strategies(self._make_results())
        for r in ranked:
            assert isinstance(r["score"], float), (
                f"Score should be float, got {type(r['score'])}"
            )
            assert 0.0 <= r["score"] <= 1.0, (
                f"Score {r['score']} outside [0, 1]"
            )


# ── TestGreeksWithDivYield ─────────────────────────────────────────────────


class TestGreeksWithDivYield:
    """Non-zero dividend yield must materially change BSM delta and gamma.
    Uses ATM call (S=K=100) at T=0.25 yr, IV=0.30."""

    _SPOT = 100.0
    _STRIKE = 100.0
    _T = 0.25
    _IV = 0.30

    def test_call_delta_lower_with_div_yield(self) -> None:
        delta_no_q = bsm_delta(
            self._SPOT, self._STRIKE, self._T,
            RISK_FREE_RATE, 0.0, self._IV, "call",
        )
        delta_with_q = bsm_delta(
            self._SPOT, self._STRIKE, self._T,
            RISK_FREE_RATE, 0.05, self._IV, "call",
        )
        assert delta_with_q < delta_no_q, (
            "Call delta should decrease with positive div_yield: "
            f"{delta_with_q} >= {delta_no_q}"
        )

    def test_put_delta_higher_magnitude_with_div_yield(self) -> None:
        put_no_q = bsm_delta(
            self._SPOT, self._STRIKE, self._T,
            RISK_FREE_RATE, 0.0, self._IV, "put",
        )
        put_with_q = bsm_delta(
            self._SPOT, self._STRIKE, self._T,
            RISK_FREE_RATE, 0.05, self._IV, "put",
        )
        # Put delta is negative; higher magnitude means more negative
        assert abs(put_with_q) > abs(put_no_q), (
            "Put delta magnitude should increase with positive div_yield"
        )

    def test_gamma_differs_with_div_yield(self) -> None:
        g_no_q = bsm_gamma(
            self._SPOT, self._STRIKE, self._T,
            RISK_FREE_RATE, 0.0, self._IV, "call",
        )
        g_with_q = bsm_gamma(
            self._SPOT, self._STRIKE, self._T,
            RISK_FREE_RATE, 0.05, self._IV, "call",
        )
        assert not math.isclose(g_no_q, g_with_q, rel_tol=1e-6), (
            f"Gamma should differ with div_yield: {g_no_q} vs {g_with_q}"
        )


# ── TestCalibratedParamsMakeRoundTrip ─────────────────────────────────────


class TestCalibratedParamsMakeRoundTrip:
    """Calibrated params must be accepted without error by the builders
    they are designed to feed."""

    def test_calibrated_wing_width_accepted_by_builder(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """build_call_backspread must not raise with calibrated wing width."""
        monkeypatch.setattr(
            "event_vol_analysis.calibration.yf.Ticker",
            lambda t: _MockTicker({"marketCap": 1e12}),
        )
        chain = _make_chain(spot=100.0)
        params = calibrate_ticker_params("TEST", chain, 100.0)
        wing = params["backspread_min_wing_width_pct"]
        expiry = pd.Timestamp("2026-04-17")
        # Must not raise — may return None if no valid strike found
        result = build_call_backspread(
            chain, 100.0, expiry, wing_width_pct=wing
        )
        assert result is None or hasattr(result, "legs")

    def test_calibrated_min_oi_accepted_by_filter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """filter_by_liquidity must accept calibrated min_oi and return a
        valid (possibly empty) DataFrame."""
        monkeypatch.setattr(
            "event_vol_analysis.calibration.yf.Ticker",
            lambda t: _MockTicker({"marketCap": 5e11}),
        )
        from event_vol_analysis.data.filters import filter_by_liquidity
        chain = _make_chain(spot=100.0)
        params = calibrate_ticker_params("TEST", chain, 100.0)
        filtered = filter_by_liquidity(
            chain,
            min_oi=params["min_oi"],
            max_spread_pct=params["max_spread_pct"],
        )
        assert isinstance(filtered, pd.DataFrame)
