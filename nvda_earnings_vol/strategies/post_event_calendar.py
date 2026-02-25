"""
Post-event calendar spread for residually-elevated front IV.

Entry window: 1-3 days after earnings. The front leg IV is still above
back-leg levels (IV ratio >= POST_EVENT_CALENDAR_MIN_IV_RATIO), creating
a premium that can be harvested before front expiry.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from nvda_earnings_vol.analytics.bsm import option_price
from nvda_earnings_vol.config import (
    DIVIDEND_YIELD,
    POST_EVENT_CALENDAR_ENTRY_MAX_DAYS,
    POST_EVENT_CALENDAR_ENTRY_MIN_DAYS,
    POST_EVENT_CALENDAR_LONG_IV_COMPRESSION,
    POST_EVENT_CALENDAR_MIN_IV_RATIO,
    POST_EVENT_CALENDAR_MIN_SHORT_DTE,
    RISK_FREE_RATE,
    TIME_EPSILON,
)
from nvda_earnings_vol.strategies.structures import OptionLeg, Strategy


LOGGER = logging.getLogger(__name__)


def post_event_calendar_conditions_met(
    snapshot: dict[str, Any],
) -> bool:
    """Return True if entry conditions for a post-event calendar are met.

    Conditions (all must be true):
    * ``days_after_event`` in [POST_EVENT_CALENDAR_ENTRY_MIN_DAYS,
      POST_EVENT_CALENDAR_ENTRY_MAX_DAYS] (1-3 days after earnings).
    * ``iv_ratio`` (front_iv / back_iv) >= POST_EVENT_CALENDAR_MIN_IV_RATIO
      (1.10) — front IV still residually elevated.
    * ``front_dte`` >= POST_EVENT_CALENDAR_MIN_SHORT_DTE (3) — enough time
      for the short leg to settle meaningfully above intrinsic.

    Args:
        snapshot: Market snapshot dict. Required keys:
            ``days_after_event``, ``iv_ratio``, ``front_dte``.

    Returns:
        True when all conditions are satisfied.
    """
    days_after = int(snapshot.get("days_after_event", 0))
    iv_ratio = float(snapshot.get("iv_ratio", 0.0))
    front_dte = int(snapshot.get("front_dte", 0))

    entry_window_ok = (
        POST_EVENT_CALENDAR_ENTRY_MIN_DAYS
        <= days_after
        <= POST_EVENT_CALENDAR_ENTRY_MAX_DAYS
    )
    iv_ratio_ok = iv_ratio >= POST_EVENT_CALENDAR_MIN_IV_RATIO
    dte_ok = front_dte >= POST_EVENT_CALENDAR_MIN_SHORT_DTE

    if not entry_window_ok:
        LOGGER.debug(
            "Post-event calendar gate: days_after_event %d not in [%d, %d]",
            days_after,
            POST_EVENT_CALENDAR_ENTRY_MIN_DAYS,
            POST_EVENT_CALENDAR_ENTRY_MAX_DAYS,
        )
    if not iv_ratio_ok:
        LOGGER.debug(
            "Post-event calendar gate: iv_ratio %.3f < %.2f",
            iv_ratio,
            POST_EVENT_CALENDAR_MIN_IV_RATIO,
        )
    if not dte_ok:
        LOGGER.debug(
            "Post-event calendar gate: front_dte %d < %d",
            front_dte,
            POST_EVENT_CALENDAR_MIN_SHORT_DTE,
        )

    return entry_window_ok and iv_ratio_ok and dte_ok


def build_post_event_calendar(
    spot: float,
    K: float,
    front_iv: float,
    back3_iv: float,
    t_short: float,
    t_long: float,
    front_expiry: pd.Timestamp,
    back3_expiry: pd.Timestamp,
) -> dict[str, Any]:
    """
    Post-event calendar: SELL 1× front ATM call / BUY 1× back3 ATM call.
    Entry: 1-3 days after earnings, front IV still residually elevated.

    Profit model: pure theta spread.
        Short leg: sold at IV-inflated premium pre-settlement.
        At front expiry, settles at intrinsic value. The profit on the
        short leg is the difference between the inflated sale price and
        intrinsic settlement — fully determined at entry, not accrued
        over the holding period.

        Long leg: retains BSM value with mild IV compression
        (iv_long × POST_EVENT_CALENDAR_LONG_IV_COMPRESSION). The cost
        of the long leg is the BSM value erosion over the holding period.

        Net P&L = (short premium - short intrinsic)
                - (long entry value - long exit value)

    This is NOT an IV convergence trade. At the time of entry, IV
    compression from the earnings event has already largely occurred.
    The edge is structural: the front leg's residual IV elevation
    creates a premium that exceeds theta erosion on the back leg.

    Scenarios test stock movement risk, not IV path risk.

    Args:
        spot: Spot price at entry.
        K: ATM strike (call strike for both legs).
        front_iv: Front-month ATM IV (residually elevated post-event).
        back3_iv: Back3-month ATM IV.
        t_short: Time to front expiry (years).
        t_long: Time to back3 expiry (years).
        front_expiry: Front-month expiry timestamp.
        back3_expiry: Back3-month expiry timestamp.

    Returns:
        Dict with pricing details and ``Strategy`` object.
    """
    short_premium = option_price(
        spot, K, max(t_short, TIME_EPSILON),
        RISK_FREE_RATE, DIVIDEND_YIELD, front_iv, "call",
    )
    long_cost = option_price(
        spot, K, max(t_long, TIME_EPSILON),
        RISK_FREE_RATE, DIVIDEND_YIELD, back3_iv, "call",
    )
    net_cost = long_cost - short_premium

    strategy = Strategy(
        name="post_event_calendar",
        legs=(
            OptionLeg(
                option_type="call",
                strike=K,
                qty=1,
                side="sell",
                expiry=front_expiry,
                entry_price=short_premium,
                iv=front_iv,
            ),
            OptionLeg(
                option_type="call",
                strike=K,
                qty=1,
                side="buy",
                expiry=back3_expiry,
                entry_price=long_cost,
                iv=back3_iv,
            ),
        ),
    )

    return {
        "strategy": strategy,
        "spot": spot,
        "K": K,
        "t_short": t_short,
        "t_long": t_long,
        "front_iv": front_iv,
        "back3_iv": back3_iv,
        "short_premium": short_premium,
        "long_cost": long_cost,
        "net_cost": net_cost,
        "front_expiry": front_expiry,
        "back3_expiry": back3_expiry,
    }


def compute_post_event_calendar_scenarios(
    spot: float,
    K: float,
    t_short: float,
    t_long: float,
    iv_long: float,
    net_cost: float,
) -> dict[str, float]:
    """Evaluate post-event calendar P&L across stock-movement scenarios.

    The short leg settles at intrinsic at front expiry (``t_short``). The
    long leg is valued using BSM with mild IV compression applied to
    ``iv_long``. No ``iv_short`` parameter is accepted — the short-leg IV
    at evaluation time is irrelevant because the short leg's P&L is fully
    determined at settlement (sale price − intrinsic), not by any IV path.

    P&L formula per scenario:
        long_exit = bsm(spot_T, K, t_remaining, iv_long × compression)
        short_intrinsic = max(spot_T − K, 0)
        pnl = long_exit − short_intrinsic − net_cost

    where ``t_remaining = t_long − t_short`` and ``net_cost`` is the
    debit paid at entry (long_cost − short_premium).

    Args:
        spot: Spot price at entry (used to anchor stock-move scenarios).
        K: ATM strike.
        t_short: Time to front expiry (years) — when short leg settles.
        t_long: Time to back3 expiry (years).
        iv_long: Back3 ATM IV at entry.
        net_cost: Net debit paid at entry (long_cost − short_premium).

    Returns:
        Dict mapping scenario names to P&L values (dollars, per contract).
        Scenarios: ``"flat"``, ``"up_5pct"``, ``"down_5pct"``,
        ``"up_10pct"``, ``"down_10pct"``.
    """
    t_remaining = max(t_long - t_short, TIME_EPSILON)
    compressed_iv = iv_long * POST_EVENT_CALENDAR_LONG_IV_COMPRESSION

    scenarios: dict[str, float] = {}
    spot_moves = {
        "flat": 0.0,
        "up_5pct": 0.05,
        "down_5pct": -0.05,
        "up_10pct": 0.10,
        "down_10pct": -0.10,
    }

    for name, move in spot_moves.items():
        spot_t = spot * (1.0 + move)

        # Short leg: settles at intrinsic — no IV needed
        short_intrinsic = max(spot_t - K, 0.0)

        # Long leg: BSM value with mild IV compression
        long_exit = option_price(
            spot_t, K, t_remaining,
            RISK_FREE_RATE, DIVIDEND_YIELD, compressed_iv, "call",
        )

        pnl = long_exit - short_intrinsic - net_cost
        scenarios[name] = float(pnl)

    return scenarios


__all__ = [
    "post_event_calendar_conditions_met",
    "build_post_event_calendar",
    "compute_post_event_calendar_scenarios",
]
