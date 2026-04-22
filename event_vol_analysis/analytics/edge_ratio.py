"""Edge-ratio helpers for implied versus conditional expected moves."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from event_vol_analysis.analytics.historical import ConditionalExpected


# Thresholds from earnings-playbook.md v1; review after 20+ observations in
# calibration loop (T031).
CHEAP_THRESHOLD = 0.8
RICH_THRESHOLD = 1.3

EDGE_RATIO_LOW_CONFIDENCE_CAVEAT = (
    "EDGE RATIO LOW CONFIDENCE: fewer than 6 observations or split sample. "
    "Treat as directional signal only - do not use as TYPE entry gate."
)


@dataclass(frozen=True)
class EdgeRatio:
    """Structured edge-ratio output for playbook move-pricing diagnostics."""

    implied: float
    conditional_expected_primary: float
    ratio: float
    label: str
    confidence: str
    secondary_ratio: float | None
    label_disagreement: bool
    note: str


def compute_edge_ratio(
    implied: float,
    conditional_expected: ConditionalExpected,
) -> EdgeRatio:
    """Compute implied/conditional expected ratio and playbook label."""

    primary = conditional_expected.primary_estimate
    if primary is None or float(primary) == 0.0:
        raise ValueError(
            "Cannot compute edge ratio: no valid conditional expected move"
        )

    implied_value = float(implied)
    primary_value = float(primary)
    ratio = implied_value / primary_value
    label = _label_from_ratio(ratio)

    secondary_ratio: float | None = None
    secondary_label: str | None = None
    if (
        conditional_expected.median is not None
        and float(conditional_expected.median) != 0.0
    ):
        secondary_ratio = implied_value / float(conditional_expected.median)
        secondary_label = _label_from_ratio(secondary_ratio)

    label_disagreement = secondary_label is not None and secondary_label != label
    confidence = str(conditional_expected.data_quality).upper()
    if label_disagreement:
        confidence = _downgrade_confidence(confidence)

    note = _build_note(conditional_expected, label_disagreement)
    return EdgeRatio(
        implied=implied_value,
        conditional_expected_primary=primary_value,
        ratio=ratio,
        label=label,
        confidence=confidence,
        secondary_ratio=secondary_ratio,
        label_disagreement=label_disagreement,
        note=note,
    )


def _label_from_ratio(ratio: float) -> str:
    """Map edge ratio to CHEAP/FAIR/RICH buckets."""

    if ratio < CHEAP_THRESHOLD and not np.isclose(ratio, CHEAP_THRESHOLD):
        return "CHEAP"
    if ratio > RICH_THRESHOLD and not np.isclose(ratio, RICH_THRESHOLD):
        return "RICH"
    return "FAIR"


def _downgrade_confidence(confidence: str) -> str:
    """Downgrade confidence by one level, with LOW as floor."""

    normalized = confidence.upper()
    if normalized == "HIGH":
        return "MEDIUM"
    if normalized == "MEDIUM":
        return "LOW"
    return "LOW"


def _build_note(
    conditional_expected: ConditionalExpected,
    label_disagreement: bool,
) -> str:
    """Build a concise note describing denominator choice and caveats."""

    if conditional_expected.recency_weighted is not None and (
        conditional_expected.primary_estimate == conditional_expected.recency_weighted
    ):
        denominator = "recency_weighted"
    elif conditional_expected.primary_estimate == conditional_expected.median:
        denominator = "median"
    else:
        denominator = "primary_estimate"

    note = f"denominator={denominator}"
    if conditional_expected.timing_method:
        note = f"{note}; timing={conditional_expected.timing_method}"
    if label_disagreement:
        note = f"{note}; primary/secondary label disagreement, confidence downgraded"
    return note
