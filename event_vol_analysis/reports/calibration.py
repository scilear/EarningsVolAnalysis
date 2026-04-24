# flake8: noqa: E501
"""Weekly calibration report generation for earnings outcomes."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from data.option_data_store import create_store

MIN_REPORT_OBSERVATIONS = 5
THRESHOLD_GATE_OBSERVATIONS = 20


@dataclass(frozen=True)
class CalibrationReport:
    """Summary statistics for weekly calibration review."""

    period: str
    n_complete: int
    edge_ratio_accuracy: dict[str, dict[str, float | int | None]]
    type_accuracy: dict[str, dict[str, float | int | None]]
    no_trade_miss_rate: float
    no_trade_condition_distribution: dict[str, int]
    decision_quality: dict[str, int]
    alerts: list[str]
    threshold_gate_met: bool


def run_calibration_report(
    db_path: Path | str = "data/options_intraday.db",
    output_dir: Path | str = "reports/calibration",
) -> CalibrationReport:
    """Run calibration loop, print summary, and save markdown output."""

    completed = _load_completed_outcomes(db_path)
    completed = _select_calibration_window(completed)

    n_complete = len(completed)
    period = _format_period(completed)
    gate_met = n_complete >= THRESHOLD_GATE_OBSERVATIONS
    alerts: list[str] = []

    if n_complete < MIN_REPORT_OBSERVATIONS:
        alerts.append(
            "INSUFFICIENT DATA: "
            f"{n_complete} completed records in calibration window; "
            f"minimum is {MIN_REPORT_OBSERVATIONS}."
        )
        report = CalibrationReport(
            period=period,
            n_complete=n_complete,
            edge_ratio_accuracy={},
            type_accuracy={},
            no_trade_miss_rate=0.0,
            no_trade_condition_distribution={},
            decision_quality={},
            alerts=alerts,
            threshold_gate_met=gate_met,
        )
        output_path = save_calibration_report(report, output_dir)
        print(render_console_summary(report))
        print(f"Saved calibration report: {output_path}")
        return report

    edge = _compute_edge_ratio_accuracy(completed, alerts)
    type_acc = _compute_type_accuracy(completed, alerts)
    miss_rate, no_trade_dist = _compute_no_trade_audit(completed, alerts)
    quality = _compute_decision_quality(completed)

    report = CalibrationReport(
        period=period,
        n_complete=n_complete,
        edge_ratio_accuracy=edge,
        type_accuracy=type_acc,
        no_trade_miss_rate=miss_rate,
        no_trade_condition_distribution=no_trade_dist,
        decision_quality=quality,
        alerts=alerts,
        threshold_gate_met=gate_met,
    )
    output_path = save_calibration_report(report, output_dir)
    print(render_console_summary(report))
    print(f"Saved calibration report: {output_path}")
    return report


def save_calibration_report(
    report: CalibrationReport,
    output_dir: Path | str = "reports/calibration",
) -> Path:
    """Save report to ``YYYY-WXX_calibration.md`` in output_dir."""

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    iso = dt.date.today().isocalendar()
    filename = f"{iso.year}-W{iso.week:02d}_calibration.md"
    out_path = out_dir / filename
    out_path.write_text(render_markdown_report(report), encoding="utf-8")
    return out_path


def render_markdown_report(report: CalibrationReport) -> str:
    """Render markdown body for a calibration report."""

    lines: list[str] = [
        "# Weekly Calibration Report",
        "",
        f"- Generated: {dt.datetime.now(dt.UTC).isoformat()}",
        f"- Period: {report.period}",
        f"- Completed outcomes: {report.n_complete}",
        "- Threshold gate (20 obs): "
        + ("MET" if report.threshold_gate_met else "NOT MET"),
    ]

    if report.n_complete < MIN_REPORT_OBSERVATIONS:
        lines.extend(["", "## Status", "", "INSUFFICIENT DATA", ""])
        for alert in report.alerts:
            lines.append(f"- {alert}")
        return "\n".join(lines) + "\n"

    lines.extend(["", "## Edge Ratio Accuracy", ""])
    lines.append("| Bucket | N | Accuracy | Mean Abs Error |")
    lines.append("| --- | ---: | ---: | ---: |")
    for bucket in sorted(report.edge_ratio_accuracy):
        item = report.edge_ratio_accuracy[bucket]
        n_obs = int(item.get("n", 0))
        accuracy = _format_pct(item.get("accuracy"))
        mae = _format_pct(item.get("mean_abs_error"))
        lines.append(f"| {bucket} | {n_obs} | {accuracy} | {mae} |")

    lines.extend(["", "## TYPE Accuracy", ""])
    lines.append("| TYPE Bucket | N | Accuracy |")
    lines.append("| --- | ---: | ---: |")
    for key in sorted(report.type_accuracy):
        item = report.type_accuracy[key]
        n_obs = int(item.get("n", 0))
        accuracy = _format_pct(item.get("accuracy"))
        lines.append(f"| {key} | {n_obs} | {accuracy} |")

    lines.extend(["", "## No-Trade Audit", ""])
    miss_rate = _format_pct(report.no_trade_miss_rate)
    miss_line = "- TYPE 5 miss rate (>1.3x conditional expected): " + miss_rate
    lines.append(miss_line)
    if report.no_trade_condition_distribution:
        lines.append("- No-trade condition distribution:")
        pairs = sorted(report.no_trade_condition_distribution.items())
        for key, count in pairs:
            lines.append(f"  - {key}: {count}")

    lines.extend(["", "## Decision Quality", ""])
    if report.decision_quality:
        keys = (
            "good_decision_good_outcome",
            "good_decision_bad_outcome",
            "bad_decision_good_outcome",
            "bad_decision_bad_outcome",
        )
        for key in keys:
            lines.append(f"- {key}: {report.decision_quality.get(key, 0)}")
    else:
        lines.append("- No entry_taken data available for decision quality.")

    lines.extend(["", "## Alerts", ""])
    if report.alerts:
        for alert in report.alerts:
            lines.append(f"- {alert}")
    else:
        lines.append("- None")

    return "\n".join(lines) + "\n"


def render_console_summary(report: CalibrationReport) -> str:
    """Render compact console summary."""

    lines = [
        "=== Weekly Calibration Summary ===",
        f"Period: {report.period}",
        f"Completed outcomes: {report.n_complete}",
        "Threshold gate: "
        + ("MET (>=20)" if report.threshold_gate_met else "NOT MET (<20)"),
    ]
    if report.n_complete < MIN_REPORT_OBSERVATIONS:
        lines.append("Status: INSUFFICIENT DATA")
        return "\n".join(lines)

    cheap = report.edge_ratio_accuracy.get("CHEAP", {})
    rich = report.edge_ratio_accuracy.get("RICH", {})
    cheap_acc = _format_pct(cheap.get("accuracy"))
    rich_acc = _format_pct(rich.get("accuracy"))
    cheap_n = int(cheap.get("n", 0))
    rich_n = int(rich.get("n", 0))
    lines.append(
        "Edge accuracy - "
        f"CHEAP: {cheap_acc} (n={cheap_n}), "
        f"RICH: {rich_acc} (n={rich_n})"
    )

    type1 = report.type_accuracy.get("TYPE_1", {})
    t4_overshoot = report.type_accuracy.get(
        "TYPE_4_POTENTIAL_OVERSHOOT",
        {},
    )
    t4_held = report.type_accuracy.get("TYPE_4_HELD_REPRICING", {})
    lines.append(
        "TYPE accuracy - "
        f"T1: {_format_pct(type1.get('accuracy'))}, "
        f"T4 overshoot: {_format_pct(t4_overshoot.get('accuracy'))}, "
        f"T4 held: {_format_pct(t4_held.get('accuracy'))}"
    )
    no_trade = _format_pct(report.no_trade_miss_rate)
    lines.append(f"No-trade miss rate: {no_trade}")
    lines.append(f"Alerts: {len(report.alerts)}")
    return "\n".join(lines)


def _load_completed_outcomes(db_path: Path | str) -> pd.DataFrame:
    """Load complete outcome rows from the sqlite store."""

    try:
        store = create_store(db_path)
        frame = store.get_earnings_outcomes()
    except Exception as exc:  # pragma: no cover
        message = f"Failed to load earnings outcomes from {db_path}"
        raise RuntimeError(message) from exc

    if frame.empty:
        return frame
    return frame[frame["outcome_complete"]].copy()


def _select_calibration_window(completed: pd.DataFrame) -> pd.DataFrame:
    """Use rolling 13 weeks, else full history if span is shorter."""

    if completed.empty:
        return completed

    frame = completed.copy()
    frame["event_date"] = pd.to_datetime(frame["event_date"]).dt.date
    min_date = min(frame["event_date"])
    max_date = max(frame["event_date"])
    if (max_date - min_date).days < 13 * 7:
        ordered = frame.sort_values(["event_date", "ticker"])
        return ordered.reset_index(drop=True)

    cutoff = max_date - dt.timedelta(weeks=13)
    subset = frame[frame["event_date"] >= cutoff]
    ordered_subset = subset.sort_values(["event_date", "ticker"])
    return ordered_subset.reset_index(drop=True)


def _format_period(completed: pd.DataFrame) -> str:
    """Format period as ISO week range."""

    if completed.empty:
        return "N/A"
    frame = completed.copy()
    frame["event_date"] = pd.to_datetime(frame["event_date"]).dt.date
    start = min(frame["event_date"])
    end = max(frame["event_date"])
    return f"{_iso_week(start)} to {_iso_week(end)}"


def _iso_week(day: dt.date) -> str:
    """Convert date to ``YYYY-Www`` label."""

    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _compute_edge_ratio_accuracy(
    frame: pd.DataFrame,
    alerts: list[str],
) -> dict[str, dict[str, float | int | None]]:
    """Compute CHEAP/RICH/FAIR bucket metrics and related alerts."""

    results: dict[str, dict[str, float | int | None]] = {}
    for label in ("CHEAP", "FAIR", "RICH"):
        subset = frame[frame["edge_ratio_label"].str.upper() == label].copy()
        subset = subset[
            subset["realized_move"].notna()
            & subset["implied_move"].notna()
            & (subset["implied_move"] > 0)
        ]
        n_obs = len(subset)
        if n_obs == 0:
            continue

        diff = (subset["realized_move"] - subset["implied_move"]).abs()
        abs_err = diff / subset["implied_move"]
        mae = float(abs_err.mean())

        if label == "RICH":
            rich_hit = subset["realized_move"] < subset["implied_move"]
            acc = float(rich_hit.mean())
        elif label == "CHEAP":
            cheap_hit = subset["realized_move"] > subset["implied_move"]
            acc = float(cheap_hit.mean())
        else:
            acc = float((abs_err <= 0.15).mean())

        results[label] = {
            "n": int(n_obs),
            "accuracy": acc,
            "mean_abs_error": mae,
        }
        if n_obs >= 5 and mae > 0.30:
            msg = "Edge ratio bucket " + label
            msg += " mean absolute error "
            msg += f"is {_format_pct(mae)}."
            alerts.append(_with_gate(msg, n_obs))

    return results


def _compute_type_accuracy(
    frame: pd.DataFrame,
    alerts: list[str],
) -> dict[str, dict[str, float | int | None]]:
    """Compute TYPE metrics including TYPE-4 subcategories."""

    out: dict[str, dict[str, float | int | None]] = {}

    def add_metric(
        key: str,
        subset: pd.DataFrame,
        success: pd.Series,
    ) -> None:
        n_obs = len(subset)
        if n_obs == 0:
            return
        acc = float(success.mean())
        out[key] = {"n": int(n_obs), "accuracy": acc}
        if n_obs >= 5 and acc < 0.50:
            msg = f"{key} accuracy dropped to {_format_pct(acc)}."
            alerts.append(_with_gate(msg, n_obs))

    t1 = frame[
        (frame["predicted_type"] == 1)
        & frame["realized_move"].notna()
        & frame["implied_move"].notna()
    ]
    if not t1.empty:
        add_metric("TYPE_1", t1, t1["realized_move"] > t1["implied_move"])

    t2 = frame[
        (frame["predicted_type"] == 2)
        & frame["realized_move"].notna()
        & frame["implied_move"].notna()
    ]
    if not t2.empty:
        add_metric("TYPE_2", t2, t2["realized_move"] < t2["implied_move"])

    t3 = frame[(frame["predicted_type"] == 3) & frame["pnl_if_entered"].notna()]
    if not t3.empty:
        add_metric("TYPE_3", t3, t3["pnl_if_entered"] > 0)

    t4 = frame[frame["predicted_type"] == 4]
    if not t4.empty:
        add_metric("TYPE_4", t4, t4.apply(_type4_success, axis=1))

    t4_overshoot = frame[
        (frame["predicted_type"] == 4)
        & (frame["phase1_category"] == "POTENTIAL_OVERSHOOT")
    ]
    if not t4_overshoot.empty:
        add_metric(
            "TYPE_4_POTENTIAL_OVERSHOOT",
            t4_overshoot,
            t4_overshoot.apply(_type4_success, axis=1),
        )

    t4_held = frame[
        (frame["predicted_type"] == 4) & (frame["phase1_category"] == "HELD_REPRICING")
    ]
    if not t4_held.empty:
        add_metric(
            "TYPE_4_HELD_REPRICING",
            t4_held,
            t4_held.apply(_type4_success, axis=1),
        )

    t5 = frame[frame["predicted_type"] == 5]
    if not t5.empty:
        add_metric("TYPE_5", t5, t5.apply(_no_trade_correct, axis=1))

    return out


def _compute_no_trade_audit(
    frame: pd.DataFrame,
    alerts: list[str],
) -> tuple[float, dict[str, int]]:
    """Compute TYPE-5 miss-rate and reason distribution."""

    t5 = frame[
        (frame["predicted_type"] == 5)
        & frame["realized_move"].notna()
        & frame["conditional_expected_move"].notna()
    ]
    if t5.empty:
        return 0.0, {}

    miss = t5["realized_move"] > 1.3 * t5["conditional_expected_move"]
    miss_rate = float(miss.mean())

    distribution: dict[str, int] = {}
    for reason in t5.apply(_infer_no_trade_reason, axis=1):
        distribution[reason] = distribution.get(reason, 0) + 1

    n_obs = len(t5)
    if n_obs >= 5 and miss_rate > 0.30:
        msg = "No-trade miss rate exceeded 30% for TYPE 5."
        alerts.append(_with_gate(msg, n_obs))

    return miss_rate, distribution


def _compute_decision_quality(frame: pd.DataFrame) -> dict[str, int]:
    """Compute decision-quality quadrants when entry data is present."""

    eligible = frame[frame["entry_taken"].notna()].copy()
    if eligible.empty:
        return {}

    counts = {
        "good_decision_good_outcome": 0,
        "good_decision_bad_outcome": 0,
        "bad_decision_good_outcome": 0,
        "bad_decision_bad_outcome": 0,
    }

    for _, row in eligible.iterrows():
        good_decision = _is_good_decision(row)
        good_outcome = _is_good_outcome(row)
        if good_decision and good_outcome:
            counts["good_decision_good_outcome"] += 1
        elif good_decision and not good_outcome:
            counts["good_decision_bad_outcome"] += 1
        elif not good_decision and good_outcome:
            counts["bad_decision_good_outcome"] += 1
        else:
            counts["bad_decision_bad_outcome"] += 1

    return counts


def _is_good_decision(row: pd.Series) -> bool:
    """Process-quality proxy; TYPE 5 is good decision by definition."""

    predicted_type = int(row.get("predicted_type", 5))
    if predicted_type == 5:
        return True
    confidence = str(row.get("predicted_confidence", "LOW")).upper()
    return confidence in {"HIGH", "MEDIUM"}


def _is_good_outcome(row: pd.Series) -> bool:
    """Outcome-quality proxy from pnl, else behavior match."""

    predicted_type = int(row.get("predicted_type", 5))
    entry_taken = row.get("entry_taken")
    pnl = _as_float(row.get("pnl_if_entered"))

    if entry_taken is True:
        if pnl is not None:
            return pnl > 0
        return _prediction_match(row)

    if predicted_type == 5 and entry_taken is False:
        return _no_trade_correct(row)

    if entry_taken is False:
        return not _prediction_match(row)

    return False


def _prediction_match(row: pd.Series) -> bool:
    """Return whether realized outcome matched TYPE thesis."""

    predicted_type = int(row.get("predicted_type", 5))
    realized = _as_float(row.get("realized_move"))
    implied = _as_float(row.get("implied_move"))

    if predicted_type == 1 and realized is not None and implied is not None:
        return realized > implied
    if predicted_type == 2 and realized is not None and implied is not None:
        return realized < implied
    if predicted_type == 3:
        pnl = _as_float(row.get("pnl_if_entered"))
        return pnl is not None and pnl > 0
    if predicted_type == 4:
        return _type4_success(row)
    if predicted_type == 5:
        return _no_trade_correct(row)
    return False


def _type4_success(row: pd.Series) -> bool:
    """Proxy TYPE-4 success from pnl or ratio/category fallback."""

    pnl = _as_float(row.get("pnl_if_entered"))
    if pnl is not None:
        return pnl > 0

    category = str(row.get("phase1_category") or "")
    ratio = _as_float(row.get("realized_vs_implied_ratio"))
    if category == "POTENTIAL_OVERSHOOT":
        return ratio is not None and ratio > 1.0
    if category == "HELD_REPRICING":
        return ratio is not None and ratio >= 1.0
    return False


def _no_trade_correct(row: pd.Series) -> bool:
    """No-trade correctness: move did not exceed 1.3x conditional move."""

    realized = _as_float(row.get("realized_move"))
    conditional = _as_float(row.get("conditional_expected_move"))
    if realized is None or conditional is None:
        return False
    return realized <= 1.3 * conditional


def _infer_no_trade_reason(row: pd.Series) -> str:
    """Infer dominant no-trade condition from stored fields."""

    vol_regime = str(row.get("vol_regime_label") or "").upper()
    edge_conf = str(row.get("edge_ratio_confidence") or "").upper()
    edge_label = str(row.get("edge_ratio_label") or "").upper()

    if vol_regime == "AMBIGUOUS":
        return "AMBIGUOUS_VOL"
    if edge_conf == "LOW":
        return "LOW_EDGE_CONFIDENCE"
    if edge_label == "FAIR":
        return "EFFICIENT_PRICING"
    return "OTHER"


def _with_gate(message: str, n_obs: int) -> str:
    """Append threshold gate language for small sample sizes."""

    if n_obs >= THRESHOLD_GATE_OBSERVATIONS:
        return message
    return (
        f"{message} PATTERN DETECTED - insufficient data for threshold "
        f"change ({n_obs}/{THRESHOLD_GATE_OBSERVATIONS} observations)."
    )


def _as_float(value: Any) -> float | None:
    """Convert optional numeric value to float."""

    if value is None or pd.isna(value):
        return None
    return float(value)


def _format_pct(value: float | int | None) -> str:
    """Format decimal value as percent string."""

    if value is None:
        return "N/A"
    return f"{float(value) * 100:.1f}%"
