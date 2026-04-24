"""Deterministic TYPE 1-5 classifier for earnings playbook snapshots."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

_MISSING = object()


@dataclass(frozen=True)
class TypeClassification:
    """Single TYPE decision with auditable rationale."""

    type: int
    rationale: list[str]
    action_guidance: str
    phase2_checklist: list[str] | None
    confidence: str
    is_no_trade: bool
    frequency_warning: bool


def classify_type(
    vol_regime: Any,
    edge_ratio: Any,
    positioning: Any,
    signal_graph: Any | None,
    event_state: dict[str, Any],
    operator_inputs: dict[str, Any] | None = None,
) -> TypeClassification:
    """Classify one name into TYPE 1..5 using deterministic rule checks."""

    if vol_regime is None:
        raise ValueError("vol_regime is required")
    if edge_ratio is None:
        raise ValueError("edge_ratio is required")
    if positioning is None:
        raise ValueError("positioning is required")

    required_event_keys = {
        "event_date",
        "today",
        "phase1_category",
        "phase1_metrics",
    }
    for key in required_event_keys:
        if key not in event_state:
            raise KeyError(key)

    operators = operator_inputs or {}
    rationale: list[str] = []

    event_date = _as_date(event_state["event_date"])
    today = _as_date(event_state["today"])
    pre_event = event_date > today
    post_event = event_date <= today

    vol_label = _normalize_text(_read(vol_regime, "label", "vol_regime"))
    vol_conf = _normalize_text(_read(vol_regime, "confidence", "vol_confidence_label"))
    ivr = _optional_float(_read(vol_regime, "ivr"))
    ivp = _optional_float(_read(vol_regime, "ivp"))

    edge_label = _normalize_text(_read(edge_ratio, "label"))
    edge_conf = _normalize_text(_read(edge_ratio, "confidence"))

    positioning_label = _normalize_text(_read(positioning, "label"))
    positioning_conf = _normalize_text(_read(positioning, "confidence"))
    drift_signal = _normalize_text(
        _read(
            _read(_read(positioning, "signals"), "drift"),
            "signal",
            default="NEUTRAL",
        )
    )

    narrative_label = _normalize_text(_read(operators, "narrative_label", default=None))
    falsifier = _read(operators, "falsifier", default=None)
    has_position = _read(operators, "has_position", default=None)

    # TYPE 1 checks
    t1_checks = [
        _check("TYPE 1: event not printed", pre_event),
        _check("TYPE 1: vol regime is CHEAP", vol_label == "CHEAP"),
        _check("TYPE 1: vol confidence is not LOW", vol_conf != "LOW"),
        _check("TYPE 1: edge ratio label is CHEAP", edge_label == "CHEAP"),
        _check("TYPE 1: edge ratio confidence is not LOW", edge_conf != "LOW"),
        _check(
            "TYPE 1: narrative label is UNCERTAIN",
            narrative_label == "UNCERTAIN",
        ),
        _check(
            "TYPE 1: drift signal not strongly directional",
            not (drift_signal in {"BULLISH", "BEARISH"} and positioning_conf == "HIGH"),
        ),
    ]
    rationale.extend(t1_checks)
    t1_match = all(_is_pass(item) for item in t1_checks)

    # TYPE 2 checks
    has_position_known = has_position is not None
    t2_checks = [
        _check("TYPE 2: event not printed", pre_event),
        _check("TYPE 2: vol regime is EXPENSIVE", vol_label == "EXPENSIVE"),
        _check(
            "TYPE 2: IVR > 80 and IVP > 80",
            ivr is not None and ivp is not None and ivr > 80.0 and ivp > 80.0,
        ),
        _check("TYPE 2: edge ratio label is RICH", edge_label == "RICH"),
        _check("TYPE 2: narrative label is PRICED", narrative_label == "PRICED"),
        _check("TYPE 2: has existing position", has_position is True),
    ]
    rationale.extend(t2_checks)
    if not has_position_known:
        rationale.append("FAIL: TYPE 2 blocked: portfolio ownership not confirmed")
    t2_match = all(_is_pass(item) for item in t2_checks)

    # TYPE 3 checks
    has_falsifier = isinstance(falsifier, str) and bool(falsifier.strip())
    t3_checks = [
        _check("TYPE 3: event not printed", pre_event),
        _check("TYPE 3: falsifier provided", has_falsifier),
    ]
    rationale.extend(t3_checks)
    if not has_falsifier:
        rationale.append(
            "FAIL: TYPE 3 blocked: no falsifiable trigger provided - defaults to TYPE 5"
        )
    t3_match = all(_is_pass(item) for item in t3_checks)

    # TYPE 4 checks
    phase1_category = _read(event_state, "phase1_category")
    phase1_metrics = _read(event_state, "phase1_metrics")
    t4_checks = [
        _check("TYPE 4: earnings have printed", post_event),
        _check("TYPE 4: phase1 category assessed", phase1_category is not None),
        _check("TYPE 4: edge confidence is not LOW", edge_conf != "LOW"),
    ]
    rationale.extend(t4_checks)
    t4_match = all(_is_pass(item) for item in t4_checks)

    if t1_match:
        return TypeClassification(
            type=1,
            rationale=rationale,
            action_guidance=(
                "Buy straddle or strangle with 7-10 DTE. Exit BEFORE print. "
                "No exceptions - this is a vol expansion trade, not an earnings bet."
            ),
            phase2_checklist=None,
            confidence="HIGH" if edge_conf == "HIGH" else "MEDIUM",
            is_no_trade=False,
            frequency_warning=True,
        )

    if t2_match:
        return TypeClassification(
            type=2,
            rationale=rationale,
            action_guidance=(
                "Sell covered call on existing position. Defined risk only. "
                "No naked short. Size by max loss, max 2% NAV."
            ),
            phase2_checklist=None,
            confidence="MEDIUM",
            is_no_trade=False,
            frequency_warning=False,
        )

    if t3_match:
        return TypeClassification(
            type=3,
            rationale=rationale,
            action_guidance=(
                "Buy small outright options only. Max 0.5% NAV. State falsifier "
                "at entry. Exit intraday if falsifier triggers. 2-day max hold."
            ),
            phase2_checklist=None,
            confidence="LOW",
            is_no_trade=False,
            frequency_warning=False,
        )

    if t4_match:
        phase2_checklist, action_guidance = _phase2_for_category(phase1_category)
        confidence = _type4_confidence(signal_graph, phase1_metrics, phase1_category)
        return TypeClassification(
            type=4,
            rationale=rationale,
            action_guidance=action_guidance,
            phase2_checklist=phase2_checklist,
            confidence=confidence,
            is_no_trade=False,
            frequency_warning=False,
        )

    no_trade_conditions = _type5_conditions(
        vol_label=vol_label,
        edge_conf=edge_conf,
        narrative_label=narrative_label,
        event_state=event_state,
        signal_graph=signal_graph,
        positioning_label=positioning_label,
        positioning_conf=positioning_conf,
        edge_label=edge_label,
        vol_conf=vol_conf,
    )
    for condition in no_trade_conditions:
        rationale.append(condition)

    if not no_trade_conditions:
        no_trade_conditions = [
            "FAIL: TYPE 5 explicit condition: no higher-priority TYPE conditions fully met"
        ]
        rationale.extend(no_trade_conditions)

    first_reason = no_trade_conditions[0].replace(
        "FAIL: TYPE 5 explicit condition: ", ""
    )
    return TypeClassification(
        type=5,
        rationale=rationale,
        action_guidance=f"No trade. Reason: {first_reason}",
        phase2_checklist=None,
        confidence="LOW",
        is_no_trade=True,
        frequency_warning=False,
    )


def _phase2_for_category(category: str) -> tuple[list[str], str]:
    """Return action and manual checklist for TYPE 4 subtype."""

    if category == "POTENTIAL_OVERSHOOT":
        return (
            [
                "Pre-market: price reversal continuing (not just close noise)?",
                "IV: crushing toward normal levels (not still elevated)?",
                (
                    "Signal graph: downstream follower has NOT already moved >50% "
                    "of upstream move?"
                ),
                "Volume: fading (not a new wave of directional volume)?",
                "Only enter if ALL four confirm. Limit order at mid. No chasing.",
            ],
            (
                "Potential fade candidate. Check pre-market: is reversal continuing? "
                "Is IV normalizing? Has downstream follower already absorbed signal? "
                "Enter next morning only if all three confirm."
            ),
        )
    if category == "HELD_REPRICING":
        return (
            [
                "Signal graph: identify downstream follower with FRESH signal",
                "Follower has NOT already moved >50% of upstream move?",
                "Follower's own pre-earnings IV is still stale (not repriced yet)?",
                "Enter follower next morning. Limit order at mid. 1-2% NAV.",
            ],
            (
                "Move held, repricing confirmed. Do NOT fade the printed name. "
                "Check if downstream follower has not yet repriced."
            ),
        )

    return (
        ["Phase 1 category must be POTENTIAL_OVERSHOOT or HELD_REPRICING."],
        "Post-earnings setup requires valid Phase 1 category.",
    )


def _type4_confidence(
    signal_graph: Any | None,
    phase1_metrics: Any,
    phase1_category: Any,
) -> str:
    """Compute TYPE 4 confidence using graph availability and freshness."""

    if phase1_category not in {"POTENTIAL_OVERSHOOT", "HELD_REPRICING"}:
        return "LOW"
    if not isinstance(phase1_metrics, dict) or not phase1_metrics:
        return "LOW"

    if signal_graph is None:
        return "MEDIUM"

    fresh_followers = _read(signal_graph, "tradeable_followers", default=[])
    if isinstance(fresh_followers, list) and len(fresh_followers) > 0:
        return "HIGH"
    return "MEDIUM"


def _type5_conditions(
    *,
    vol_label: str,
    edge_conf: str,
    narrative_label: str | None,
    event_state: dict[str, Any],
    signal_graph: Any | None,
    positioning_label: str,
    positioning_conf: str,
    edge_label: str,
    vol_conf: str,
) -> list[str]:
    """Evaluate explicit TYPE 5 no-trade conditions and return reasons."""

    reasons: list[str] = []

    if vol_label == "AMBIGUOUS":
        reasons.append("FAIL: TYPE 5 explicit condition: vol regime is AMBIGUOUS")
    if edge_conf == "LOW":
        reasons.append("FAIL: TYPE 5 explicit condition: edge ratio confidence is LOW")

    move_vs_implied = None
    phase1_metrics = _read(event_state, "phase1_metrics")
    if isinstance(phase1_metrics, dict):
        move_vs_implied = _optional_float(phase1_metrics.get("move_vs_implied"))
    if (
        move_vs_implied is not None
        and abs(move_vs_implied - 1.0) <= 0.10
        and narrative_label == "PRICED"
    ):
        reasons.append(
            "FAIL: TYPE 5 explicit condition: move approximately equals implied and narrative is PRICED"
        )

    absorbed_followers = []
    if signal_graph is not None:
        absorbed_followers = _read(signal_graph, "absorbed_followers", default=[])
    if isinstance(absorbed_followers, list) and len(absorbed_followers) > 0:
        reasons.append(
            "FAIL: TYPE 5 explicit condition: signal graph shows signal absorbed"
        )

    strong_layer = (vol_label in {"CHEAP", "EXPENSIVE"} and vol_conf != "LOW") or (
        edge_label in {"CHEAP", "RICH"} and edge_conf != "LOW"
    )
    if (
        positioning_label == "BALANCED"
        and positioning_conf == "LOW"
        and not strong_layer
    ):
        reasons.append(
            "FAIL: TYPE 5 explicit condition: positioning BALANCED/LOW with no other strong layer signal"
        )

    event_date = _as_date(_read(event_state, "event_date"))
    today = _as_date(_read(event_state, "today"))
    if event_date <= today and _read(event_state, "phase1_category") is None:
        reasons.append(
            "FAIL: TYPE 5 explicit condition: earnings printed but Phase 1 not assessed"
        )

    return reasons


def _as_date(value: Any) -> dt.date:
    """Normalize date-like values to date."""

    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if hasattr(value, "date"):
        return value.date()
    if isinstance(value, str):
        return dt.date.fromisoformat(value)
    raise TypeError(f"Unsupported date value: {value!r}")


def _check(message: str, passed: bool) -> str:
    """Format one rationale line from a boolean check."""

    prefix = "PASS" if passed else "FAIL"
    return f"{prefix}: {message}"


def _is_pass(line: str) -> bool:
    """Return whether rationale line is a passing condition."""

    return line.startswith("PASS:")


def _read(obj: Any, *keys: str, default: Any = _MISSING) -> Any:
    """Read value from dataclass-like object or mapping with fallback keys."""

    if obj is None:
        return default
    for key in keys:
        if isinstance(obj, dict) and key in obj:
            return obj[key]
        if hasattr(obj, key):
            return getattr(obj, key)
    if default is not _MISSING:
        return default
    joined = ", ".join(keys)
    raise KeyError(joined)


def _optional_float(value: Any) -> float | None:
    """Convert optional numeric input to float or None."""

    if value in (None, "", "N/A"):
        return None
    return float(value)


def _normalize_text(value: Any) -> str | None:
    """Normalize text-like fields for deterministic comparisons."""

    if value is None:
        return None
    if hasattr(value, "value"):
        return str(value.value).strip().upper()
    return str(value).strip().upper()
