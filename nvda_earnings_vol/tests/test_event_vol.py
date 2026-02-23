"""Tests for event variance extraction."""

import datetime as dt

import pandas as pd

from nvda_earnings_vol.analytics.event_vol import event_variance


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
    assert output["assumption"] == "single_point"


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
