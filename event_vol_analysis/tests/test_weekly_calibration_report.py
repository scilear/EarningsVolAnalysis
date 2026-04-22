"""Tests for weekly calibration reporting (T031)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from data.option_data_store import create_store
from event_vol_analysis.reports.calibration import run_calibration_report


def _seed_complete(
    db_path: Path,
    *,
    ticker: str,
    event_date: dt.date,
    predicted_type: int,
    predicted_confidence: str = "HIGH",
    edge_label: str = "CHEAP",
    edge_confidence: str = "MEDIUM",
    vol_regime_label: str = "CHEAP",
    implied_move: float = 0.05,
    conditional_expected_move: float = 0.05,
    realized_move: float = 0.06,
    phase1_category: str = "NOT_ASSESSED",
    entry_taken: bool = True,
    pnl_if_entered: float | None = 1.0,
) -> None:
    """Insert one complete outcome row for calibration tests."""

    store = create_store(db_path)
    timestamp = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)
    store.store_earnings_prediction(
        ticker=ticker,
        event_date=event_date,
        timing="AMC",
        analysis_timestamp=timestamp,
        predicted_type=predicted_type,
        predicted_confidence=predicted_confidence,
        edge_ratio_label=edge_label,
        edge_ratio_value=1.0,
        edge_ratio_confidence=edge_confidence,
        vol_regime_label=vol_regime_label,
        implied_move=implied_move,
        conditional_expected_move=conditional_expected_move,
    )
    ratio = realized_move / implied_move if implied_move > 0 else None
    direction = "UP" if realized_move >= 0 else "DOWN"
    store.set_earnings_realized_move(
        ticker=ticker,
        event_date=event_date,
        realized_move=abs(realized_move),
        realized_move_direction=direction,
        realized_vs_implied_ratio=ratio,
    )
    store.update_earnings_outcome(
        ticker=ticker,
        event_date=event_date,
        phase1_category=phase1_category,
        entry_taken=entry_taken,
        pnl_if_entered=pnl_if_entered,
    )


def _date_at(index: int) -> dt.date:
    """Return deterministic event dates for fixtures."""

    return dt.date(2026, 1, 1) + dt.timedelta(days=index)


def test_insufficient_data_warning_below_5(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"
    output_dir = tmp_path / "reports"

    for i in range(4):
        _seed_complete(
            db_path,
            ticker=f"A{i}",
            event_date=_date_at(i),
            predicted_type=1,
        )

    report = run_calibration_report(db_path=db_path, output_dir=output_dir)
    assert report.n_complete == 4
    assert any("INSUFFICIENT DATA" in text for text in report.alerts)


def test_edge_ratio_accuracy_rich_bucket(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"

    realized = [0.03, 0.02, 0.04, 0.01, 0.06]
    for i, move in enumerate(realized):
        _seed_complete(
            db_path,
            ticker=f"R{i}",
            event_date=_date_at(i),
            predicted_type=2,
            edge_label="RICH",
            implied_move=0.05,
            realized_move=move,
        )

    report = run_calibration_report(db_path=db_path, output_dir=tmp_path)
    assert report.edge_ratio_accuracy["RICH"]["n"] == 5
    assert report.edge_ratio_accuracy["RICH"]["accuracy"] == pytest.approx(0.8)


def test_edge_ratio_accuracy_cheap_bucket(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"

    realized = [0.06, 0.07, 0.08, 0.04, 0.03]
    for i, move in enumerate(realized):
        _seed_complete(
            db_path,
            ticker=f"C{i}",
            event_date=_date_at(i),
            predicted_type=1,
            edge_label="CHEAP",
            implied_move=0.05,
            realized_move=move,
        )

    report = run_calibration_report(db_path=db_path, output_dir=tmp_path)
    assert report.edge_ratio_accuracy["CHEAP"]["n"] == 5
    assert report.edge_ratio_accuracy["CHEAP"]["accuracy"] == pytest.approx(
        0.6
    )


def test_type_accuracy_type1(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"

    realized = [0.07, 0.08, 0.06, 0.02, 0.03]
    for i, move in enumerate(realized):
        _seed_complete(
            db_path,
            ticker=f"T1{i}",
            event_date=_date_at(i),
            predicted_type=1,
            implied_move=0.05,
            realized_move=move,
        )

    report = run_calibration_report(db_path=db_path, output_dir=tmp_path)
    assert report.type_accuracy["TYPE_1"]["accuracy"] == pytest.approx(0.6)


def test_type_accuracy_type4_overshoot(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"

    pnl_values = [2.0, 1.5, 1.0, -0.5, -1.0]
    for i, pnl in enumerate(pnl_values):
        _seed_complete(
            db_path,
            ticker=f"O{i}",
            event_date=_date_at(i),
            predicted_type=4,
            phase1_category="POTENTIAL_OVERSHOOT",
            pnl_if_entered=pnl,
        )

    report = run_calibration_report(db_path=db_path, output_dir=tmp_path)
    assert report.type_accuracy["TYPE_4_POTENTIAL_OVERSHOOT"]["n"] == 5
    assert report.type_accuracy["TYPE_4_POTENTIAL_OVERSHOOT"]["accuracy"] == (
        pytest.approx(0.6)
    )


def test_type_accuracy_type4_held(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"

    pnl_values = [2.0, 1.0, -0.5, 0.5, -1.0]
    for i, pnl in enumerate(pnl_values):
        _seed_complete(
            db_path,
            ticker=f"H{i}",
            event_date=_date_at(i),
            predicted_type=4,
            phase1_category="HELD_REPRICING",
            pnl_if_entered=pnl,
        )

    report = run_calibration_report(db_path=db_path, output_dir=tmp_path)
    assert report.type_accuracy["TYPE_4_HELD_REPRICING"]["n"] == 5
    assert report.type_accuracy["TYPE_4_HELD_REPRICING"]["accuracy"] == (
        pytest.approx(0.6)
    )


def test_no_trade_miss_rate_calculation(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"

    realized = [0.04, 0.05, 0.09, 0.08, 0.03]
    for i, move in enumerate(realized):
        _seed_complete(
            db_path,
            ticker=f"N{i}",
            event_date=_date_at(i),
            predicted_type=5,
            entry_taken=False,
            pnl_if_entered=None,
            implied_move=0.05,
            conditional_expected_move=0.05,
            realized_move=move,
        )

    report = run_calibration_report(db_path=db_path, output_dir=tmp_path)
    assert report.no_trade_miss_rate == pytest.approx(0.4)


def test_no_trade_condition_distribution(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"

    _seed_complete(
        db_path,
        ticker="NV1",
        event_date=_date_at(0),
        predicted_type=5,
        entry_taken=False,
        pnl_if_entered=None,
        vol_regime_label="AMBIGUOUS",
    )
    _seed_complete(
        db_path,
        ticker="NV2",
        event_date=_date_at(1),
        predicted_type=5,
        entry_taken=False,
        pnl_if_entered=None,
        vol_regime_label="AMBIGUOUS",
    )
    _seed_complete(
        db_path,
        ticker="NE1",
        event_date=_date_at(2),
        predicted_type=5,
        entry_taken=False,
        pnl_if_entered=None,
        edge_confidence="LOW",
    )
    _seed_complete(
        db_path,
        ticker="NE2",
        event_date=_date_at(3),
        predicted_type=5,
        entry_taken=False,
        pnl_if_entered=None,
        edge_confidence="LOW",
    )
    _seed_complete(
        db_path,
        ticker="NF1",
        event_date=_date_at(4),
        predicted_type=5,
        entry_taken=False,
        pnl_if_entered=None,
        edge_label="FAIR",
    )

    report = run_calibration_report(db_path=db_path, output_dir=tmp_path)
    assert report.no_trade_condition_distribution["AMBIGUOUS_VOL"] == 2
    assert report.no_trade_condition_distribution["LOW_EDGE_CONFIDENCE"] == 2
    assert report.no_trade_condition_distribution["EFFICIENT_PRICING"] == 1


def test_decision_quality_four_quadrants(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"

    _seed_complete(
        db_path,
        ticker="Q1",
        event_date=_date_at(0),
        predicted_type=1,
        predicted_confidence="HIGH",
        pnl_if_entered=2.0,
    )
    _seed_complete(
        db_path,
        ticker="Q2",
        event_date=_date_at(1),
        predicted_type=1,
        predicted_confidence="HIGH",
        pnl_if_entered=-1.0,
    )
    _seed_complete(
        db_path,
        ticker="Q3",
        event_date=_date_at(2),
        predicted_type=1,
        predicted_confidence="LOW",
        pnl_if_entered=1.0,
    )
    _seed_complete(
        db_path,
        ticker="Q4",
        event_date=_date_at(3),
        predicted_type=1,
        predicted_confidence="LOW",
        pnl_if_entered=-1.5,
    )
    _seed_complete(
        db_path,
        ticker="Q5",
        event_date=_date_at(4),
        predicted_type=2,
        predicted_confidence="HIGH",
        pnl_if_entered=0.5,
    )

    report = run_calibration_report(db_path=db_path, output_dir=tmp_path)
    assert report.decision_quality["good_decision_good_outcome"] == 2
    assert report.decision_quality["good_decision_bad_outcome"] == 1
    assert report.decision_quality["bad_decision_good_outcome"] == 1
    assert report.decision_quality["bad_decision_bad_outcome"] == 1


def test_threshold_gate_message_below_20(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"

    for i in range(5):
        _seed_complete(
            db_path,
            ticker=f"G{i}",
            event_date=_date_at(i),
            predicted_type=1,
            edge_label="CHEAP",
            implied_move=0.05,
            realized_move=0.01,
        )

    report = run_calibration_report(db_path=db_path, output_dir=tmp_path)
    joined = "\n".join(report.alerts)
    assert "PATTERN DETECTED" in joined
    assert "(5/20 observations)" in joined


def test_alert_fires_on_poor_accuracy(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"

    realized = [0.07, 0.08, 0.01, 0.02, 0.03]
    for i, move in enumerate(realized):
        _seed_complete(
            db_path,
            ticker=f"A{i}",
            event_date=_date_at(i),
            predicted_type=1,
            implied_move=0.05,
            realized_move=move,
        )

    report = run_calibration_report(db_path=db_path, output_dir=tmp_path)
    assert any("TYPE_1 accuracy dropped" in alert for alert in report.alerts)


def test_report_saved_to_calibration_dir(tmp_path: Path) -> None:
    db_path = tmp_path / "options.db"
    output_dir = tmp_path / "reports" / "calibration"

    for i in range(5):
        _seed_complete(
            db_path,
            ticker=f"S{i}",
            event_date=_date_at(i),
            predicted_type=1,
        )

    run_calibration_report(db_path=db_path, output_dir=output_dir)
    iso = dt.date.today().isocalendar()
    expected = output_dir / f"{iso.year}-W{iso.week:02d}_calibration.md"
    assert expected.exists()


def test_integration_run_with_10_records_prints_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "options.db"

    for i in range(10):
        _seed_complete(
            db_path,
            ticker=f"I{i}",
            event_date=_date_at(i),
            predicted_type=1 if i < 5 else 5,
            entry_taken=(i < 5),
            pnl_if_entered=1.0 if i < 3 else -1.0 if i < 5 else None,
            phase1_category="NOT_ASSESSED",
        )

    report = run_calibration_report(db_path=db_path, output_dir=tmp_path)
    out = capsys.readouterr().out
    assert report.n_complete == 10
    assert "Weekly Calibration Summary" in out
    assert "Saved calibration report:" in out
