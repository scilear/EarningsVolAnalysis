"""Positioning proxies for earnings setups.

OI does not equal directional conviction. P/C ratios are distorted by hedging
and structured products. Max pain is noise at a 10-day horizon. These are
weak proxies - use as tiebreaker only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd


class PositioningSignal(str, Enum):
    """Direction labels for individual positioning proxies."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class SignalResult:
    """One positioning sub-signal with availability metadata."""

    signal: PositioningSignal
    is_available: bool
    note: str


@dataclass(frozen=True)
class PositioningResult:
    """Consensus classification over four positioning proxy signals."""

    label: str
    direction: str | None
    confidence: str
    signals: dict[str, SignalResult]
    available_count: int
    note: str


def oi_concentration(chain: pd.DataFrame) -> SignalResult:
    """Classify call/put OI concentration at top strikes."""

    if chain.empty:
        return SignalResult(
            signal=PositioningSignal.NEUTRAL,
            is_available=False,
            note="empty chain",
        )
    if "openInterest" not in chain.columns:
        return SignalResult(
            signal=PositioningSignal.NEUTRAL,
            is_available=False,
            note="openInterest column missing",
        )
    if "option_type" not in chain.columns:
        return SignalResult(
            signal=PositioningSignal.NEUTRAL,
            is_available=False,
            note="option_type column missing",
        )

    oi = pd.to_numeric(chain["openInterest"], errors="coerce").fillna(0.0)
    if float(oi.sum()) <= 0.0:
        return SignalResult(
            signal=PositioningSignal.NEUTRAL,
            is_available=False,
            note="OI all zero",
        )

    normalized = chain.copy()
    normalized["openInterest"] = oi
    normalized["option_type"] = normalized["option_type"].astype(str).str.lower()

    call_group = (
        normalized[normalized["option_type"] == "call"]
        .groupby("strike", as_index=True)["openInterest"]
        .sum()
    )
    put_group = (
        normalized[normalized["option_type"] == "put"]
        .groupby("strike", as_index=True)["openInterest"]
        .sum()
    )

    total_call = float(call_group.sum())
    total_put = float(put_group.sum())

    bullish = _side_concentration_signal(
        own=call_group,
        other=put_group,
        own_total=total_call,
    )
    bearish = _side_concentration_signal(
        own=put_group,
        other=call_group,
        own_total=total_put,
    )

    if bullish:
        return SignalResult(
            signal=PositioningSignal.BULLISH,
            is_available=True,
            note="top-3 call OI concentrated and dominates puts at same strikes",
        )
    if bearish:
        return SignalResult(
            signal=PositioningSignal.BEARISH,
            is_available=True,
            note="top-3 put OI concentrated and dominates calls at same strikes",
        )
    return SignalResult(
        signal=PositioningSignal.NEUTRAL,
        is_available=True,
        note="no directional OI concentration",
    )


def pc_ratio_signal(
    pc_5d: float | None,
    pc_20d_avg: float | None,
) -> SignalResult:
    """Classify recent put/call ratio versus trailing baseline."""

    if pc_5d is None or pc_20d_avg is None:
        return SignalResult(
            signal=PositioningSignal.NEUTRAL,
            is_available=False,
            note="missing put/call inputs",
        )

    baseline = float(pc_20d_avg)
    current = float(pc_5d)
    if baseline <= 0.0:
        return SignalResult(
            signal=PositioningSignal.NEUTRAL,
            is_available=False,
            note="invalid 20d put/call baseline",
        )

    if current > 1.2 * baseline:
        return SignalResult(
            signal=PositioningSignal.BEARISH,
            is_available=True,
            note="5d put/call ratio above 1.2x baseline",
        )
    if current < 0.8 * baseline:
        return SignalResult(
            signal=PositioningSignal.BULLISH,
            is_available=True,
            note="5d put/call ratio below 0.8x baseline",
        )
    return SignalResult(
        signal=PositioningSignal.NEUTRAL,
        is_available=True,
        note="put/call ratio within neutral band",
    )


def drift_vs_sector(
    ticker_10d_ret: float | None,
    sector_10d_ret: float | None,
) -> SignalResult:
    """Classify relative 10-day drift versus sector benchmark."""

    if ticker_10d_ret is None or sector_10d_ret is None:
        return SignalResult(
            signal=PositioningSignal.NEUTRAL,
            is_available=False,
            note="missing ticker/sector drift inputs",
        )

    ticker_ret = float(ticker_10d_ret)
    sector_ret = float(sector_10d_ret)
    relative = ticker_ret - sector_ret

    if np.isclose(sector_ret, 0.0):
        threshold = 0.02
        threshold_note = "sector flat fallback threshold 2%"
    else:
        threshold = 2.0 * abs(sector_ret)
        threshold_note = "relative threshold 2x |sector return|"

    if relative > threshold:
        return SignalResult(
            signal=PositioningSignal.BULLISH,
            is_available=True,
            note=f"relative drift {relative:.4f} > {threshold:.4f} ({threshold_note})",
        )
    if relative < -threshold:
        return SignalResult(
            signal=PositioningSignal.BEARISH,
            is_available=True,
            note=f"relative drift {relative:.4f} < -{threshold:.4f} ({threshold_note})",
        )
    return SignalResult(
        signal=PositioningSignal.NEUTRAL,
        is_available=True,
        note=f"relative drift {relative:.4f} within threshold {threshold:.4f}",
    )


def max_pain_distance(chain: pd.DataFrame, spot: float) -> SignalResult:
    """Classify direction from max-pain strike distance versus spot."""

    if chain.empty:
        return SignalResult(
            signal=PositioningSignal.NEUTRAL,
            is_available=False,
            note="empty chain",
        )
    if spot <= 0:
        return SignalResult(
            signal=PositioningSignal.NEUTRAL,
            is_available=False,
            note="invalid spot",
        )
    if "openInterest" not in chain.columns or "option_type" not in chain.columns:
        return SignalResult(
            signal=PositioningSignal.NEUTRAL,
            is_available=False,
            note="missing openInterest/option_type",
        )

    normalized = chain.copy()
    normalized["openInterest"] = pd.to_numeric(
        normalized["openInterest"], errors="coerce"
    ).fillna(0.0)
    normalized = normalized[normalized["openInterest"] > 0.0]
    if normalized.empty:
        return SignalResult(
            signal=PositioningSignal.NEUTRAL,
            is_available=False,
            note="no positive OI rows",
        )

    try:
        max_pain_strike = _compute_max_pain_strike(normalized)
    except ValueError:
        return SignalResult(
            signal=PositioningSignal.NEUTRAL,
            is_available=False,
            note="max pain computation degenerate",
        )

    distance = (max_pain_strike - float(spot)) / float(spot)
    if distance > 0.03:
        return SignalResult(
            signal=PositioningSignal.BULLISH,
            is_available=True,
            note=(f"max pain {max_pain_strike:.2f} is {distance:.2%} above spot"),
        )
    if distance < -0.03:
        return SignalResult(
            signal=PositioningSignal.BEARISH,
            is_available=True,
            note=(f"max pain {max_pain_strike:.2f} is {distance:.2%} below spot"),
        )
    return SignalResult(
        signal=PositioningSignal.NEUTRAL,
        is_available=True,
        note=f"max pain {max_pain_strike:.2f} within +/-3% of spot",
    )


def classify_positioning(
    oi: SignalResult,
    pc: SignalResult,
    drift: SignalResult,
    mp: SignalResult,
) -> PositioningResult:
    """Aggregate proxy signals into CROWDED/BALANCED/UNDER-POSITIONED."""

    signals = {
        "oi": oi,
        "pc": pc,
        "drift": drift,
        "max_pain": mp,
    }
    available = {name: sig for name, sig in signals.items() if sig.is_available}
    available_count = len(available)
    available_signals = [sig.signal for sig in available.values()]

    all_agree = len(set(available_signals)) == 1 if available_signals else False
    bullish_unanimous = all_agree and available_signals[0] == PositioningSignal.BULLISH
    bearish_unanimous = all_agree and available_signals[0] == PositioningSignal.BEARISH
    neutral_unanimous = all_agree and available_signals[0] == PositioningSignal.NEUTRAL

    if available_count >= 3 and (bullish_unanimous or bearish_unanimous):
        label = "CROWDED"
        direction = "UPSIDE" if bullish_unanimous else "DOWNSIDE"
    elif available_count >= 2 and neutral_unanimous:
        label = "UNDER-POSITIONED"
        direction = None
    else:
        label = "BALANCED"
        direction = None

    confidence = _consensus_confidence(available_count, all_agree)
    note = _build_positioning_note(
        signals=signals,
        label=label,
        direction=direction,
        available_count=available_count,
    )
    return PositioningResult(
        label=label,
        direction=direction,
        confidence=confidence,
        signals=signals,
        available_count=available_count,
        note=note,
    )


def _side_concentration_signal(
    own: pd.Series,
    other: pd.Series,
    own_total: float,
) -> bool:
    """Return True when one side is concentrated and dominates same strikes."""

    if own_total <= 0.0:
        return False

    top = own.sort_values(ascending=False).head(3)
    top_sum = float(top.sum())
    own_share = float(top.sum()) / own_total
    if own_share <= 0.40:
        return False

    overlap_strikes = list(top.index)
    other_overlap = float(other.reindex(overlap_strikes).fillna(0.0).sum())
    return top_sum > (2.0 * other_overlap)


def _compute_max_pain_strike(chain: pd.DataFrame) -> float:
    """Compute strike that minimizes writer losses over chain OI."""

    if "strike" not in chain.columns:
        raise ValueError("strike column missing")

    normalized = chain.copy()
    normalized["option_type"] = normalized["option_type"].astype(str).str.lower()
    strikes = sorted({float(value) for value in normalized["strike"].dropna().tolist()})
    if not strikes:
        raise ValueError("no strikes")

    min_loss: float | None = None
    min_strike = strikes[0]
    for candidate in strikes:
        total_loss = 0.0
        for _, row in normalized.iterrows():
            strike = float(row["strike"])
            oi = float(row["openInterest"])
            if row["option_type"] == "call":
                loss = max(candidate - strike, 0.0) * oi
            else:
                loss = max(strike - candidate, 0.0) * oi
            total_loss += loss
        if min_loss is None or total_loss < min_loss:
            min_loss = total_loss
            min_strike = candidate

    return float(min_strike)


def _consensus_confidence(available_count: int, all_agree: bool) -> str:
    """Map availability + agreement to HIGH/MEDIUM/LOW confidence."""

    if all_agree and available_count == 4:
        return "HIGH"
    if all_agree and available_count == 3:
        return "MEDIUM"
    return "LOW"


def _build_positioning_note(
    *,
    signals: dict[str, SignalResult],
    label: str,
    direction: str | None,
    available_count: int,
) -> str:
    """Build a compact human-readable signal summary."""

    parts = [
        f"oi={signals['oi'].signal.value}",
        f"pc={signals['pc'].signal.value}",
        f"drift={signals['drift'].signal.value}",
        f"max_pain={signals['max_pain'].signal.value}",
    ]
    tail = f"{label}"
    if direction is not None:
        tail = f"{tail} {direction}"
    return f"available={available_count}/4; {', '.join(parts)}; consensus={tail}"
