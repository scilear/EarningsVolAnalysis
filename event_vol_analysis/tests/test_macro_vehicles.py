"""Tests for macro-event vehicle support classification."""

from __future__ import annotations

from event_vol_analysis.analytics.macro_vehicles import classify_macro_vehicle


def test_supported_macro_etf_vehicle() -> None:
    profile = classify_macro_vehicle("SPY")
    assert profile.supported is True
    assert profile.class_label == "macro_etf"
    assert profile.requires_forward_model is False
    assert profile.note is None


def test_vix_vehicle_requires_forward_model_note() -> None:
    profile = classify_macro_vehicle("VIX")
    assert profile.supported is True
    assert profile.class_label == "vol_index_proxy"
    assert profile.requires_forward_model is True
    assert profile.note is not None


def test_unknown_vehicle_not_supported() -> None:
    profile = classify_macro_vehicle("QQQ")
    assert profile.supported is False
    assert profile.class_label == "other"
    assert profile.note is not None
