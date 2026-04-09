"""Reproducible earnings event workbook built on the event replay foundation."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from data.option_data_store import create_store


@dataclass(frozen=True)
class WorkbookConfig:
    """Configuration for the earnings research workbook."""

    db_path: str = "data/options_intraday.db"
    ticker: str | None = None
    horizon_code: str = "h1_close"
    metric_version: str = "v1"
    outcome_version: str = "v1"
    assumptions_version: str = "v1"


def load_earnings_event_dataset(config: WorkbookConfig) -> dict[str, pd.DataFrame]:
    """Load the earnings event dataset needed for the workbook."""

    ticker_filter = config.ticker.upper() if config.ticker else None
    store = create_store(config.db_path)
    with store._get_connection() as conn:
        events = pd.read_sql_query(
            """
            SELECT *
            FROM event_registry
            WHERE event_family = 'earnings'
              AND (? IS NULL OR underlying_symbol = ?)
            ORDER BY event_date, underlying_symbol
            """,
            conn,
            params=[ticker_filter, ticker_filter],
        )
        outcomes = pd.read_sql_query(
            """
            SELECT ero.*, er.underlying_symbol, er.event_name, er.event_date
            FROM event_realized_outcome ero
            JOIN event_registry er ON er.event_id = ero.event_id
            WHERE er.event_family = 'earnings'
              AND ero.horizon_code = ?
              AND ero.outcome_version = ?
              AND (? IS NULL OR er.underlying_symbol = ?)
            ORDER BY er.event_date, er.underlying_symbol
            """,
            conn,
            params=[
                config.horizon_code,
                config.outcome_version,
                ticker_filter,
                ticker_filter,
            ],
        )
        metrics = pd.read_sql_query(
            """
            SELECT esm.*, er.underlying_symbol, er.event_name, er.event_date
            FROM event_surface_metrics esm
            JOIN event_registry er ON er.event_id = esm.event_id
            WHERE er.event_family = 'earnings'
              AND esm.metric_version = ?
              AND (? IS NULL OR er.underlying_symbol = ?)
            ORDER BY er.event_date, er.underlying_symbol
            """,
            conn,
            params=[
                config.metric_version,
                ticker_filter,
                ticker_filter,
            ],
        )
        replays = pd.read_sql_query(
            """
            SELECT sro.*, er.underlying_symbol, er.event_name, er.event_date
            FROM structure_replay_outcome sro
            JOIN event_registry er ON er.event_id = sro.event_id
            WHERE er.event_family = 'earnings'
              AND sro.exit_horizon_code = ?
              AND sro.assumptions_version = ?
              AND (? IS NULL OR er.underlying_symbol = ?)
            ORDER BY er.event_date, er.underlying_symbol, sro.structure_code
            """,
            conn,
            params=[
                config.horizon_code,
                config.assumptions_version,
                ticker_filter,
                ticker_filter,
            ],
        )

    return {
        "events": events,
        "outcomes": outcomes,
        "metrics": metrics,
        "replays": replays,
    }


def summarize_realized_moves(outcomes: pd.DataFrame) -> dict[str, Any]:
    """Summarize realized earnings moves at the chosen horizon."""

    if outcomes.empty:
        return {
            "sample_size": 0,
            "mean_abs_move_pct": None,
            "median_abs_move_pct": None,
            "p75_abs_move_pct": None,
            "max_abs_move_pct": None,
        }

    abs_moves = outcomes["realized_move_abs_pct"].astype(float)
    return {
        "sample_size": int(len(outcomes)),
        "mean_abs_move_pct": float(abs_moves.mean()),
        "median_abs_move_pct": float(abs_moves.median()),
        "p75_abs_move_pct": float(abs_moves.quantile(0.75)),
        "max_abs_move_pct": float(abs_moves.max()),
    }


def summarize_iv_crush(outcomes: pd.DataFrame) -> dict[str, Any]:
    """Summarize post-event IV compression across the sample."""

    if outcomes.empty or "iv_crush_pct" not in outcomes.columns:
        return {
            "sample_size": 0,
            "mean_iv_crush_pct": None,
            "median_iv_crush_pct": None,
            "p75_iv_crush_pct": None,
        }

    valid = outcomes["iv_crush_pct"].dropna().astype(float)
    if valid.empty:
        return {
            "sample_size": 0,
            "mean_iv_crush_pct": None,
            "median_iv_crush_pct": None,
            "p75_iv_crush_pct": None,
        }
    return {
        "sample_size": int(len(valid)),
        "mean_iv_crush_pct": float(valid.mean()),
        "median_iv_crush_pct": float(valid.median()),
        "p75_iv_crush_pct": float(valid.quantile(0.75)),
    }


def summarize_structure_outcomes(replays: pd.DataFrame) -> list[dict[str, Any]]:
    """Summarize standardized structure replay outcomes by structure code."""

    if replays.empty:
        return []

    summary: list[dict[str, Any]] = []
    grouped = replays.groupby("structure_code", dropna=False)
    for structure_code, frame in grouped:
        realized = frame["realized_pnl"].astype(float)
        summary.append(
            {
                "structure_code": str(structure_code),
                "sample_size": int(len(frame)),
                "mean_realized_pnl": float(realized.mean()),
                "median_realized_pnl": float(realized.median()),
                "win_rate": float((realized > 0).mean()),
                "worst_realized_pnl": float(realized.min()),
                "best_realized_pnl": float(realized.max()),
            }
        )
    summary.sort(key=lambda row: row["mean_realized_pnl"], reverse=True)
    return summary


def summarize_surface_pricing(metrics: pd.DataFrame) -> dict[str, Any]:
    """Summarize pre-event surface conditions observed across the sample."""

    if metrics.empty:
        return {
            "sample_size": 0,
            "mean_implied_move_pct": None,
            "mean_event_variance_ratio": None,
            "mean_iv_ratio": None,
        }

    return {
        "sample_size": int(len(metrics)),
        "mean_implied_move_pct": float(metrics["implied_move_pct"].astype(float).mean()),
        "mean_event_variance_ratio": float(metrics["event_variance_ratio"].astype(float).mean()),
        "mean_iv_ratio": float(metrics["iv_ratio"].astype(float).mean()),
    }


def build_workbook_summary(config: WorkbookConfig) -> dict[str, Any]:
    """Build the full earnings workbook summary payload."""

    dataset = load_earnings_event_dataset(config)
    return {
        "config": asdict(config),
        "coverage": {
            "events": int(len(dataset["events"])),
            "outcomes": int(len(dataset["outcomes"])),
            "metrics": int(len(dataset["metrics"])),
            "replays": int(len(dataset["replays"])),
        },
        "realized_moves": summarize_realized_moves(dataset["outcomes"]),
        "iv_crush": summarize_iv_crush(dataset["outcomes"]),
        "surface_pricing": summarize_surface_pricing(dataset["metrics"]),
        "structure_outcomes": summarize_structure_outcomes(dataset["replays"]),
        "limitations": [
            "Results are only as complete as the registered event sample and bound snapshots.",
            "Missing replay rows mean structure comparisons are partial, not absent in reality.",
            "The current workbook is store-driven and does not fetch new data on demand.",
        ],
    }


def render_markdown(summary: dict[str, Any]) -> str:
    """Render the workbook summary into a concise markdown report."""

    lines = [
        "# Earnings Event Workbook",
        "",
        "## Configuration",
        "",
        f"- db_path: `{summary['config']['db_path']}`",
        f"- ticker: `{summary['config']['ticker']}`",
        f"- horizon_code: `{summary['config']['horizon_code']}`",
        f"- assumptions_version: `{summary['config']['assumptions_version']}`",
        "",
        "## Coverage",
        "",
        f"- events: {summary['coverage']['events']}",
        f"- outcomes: {summary['coverage']['outcomes']}",
        f"- metrics: {summary['coverage']['metrics']}",
        f"- replays: {summary['coverage']['replays']}",
        "",
        "## Realized Moves",
        "",
        f"- sample_size: {summary['realized_moves']['sample_size']}",
        f"- mean_abs_move_pct: {summary['realized_moves']['mean_abs_move_pct']}",
        f"- median_abs_move_pct: {summary['realized_moves']['median_abs_move_pct']}",
        f"- p75_abs_move_pct: {summary['realized_moves']['p75_abs_move_pct']}",
        "",
        "## IV Crush",
        "",
        f"- sample_size: {summary['iv_crush']['sample_size']}",
        f"- mean_iv_crush_pct: {summary['iv_crush']['mean_iv_crush_pct']}",
        f"- median_iv_crush_pct: {summary['iv_crush']['median_iv_crush_pct']}",
        f"- p75_iv_crush_pct: {summary['iv_crush']['p75_iv_crush_pct']}",
        "",
        "## Surface Pricing",
        "",
        f"- mean_implied_move_pct: {summary['surface_pricing']['mean_implied_move_pct']}",
        f"- mean_event_variance_ratio: {summary['surface_pricing']['mean_event_variance_ratio']}",
        f"- mean_iv_ratio: {summary['surface_pricing']['mean_iv_ratio']}",
        "",
        "## Structure Outcomes",
        "",
    ]
    if summary["structure_outcomes"]:
        for row in summary["structure_outcomes"]:
            lines.append(
                f"- {row['structure_code']}: "
                f"n={row['sample_size']}, "
                f"mean_pnl={row['mean_realized_pnl']}, "
                f"win_rate={row['win_rate']}"
            )
    else:
        lines.append("- No replay outcomes available yet.")

    lines.extend(
        [
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in summary["limitations"])
    return "\n".join(lines) + "\n"


def main() -> None:
    """CLI entry point for the earnings workbook."""

    parser = argparse.ArgumentParser(description="Earnings event workbook")
    parser.add_argument("--db", default="data/options_intraday.db")
    parser.add_argument("--ticker", default=None)
    parser.add_argument("--horizon", default="h1_close")
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--output-md", default=None)
    args = parser.parse_args()

    summary = build_workbook_summary(
        WorkbookConfig(
            db_path=args.db,
            ticker=args.ticker,
            horizon_code=args.horizon,
        )
    )

    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )
    if args.output_md:
        Path(args.output_md).write_text(
            render_markdown(summary),
            encoding="utf-8",
        )

    if not args.output_json and not args.output_md:
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
