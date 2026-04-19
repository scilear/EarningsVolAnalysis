"""Tests for checked-in sample event manifests."""

from __future__ import annotations

from pathlib import Path

from event_option_playbook.backfill import load_event_manifest


def test_sample_nvda_manifest_loads_with_expected_sections() -> None:
    manifest_path = (
        Path(__file__).resolve().parents[2]
        / "research"
        / "earnings"
        / "sample_event_manifest_nvda_q1.json"
    )

    events = load_event_manifest(manifest_path)

    assert len(events) == 1
    event = events[0]
    assert event["event_family"] == "earnings"
    assert event["underlying_symbol"] == "NVDA"
    assert len(event["snapshot_bindings"]) == 1
    assert len(event["surface_metrics"]) == 1
    assert len(event["realized_outcomes"]) == 1
    assert len(event["structure_replays"]) == 1


def test_sample_cpi_manifest_loads_with_expected_sections() -> None:
    manifest_path = (
        Path(__file__).resolve().parents[2]
        / "research"
        / "macro"
        / "sample_event_manifest_cpi_qqq.json"
    )

    events = load_event_manifest(manifest_path)

    assert len(events) == 1
    event = events[0]
    assert event["event_family"] == "macro"
    assert event["event_name"] == "cpi"
    assert event["underlying_symbol"] == "QQQ"
    assert event["proxy_symbol"] == "TLT"
    assert len(event["snapshot_bindings"]) == 1
    assert len(event["surface_metrics"]) == 1
    assert len(event["realized_outcomes"]) == 1
    assert len(event["structure_replays"]) == 1
