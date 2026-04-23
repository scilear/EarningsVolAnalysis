"""Macro-event vehicle classification and support notes.

This module centralizes support metadata for macro-event underlyings used in
regime diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MacroVehicleProfile:
    """Support profile for one macro-event vehicle."""

    ticker: str
    class_label: str
    supported: bool
    requires_forward_model: bool
    note: str | None


_SUPPORTED_ETFS = {
    "SPY",
    "XOP",
    "XLE",
}
_VIX_TICKERS = {
    "VIX",
    "^VIX",
    "VIXY",
    "UVXY",
}


def classify_macro_vehicle(ticker: str | None) -> MacroVehicleProfile:
    """Return support metadata for a macro-event vehicle ticker."""

    symbol = (ticker or "").strip().upper()
    if symbol in _SUPPORTED_ETFS:
        return MacroVehicleProfile(
            ticker=symbol,
            class_label="macro_etf",
            supported=True,
            requires_forward_model=False,
            note=None,
        )
    if symbol in _VIX_TICKERS:
        return MacroVehicleProfile(
            ticker=symbol,
            class_label="vol_index_proxy",
            supported=True,
            requires_forward_model=True,
            note=(
                "VIX-family options are forward-settled. Current GEX uses "
                "spot-proxy scaling; treat directionality as qualitative."
            ),
        )
    if not symbol:
        return MacroVehicleProfile(
            ticker="",
            class_label="unknown",
            supported=False,
            requires_forward_model=False,
            note="No ticker provided for macro vehicle classification.",
        )
    return MacroVehicleProfile(
        ticker=symbol,
        class_label="other",
        supported=False,
        requires_forward_model=False,
        note=(
            f"{symbol} is not in the validated macro vehicle set "
            "(SPY, XOP, XLE, VIX-family)."
        ),
    )
