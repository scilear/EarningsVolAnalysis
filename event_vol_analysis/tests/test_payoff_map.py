"""Tests for payoff-type mapping and added structure coverage."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from event_vol_analysis.strategies.payoff import strategy_pnl_vec
from event_vol_analysis.strategies.payoff_map import (
    PAYOFF_STRUCTURE_MAP,
    PayoffType,
    build_structure_by_key,
    get_structures_for_payoff,
)


def test_payoff_map_crash_has_min_4_structures() -> None:
    assert len(PAYOFF_STRUCTURE_MAP[PayoffType.CRASH]) >= 4


def test_payoff_map_sideways_has_min_3_structures() -> None:
    assert len(PAYOFF_STRUCTURE_MAP[PayoffType.SIDEWAYS]) >= 3


def test_payoff_map_vol_expansion_has_min_2_structures() -> None:
    assert len(PAYOFF_STRUCTURE_MAP[PayoffType.VOL_EXPANSION]) >= 2


def test_all_payoff_types_present_in_map() -> None:
    assert set(PAYOFF_STRUCTURE_MAP.keys()) == set(PayoffType)


def test_get_structures_for_payoff_returns_structure_objects() -> None:
    structures = get_structures_for_payoff(
        PayoffType.CRASH,
        expiry=dt.date(2030, 5, 17),
        back_expiry=dt.date(2030, 6, 21),
        spot=100.0,
    )
    assert structures
    assert all(hasattr(item, "legs") for item in structures)


def test_charter_flag_on_short_strangle() -> None:
    structures = get_structures_for_payoff(
        PayoffType.SIDEWAYS,
        expiry=dt.date(2030, 5, 17),
        back_expiry=dt.date(2030, 6, 21),
        spot=100.0,
    )
    short_strangle = next(
        item for item in structures if item.name == "short_strangle_96_104"
    )
    assert short_strangle.requires_naked_short_approval is True


def test_charter_flag_on_covered_call() -> None:
    structures = get_structures_for_payoff(
        PayoffType.DIRECTIONAL_CONVEX,
        expiry=dt.date(2030, 5, 17),
        back_expiry=dt.date(2030, 6, 21),
        spot=100.0,
    )
    covered_call = next(item for item in structures if item.name == "covered_call_104")
    assert covered_call.requires_existing_long is True


def test_diagonal_spread_payoff_at_expiry_long_leg() -> None:
    strategy = build_structure_by_key(
        "diagonal_put_backspread_96_93",
        spot=100.0,
        expiry=dt.date(2030, 5, 17),
        back_expiry=dt.date(2030, 6, 21),
    )
    chain = _chain_for_strategy(strategy)
    pnls = strategy_pnl_vec(
        strategy=strategy,
        chain=chain,
        spot=100.0,
        moves=np.array([0.0]),
        front_expiry=dt.date(2030, 5, 17),
        back_expiry=dt.date(2030, 6, 21),
        event_date=dt.date(2030, 5, 17),
        front_iv=0.35,
        back_iv=0.30,
        slippage_pct=0.10,
        scenario="base_crush",
    )
    assert np.isfinite(pnls).all()


def test_diagonal_spread_payoff_at_expiry_both_expired() -> None:
    strategy = build_structure_by_key(
        "diagonal_put_backspread_96_93",
        spot=100.0,
        expiry=dt.date(2030, 5, 17),
        back_expiry=dt.date(2030, 6, 21),
    )
    chain = _chain_for_strategy(strategy)
    pnls = strategy_pnl_vec(
        strategy=strategy,
        chain=chain,
        spot=100.0,
        moves=np.array([-0.10]),
        front_expiry=dt.date(2030, 5, 17),
        back_expiry=dt.date(2030, 6, 21),
        event_date=dt.date(2030, 6, 21),
        front_iv=0.35,
        back_iv=0.30,
        slippage_pct=0.10,
        scenario="base_crush",
    )
    assert np.isfinite(pnls).all()


def test_risk_reversal_payoff_bullish() -> None:
    strategy = build_structure_by_key(
        "risk_reversal_bullish",
        spot=100.0,
        expiry=dt.date(2030, 5, 17),
        back_expiry=dt.date(2030, 6, 21),
    )
    chain = _chain_for_strategy(strategy)
    pnls = strategy_pnl_vec(
        strategy=strategy,
        chain=chain,
        spot=100.0,
        moves=np.array([0.05]),
        front_expiry=dt.date(2030, 5, 17),
        back_expiry=dt.date(2030, 6, 21),
        event_date=dt.date(2030, 5, 10),
        front_iv=0.30,
        back_iv=0.28,
        slippage_pct=0.10,
        scenario="base_crush",
    )
    assert np.isfinite(pnls).all()


def test_risk_reversal_payoff_bearish() -> None:
    strategy = build_structure_by_key(
        "risk_reversal_bearish",
        spot=100.0,
        expiry=dt.date(2030, 5, 17),
        back_expiry=dt.date(2030, 6, 21),
    )
    chain = _chain_for_strategy(strategy)
    pnls = strategy_pnl_vec(
        strategy=strategy,
        chain=chain,
        spot=100.0,
        moves=np.array([-0.05]),
        front_expiry=dt.date(2030, 5, 17),
        back_expiry=dt.date(2030, 6, 21),
        event_date=dt.date(2030, 5, 10),
        front_iv=0.30,
        back_iv=0.28,
        slippage_pct=0.10,
        scenario="base_crush",
    )
    assert np.isfinite(pnls).all()


def _chain_for_strategy(strategy) -> pd.DataFrame:
    """Create minimal chain rows needed by payoff pricing."""
    rows: dict[tuple[dt.date, str, float], dict[str, object]] = {}
    for leg in strategy.legs:
        key = (leg.expiry.date(), leg.option_type, float(leg.strike))
        rows[key] = {
            "expiry": pd.Timestamp(leg.expiry.date()),
            "option_type": leg.option_type,
            "strike": float(leg.strike),
            "mid": 2.00,
            "spread": 0.10,
            "impliedVolatility": 0.35,
        }
    return pd.DataFrame(rows.values())
