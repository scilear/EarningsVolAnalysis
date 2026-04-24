"""Acceptance-criteria tests for multi-ticker profile scenarios.

Validates that the strategy gate logic and calibration boundary behaviour
are correct for substantially different market structures: high-dividend
mature names, mega-cap liquid names, and small-cap sparse chains.

Mirrors the structure of test_backspreads.py (snapshot-level tests) and
adds full-pipeline smoke tests for all six new TEST_SCENARIOS.
"""

from __future__ import annotations

import pandas as pd
import pytest

from event_vol_analysis.calibration import (
    _max_spread_pct,
    _wing_width_pct,
)
from event_vol_analysis.config import (
    BACKSPREAD_MAX_IMPLIED_OVER_P75,
    BACKSPREAD_MIN_EVENT_VAR_RATIO,
    BACKSPREAD_MIN_IV_RATIO,
)
from event_vol_analysis.data.test_data import (
    generate_scenario,
    generate_test_data_set,
)
from event_vol_analysis.strategies.backspreads import backspread_conditions_met
from event_vol_analysis.strategies.registry import should_build_strategy

# ── Helper ─────────────────────────────────────────────────────────────────


_REQUIRED_KEYS = {
    "spot",
    "event_date",
    "front_expiry",
    "back_expiry",
    "front_chain",
    "back_chain",
    "history",
    "earnings_dates",
    "scenario",
}


# ── TestHighDividendProfile ────────────────────────────────────────────────


class TestHighDividendProfile:
    """High-dividend mature name: iv_ratio 1.18, EVR 0.28.
    Both backspread gates fail; strategy building must be blocked."""

    def test_call_backspread_blocked(self) -> None:
        snap = generate_scenario("high_dividend_snap")
        assert not should_build_strategy(
            "CALL_BACKSPREAD", snap
        ), "CALL_BACKSPREAD must be blocked for high-dividend profile"

    def test_put_backspread_blocked(self) -> None:
        snap = generate_scenario("high_dividend_snap")
        assert not should_build_strategy(
            "PUT_BACKSPREAD", snap
        ), "PUT_BACKSPREAD must be blocked for high-dividend profile"

    def test_iv_ratio_below_threshold(self) -> None:
        snap = generate_scenario("high_dividend_snap")
        assert snap["iv_ratio"] < BACKSPREAD_MIN_IV_RATIO, (
            f"high_dividend iv_ratio {snap['iv_ratio']} "
            f"should be < {BACKSPREAD_MIN_IV_RATIO}"
        )

    def test_evr_below_threshold(self) -> None:
        snap = generate_scenario("high_dividend_snap")
        assert snap["event_variance_ratio"] < BACKSPREAD_MIN_EVENT_VAR_RATIO, (
            f"high_dividend EVR {snap['event_variance_ratio']} "
            f"should be < {BACKSPREAD_MIN_EVENT_VAR_RATIO}"
        )


# ── TestStrongBackspreadProfile ───────────────────────────────────────────


class TestStrongBackspreadProfile:
    """strong_backspread_snap: all five gates pass."""

    def test_call_backspread_qualifies(self) -> None:
        snap = generate_scenario("strong_backspread_snap")
        assert should_build_strategy(
            "CALL_BACKSPREAD", snap
        ), "CALL_BACKSPREAD must qualify for strong_backspread_snap"

    def test_put_backspread_qualifies(self) -> None:
        snap = generate_scenario("strong_backspread_snap")
        assert should_build_strategy(
            "PUT_BACKSPREAD", snap
        ), "PUT_BACKSPREAD must qualify for strong_backspread_snap"

    def test_all_five_gates_pass(self) -> None:
        snap = generate_scenario("strong_backspread_snap")
        assert backspread_conditions_met(
            snap
        ), "All five backspread gates must pass for strong_backspread_snap"


# ── TestSmallCapBoundaryProfile ───────────────────────────────────────────


class TestSmallCapBoundaryProfile:
    """small_cap_snap: iv_ratio 1.38, just below 1.40 threshold.
    Gate fails on iv_ratio alone; all other conditions would pass."""

    def test_blocked_on_iv_ratio_alone(self) -> None:
        snap = generate_scenario("small_cap_snap")
        assert not backspread_conditions_met(
            snap
        ), "backspread_conditions_met must return False for small_cap_snap"

    def test_iv_ratio_is_below_threshold(self) -> None:
        snap = generate_scenario("small_cap_snap")
        assert snap["iv_ratio"] < BACKSPREAD_MIN_IV_RATIO, (
            f"small_cap iv_ratio {snap['iv_ratio']} "
            f"should be < {BACKSPREAD_MIN_IV_RATIO}"
        )

    def test_evr_would_otherwise_pass(self) -> None:
        snap = generate_scenario("small_cap_snap")
        assert snap["event_variance_ratio"] >= (
            BACKSPREAD_MIN_EVENT_VAR_RATIO
        ), "EVR should pass if iv_ratio were sufficient"

    def test_pricing_gate_would_pass(self) -> None:
        snap = generate_scenario("small_cap_snap")
        threshold = snap["historical_p75"] * BACKSPREAD_MAX_IMPLIED_OVER_P75
        assert (
            snap["implied_move"] <= threshold
        ), "Pricing gate should pass if iv_ratio were sufficient"


# ── TestFullPipelineNewScenarios ──────────────────────────────────────────


class TestFullPipelineNewScenarios:
    """generate_test_data_set must complete without exception and return
    a dict with all required keys for each new scenario."""

    @pytest.mark.parametrize(
        "scenario",
        [
            "high_dividend",
            "mega_cap_tight",
            "small_cap_wide_spread",
            "high_iv_ratio_entry",
            "distressed_deep_skew",
            "minimal_history",
        ],
    )
    def test_pipeline_returns_required_keys(self, scenario: str) -> None:
        data = generate_test_data_set(scenario=scenario)
        missing = _REQUIRED_KEYS - set(data.keys())
        assert not missing, f"Scenario '{scenario}' missing keys: {missing}"

    def test_high_dividend_chain_is_dataframe(self) -> None:
        data = generate_test_data_set(scenario="high_dividend")
        assert isinstance(data["front_chain"], pd.DataFrame)
        assert not data["front_chain"].empty

    def test_mega_cap_chain_is_dataframe(self) -> None:
        data = generate_test_data_set(scenario="mega_cap_tight")
        assert isinstance(data["front_chain"], pd.DataFrame)
        assert not data["front_chain"].empty

    def test_minimal_history_fewer_earnings_dates(self) -> None:
        """minimal_history must produce exactly 3 earnings dates."""
        data = generate_test_data_set(scenario="minimal_history")
        assert len(data["earnings_dates"]) == 3, (
            f"Expected 3 earnings dates, " f"got {len(data['earnings_dates'])}"
        )

    def test_small_cap_sparse_chain(self) -> None:
        """small_cap_wide_spread chain must have 13 strikes × 2 types."""
        data = generate_test_data_set(scenario="small_cap_wide_spread")
        n_strikes = data["front_chain"]["strike"].nunique()
        assert n_strikes == 13, f"Expected 13 strikes, got {n_strikes}"


# ── TestCalibrationBoundaryBehavior ───────────────────────────────────────


class TestCalibrationBoundaryBehavior:
    """Calibration parameters must stay within their clamped bounds even
    for extreme chain profiles."""

    def _get_front_chain(self, scenario: str) -> tuple[pd.DataFrame, float]:
        data = generate_test_data_set(scenario=scenario)
        return data["front_chain"], data["spot"]

    def test_mega_cap_spread_pct_within_bounds(self) -> None:
        """Tight-spread chain → _max_spread_pct must stay in [0.03, 0.20]."""
        chain, spot = self._get_front_chain("mega_cap_tight")
        val = _max_spread_pct(chain, spot)
        assert 0.03 <= val <= 0.20, f"mega_cap spread_pct {val} outside [0.03, 0.20]"

    def test_small_cap_spread_pct_within_bounds(self) -> None:
        """Wide-spread chain → _max_spread_pct must stay in [0.03, 0.20]."""
        chain, spot = self._get_front_chain("small_cap_wide_spread")
        val = _max_spread_pct(chain, spot)
        assert 0.03 <= val <= 0.20, f"small_cap spread_pct {val} outside [0.03, 0.20]"

    @pytest.mark.parametrize(
        "scenario",
        [
            "high_dividend",
            "mega_cap_tight",
            "small_cap_wide_spread",
            "high_iv_ratio_entry",
            "distressed_deep_skew",
            "minimal_history",
        ],
    )
    def test_wing_width_reasonable_for_any_chain(self, scenario: str) -> None:
        chain, spot = self._get_front_chain(scenario)
        val = _wing_width_pct(chain, spot)
        assert 0.005 <= val <= 0.05, (
            f"wing_width_pct {val} outside [0.005, 0.05] " f"for scenario '{scenario}'"
        )
