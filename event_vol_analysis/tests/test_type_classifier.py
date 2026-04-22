"""Unit tests for deterministic TYPE 1-5 classifier."""

from __future__ import annotations

import datetime as dt

from event_vol_analysis.strategies.type_classifier import classify_type


def _event_state(
    *,
    event_date: dt.date,
    today: dt.date,
    phase1_category: str | None = None,
    phase1_metrics: dict | None = None,
) -> dict:
    return {
        "event_date": event_date,
        "today": today,
        "phase1_category": phase1_category,
        "phase1_metrics": phase1_metrics,
    }


def _vol(
    *,
    label: str = "CHEAP",
    confidence: str = "HIGH",
    ivr: float = 20.0,
    ivp: float = 20.0,
) -> dict:
    return {
        "label": label,
        "vol_regime": label,
        "confidence": confidence,
        "vol_confidence_label": confidence,
        "ivr": ivr,
        "ivp": ivp,
    }


def _edge(*, label: str = "CHEAP", confidence: str = "HIGH") -> dict:
    return {
        "label": label,
        "confidence": confidence,
    }


def _positioning(
    *,
    label: str = "BALANCED",
    confidence: str = "LOW",
    drift_signal: str = "NEUTRAL",
) -> dict:
    return {
        "label": label,
        "confidence": confidence,
        "signals": {
            "drift": {
                "signal": drift_signal,
            }
        },
    }


def test_type1_all_conditions_met() -> None:
    result = classify_type(
        vol_regime=_vol(label="CHEAP", confidence="HIGH"),
        edge_ratio=_edge(label="CHEAP", confidence="HIGH"),
        positioning=_positioning(label="BALANCED", confidence="LOW"),
        signal_graph=None,
        event_state=_event_state(
            event_date=dt.date(2026, 5, 1),
            today=dt.date(2026, 4, 1),
        ),
        operator_inputs={"narrative_label": "UNCERTAIN"},
    )
    assert result.type == 1
    assert result.frequency_warning is True


def test_type1_blocked_ambiguous_vol_regime() -> None:
    result = classify_type(
        vol_regime=_vol(label="AMBIGUOUS", confidence="LOW"),
        edge_ratio=_edge(label="CHEAP", confidence="HIGH"),
        positioning=_positioning(),
        signal_graph=None,
        event_state=_event_state(
            event_date=dt.date(2026, 5, 1),
            today=dt.date(2026, 4, 1),
        ),
        operator_inputs={"narrative_label": "UNCERTAIN"},
    )
    assert result.type == 5


def test_type1_blocked_low_edge_confidence() -> None:
    result = classify_type(
        vol_regime=_vol(),
        edge_ratio=_edge(label="CHEAP", confidence="LOW"),
        positioning=_positioning(),
        signal_graph=None,
        event_state=_event_state(
            event_date=dt.date(2026, 5, 1),
            today=dt.date(2026, 4, 1),
        ),
        operator_inputs={"narrative_label": "UNCERTAIN"},
    )
    assert result.type == 5


def test_type1_blocked_edge_not_cheap() -> None:
    result = classify_type(
        vol_regime=_vol(),
        edge_ratio=_edge(label="FAIR", confidence="HIGH"),
        positioning=_positioning(),
        signal_graph=None,
        event_state=_event_state(
            event_date=dt.date(2026, 5, 1),
            today=dt.date(2026, 4, 1),
        ),
        operator_inputs={"narrative_label": "UNCERTAIN"},
    )
    assert result.type == 5


def test_type1_blocked_narrative_not_uncertain() -> None:
    result = classify_type(
        vol_regime=_vol(),
        edge_ratio=_edge(),
        positioning=_positioning(),
        signal_graph=None,
        event_state=_event_state(
            event_date=dt.date(2026, 5, 1),
            today=dt.date(2026, 4, 1),
        ),
        operator_inputs={"narrative_label": "PRICED"},
    )
    assert result.type == 5


def test_type2_all_conditions_met() -> None:
    result = classify_type(
        vol_regime=_vol(label="EXPENSIVE", confidence="HIGH", ivr=90.0, ivp=92.0),
        edge_ratio=_edge(label="RICH", confidence="HIGH"),
        positioning=_positioning(),
        signal_graph=None,
        event_state=_event_state(
            event_date=dt.date(2026, 5, 1),
            today=dt.date(2026, 4, 1),
        ),
        operator_inputs={"narrative_label": "PRICED", "has_position": True},
    )
    assert result.type == 2


def test_type2_blocked_no_position_confirmed() -> None:
    result = classify_type(
        vol_regime=_vol(label="EXPENSIVE", ivr=90.0, ivp=90.0),
        edge_ratio=_edge(label="RICH"),
        positioning=_positioning(),
        signal_graph=None,
        event_state=_event_state(
            event_date=dt.date(2026, 5, 1),
            today=dt.date(2026, 4, 1),
        ),
        operator_inputs={"narrative_label": "PRICED", "has_position": None},
    )
    assert result.type == 5


def test_type2_blocked_ivr_below_80() -> None:
    result = classify_type(
        vol_regime=_vol(label="EXPENSIVE", ivr=65.0, ivp=90.0),
        edge_ratio=_edge(label="RICH"),
        positioning=_positioning(),
        signal_graph=None,
        event_state=_event_state(
            event_date=dt.date(2026, 5, 1),
            today=dt.date(2026, 4, 1),
        ),
        operator_inputs={"narrative_label": "PRICED", "has_position": True},
    )
    assert result.type == 5


def test_type3_with_falsifier() -> None:
    result = classify_type(
        vol_regime=_vol(label="NEUTRAL", confidence="LOW"),
        edge_ratio=_edge(label="FAIR", confidence="LOW"),
        positioning=_positioning(),
        signal_graph=None,
        event_state=_event_state(
            event_date=dt.date(2026, 5, 1),
            today=dt.date(2026, 4, 1),
        ),
        operator_inputs={"falsifier": "Guidance misses by >5%"},
    )
    assert result.type == 3


def test_type3_blocked_no_falsifier() -> None:
    result = classify_type(
        vol_regime=_vol(label="NEUTRAL", confidence="LOW"),
        edge_ratio=_edge(label="FAIR", confidence="LOW"),
        positioning=_positioning(),
        signal_graph=None,
        event_state=_event_state(
            event_date=dt.date(2026, 5, 1),
            today=dt.date(2026, 4, 1),
        ),
        operator_inputs={"falsifier": None},
    )
    assert result.type == 5


def test_type4_potential_overshoot_phase2_checklist() -> None:
    result = classify_type(
        vol_regime=_vol(label="NEUTRAL", confidence="HIGH"),
        edge_ratio=_edge(label="FAIR", confidence="MEDIUM"),
        positioning=_positioning(),
        signal_graph={"tradeable_followers": ["AXP"]},
        event_state=_event_state(
            event_date=dt.date(2026, 4, 1),
            today=dt.date(2026, 4, 2),
            phase1_category="POTENTIAL_OVERSHOOT",
            phase1_metrics={"vol_held": True},
        ),
        operator_inputs={},
    )
    assert result.type == 4
    assert result.phase2_checklist is not None


def test_type4_held_repricing_phase2_checklist() -> None:
    result = classify_type(
        vol_regime=_vol(label="NEUTRAL", confidence="HIGH"),
        edge_ratio=_edge(label="FAIR", confidence="MEDIUM"),
        positioning=_positioning(),
        signal_graph={"tradeable_followers": []},
        event_state=_event_state(
            event_date=dt.date(2026, 4, 1),
            today=dt.date(2026, 4, 2),
            phase1_category="HELD_REPRICING",
            phase1_metrics={"vol_held": True},
        ),
        operator_inputs={},
    )
    assert result.type == 4
    assert result.phase2_checklist is not None


def test_type4_blocked_phase1_not_assessed() -> None:
    result = classify_type(
        vol_regime=_vol(label="NEUTRAL", confidence="HIGH"),
        edge_ratio=_edge(label="FAIR", confidence="MEDIUM"),
        positioning=_positioning(),
        signal_graph=None,
        event_state=_event_state(
            event_date=dt.date(2026, 4, 1),
            today=dt.date(2026, 4, 2),
            phase1_category=None,
            phase1_metrics={"vol_held": True},
        ),
        operator_inputs={},
    )
    assert result.type == 5


def test_type4_blocked_low_edge_confidence() -> None:
    result = classify_type(
        vol_regime=_vol(label="NEUTRAL", confidence="HIGH"),
        edge_ratio=_edge(label="FAIR", confidence="LOW"),
        positioning=_positioning(),
        signal_graph=None,
        event_state=_event_state(
            event_date=dt.date(2026, 4, 1),
            today=dt.date(2026, 4, 2),
            phase1_category="HELD_REPRICING",
            phase1_metrics={"vol_held": True},
        ),
        operator_inputs={},
    )
    assert result.type == 5


def test_type5_ambiguous_vol() -> None:
    result = classify_type(
        vol_regime=_vol(label="AMBIGUOUS", confidence="LOW"),
        edge_ratio=_edge(label="FAIR", confidence="MEDIUM"),
        positioning=_positioning(),
        signal_graph=None,
        event_state=_event_state(
            event_date=dt.date(2026, 5, 1),
            today=dt.date(2026, 4, 1),
        ),
        operator_inputs={},
    )
    assert result.type == 5
    assert any("AMBIGUOUS" in line for line in result.rationale)


def test_type5_efficient_pricing() -> None:
    result = classify_type(
        vol_regime=_vol(label="NEUTRAL", confidence="HIGH"),
        edge_ratio=_edge(label="FAIR", confidence="MEDIUM"),
        positioning=_positioning(),
        signal_graph=None,
        event_state=_event_state(
            event_date=dt.date(2026, 5, 1),
            today=dt.date(2026, 4, 1),
            phase1_metrics={"move_vs_implied": 1.02},
        ),
        operator_inputs={"narrative_label": "PRICED"},
    )
    assert result.type == 5
    assert "No trade." in result.action_guidance


def test_type5_is_default_when_no_match() -> None:
    result = classify_type(
        vol_regime=_vol(label="NEUTRAL", confidence="MEDIUM"),
        edge_ratio=_edge(label="FAIR", confidence="MEDIUM"),
        positioning=_positioning(label="BALANCED", confidence="LOW"),
        signal_graph=None,
        event_state=_event_state(
            event_date=dt.date(2026, 5, 1),
            today=dt.date(2026, 4, 1),
        ),
        operator_inputs={},
    )
    assert result.type == 5


def test_rationale_always_populated() -> None:
    result = classify_type(
        vol_regime=_vol(label="NEUTRAL", confidence="MEDIUM"),
        edge_ratio=_edge(label="FAIR", confidence="MEDIUM"),
        positioning=_positioning(),
        signal_graph=None,
        event_state=_event_state(
            event_date=dt.date(2026, 5, 1),
            today=dt.date(2026, 4, 1),
        ),
        operator_inputs={},
    )
    assert len(result.rationale) > 0


def test_phase2_checklist_none_for_non_type4() -> None:
    result = classify_type(
        vol_regime=_vol(),
        edge_ratio=_edge(),
        positioning=_positioning(),
        signal_graph=None,
        event_state=_event_state(
            event_date=dt.date(2026, 5, 1),
            today=dt.date(2026, 4, 1),
        ),
        operator_inputs={"narrative_label": "UNCERTAIN"},
    )
    assert result.type == 1
    assert result.phase2_checklist is None


def test_frequency_warning_set_on_type1() -> None:
    result = classify_type(
        vol_regime=_vol(),
        edge_ratio=_edge(),
        positioning=_positioning(),
        signal_graph=None,
        event_state=_event_state(
            event_date=dt.date(2026, 5, 1),
            today=dt.date(2026, 4, 1),
        ),
        operator_inputs={"narrative_label": "UNCERTAIN"},
    )
    assert result.type == 1
    assert result.frequency_warning is True
