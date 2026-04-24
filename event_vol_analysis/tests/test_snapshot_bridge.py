"""Tests for the legacy snapshot compatibility bridge."""

from __future__ import annotations

import datetime as dt

from event_option_playbook import (
    EventFamily,
    build_playbook_recommendation,
    ranked_results_to_candidates,
    snapshot_to_event_spec,
    snapshot_to_market_context,
)


def _snapshot() -> dict:
    return {
        "spot": 100.0,
        "event_date": dt.date(2026, 5, 28),
        "implied_move": 0.08,
        "historical_p75": 0.065,
        "front_iv": 0.75,
        "back_iv": 0.52,
        "event_vol_ratio": 0.64,
        "iv_ratio": 1.44,
        "rr25": "0.11",
        "bf25": "0.03",
        "gex_net": 1250000.0,
        "gex_abs": 3000000.0,
        "gamma_flip": 98.5,
        "min_oi": 250,
        "max_spread_pct": 0.05,
        "atm_width_pct": 0.01,
    }


def _ranked() -> list[dict]:
    return [
        {
            "strategy": "call_backspread",
            "score": 0.83,
            "ev": 42.0,
            "convexity": 2.1,
            "risk_classification": "defined_risk",
            "max_loss": -145.0,
            "legs": [
                {"expiry": "2026-05-30"},
                {"expiry": "2026-05-30"},
            ],
        },
        {
            "strategy": "iron_condor",
            "score": 0.61,
            "ev": 20.0,
            "convexity": 0.7,
            "risk_classification": "undefined_risk",
            "max_loss": -500.0,
            "legs": [
                {"expiry": "2026-05-30"},
            ],
        },
    ]


def test_snapshot_to_event_spec_builds_generic_earnings_event() -> None:
    event = snapshot_to_event_spec("NVDA", _snapshot())
    assert event.family == EventFamily.EARNINGS
    assert event.underlying == "NVDA"
    assert event.event_date == dt.date(2026, 5, 28)
    assert event.key == "earnings:nvda_earnings_2026-05-28:NVDA:2026-05-28"


def test_snapshot_to_market_context_maps_legacy_fields() -> None:
    context = snapshot_to_market_context(_snapshot())
    assert context.spot == 100.0
    assert round(context.implied_vs_history_ratio, 4) == round(0.08 / 0.065, 4)
    assert context.liquidity is not None
    assert context.liquidity.min_open_interest == 250
    assert context.gamma_flip == 98.5


def test_ranked_results_to_candidates_promotes_top_rows() -> None:
    candidates = ranked_results_to_candidates(_ranked(), top_n=1)
    assert len(candidates) == 1
    assert candidates[0].structure_name == "CALL_BACKSPREAD"
    assert "EV" in candidates[0].expected_edge


def test_build_playbook_recommendation_emits_recommendation() -> None:
    event = snapshot_to_event_spec("NVDA", _snapshot())
    context = snapshot_to_market_context(_snapshot())
    recommendation = build_playbook_recommendation(
        event,
        context,
        _ranked(),
        regime={
            "composite_regime": "Convex Breakout Setup",
            "gamma_regime": "Neutral Gamma",
        },
        not_applicable=[{"name": "POST_EVENT_CALENDAR"}],
    )
    assert recommendation.event_key == event.key
    assert not recommendation.is_no_trade
    assert recommendation.recommended[0].structure_name == "CALL_BACKSPREAD"
    assert recommendation.key_levels == ["Gamma flip: 98.50"]
    assert any(
        note.category == "blocked_structures" for note in recommendation.risk_notes
    )


def test_build_playbook_recommendation_returns_no_trade_when_empty() -> None:
    event = snapshot_to_event_spec("NVDA", _snapshot())
    context = snapshot_to_market_context(_snapshot())
    recommendation = build_playbook_recommendation(event, context, [])
    assert recommendation.is_no_trade
    assert recommendation.no_trade_reason is not None


def test_build_playbook_recommendation_returns_no_trade_when_trust_blocked() -> None:
    event = snapshot_to_event_spec("NVDA", _snapshot())
    blocked_snapshot = _snapshot() | {
        "trust_metrics": {
            "status": "FAIL",
            "ranking_allowed": False,
            "mismatch_ratio": 2.6,
        }
    }
    context = snapshot_to_market_context(blocked_snapshot)
    recommendation = build_playbook_recommendation(event, context, [])
    assert recommendation.is_no_trade
    assert recommendation.no_trade_reason is not None
