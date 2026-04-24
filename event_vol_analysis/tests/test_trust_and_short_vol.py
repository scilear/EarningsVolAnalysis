"""Tests for trust hardening v2 diagnostics and short-vol gating."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from event_vol_analysis import main as main_module


def test_trust_gate_continuous_score() -> None:
    comparison = {
        "lognormal": {
            "tail_prob_gt_6pct": 0.10,
        },
        "fat_tailed": {
            "mean_abs_move": 0.06,
            "abs_q10": 0.03,
            "abs_q50": 0.06,
            "abs_q90": 0.09,
            "tail_prob_gt_6pct": 0.12,
            "ks_pvalue": 0.80,
        },
    }
    trust = main_module._compute_trust_metrics(
        implied_move=0.06,
        simulation_comparison=comparison,
    )

    assert isinstance(trust["trust_score"], float)
    assert 0.0 <= float(trust["trust_score"]) <= 100.0
    assert trust["status"] in {"PASS", "WARN", "FAIL"}
    assert trust["confidence"] in {"HIGH", "MEDIUM", "LOW"}
    assert "quantile_deviation" in trust


def test_dte_weighting_allows_boundary_cases() -> None:
    inside = main_module._short_vol_dte_weight(7)
    low_outside = main_module._short_vol_dte_weight(0)
    high_outside = main_module._short_vol_dte_weight(18)

    assert inside == 1.0
    assert 0.35 <= low_outside < 1.0
    assert 0.35 <= high_outside < 1.0


def test_short_vol_earnings_evidence_gate(monkeypatch) -> None:
    class _Store:
        def get_earnings_outcomes(self, ticker: str):
            return pd.DataFrame(
                {
                    "event_date": [
                        dt.date(2026, 5, 1),
                        dt.date(2026, 2, 1),
                        dt.date(2025, 11, 1),
                    ],
                    "realized_vs_implied_ratio": [0.80, 0.95, 1.10],
                }
            )

    monkeypatch.setattr(
        "data.option_data_store.create_store",
        lambda path: _Store(),
    )
    monkeypatch.setattr(main_module.Path, "exists", lambda self: True)

    gate = main_module._short_vol_evidence_gate("AAPL", lookback=8)

    assert gate["allowed"] is True
    assert gate["wins"] == 2
    assert gate["samples"] == 3


def test_quantile_deviation_direction_reports_under() -> None:
    result = main_module._compute_quantile_deviation(
        implied_move=0.08,
        simulated_abs_quantiles={
            "p10": 0.02,
            "p50": 0.03,
            "p90": 0.04,
        },
    )
    assert result["mismatch_direction"] == "simulation_under"


def test_implied_abs_move_reference_shape() -> None:
    sample = main_module._implied_abs_move_reference(0.06, 1_000, seed=7)
    assert isinstance(sample, np.ndarray)
    assert sample.shape == (1_000,)
    assert np.all(sample >= 0.0)
