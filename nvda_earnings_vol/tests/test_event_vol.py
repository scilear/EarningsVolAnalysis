"""Tests for event variance extraction."""

import datetime as dt

from pathlib import Path

import pandas as pd
import pytest

from nvda_earnings_vol.analytics.event_vol import event_variance
from nvda_earnings_vol import main as main_module


def _chain(iv: float, expiry: dt.date) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "strike": [100.0, 100.0],
            "option_type": ["call", "put"],
            "impliedVolatility": [iv, iv],
            "expiry": [pd.Timestamp(expiry), pd.Timestamp(expiry)],
        }
    )


def test_negative_event_variance_clamps() -> None:
    today = dt.date.today()
    event_date = today + dt.timedelta(days=7)
    front_expiry = today + dt.timedelta(days=10)
    back1_expiry = today + dt.timedelta(days=20)
    back2_expiry = today + dt.timedelta(days=40)

    front = _chain(0.2, front_expiry)
    back1 = _chain(0.4, back1_expiry)
    back2 = _chain(0.4, back2_expiry)

    output = event_variance(
        front,
        back1,
        back2,
        100.0,
        event_date,
        front_expiry,
        back1_expiry,
        back2_expiry,
    )
    assert float(output["event_var"]) == 0.0
    assert float(output["raw_event_var"]) < 0
    assert output["warning_level"] is not None


def test_single_point_assumption() -> None:
    today = dt.date.today()
    event_date = today + dt.timedelta(days=5)
    front_expiry = today + dt.timedelta(days=7)
    back1_expiry = today + dt.timedelta(days=20)

    front = _chain(0.4, front_expiry)
    back1 = _chain(0.3, back1_expiry)

    output = event_variance(
        front,
        back1,
        None,
        100.0,
        event_date,
        front_expiry,
        back1_expiry,
        None,
    )
    assert output["assumption"] == "Single-point term structure assumption"


def test_event_vol_handles_zero_iv() -> None:
    today = dt.date.today()
    event_date = today + dt.timedelta(days=5)
    front_expiry = today + dt.timedelta(days=7)
    back1_expiry = today + dt.timedelta(days=20)

    front = _chain(0.0, front_expiry)
    back1 = _chain(0.2, back1_expiry)

    output = event_variance(
        front,
        back1,
        None,
        100.0,
        event_date,
        front_expiry,
        back1_expiry,
        None,
    )
    assert output["event_var"] >= 0


def test_event_vol_front_expiry_zero_dte() -> None:
    today = dt.date.today()
    event_date = today
    front_expiry = today
    back1_expiry = today + dt.timedelta(days=10)

    front = _chain(0.3, front_expiry)
    back1 = _chain(0.3, back1_expiry)

    output = event_variance(
        front,
        back1,
        None,
        100.0,
        event_date,
        front_expiry,
        back1_expiry,
        None,
    )
    assert output["dt_event"] > 0


def test_flat_term_structure_event_var_zero() -> None:
    today = dt.date.today()
    event_date = today + dt.timedelta(days=7)
    front_expiry = today + dt.timedelta(days=10)
    back1_expiry = today + dt.timedelta(days=20)
    back2_expiry = today + dt.timedelta(days=40)

    front = _chain(0.5, front_expiry)
    back1 = _chain(0.5, back1_expiry)
    back2 = _chain(0.5, back2_expiry)

    output = event_variance(
        front,
        back1,
        back2,
        100.0,
        event_date,
        front_expiry,
        back1_expiry,
        back2_expiry,
    )
    iv = 0.5
    expected = iv**2
    assert abs(float(output["raw_event_var"]) - expected) < 1e-9


def test_zero_liquidity_after_filtering_raises(tmp_path, monkeypatch) -> None:
    expiry = dt.date(2030, 1, 1)
    chain = pd.DataFrame(
        {
            "strike": [100.0],
            "bid": [1.0],
            "ask": [1.0],
            "impliedVolatility": [0.2],
            "openInterest": [0],
            "option_type": ["call"],
            "expiry": [pd.Timestamp(expiry)],
            "mid": [1.0],
            "spread": [0.0],
        }
    )

    def _mock_chain(*_args, **_kwargs):
        return chain

    monkeypatch.setattr(main_module, "get_options_chain", _mock_chain)
    with pytest.raises(ValueError, match="No options remain after filtering"):
        main_module._load_filtered_chain(
            expiry,
            100.0,
            Path(tmp_path),
            use_cache=False,
            refresh_cache=False,
        )


def test_front_expiry_guard() -> None:
    event_date = dt.date(2030, 1, 1)
    front_expiry = dt.date(2030, 1, 1)
    with pytest.raises(ValueError):
        main_module._validate_front_expiry(event_date, front_expiry)
