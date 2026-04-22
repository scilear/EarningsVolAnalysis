"""Unit tests for positioning proxy signals and consensus classifier."""

from __future__ import annotations

import pandas as pd

from event_vol_analysis.analytics.positioning import (
    PositioningSignal,
    SignalResult,
    classify_positioning,
    drift_vs_sector,
    max_pain_distance,
    oi_concentration,
    pc_ratio_signal,
)


def _chain(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_oi_concentration_bullish() -> None:
    chain = _chain(
        [
            {"strike": 100, "option_type": "call", "openInterest": 800},
            {"strike": 105, "option_type": "call", "openInterest": 700},
            {"strike": 110, "option_type": "call", "openInterest": 600},
            {"strike": 95, "option_type": "call", "openInterest": 100},
            {"strike": 100, "option_type": "put", "openInterest": 50},
            {"strike": 105, "option_type": "put", "openInterest": 50},
            {"strike": 110, "option_type": "put", "openInterest": 50},
        ]
    )
    out = oi_concentration(chain)
    assert out.signal == PositioningSignal.BULLISH
    assert out.is_available is True


def test_oi_concentration_bearish() -> None:
    chain = _chain(
        [
            {"strike": 90, "option_type": "put", "openInterest": 900},
            {"strike": 95, "option_type": "put", "openInterest": 700},
            {"strike": 100, "option_type": "put", "openInterest": 600},
            {"strike": 90, "option_type": "call", "openInterest": 50},
            {"strike": 95, "option_type": "call", "openInterest": 50},
            {"strike": 100, "option_type": "call", "openInterest": 50},
        ]
    )
    out = oi_concentration(chain)
    assert out.signal == PositioningSignal.BEARISH
    assert out.is_available is True


def test_oi_concentration_neutral() -> None:
    chain = _chain(
        [
            {"strike": 100, "option_type": "call", "openInterest": 100},
            {"strike": 105, "option_type": "call", "openInterest": 100},
            {"strike": 110, "option_type": "call", "openInterest": 100},
            {"strike": 100, "option_type": "put", "openInterest": 100},
            {"strike": 105, "option_type": "put", "openInterest": 100},
            {"strike": 110, "option_type": "put", "openInterest": 100},
        ]
    )
    out = oi_concentration(chain)
    assert out.signal == PositioningSignal.NEUTRAL
    assert out.is_available is True


def test_oi_no_oi_column() -> None:
    out = oi_concentration(pd.DataFrame({"strike": [100], "option_type": ["call"]}))
    assert out.signal == PositioningSignal.NEUTRAL
    assert out.is_available is False


def test_pc_ratio_elevated_puts() -> None:
    out = pc_ratio_signal(pc_5d=1.5, pc_20d_avg=1.0)
    assert out.signal == PositioningSignal.BEARISH


def test_pc_ratio_elevated_calls() -> None:
    out = pc_ratio_signal(pc_5d=0.6, pc_20d_avg=1.0)
    assert out.signal == PositioningSignal.BULLISH


def test_pc_ratio_normal() -> None:
    out = pc_ratio_signal(pc_5d=1.0, pc_20d_avg=1.0)
    assert out.signal == PositioningSignal.NEUTRAL


def test_pc_ratio_missing_input() -> None:
    out = pc_ratio_signal(pc_5d=None, pc_20d_avg=1.0)
    assert out.signal == PositioningSignal.NEUTRAL
    assert out.is_available is False


def test_drift_outperform() -> None:
    out = drift_vs_sector(ticker_10d_ret=0.10, sector_10d_ret=0.02)
    assert out.signal == PositioningSignal.BULLISH


def test_drift_underperform() -> None:
    out = drift_vs_sector(ticker_10d_ret=-0.10, sector_10d_ret=0.02)
    assert out.signal == PositioningSignal.BEARISH


def test_drift_flat() -> None:
    out = drift_vs_sector(ticker_10d_ret=0.03, sector_10d_ret=0.02)
    assert out.signal == PositioningSignal.NEUTRAL


def test_drift_sector_zero_degenerate() -> None:
    out = drift_vs_sector(ticker_10d_ret=0.03, sector_10d_ret=0.0)
    assert out.signal == PositioningSignal.BULLISH


def test_max_pain_above_spot() -> None:
    chain = _chain(
        [
            {"strike": 110, "option_type": "call", "openInterest": 1000},
            {"strike": 110, "option_type": "put", "openInterest": 1000},
            {"strike": 90, "option_type": "call", "openInterest": 10},
            {"strike": 90, "option_type": "put", "openInterest": 10},
        ]
    )
    out = max_pain_distance(chain, spot=100.0)
    assert out.signal == PositioningSignal.BULLISH


def test_max_pain_below_spot() -> None:
    chain = _chain(
        [
            {"strike": 90, "option_type": "call", "openInterest": 1000},
            {"strike": 90, "option_type": "put", "openInterest": 1000},
            {"strike": 110, "option_type": "call", "openInterest": 10},
            {"strike": 110, "option_type": "put", "openInterest": 10},
        ]
    )
    out = max_pain_distance(chain, spot=100.0)
    assert out.signal == PositioningSignal.BEARISH


def test_max_pain_at_spot() -> None:
    chain = _chain(
        [
            {"strike": 100, "option_type": "call", "openInterest": 1000},
            {"strike": 100, "option_type": "put", "openInterest": 1000},
        ]
    )
    out = max_pain_distance(chain, spot=100.0)
    assert out.signal == PositioningSignal.NEUTRAL


def test_classify_all_agree_bullish() -> None:
    out = classify_positioning(
        SignalResult(PositioningSignal.BULLISH, True, ""),
        SignalResult(PositioningSignal.BULLISH, True, ""),
        SignalResult(PositioningSignal.BULLISH, True, ""),
        SignalResult(PositioningSignal.BULLISH, True, ""),
    )
    assert out.label == "CROWDED"
    assert out.direction == "UPSIDE"
    assert out.confidence == "HIGH"


def test_classify_all_agree_bearish() -> None:
    out = classify_positioning(
        SignalResult(PositioningSignal.BEARISH, True, ""),
        SignalResult(PositioningSignal.BEARISH, True, ""),
        SignalResult(PositioningSignal.BEARISH, True, ""),
        SignalResult(PositioningSignal.BEARISH, True, ""),
    )
    assert out.label == "CROWDED"
    assert out.direction == "DOWNSIDE"
    assert out.confidence == "HIGH"


def test_classify_disagreement() -> None:
    out = classify_positioning(
        SignalResult(PositioningSignal.BULLISH, True, ""),
        SignalResult(PositioningSignal.BEARISH, True, ""),
        SignalResult(PositioningSignal.NEUTRAL, True, ""),
        SignalResult(PositioningSignal.BULLISH, True, ""),
    )
    assert out.label == "BALANCED"
    assert out.confidence == "LOW"


def test_classify_two_unavailable() -> None:
    out = classify_positioning(
        SignalResult(PositioningSignal.BULLISH, True, ""),
        SignalResult(PositioningSignal.NEUTRAL, False, ""),
        SignalResult(PositioningSignal.NEUTRAL, False, ""),
        SignalResult(PositioningSignal.BEARISH, True, ""),
    )
    assert out.label == "BALANCED"
    assert out.confidence == "LOW"


def test_classify_three_agree_one_missing() -> None:
    out = classify_positioning(
        SignalResult(PositioningSignal.BULLISH, True, ""),
        SignalResult(PositioningSignal.BULLISH, True, ""),
        SignalResult(PositioningSignal.BULLISH, True, ""),
        SignalResult(PositioningSignal.NEUTRAL, False, ""),
    )
    assert out.label == "CROWDED"
    assert out.confidence == "MEDIUM"


def test_classify_all_neutral() -> None:
    out = classify_positioning(
        SignalResult(PositioningSignal.NEUTRAL, True, ""),
        SignalResult(PositioningSignal.NEUTRAL, True, ""),
        SignalResult(PositioningSignal.NEUTRAL, True, ""),
        SignalResult(PositioningSignal.NEUTRAL, True, ""),
    )
    assert out.label == "UNDER-POSITIONED"
