"""Payoff-type to structure mapping for the Structure Advisor."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from enum import Enum

import pandas as pd

from event_vol_analysis.strategies.structures import (
    OptionLeg,
    Strategy,
    _snap_to_strike,
    make_call_spread,
    make_covered_call,
    make_diagonal_put_backspread,
    make_long_call,
    make_long_put,
    make_long_straddle,
    make_long_strangle,
    make_put_spread,
    make_risk_reversal,
    make_short_straddle,
    make_short_strangle,
)


class PayoffType(str, Enum):
    """Atomic payoff intents for structure selection."""

    CRASH = "crash"
    RALLY = "rally"
    SIDEWAYS = "sideways"
    VOL_EXPANSION = "vol-expansion"
    VOL_COMPRESSION = "vol-compression"
    DIRECTIONAL_CONVEX = "directional-convex"


PAYOFF_STRUCTURE_MAP: dict[PayoffType, list[str]] = {
    PayoffType.CRASH: [
        "long_put_otm_2",
        "long_put_otm_4",
        "put_spread_96_90",
        "put_backspread_96_90",
        "diagonal_put_backspread_96_93",
        "long_put_atm",
    ],
    PayoffType.RALLY: [
        "long_call_otm_2",
        "call_spread_104_110",
        "call_backspread_104_110",
    ],
    PayoffType.SIDEWAYS: [
        "iron_condor_96_104",
        "iron_butterfly_atm",
        "short_strangle_96_104",
        "calendar_atm",
    ],
    PayoffType.VOL_EXPANSION: [
        "long_straddle_atm",
        "long_strangle_96_104",
        "calendar_atm",
    ],
    PayoffType.VOL_COMPRESSION: [
        "short_straddle_atm",
        "short_strangle_96_104",
        "credit_put_spread_96_90",
        "credit_call_spread_104_110",
        "iron_condor_96_104",
    ],
    PayoffType.DIRECTIONAL_CONVEX: [
        "call_spread_102_107",
        "put_spread_98_93",
        "risk_reversal_bullish",
        "risk_reversal_bearish",
        "call_backspread_104_110",
        "covered_call_104",
    ],
}


def _resolve_payoff_type(payoff_type: PayoffType | str) -> PayoffType:
    """Normalize a payoff string or enum into ``PayoffType``."""
    if isinstance(payoff_type, PayoffType):
        return payoff_type
    try:
        return PayoffType(payoff_type.strip().lower())
    except ValueError as exc:
        valid = ", ".join(item.value for item in PayoffType)
        raise ValueError(
            f"Unsupported payoff_type '{payoff_type}'. Valid: {valid}"
        ) from exc


def _default_expiries(
    expiry: dt.date | pd.Timestamp | None,
    back_expiry: dt.date | pd.Timestamp | None,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Resolve front and back expiries with conservative defaults."""
    today = dt.date.today()
    front = pd.Timestamp(expiry or (today + dt.timedelta(days=23)))
    back = pd.Timestamp(back_expiry or (front.date() + dt.timedelta(days=35)))
    return front, back


def _build_structure_catalog(
    *,
    spot: float,
    front_expiry: pd.Timestamp,
    back_expiry: pd.Timestamp,
    strike_step: float,
) -> dict[str, Strategy]:
    """Build all reusable structure templates keyed by structure id."""
    atm = _snap_to_strike(spot, strike_step)
    put_2 = _snap_to_strike(spot * 0.98, strike_step)
    put_4 = _snap_to_strike(spot * 0.96, strike_step)
    put_7 = _snap_to_strike(spot * 0.93, strike_step)
    put_10 = _snap_to_strike(spot * 0.90, strike_step)
    call_2 = _snap_to_strike(spot * 1.02, strike_step)
    call_4 = _snap_to_strike(spot * 1.04, strike_step)
    call_7 = _snap_to_strike(spot * 1.07, strike_step)
    call_10 = _snap_to_strike(spot * 1.10, strike_step)

    catalog: dict[str, Strategy] = {
        "long_put_atm": make_long_put(front_expiry, atm),
        "long_put_otm_2": make_long_put(front_expiry, put_2),
        "long_put_otm_4": make_long_put(front_expiry, put_4),
        "long_put_otm_7": make_long_put(front_expiry, put_7),
        "long_put_otm_10": make_long_put(front_expiry, put_10),
        "long_call_otm_2": make_long_call(front_expiry, call_2),
        "put_spread_96_90": make_put_spread(front_expiry, put_4, put_10),
        "put_spread_98_93": make_put_spread(front_expiry, put_2, put_7),
        "call_spread_104_110": make_call_spread(front_expiry, call_4, call_10),
        "call_spread_102_107": make_call_spread(front_expiry, call_2, call_7),
        "long_straddle_atm": make_long_straddle(front_expiry, atm),
        "long_strangle_96_104": make_long_strangle(front_expiry, call_4, put_4),
        "short_straddle_atm": make_short_straddle(front_expiry, atm),
        "short_strangle_96_104": make_short_strangle(front_expiry, call_4, put_4),
        "covered_call_104": make_covered_call(front_expiry, call_4),
        "diagonal_put_backspread_96_93": make_diagonal_put_backspread(
            short_expiry=front_expiry,
            long_expiry=back_expiry,
            short_strike=put_4,
            long_strike=put_7,
            ratio=2,
        ),
        "risk_reversal_bullish": make_risk_reversal(
            expiry=front_expiry,
            put_strike=put_4,
            call_strike=call_4,
            direction="bullish",
        ),
        "risk_reversal_bearish": make_risk_reversal(
            expiry=front_expiry,
            put_strike=put_4,
            call_strike=call_4,
            direction="bearish",
        ),
        "calendar_atm": Strategy(
            name="calendar",
            legs=(
                OptionLeg("call", atm, 1, "sell", front_expiry),
                OptionLeg("call", atm, 1, "buy", back_expiry),
            ),
        ),
        "put_backspread_96_90": Strategy(
            name="put_backspread",
            legs=(
                OptionLeg("put", put_4, 1, "sell", front_expiry),
                OptionLeg("put", put_10, 2, "buy", front_expiry),
            ),
        ),
        "call_backspread_104_110": Strategy(
            name="call_backspread",
            legs=(
                OptionLeg("call", call_4, 1, "sell", front_expiry),
                OptionLeg("call", call_10, 2, "buy", front_expiry),
            ),
        ),
        "credit_put_spread_96_90": Strategy(
            name="credit_put_spread",
            legs=(
                OptionLeg("put", put_4, 1, "sell", front_expiry),
                OptionLeg("put", put_10, 1, "buy", front_expiry),
            ),
        ),
        "credit_call_spread_104_110": Strategy(
            name="credit_call_spread",
            legs=(
                OptionLeg("call", call_4, 1, "sell", front_expiry),
                OptionLeg("call", call_10, 1, "buy", front_expiry),
            ),
        ),
        "iron_condor_96_104": Strategy(
            name="iron_condor",
            legs=(
                OptionLeg("put", put_4, 1, "sell", front_expiry),
                OptionLeg("put", put_10, 1, "buy", front_expiry),
                OptionLeg("call", call_4, 1, "sell", front_expiry),
                OptionLeg("call", call_10, 1, "buy", front_expiry),
            ),
        ),
        "iron_butterfly_atm": Strategy(
            name="iron_butterfly",
            legs=(
                OptionLeg("put", atm, 1, "sell", front_expiry),
                OptionLeg("call", atm, 1, "sell", front_expiry),
                OptionLeg("put", put_4, 1, "buy", front_expiry),
                OptionLeg("call", call_4, 1, "buy", front_expiry),
            ),
        ),
    }
    return catalog


def build_structure_by_key(
    structure_key: str,
    *,
    spot: float,
    expiry: dt.date | pd.Timestamp | None = None,
    back_expiry: dt.date | pd.Timestamp | None = None,
    strike_step: float = 1.0,
) -> Strategy:
    """Build one structure instance from a structure key."""
    front, back = _default_expiries(expiry, back_expiry)
    catalog = _build_structure_catalog(
        spot=spot,
        front_expiry=front,
        back_expiry=back,
        strike_step=strike_step,
    )
    if structure_key not in catalog:
        raise KeyError(f"Unknown structure key: {structure_key}")
    return replace(catalog[structure_key], name=structure_key)


def get_structures_for_payoff(
    payoff_type: PayoffType | str,
    *,
    expiry: dt.date | pd.Timestamp | None = None,
    spot: float = 100.0,
    back_expiry: dt.date | pd.Timestamp | None = None,
    strike_step: float = 1.0,
) -> list[Strategy]:
    """Return concrete structure objects for a payoff intent."""
    resolved = _resolve_payoff_type(payoff_type)
    keys = PAYOFF_STRUCTURE_MAP[resolved]
    return [
        build_structure_by_key(
            key,
            spot=spot,
            expiry=expiry,
            back_expiry=back_expiry,
            strike_step=strike_step,
        )
        for key in keys
    ]


__all__ = [
    "PayoffType",
    "PAYOFF_STRUCTURE_MAP",
    "build_structure_by_key",
    "get_structures_for_payoff",
]
