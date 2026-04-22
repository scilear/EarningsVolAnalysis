"""Unit tests for edge ratio classification."""

from __future__ import annotations

import pytest

from event_vol_analysis.analytics.edge_ratio import compute_edge_ratio
from event_vol_analysis.analytics.historical import ConditionalExpected


def _conditional(
    *,
    primary: float | None,
    median: float | None = 0.05,
    quality: str = "HIGH",
) -> ConditionalExpected:
    primary_estimate = 0.0 if primary is None else primary
    return ConditionalExpected(
        median=0.0 if median is None else median,
        trimmed_mean=0.05,
        recency_weighted=primary if primary is not None else None,
        timing_method="combined",
        n_observations=12,
        data_quality=quality,
        conditioning_applied=[],
        primary_estimate=primary_estimate,
        peer_conditioned=None,
    )


def test_cheap_label() -> None:
    out = compute_edge_ratio(0.040, _conditional(primary=0.060))
    assert out.ratio == pytest.approx(0.6666667)
    assert out.label == "CHEAP"


def test_fair_label() -> None:
    out = compute_edge_ratio(0.050, _conditional(primary=0.050))
    assert out.ratio == pytest.approx(1.0)
    assert out.label == "FAIR"


def test_rich_label() -> None:
    out = compute_edge_ratio(0.080, _conditional(primary=0.050))
    assert out.ratio == pytest.approx(1.6)
    assert out.label == "RICH"


def test_boundary_at_0_8_is_fair() -> None:
    out = compute_edge_ratio(0.04, _conditional(primary=0.05))
    assert out.ratio == pytest.approx(0.8)
    assert out.label == "FAIR"


def test_boundary_at_1_3_is_fair() -> None:
    out = compute_edge_ratio(0.065, _conditional(primary=0.05))
    assert out.ratio == pytest.approx(1.3)
    assert out.label == "FAIR"


def test_confidence_high_inherited() -> None:
    out = compute_edge_ratio(0.05, _conditional(primary=0.05, quality="HIGH"))
    assert out.confidence == "HIGH"


def test_confidence_medium_inherited() -> None:
    out = compute_edge_ratio(0.05, _conditional(primary=0.05, quality="MEDIUM"))
    assert out.confidence == "MEDIUM"


def test_confidence_low_inherited() -> None:
    out = compute_edge_ratio(0.05, _conditional(primary=0.05, quality="LOW"))
    assert out.confidence == "LOW"


def test_label_disagreement_downgrades_confidence() -> None:
    conditional = ConditionalExpected(
        median=0.04,
        trimmed_mean=0.05,
        recency_weighted=0.05,
        timing_method="combined",
        n_observations=12,
        data_quality="HIGH",
        conditioning_applied=[],
        primary_estimate=0.05,
        peer_conditioned=None,
    )
    out = compute_edge_ratio(0.0524, conditional)
    assert out.label == "FAIR"
    assert out.secondary_ratio == pytest.approx(1.31)
    assert out.label_disagreement is True
    assert out.confidence == "MEDIUM"


def test_no_disagreement_confidence_unchanged() -> None:
    out = compute_edge_ratio(0.05, _conditional(primary=0.05, median=0.05))
    assert out.label_disagreement is False
    assert out.confidence == "HIGH"


def test_zero_conditional_raises() -> None:
    with pytest.raises(ValueError, match="no valid conditional expected move"):
        compute_edge_ratio(0.05, _conditional(primary=0.0))


def test_none_conditional_raises() -> None:
    out = _conditional(primary=None)
    with pytest.raises(ValueError, match="no valid conditional expected move"):
        compute_edge_ratio(0.05, out)


def test_note_field_populated() -> None:
    out = compute_edge_ratio(0.05, _conditional(primary=0.05))
    assert out.note


def test_secondary_ratio_present() -> None:
    out = compute_edge_ratio(0.05, _conditional(primary=0.05, median=0.05))
    assert out.secondary_ratio == pytest.approx(1.0)
