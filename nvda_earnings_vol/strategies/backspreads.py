"""
Backspread strategy builder for earnings volatility events.

A backspread is a 1×2 ratio spread: SELL 1 near-ATM option, BUY 2 OTM
options of the same type. The structure profits from a large directional
move while capping losses near the short strike.

Entry conditions (all must be met):
    - iv_ratio (front_iv / back_iv) >= BACKSPREAD_MIN_IV_RATIO (1.40)
    - event_variance_ratio >= BACKSPREAD_MIN_EVENT_VAR_RATIO (0.50)
    - implied_move <= historical_p75 * BACKSPREAD_MAX_IMPLIED_OVER_P75 (0.90)
    - short_delta >= BACKSPREAD_MIN_SHORT_DELTA (0.08)

Both a call backspread and a put backspread are evaluated independently.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from nvda_earnings_vol.config import (
    BACK3_DTE_MIN,
    BACK3_DTE_MAX,
    BACKSPREAD_MAX_IMPLIED_OVER_P75,
    BACKSPREAD_MIN_EVENT_VAR_RATIO,
    BACKSPREAD_MIN_IV_RATIO,
    BACKSPREAD_MIN_SHORT_DELTA,
    BACKSPREAD_MIN_WING_WIDTH,
    BACKSPREAD_RATIO,
)
from nvda_earnings_vol.strategies.structures import OptionLeg, Strategy


LOGGER = logging.getLogger(__name__)


def backspread_conditions_met(snapshot: dict[str, Any]) -> bool:
    """Return True if all entry conditions for backspreads are satisfied.

    Conditions (all must pass):
    * ``iv_ratio`` (front_iv / back_iv) >= BACKSPREAD_MIN_IV_RATIO (1.40)
    * ``event_variance_ratio`` >= BACKSPREAD_MIN_EVENT_VAR_RATIO (0.50)
    * ``implied_move`` <= ``historical_p75`` × BACKSPREAD_MAX_IMPLIED_OVER_P75
    * ``short_delta`` >= BACKSPREAD_MIN_SHORT_DELTA (0.08)
    * ``back_dte`` in [BACK3_DTE_MIN, BACK3_DTE_MAX] (21–45 days) — ensures
      the long leg expiry is within the same window used by the data loader.
      This is a redundant guard: ``_select_back3_expiry()`` already filters
      to this range, so a mismatch here signals a data-wiring bug.

    Args:
        snapshot: Market snapshot dict. Required keys:
            ``iv_ratio``, ``event_variance_ratio``, ``implied_move``,
            ``historical_p75``, ``short_delta``, ``back_dte``.

    Returns:
        True when all five conditions are met.
    """
    iv_ratio = float(snapshot.get("iv_ratio", 0.0))
    event_var_ratio = float(snapshot.get("event_variance_ratio", 0.0))
    implied_move = float(snapshot.get("implied_move", 0.0))
    historical_p75 = float(snapshot.get("historical_p75", 1.0))
    short_delta = float(snapshot.get("short_delta", 0.0))
    back_dte = int(snapshot.get("back_dte", 0))

    iv_ok = iv_ratio >= BACKSPREAD_MIN_IV_RATIO
    event_ok = event_var_ratio >= BACKSPREAD_MIN_EVENT_VAR_RATIO
    pricing_ok = (
        implied_move <= historical_p75 * BACKSPREAD_MAX_IMPLIED_OVER_P75
    )
    delta_ok = short_delta >= BACKSPREAD_MIN_SHORT_DELTA
    dte_ok = BACK3_DTE_MIN <= back_dte <= BACK3_DTE_MAX

    if not iv_ok:
        LOGGER.debug(
            "Backspread gate: iv_ratio %.3f < %.2f",
            iv_ratio,
            BACKSPREAD_MIN_IV_RATIO,
        )
    if not event_ok:
        LOGGER.debug(
            "Backspread gate: event_var_ratio %.3f < %.2f",
            event_var_ratio,
            BACKSPREAD_MIN_EVENT_VAR_RATIO,
        )
    if not pricing_ok:
        LOGGER.debug(
            "Backspread gate: implied_move %.3f > p75 %.3f * %.2f",
            implied_move,
            historical_p75,
            BACKSPREAD_MAX_IMPLIED_OVER_P75,
        )
    if not delta_ok:
        LOGGER.debug(
            "Backspread gate: short_delta %.3f < %.2f",
            short_delta,
            BACKSPREAD_MIN_SHORT_DELTA,
        )
    if not dte_ok:
        LOGGER.debug(
            "Backspread gate: back_dte %d not in [%d, %d]",
            back_dte,
            BACK3_DTE_MIN,
            BACK3_DTE_MAX,
        )

    return iv_ok and event_ok and pricing_ok and delta_ok and dte_ok


def build_call_backspread(
    front_chain: pd.DataFrame,
    spot: float,
    front_expiry: pd.Timestamp,
) -> Strategy | None:
    """Build a 1×2 call backspread: SELL 1 ATM call, BUY 2 OTM calls.

    Args:
        front_chain: Front-month option chain DataFrame. Must include
            ``strike``, ``option_type``, and ``expiry`` columns.
        spot: Current underlying spot price.
        front_expiry: Front-month expiry timestamp for leg labelling.

    Returns:
        A :class:`Strategy` for the call backspread, or ``None`` if no
        OTM strike satisfying the minimum wing-width constraint exists.
    """
    short_strike, long_strike = _select_backspread_strikes(
        front_chain, spot, "call"
    )
    if short_strike is None or long_strike is None:
        LOGGER.warning("Call backspread: no valid strikes found.")
        return None

    sell_qty, buy_qty = BACKSPREAD_RATIO
    return Strategy(
        name="call_backspread",
        legs=(
            OptionLeg(
                option_type="call",
                strike=short_strike,
                qty=sell_qty,
                side="sell",
                expiry=front_expiry,
            ),
            OptionLeg(
                option_type="call",
                strike=long_strike,
                qty=buy_qty,
                side="buy",
                expiry=front_expiry,
            ),
        ),
    )


def build_put_backspread(
    front_chain: pd.DataFrame,
    spot: float,
    front_expiry: pd.Timestamp,
) -> Strategy | None:
    """Build a 1×2 put backspread: SELL 1 ATM put, BUY 2 OTM puts.

    Args:
        front_chain: Front-month option chain DataFrame. Must include
            ``strike``, ``option_type``, and ``expiry`` columns.
        spot: Current underlying spot price.
        front_expiry: Front-month expiry timestamp for leg labelling.

    Returns:
        A :class:`Strategy` for the put backspread, or ``None`` if no
        OTM strike satisfying the minimum wing-width constraint exists.
    """
    short_strike, long_strike = _select_backspread_strikes(
        front_chain, spot, "put"
    )
    if short_strike is None or long_strike is None:
        LOGGER.warning("Put backspread: no valid strikes found.")
        return None

    sell_qty, buy_qty = BACKSPREAD_RATIO
    return Strategy(
        name="put_backspread",
        legs=(
            OptionLeg(
                option_type="put",
                strike=short_strike,
                qty=sell_qty,
                side="sell",
                expiry=front_expiry,
            ),
            OptionLeg(
                option_type="put",
                strike=long_strike,
                qty=buy_qty,
                side="buy",
                expiry=front_expiry,
            ),
        ),
    )


def build_backspreads(
    snapshot: dict[str, Any],
    front_chain: pd.DataFrame,
    spot: float,
    front_expiry: pd.Timestamp,
) -> list[Strategy]:
    """Build call and put backspreads if entry conditions are met.

    Evaluates both call and put backspread constructions independently.
    Returns an empty list when entry conditions are not satisfied.

    Args:
        snapshot: Market snapshot dict (see :func:`backspread_conditions_met`).
        front_chain: Front-month option chain.
        spot: Current spot price.
        front_expiry: Front-month expiry timestamp.

    Returns:
        List of zero, one, or two :class:`Strategy` objects.
    """
    if not backspread_conditions_met(snapshot):
        LOGGER.info("Backspread entry conditions not met; skipping.")
        return []

    strategies: list[Strategy] = []
    call_bs = build_call_backspread(front_chain, spot, front_expiry)
    if call_bs is not None:
        strategies.append(call_bs)

    put_bs = build_put_backspread(front_chain, spot, front_expiry)
    if put_bs is not None:
        strategies.append(put_bs)

    LOGGER.info("Built %d backspread(s).", len(strategies))
    return strategies


# ── Internal helpers ───────────────────────────────────────────────────────


def _select_backspread_strikes(
    chain: pd.DataFrame,
    spot: float,
    option_type: str,
) -> tuple[float | None, float | None]:
    """Select short and long strikes for a backspread.

    Short strike is the ATM strike. Long strike is the first OTM strike
    beyond ``BACKSPREAD_MIN_WING_WIDTH`` from the short strike.

    Args:
        chain: Option chain with ``strike`` and ``option_type`` columns.
        spot: Current underlying price.
        option_type: ``"call"`` or ``"put"``.

    Returns:
        Tuple of (short_strike, long_strike).  Either element may be
        ``None`` if a valid strike cannot be found.
    """
    legs = chain[chain["option_type"] == option_type].copy()
    if legs.empty:
        return None, None

    legs["dist"] = (legs["strike"] - spot).abs()
    short_strike = float(legs.sort_values("dist").iloc[0]["strike"])

    if option_type == "call":
        # Long strike is above short strike (OTM call)
        candidates = legs[
            legs["strike"] >= short_strike + BACKSPREAD_MIN_WING_WIDTH
        ].sort_values("strike")
    else:
        # Long strike is below short strike (OTM put)
        candidates = legs[
            legs["strike"] <= short_strike - BACKSPREAD_MIN_WING_WIDTH
        ].sort_values("strike", ascending=False)

    if candidates.empty:
        return None, None

    long_strike = float(candidates.iloc[0]["strike"])
    return short_strike, long_strike


__all__ = [
    "BACK3_DTE_MIN",
    "BACK3_DTE_MAX",
    "backspread_conditions_met",
    "build_call_backspread",
    "build_put_backspread",
    "build_backspreads",
]
