"""Tests for scoring logic."""

import numpy as np
import pandas as pd

from nvda_earnings_vol.strategies.scoring import compute_metrics
from nvda_earnings_vol.strategies.structures import OptionLeg, Strategy


def test_convexity_guard() -> None:
    pnls = np.array([0.0] * 100)
    strategy = Strategy(
        name="flat",
        legs=(OptionLeg("call", 100.0, 1, "buy", pd.Timestamp("2030-01-01")),),
    )
    metrics = compute_metrics(strategy, pnls, 0.05, 0.04, 100.0)
    assert metrics["convexity"] > 0


def test_undefined_risk_detection() -> None:
    strategy = Strategy(
        name="short_call",
        legs=(OptionLeg("call", 100.0, 1, "sell", pd.Timestamp("2030-01-01")),),
    )
    pnls = np.array([1.0, -10.0, 2.0])
    metrics = compute_metrics(strategy, pnls, 0.05, 0.04, 100.0)
    assert metrics["risk_classification"] == "undefined_risk"
