"""Per-ticker parameter calibration from live market data.

All public functions return calibrated values derived from the option
chain and yfinance metadata.  Config defaults are always used as fallbacks
so test-mode callers are unaffected.

Two calibration phases:

1. ``calibrate_ticker_params()`` — called *before* chain filtering, on the
   raw (unfiltered) front-expiry chain plus yfinance ``.info``.  Produces
   liquidity filter thresholds, wing width, and GEX significance level.

2. ``calibrate_iv_scenarios()`` — called *after* event analytics are computed.
   Derives hard-crush and expansion scenario magnitudes from the event
   variance ratio and mutates ``config.IV_SCENARIOS`` in-place.  The
   ``base_crush`` scenario is market-data-relative and is left unchanged.
"""

from __future__ import annotations

import logging
import math

import pandas as pd
import yfinance as yf

from event_vol_analysis import config


LOGGER = logging.getLogger(__name__)


# ── Public API ────────────────────────────────────────────────────────────────


def calibrate_ticker_params(
    ticker: str,
    raw_chain: pd.DataFrame,
    spot: float,
) -> dict[str, float | int]:
    """Calibrate chain-level and market-level parameters from live data.

    Must be called on an *unfiltered* option chain so that the liquidity
    thresholds are derived from the full OI/spread distribution, not the
    already-filtered subset.

    Parameters derived
    ------------------
    ``min_oi``
        Minimum open-interest filter threshold (int).
    ``max_spread_pct``
        Maximum bid-ask spread as a fraction of mid (float).
    ``backspread_min_wing_width_pct``
        Minimum wing-width for backspread strike selection as a fraction
        of spot (float).
    ``gex_large_abs``
        GEX absolute threshold for regime classification (float).

    All values fall back to config defaults on any per-parameter failure.

    Args:
        ticker: Underlying ticker symbol (used for market cap lookup).
        raw_chain: Unfiltered combined option chain for the front expiry.
        spot: Current underlying spot price.

    Returns:
        Dict with keys ``min_oi``, ``max_spread_pct``,
        ``backspread_min_wing_width_pct``, ``gex_large_abs``.
    """
    result: dict[str, float | int] = {
        "min_oi": _min_oi(raw_chain, spot),
        "max_spread_pct": _max_spread_pct(raw_chain, spot),
        "backspread_min_wing_width_pct": _wing_width_pct(raw_chain, spot),
        "gex_large_abs": _gex_large_abs(ticker),
    }
    LOGGER.info(
        "Calibrated params for %s: min_oi=%d, max_spread_pct=%.3f, "
        "wing_width_pct=%.4f, gex_large_abs=%.2e",
        ticker,
        result["min_oi"],
        result["max_spread_pct"],
        result["backspread_min_wing_width_pct"],
        result["gex_large_abs"],
    )
    return result


def calibrate_iv_scenarios(
    front_iv: float,
    back_iv: float,
    event_variance_ratio: float,
) -> None:
    """Update IV scenario magnitudes from the event's vol structure.

    Mutates ``config.IV_SCENARIOS`` **in-place** so that ``payoff.py``
    (which holds a reference to the same dict object via
    ``from config import IV_SCENARIOS``) picks up the new values without
    any API changes to the payoff layer.

    The ``base_crush`` scenario is left unchanged — it already collapses
    the front IV to the back IV level, which is fully market-data-relative.

    Derivation
    ----------
    ``hard_crush`` front magnitude:
        Removing the event variance component from the front IV gives
        ``new_front_iv = front_iv × sqrt(1 − evr)``, so the relative
        change is ``sqrt(1 − evr) − 1`` (always ≤ 0).

    ``hard_crush`` back magnitude:
        Small residual crush proportional to event dominance:
        ``−max(0.03, evr × 0.12)``.

    ``expansion`` front magnitude:
        Scales inversely with event dominance; residual structural vol
        can expand on surprise events: ``0.05 + (1 − evr) × 0.08``.

    ``expansion`` back magnitude:
        ``0.03 + (1 − evr) × 0.03``.

    Args:
        front_iv: Front-month ATM IV (pre-event).
        back_iv: Back-month ATM IV.
        event_variance_ratio: Fraction of front-month variance attributable
            to the earnings event (0–1).
    """
    evr = max(0.0, min(1.0, event_variance_ratio))

    hard_crush_front = math.sqrt(1.0 - evr) - 1.0   # always ≤ 0
    hard_crush_back = -max(0.03, evr * 0.12)

    expansion_front = 0.05 + (1.0 - evr) * 0.08
    expansion_back = 0.03 + (1.0 - evr) * 0.03

    config.IV_SCENARIOS["hard_crush"] = {
        "front": round(hard_crush_front, 4),
        "back": round(hard_crush_back, 4),
    }
    config.IV_SCENARIOS["expansion"] = {
        "front": round(expansion_front, 4),
        "back": round(expansion_back, 4),
    }
    LOGGER.info(
        "Calibrated IV scenarios (evr=%.3f): "
        "hard_crush front=%.3f back=%.3f | "
        "expansion front=+%.3f back=+%.3f",
        evr,
        hard_crush_front,
        hard_crush_back,
        expansion_front,
        expansion_back,
    )


# ── Private helpers ───────────────────────────────────────────────────────────


def _atm_region(
    chain: pd.DataFrame, spot: float, width: float = 0.15
) -> pd.DataFrame:
    """Return rows where strike is within ±*width* fraction of *spot*."""
    lo = spot * (1.0 - width)
    hi = spot * (1.0 + width)
    return chain[(chain["strike"] >= lo) & (chain["strike"] <= hi)].copy()


def _min_oi(chain: pd.DataFrame, spot: float) -> int:
    """20th-percentile OI in the ATM ±15% region, clamped to [10, 200].

    Args:
        chain: Raw (unfiltered) option chain.
        spot: Current spot price.

    Returns:
        Calibrated minimum OI threshold, or ``config.MIN_OI`` on failure.
    """
    region = _atm_region(chain, spot)
    if region.empty or "openInterest" not in region.columns:
        LOGGER.warning("Cannot calibrate min_oi; using config default.")
        return config.MIN_OI
    oi = region["openInterest"].dropna()
    oi = oi[oi > 0]
    if oi.empty:
        LOGGER.warning("No positive OI found; using config default.")
        return config.MIN_OI
    val = int(oi.quantile(0.20))
    clamped = max(10, min(200, val))
    if clamped != val:
        LOGGER.debug("min_oi clamped %d → %d", val, clamped)
    return clamped


def _max_spread_pct(chain: pd.DataFrame, spot: float) -> float:
    """65th-percentile bid-ask spread% in ATM ±15%, clamped to [0.03, 0.20].

    Spread% is computed as ``(ask − bid) / mid`` for rows with positive mid.

    Args:
        chain: Raw (unfiltered) option chain.
        spot: Current spot price.

    Returns:
        Calibrated maximum spread-pct threshold, or ``config.MAX_SPREAD_PCT``
        on failure.
    """
    region = _atm_region(chain, spot)
    if region.empty:
        return config.MAX_SPREAD_PCT
    mid = (region["bid"].fillna(0.0) + region["ask"].fillna(0.0)) / 2.0
    spread = (
        region["ask"].fillna(0.0) - region["bid"].fillna(0.0)
    ).clip(lower=0.0)
    valid = mid > 0.0
    if not valid.any():
        return config.MAX_SPREAD_PCT
    spread_pct = spread[valid] / mid[valid]
    val = float(spread_pct.quantile(0.65))
    return max(0.03, min(0.20, val))


def _wing_width_pct(chain: pd.DataFrame, spot: float) -> float:
    """Minimum ATM-region strike spacing as % of spot, clamped to [0.005, 0.05].

    Ensures the backspread wing-width gate is at least one strike increment
    wide for this chain's specific strike ladder.

    Args:
        chain: Raw (unfiltered) option chain.
        spot: Current spot price.

    Returns:
        Calibrated wing-width threshold, or
        ``config.BACKSPREAD_MIN_WING_WIDTH_PCT`` on failure.
    """
    region = _atm_region(chain, spot)
    if region.empty or "strike" not in region.columns:
        return config.BACKSPREAD_MIN_WING_WIDTH_PCT
    strikes = sorted(region["strike"].unique())
    if len(strikes) < 2:
        return config.BACKSPREAD_MIN_WING_WIDTH_PCT
    min_spacing = min(b - a for a, b in zip(strikes, strikes[1:]))
    val = min_spacing / spot
    return max(0.005, min(0.05, val))


def _gex_large_abs(ticker: str) -> float:
    """Return 0.5% of market cap as the GEX significance threshold.

    A fixed dollar threshold (e.g. $1B) is meaningless across market caps.
    Using 0.5% of market cap scales the threshold to the OI footprint of
    the underlying: large-caps have proportionally larger GEX.

    Args:
        ticker: Underlying ticker symbol.

    Returns:
        Calibrated GEX threshold, or ``config.GEX_LARGE_ABS`` on failure.
    """
    try:
        info = yf.Ticker(ticker).info
        mkt_cap = info.get("marketCap")
        if mkt_cap and mkt_cap > 0:
            return float(mkt_cap) * 0.005
    except Exception as exc:
        LOGGER.warning(
            "Market cap fetch failed for %s: %s; "
            "using config default for gex_large_abs.",
            ticker,
            exc,
        )
    return config.GEX_LARGE_ABS


__all__ = ["calibrate_ticker_params", "calibrate_iv_scenarios"]
