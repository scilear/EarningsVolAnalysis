"""Tests for strategy construction."""

import pandas as pd
import pytest

from nvda_earnings_vol.analytics.skew import skew_metrics
from nvda_earnings_vol.strategies.structures import build_strategies


def _chain(expiry: str) -> pd.DataFrame:
    """Create a test chain with both calls and puts."""
    strikes = [90.0, 95.0, 100.0, 105.0, 110.0]
    rows = []
    for strike in strikes:
        rows.append(
            {"strike": strike, "option_type": "call", "expiry": pd.Timestamp(expiry)}
        )
        rows.append(
            {"strike": strike, "option_type": "put", "expiry": pd.Timestamp(expiry)}
        )
    return pd.DataFrame(rows)


def test_build_strategies_count() -> None:
    front = _chain("2030-01-01")
    back = _chain("2030-02-01")
    strategies = build_strategies(front, back, 100.0)
    assert len(strategies) >= 9


def test_symmetric_butterfly_structure_and_symmetry() -> None:
    front = _chain("2030-01-01")
    back = _chain("2030-02-01")
    strategies = build_strategies(front, back, 100.0)
    butterfly = next(item for item in strategies if item.name == "symmetric_butterfly")

    assert len(butterfly.legs) == 4
    calls = [leg for leg in butterfly.legs if leg.option_type == "call"]
    assert len(calls) == 4
    buys = [leg for leg in calls if leg.side == "buy"]
    sells = [leg for leg in calls if leg.side == "sell"]
    assert len(buys) == 2
    assert len(sells) == 2

    strikes = sorted(leg.strike for leg in calls)
    lower, body_1, body_2, upper = strikes
    assert body_1 == body_2
    assert abs((body_1 - lower) - (upper - body_1)) <= 1e-9


def test_strangle_offset_guard() -> None:
    front = _chain("2030-01-01")
    back = _chain("2030-02-01")
    with pytest.raises(ValueError):
        build_strategies(front, back, 100.0, strangle_offset_pct=0.0)


def test_strangle_offset_affects_strikes() -> None:
    front = _chain("2030-01-01")
    back = _chain("2030-02-01")
    strategies = build_strategies(
        front,
        back,
        100.0,
        strangle_offset_pct=0.08,
    )
    strangle = next(item for item in strategies if item.name == "long_strangle")
    call_leg = next(leg for leg in strangle.legs if leg.option_type == "call")
    put_leg = next(leg for leg in strangle.legs if leg.option_type == "put")
    assert call_leg.strike >= 100.0 * 1.07
    assert put_leg.strike <= 100.0 * 0.93


def test_skew_metrics_no_25d_strike() -> None:
    chain = pd.DataFrame(
        {
            "strike": [50.0, 150.0],
            "option_type": ["call", "put"],
            "impliedVolatility": [float("nan"), float("nan")],
        }
    )
    output = skew_metrics(chain, 100.0, 0.1)
    assert output["rr25"] is None
    assert output["bf25"] is None
