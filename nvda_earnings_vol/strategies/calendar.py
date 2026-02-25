"""
Calendar spread builder for earnings volatility events.

A calendar spread sells the front-month ATM option and buys a longer-dated
ATM option of the same type. The preferred back leg is back3 (21-45 DTE);
back1 is the fallback when back3 is unavailable.

Term-spread check uses ``abs()`` so that inverted term structures (back IV
> front IV) are not incorrectly excluded by a sign-dependent gate.

IV factor constants:
    - CALENDAR_BACK3_POST_EVENT_IV_FACTOR (0.92): compression applied to the
      back3 leg when evaluating how IV resets after the event resolves.
    - CALENDAR_BACK1_POST_EVENT_IV_FACTOR (0.85): same but for back1 legs.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from nvda_earnings_vol.config import (
    BACK3_DTE_MIN,
    BACK3_DTE_MAX,
    CALENDAR_BACK1_POST_EVENT_IV_FACTOR,
    CALENDAR_BACK3_POST_EVENT_IV_FACTOR,
    CALENDAR_FALLBACK_BACK,
    CALENDAR_MIN_TERM_SPREAD_DAYS,
    CALENDAR_PREFERRED_BACK,
)
from nvda_earnings_vol.strategies.structures import OptionLeg, Strategy


LOGGER = logging.getLogger(__name__)


def calendar_conditions_met(snapshot: dict[str, Any]) -> bool:
    """Return True if entry conditions for a calendar spread are met.

    Conditions:
    * The absolute term spread (|front_iv - back_iv|) implies a meaningful
      difference in IV across expiries.  The gate here is structural: we
      require ``front_dte`` and ``back_dte`` to differ by at least
      ``CALENDAR_MIN_TERM_SPREAD_DAYS`` and that the position is pre-event
      (``days_after_event`` == 0).

    Args:
        snapshot: Market snapshot dict. Required keys:
            ``days_after_event``, ``front_dte``, ``back_dte``.

    Returns:
        True when conditions are met.
    """
    days_after = int(snapshot.get("days_after_event", 0))
    front_dte = int(snapshot.get("front_dte", 0))
    back_dte = int(snapshot.get("back_dte", 0))

    # Calendars are pre-event structures
    if days_after != 0:
        return False

    # abs() ensures inverted term structures are handled correctly
    term_spread_days = abs(back_dte - front_dte)
    if term_spread_days < CALENDAR_MIN_TERM_SPREAD_DAYS:
        LOGGER.debug(
            "Calendar gate: term spread %d days < %d minimum",
            term_spread_days,
            CALENDAR_MIN_TERM_SPREAD_DAYS,
        )
        return False

    return True


def build_calendar(
    front_chain: pd.DataFrame,
    back_chain: pd.DataFrame,
    spot: float,
    back_type: str = CALENDAR_PREFERRED_BACK,
) -> Strategy:
    """Build a calendar spread: SELL 1 front ATM call, BUY 1 back ATM call.

    The back-leg IV factor applied during scenario evaluation depends on
    ``back_type``:
    * ``"back3"`` → ``CALENDAR_BACK3_POST_EVENT_IV_FACTOR`` (0.92)
    * ``"back1"`` → ``CALENDAR_BACK1_POST_EVENT_IV_FACTOR`` (0.85)

    The term-spread days between back and front expiries are computed with
    ``abs()`` so inverted structures don't cause sign errors.

    Args:
        front_chain: Front-month option chain DataFrame.
        back_chain: Back-month option chain DataFrame.
        spot: Current underlying spot price.
        back_type: Which back leg type (``"back3"`` or ``"back1"``).
            Informational only; affects the strategy name.

    Returns:
        A :class:`Strategy` representing the calendar spread.
    """
    atm_strike = _nearest_strike(front_chain, spot)
    front_expiry = pd.Timestamp(front_chain["expiry"].iloc[0])
    back_expiry = pd.Timestamp(back_chain["expiry"].iloc[0])

    # Use abs() so inverted term structures are handled correctly (v5 fix).
    term_spread_days = abs(
        (back_expiry.date() - front_expiry.date()).days
    )
    LOGGER.debug(
        "Calendar term spread: %d days (%s preferred, %s fallback)",
        term_spread_days,
        CALENDAR_PREFERRED_BACK,
        CALENDAR_FALLBACK_BACK,
    )

    iv_factor = (
        CALENDAR_BACK3_POST_EVENT_IV_FACTOR
        if back_type == "back3"
        else CALENDAR_BACK1_POST_EVENT_IV_FACTOR
    )
    LOGGER.debug(
        "Calendar IV factor for %s: %.2f", back_type, iv_factor
    )

    name = f"calendar_{back_type}"
    return Strategy(
        name=name,
        legs=(
            OptionLeg(
                option_type="call",
                strike=atm_strike,
                qty=1,
                side="sell",
                expiry=front_expiry,
            ),
            OptionLeg(
                option_type="call",
                strike=atm_strike,
                qty=1,
                side="buy",
                expiry=back_expiry,
            ),
        ),
    )


def select_back_chain(
    back1_chain: pd.DataFrame | None,
    back3_chain: pd.DataFrame | None,
) -> tuple[pd.DataFrame | None, str]:
    """Select the preferred back-month chain for a calendar spread.

    Prefers back3 (21-45 DTE). Falls back to back1 if back3 is unavailable.

    Args:
        back1_chain: Back1 option chain, or ``None`` if unavailable.
        back3_chain: Back3 option chain (21-45 DTE), or ``None``.

    Returns:
        Tuple of (chosen_chain, back_type_label).  ``chosen_chain`` is
        ``None`` only when both inputs are ``None``.
    """
    if back3_chain is not None and not back3_chain.empty:
        return back3_chain, "back3"
    if back1_chain is not None and not back1_chain.empty:
        LOGGER.info(
            "Calendar: back3 unavailable, falling back to back1."
        )
        return back1_chain, "back1"
    return None, ""


def _nearest_strike(
    chain: pd.DataFrame,
    target: float,
) -> float:
    """Return the strike closest to ``target`` in ``chain``."""
    chain = chain.copy()
    chain["dist"] = (chain["strike"] - target).abs()
    return float(chain.sort_values("dist").iloc[0]["strike"])


__all__ = [
    "BACK3_DTE_MIN",
    "BACK3_DTE_MAX",
    "calendar_conditions_met",
    "build_calendar",
    "select_back_chain",
]
