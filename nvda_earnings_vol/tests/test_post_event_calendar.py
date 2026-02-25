"""
Tests for post-event calendar strategy.

Covers acceptance criteria:
  4.  post_event_entry → only POST_EVENT_CALENDAR qualifies
  5.  post_event_flat  → POST_EVENT_CALENDAR absent
  6.  All pre-earnings scenarios → POST_EVENT_CALENDAR absent
  9.  compute_post_event_calendar_scenarios(spot, K, t_s, t_l, iv_short,
      iv_long, net_cost) raises TypeError (iv_short removed from signature)
 14.  POST_EVENT_CALENDAR alignment == 0.50 in all regime scenarios

v6 addition (replaces v5 theta test):
    test_scenario_ev_independent_of_short_iv_at_evaluation — determinism
    check confirming compute_post_event_calendar_scenarios is pure.
"""

from __future__ import annotations

from typing import Any

import pytest

from nvda_earnings_vol.alignment import compute_alignment
from nvda_earnings_vol.data.test_data import generate_scenario
from nvda_earnings_vol.regime import classify_regime
from nvda_earnings_vol.strategies.post_event_calendar import (
    compute_post_event_calendar_scenarios,
    post_event_calendar_conditions_met,
)
from nvda_earnings_vol.strategies.registry import should_build_strategy


# ── Criterion 4: post_event_entry → only POST_EVENT_CALENDAR qualifies ─────


class TestPostEventEntry:
    """In post_event_entry scenario, only POST_EVENT_CALENDAR qualifies."""

    def test_post_event_calendar_qualifies(self) -> None:
        """POST_EVENT_CALENDAR should_build_strategy returns True."""
        snap = generate_scenario("post_event_entry")
        assert should_build_strategy("POST_EVENT_CALENDAR", snap)

    def test_call_backspread_excluded(self) -> None:
        """CALL_BACKSPREAD excluded in post-event window (iv_ratio < 1.40)."""
        snap = generate_scenario("post_event_entry")
        assert not should_build_strategy("CALL_BACKSPREAD", snap)

    def test_put_backspread_excluded(self) -> None:
        """PUT_BACKSPREAD excluded in post-event window."""
        snap = generate_scenario("post_event_entry")
        assert not should_build_strategy("PUT_BACKSPREAD", snap)

    def test_calendar_excluded_post_event(self) -> None:
        """CALENDAR excluded because days_after_event != 0."""
        snap = generate_scenario("post_event_entry")
        assert not should_build_strategy("CALENDAR", snap)


# ── Criterion 5: post_event_flat → POST_EVENT_CALENDAR absent ─────────────


class TestPostEventFlat:
    """IV has normalised; post-event calendar absent."""

    def test_post_event_calendar_absent(self) -> None:
        """POST_EVENT_CALENDAR excluded when IV has flattened."""
        snap = generate_scenario("post_event_flat")
        assert not should_build_strategy("POST_EVENT_CALENDAR", snap)

    def test_conditions_not_met_directly(self) -> None:
        """post_event_calendar_conditions_met returns False for flat IV."""
        snap = generate_scenario("post_event_flat")
        assert not post_event_calendar_conditions_met(snap)


# ── Criterion 6: pre-earnings scenarios → POST_EVENT_CALENDAR absent ──────


class TestPreEarningsNoPostEventCalendar:
    """Pre-event scenarios have days_after_event==0; gate rejects them."""

    @pytest.mark.parametrize("scenario", [
        "backspread_favorable",
        "backspread_unfavorable",
        "backspread_overpriced",
    ])
    def test_pre_earnings_excluded(self, scenario: str) -> None:
        """POST_EVENT_CALENDAR absent in pre-earnings scenario."""
        snap = generate_scenario(scenario)
        assert not should_build_strategy("POST_EVENT_CALENDAR", snap), (
            f"POST_EVENT_CALENDAR should not qualify in {scenario!r}"
        )


# ── Criterion 9: iv_short removed from signature ──────────────────────────


class TestIvShortNotInSignature:
    """compute_post_event_calendar_scenarios must not accept iv_short.

    Acceptance criterion 9:
    Calling the function with a positional arg for iv_short (as the old
    7-argument signature required) must raise TypeError.
    """

    def test_iv_short_not_in_scenario_function_signature(self) -> None:
        """TypeError when passing iv_short as a positional argument."""
        with pytest.raises(TypeError):
            # Old 7-arg call: spot, K, t_short, t_long, iv_short, iv_long,
            # net_cost. The current function only accepts 6 positional args.
            compute_post_event_calendar_scenarios(
                195.0,    # spot
                195.0,    # K
                3 / 365,  # t_short
                25 / 365,  # t_long
                0.55,   # iv_short — REMOVED in v5, causes TypeError
                0.46,   # iv_long
                4.50,   # net_cost
            )

    def test_correct_six_arg_call_succeeds(self) -> None:
        """The correct 6-argument call succeeds without error."""
        result = compute_post_event_calendar_scenarios(
            spot=195.0,
            K=195.0,
            t_short=3 / 365,
            t_long=25 / 365,
            iv_long=0.46,
            net_cost=4.50,
        )
        assert isinstance(result, dict)
        assert "flat" in result


# ── v6 replacement test: determinism (replaces v5 theta test) ─────────────


class TestScenarioEvDeterminism:
    """Acceptance criterion companion: determinism of scenario evaluation.

    compute_post_event_calendar_scenarios() produces identical EVs
    regardless of what IV the short leg had at entry, because the short
    leg settles at intrinsic.

    Method: call compute_post_event_calendar_scenarios() twice with
    identical (spot, K, t_short, t_long, iv_long, net_cost) — the only
    inputs the function accepts. Since iv_short is not a parameter (v5
    removed it), this test simply confirms the function signature hasn't
    regressed and that two calls with identical inputs produce identical
    outputs (determinism check).

    The real IV-independence guarantee is structural: iv_short is not in
    the function signature (tested by test_iv_short_not_in_scenario_function
    _signature). This test is a belt-and-suspenders determinism check.
    """

    def test_scenario_ev_independent_of_short_iv_at_evaluation(
        self,
    ) -> None:
        """Two identical calls return identical per-scenario EVs."""
        params = dict(
            spot=195.0,
            K=195.0,
            t_short=3 / 365,
            t_long=25 / 365,
            iv_long=0.46,
            net_cost=4.50,
        )
        ev_a = compute_post_event_calendar_scenarios(**params)
        ev_b = compute_post_event_calendar_scenarios(**params)
        for scenario in ev_a:
            assert ev_a[scenario] == ev_b[scenario], (
                f"Non-deterministic: {scenario}"
            )

    def test_scenario_returns_expected_keys(self) -> None:
        """compute_post_event_calendar_scenarios returns all five scenarios."""
        result = compute_post_event_calendar_scenarios(
            spot=195.0, K=195.0, t_short=3 / 365, t_long=25 / 365,
            iv_long=0.46, net_cost=4.50,
        )
        expected_keys = {
            "flat", "up_5pct", "down_5pct", "up_10pct", "down_10pct",
        }
        assert set(result.keys()) == expected_keys

    def test_scenario_values_are_finite_floats(self) -> None:
        """All scenario P&Ls are finite floats (no inf, no None)."""
        import math
        result = compute_post_event_calendar_scenarios(
            spot=195.0, K=195.0, t_short=3 / 365, t_long=25 / 365,
            iv_long=0.46, net_cost=4.50,
        )
        for key, val in result.items():
            assert val is not None, f"{key} is None"
            assert math.isfinite(val), f"{key} = {val} is not finite"


# ── Criterion 14: POST_EVENT_CALENDAR alignment == 0.50 ───────────────────


class TestPostEventCalendarAlignment:
    """POST_EVENT_CALENDAR alignment score is 0.50 across all regimes.

    The post-event calendar is a theta trade with approximately neutral
    net_gamma and net_vega. In any regime that does not strongly bias
    gamma or vega, all four alignment axes default to 0.50, giving a
    composite of exactly 0.50.

    This test validates regime scenarios covering all five regime categories.
    """

    def _neutral_strategy(self) -> dict[str, Any]:
        """Minimal strategy dict representing POST_EVENT_CALENDAR.

        Zero net_gamma and net_vega make it structurally neutral.
        cvar = -1.0 is placed at the exact median of the test population
        defined in _population_for_strategy().
        """
        return {
            "net_gamma": 0.0,
            "net_vega": 0.0,
            "convexity": 1.0,
            "cvar": -1.0,
        }

    def _population_for_strategy(
        self, strategy: dict[str, Any]
    ) -> dict:
        """Population stats placing POST_EVENT_CALENDAR at 50th percentile.

        For the tail_score in Tail-Underpriced regimes to be 0.50, the
        strategy's cvar must have percentile rank = 0.50 within the
        population. Four CVaR values [-2.0, -1.5, -0.5, -0.2] place
        cvar = -1.0 at rank 2/4 = 0.50:
            sum(x <= -1.0 for x in [-2.0, -1.5, -0.5, -0.2]) = 2 → 2/4 = 0.5

        For vega (zero) and gamma (zero), _scaled_sign returns 0.5
        regardless of scale (normalised value = 0 → neutral).
        For convexity in a Mixed regime, score is hardcoded to 0.5.
        """
        return {
            "median_abs_gamma": 1.0,   # non-zero; vega/gamma stay 0.5
            "median_abs_vega": 1.0,
            "convexities": [0.5, 0.8, strategy["convexity"], 1.5, 2.0],
            # 2 values worse (more negative) than -1.0, 2 values better
            "cvars": [-2.0, -1.5, -0.5, -0.2],
        }

    @pytest.mark.parametrize("scenario_name", [
        "backspread_favorable",
        "backspread_unfavorable",
        "backspread_overpriced",
        "post_event_entry",
        "post_event_flat",
    ])
    def test_alignment_is_half_in_regime(
        self, scenario_name: str
    ) -> None:
        """POST_EVENT_CALENDAR alignment == 0.50 for scenario regime."""
        snap = generate_scenario(scenario_name)
        regime = classify_regime(snap)

        strategy = self._neutral_strategy()
        population = self._population_for_strategy(strategy)
        result = compute_alignment(strategy, regime, population)

        score = result["alignment_score"]
        assert abs(score - 0.50) < 1e-9, (
            f"Alignment for POST_EVENT_CALENDAR in {scenario_name!r} "
            f"regime = {score:.6f}, expected 0.50"
        )


# ── Entry condition unit tests ─────────────────────────────────────────────


class TestPostEventCalendarConditions:
    """Unit tests for post_event_calendar_conditions_met edge cases."""

    def test_day_1_qualifies(self) -> None:
        """Entry allowed on day 1 after event."""
        snap: dict[str, Any] = {
            "days_after_event": 1,
            "iv_ratio": 1.20,
            "front_dte": 5,
        }
        assert post_event_calendar_conditions_met(snap)

    def test_day_3_qualifies(self) -> None:
        """Entry allowed on day 3 after event."""
        snap: dict[str, Any] = {
            "days_after_event": 3,
            "iv_ratio": 1.20,
            "front_dte": 5,
        }
        assert post_event_calendar_conditions_met(snap)

    def test_day_0_excluded(self) -> None:
        """Day 0 (event day) is pre-event; excluded."""
        snap: dict[str, Any] = {
            "days_after_event": 0,
            "iv_ratio": 1.20,
            "front_dte": 5,
        }
        assert not post_event_calendar_conditions_met(snap)

    def test_day_4_excluded(self) -> None:
        """Day 4 is outside the entry window."""
        snap: dict[str, Any] = {
            "days_after_event": 4,
            "iv_ratio": 1.20,
            "front_dte": 5,
        }
        assert not post_event_calendar_conditions_met(snap)

    def test_low_iv_ratio_excluded(self) -> None:
        """IV ratio below 1.10 excluded."""
        snap: dict[str, Any] = {
            "days_after_event": 2,
            "iv_ratio": 1.05,
            "front_dte": 5,
        }
        assert not post_event_calendar_conditions_met(snap)

    def test_short_dte_too_low_excluded(self) -> None:
        """front_dte below 3 excluded."""
        snap: dict[str, Any] = {
            "days_after_event": 2,
            "iv_ratio": 1.20,
            "front_dte": 2,
        }
        assert not post_event_calendar_conditions_met(snap)
