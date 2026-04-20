"""Tests for scoring logic."""

import numpy as np
import pandas as pd

from event_vol_analysis.config import CONVEXITY_CAP
from event_vol_analysis.strategies.scoring import (
    _capital_normalized_ev,
    _is_undefined_risk,
    compute_metrics,
    score_strategies,
)
from event_vol_analysis.strategies.structures import OptionLeg, Strategy


def test_convexity_guard() -> None:
    pnls = np.array([0.0] * 100)
    strategy = Strategy(
        name="flat",
        legs=(
            OptionLeg(
                "call",
                100.0,
                1,
                "buy",
                pd.Timestamp("2030-01-01"),
            ),
        ),
    )
    metrics = compute_metrics(strategy, pnls, 0.05, 0.04, 100.0, 1.0)
    assert metrics["convexity"] > 0


def test_undefined_risk_detection() -> None:
    strategy = Strategy(
        name="short_call",
        legs=(
            OptionLeg(
                "call",
                100.0,
                1,
                "sell",
                pd.Timestamp("2030-01-01"),
            ),
        ),
    )
    pnls = np.array([1.0, -10.0, 2.0])
    metrics = compute_metrics(strategy, pnls, 0.05, 0.04, 100.0, 1.0)
    assert metrics["risk_classification"] == "undefined_risk"


def test_undefined_risk_calendar_and_condor() -> None:
    front_expiry = pd.Timestamp("2026-03-21")
    back_expiry = pd.Timestamp("2026-04-18")

    calendar = Strategy(
        name="calendar",
        legs=(
            OptionLeg("call", 800.0, 1, "sell", front_expiry),
            OptionLeg("call", 800.0, 1, "buy", back_expiry),
        ),
    )
    assert not _is_undefined_risk(calendar)

    naked = Strategy(
        name="naked_call",
        legs=(OptionLeg("call", 800.0, 1, "sell", front_expiry),),
    )
    assert _is_undefined_risk(naked)

    condor = Strategy(
        name="iron_condor",
        legs=(
            OptionLeg("call", 820.0, 1, "sell", front_expiry),
            OptionLeg("call", 840.0, 1, "buy", front_expiry),
            OptionLeg("put", 780.0, 1, "sell", front_expiry),
            OptionLeg("put", 760.0, 1, "buy", front_expiry),
        ),
    )
    assert not _is_undefined_risk(condor)

    butterfly = Strategy(
        name="symmetric_butterfly",
        legs=(
            OptionLeg("call", 780.0, 1, "buy", front_expiry),
            OptionLeg("call", 800.0, 1, "sell", front_expiry),
            OptionLeg("call", 800.0, 1, "sell", front_expiry),
            OptionLeg("call", 820.0, 1, "buy", front_expiry),
        ),
    )
    assert not _is_undefined_risk(butterfly)


def test_convexity_cap_on_near_zero_bottom() -> None:
    pnls = np.array([0.0] * 90 + [10.0] * 10)
    strategy = Strategy(
        name="convex",
        legs=(OptionLeg("call", 100.0, 1, "buy", pd.Timestamp("2030-01-01")),),
    )
    metrics = compute_metrics(strategy, pnls, 0.05, 0.04, 100.0, 1.0)
    assert metrics["convexity"] == CONVEXITY_CAP


def test_robustness_direction() -> None:
    strategy = Strategy(
        name="test",
        legs=(OptionLeg("call", 100.0, 1, "buy", pd.Timestamp("2030-01-01")),),
    )
    pnls = np.array([0.0, 1.0, -1.0])

    stable_evs = [100.0, 100.0, 100.0]
    unstable_evs = [200.0, -50.0, 10.0]

    robust_stable = 1.0 / (np.std(stable_evs) + 1e-9)
    robust_unstable = 1.0 / (np.std(unstable_evs) + 1e-9)
    assert robust_stable > robust_unstable

    metrics = compute_metrics(
        strategy,
        pnls,
        0.05,
        0.04,
        100.0,
        robustness_override=robust_stable,
    )
    assert metrics["robustness"] == robust_stable


def test_capital_normalized_ev_metric_in_compute_metrics() -> None:
    strategy = Strategy(
        name="test",
        legs=(OptionLeg("call", 100.0, 1, "buy", pd.Timestamp("2030-01-01")),),
    )
    pnls = np.array([0.0, 100.0, 200.0])
    metrics = compute_metrics(
        strategy,
        pnls,
        0.05,
        0.04,
        100.0,
        robustness_override=1.0,
        capital={"capital_required": 250.0, "capital_efficiency": 0.4},
    )
    assert metrics["ev"] == 100.0
    assert metrics["capital_required"] == 250.0
    assert metrics["capital_normalized_ev"] == 0.4


def test_capital_normalized_ev_prefers_better_return_per_capital() -> None:
    high_return = {
        "strategy": "high_return",
        "ev": 150.0,
        "capital_required": 300.0,
        "convexity": 2.0,
        "cvar": -100.0,
        "robustness": 1.0,
        "risk_classification": "defined_risk",
    }
    low_return = {
        "strategy": "low_return",
        "ev": 180.0,
        "capital_required": 900.0,
        "convexity": 2.0,
        "cvar": -100.0,
        "robustness": 1.0,
        "risk_classification": "defined_risk",
    }
    ranked = score_strategies([high_return, low_return])
    assert ranked[0]["strategy"] == "high_return"
    assert ranked[0]["capital_normalized_ev"] > ranked[1]["capital_normalized_ev"]


def test_capital_normalized_ev_fallback_on_invalid_capital() -> None:
    item = {"ev": 50.0, "capital_required": 0.0, "max_loss": -200.0}
    assert _capital_normalized_ev(item) == 0.25
