"""Tests for scoring logic."""

import numpy as np
import pandas as pd

from nvda_earnings_vol.config import CONVEXITY_CAP
from nvda_earnings_vol.strategies.scoring import (
    _is_undefined_risk,
    compute_metrics,
)
from nvda_earnings_vol.strategies.structures import OptionLeg, Strategy


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
    metrics = compute_metrics(strategy, pnls, 0.05, 0.04, 100.0)
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
    metrics = compute_metrics(strategy, pnls, 0.05, 0.04, 100.0)
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


def test_convexity_cap_on_near_zero_bottom() -> None:
    pnls = np.array([0.0] * 90 + [10.0] * 10)
    strategy = Strategy(
        name="convex",
        legs=(OptionLeg("call", 100.0, 1, "buy", pd.Timestamp("2030-01-01")),),
    )
    metrics = compute_metrics(strategy, pnls, 0.05, 0.04, 100.0)
    assert metrics["convexity"] == CONVEXITY_CAP
