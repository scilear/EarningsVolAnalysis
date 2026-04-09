"""Reproducible macro ETF event workbook built on the event replay foundation."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from data.option_data_store import create_store


@dataclass(frozen=True)
class MacroWorkbookConfig:
    """Configuration for the macro ETF research workbook."""

    db_path: str = "data/options_intraday.db"
    event_name: str = "cpi"
    proxy_symbol: str | None = None
    horizon_code: str = "h1_close"
    metric_version: str = "v1"
    outcome_version: str = "v1"
    assumptions_version: str = "v1"


def load_macro_event_dataset(config: MacroWorkbookConfig) -> dict[str, pd.DataFrame]:
    """Load the macro event dataset needed for the workbook."""

    proxy_filter = config.proxy_symbol.upper() if config.proxy_symbol else None
    store = create_store(config.db_path)
    with store._get_connection() as conn:
        events = pd.read_sql_query(
            """
            SELECT *
            FROM event_registry
            WHERE event_family = 'macro'
              AND event_name = ?
              AND (? IS NULL OR proxy_symbol = ?)
            ORDER BY event_date, proxy_symbol, underlying_symbol
            """,
            conn,
            params=[config.event_name, proxy_filter, proxy_filter],
        )
        outcomes = pd.read_sql_query(
            """
            SELECT ero.*, er.underlying_symbol, er.proxy_symbol, er.event_name, er.event_date
            FROM event_realized_outcome ero
            JOIN event_registry er ON er.event_id = ero.event_id
            WHERE er.event_family = 'macro'
              AND er.event_name = ?
              AND ero.horizon_code = ?
              AND ero.outcome_version = ?
              AND (? IS NULL OR er.proxy_symbol = ?)
            ORDER BY er.event_date, er.proxy_symbol, er.underlying_symbol
            """,
            conn,
            params=[
                config.event_name,
                config.horizon_code,
                config.outcome_version,
                proxy_filter,
                proxy_filter,
            ],
        )
        metrics = pd.read_sql_query(
            """
            SELECT esm.*, er.underlying_symbol, er.proxy_symbol, er.event_name, er.event_date
            FROM event_surface_metrics esm
            JOIN event_registry er ON er.event_id = esm.event_id
            WHERE er.event_family = 'macro'
              AND er.event_name = ?
              AND esm.metric_version = ?
              AND (? IS NULL OR er.proxy_symbol = ?)
            ORDER BY er.event_date, er.proxy_symbol, er.underlying_symbol
            """,
            conn,
            params=[
                config.event_name,
                config.metric_version,
                proxy_filter,
                proxy_filter,
            ],
        )
        replays = pd.read_sql_query(
            """
            SELECT sro.*, er.underlying_symbol, er.proxy_symbol, er.event_name, er.event_date
            FROM structure_replay_outcome sro
            JOIN event_registry er ON er.event_id = sro.event_id
            WHERE er.event_family = 'macro'
              AND er.event_name = ?
              AND sro.exit_horizon_code = ?
              AND sro.assumptions_version = ?
              AND (? IS NULL OR er.proxy_symbol = ?)
            ORDER BY er.event_date, er.proxy_symbol, er.underlying_symbol, sro.structure_code
            """,
            conn,
            params=[
                config.event_name,
                config.horizon_code,
                config.assumptions_version,
                proxy_filter,
                proxy_filter,
            ],
        )

    return {
        "events": events,
        "outcomes": outcomes,
        "metrics": metrics,
        "replays": replays,
    }


def summarize_event_timing(events: pd.DataFrame) -> dict[str, Any]:
    """Summarize macro event timing precision and proxy coverage."""

    if events.empty:
        return {
            "sample_size": 0,
            "event_time_labels": [],
            "proxy_symbols": [],
            "events_with_precise_timestamp": 0,
        }

    return {
        "sample_size": int(len(events)),
        "event_time_labels": sorted(events["event_time_label"].dropna().astype(str).unique().tolist()),
        "proxy_symbols": sorted(events["proxy_symbol"].dropna().astype(str).unique().tolist()),
        "events_with_precise_timestamp": int(events["event_ts_utc"].notna().sum()),
    }


def summarize_realized_moves(outcomes: pd.DataFrame) -> dict[str, Any]:
    """Summarize realized macro-event moves at the chosen horizon."""

    if outcomes.empty:
        return {
            "sample_size": 0,
            "mean_abs_move_pct": None,
            "median_abs_move_pct": None,
            "p75_abs_move_pct": None,
        }

    abs_moves = outcomes["realized_move_abs_pct"].astype(float)
    return {
        "sample_size": int(len(outcomes)),
        "mean_abs_move_pct": float(abs_moves.mean()),
        "median_abs_move_pct": float(abs_moves.median()),
        "p75_abs_move_pct": float(abs_moves.quantile(0.75)),
    }


def summarize_surface_pricing(metrics: pd.DataFrame) -> dict[str, Any]:
    """Summarize pre-event surface conditions for the macro sample."""

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
            }
        )
    summary.sort(key=lambda row: row["mean_realized_pnl"], reverse=True)
    return summary


def build_workbook_summary(config: MacroWorkbookConfig) -> dict[str, Any]:
    """Build the full macro workbook summary payload."""

    dataset = load_macro_event_dataset(config)
    return {
        "config": asdict(config),
        "coverage": {
            "events": int(len(dataset["events"])),
            "outcomes": int(len(dataset["outcomes"])),
            "metrics": int(len(dataset["metrics"])),
            "replays": int(len(dataset["replays"])),
        },
        "event_timing": summarize_event_timing(dataset["events"]),
        "realized_moves": summarize_realized_moves(dataset["outcomes"]),
        "surface_pricing": summarize_surface_pricing(dataset["metrics"]),
        "structure_outcomes": summarize_structure_outcomes(dataset["replays"]),
        "limitations": [
            "This workbook is specific to one macro catalyst at a time.",
            "Results are only as complete as the registered macro sample and bound snapshots.",
            "Proxy ETFs are explicit defaults, not proof of best execution vehicle in all regimes.",
        ],
    }


def render_markdown(summary: dict[str, Any]) -> str:
    """Render the workbook summary into a concise markdown report."""

    lines = [
        "# Macro Event Workbook",
        "",
        "## Configuration",
        "",
        f"- db_path: `{summary['config']['db_path']}`",
        f"- event_name: `{summary['config']['event_name']}`",
        f"- proxy_symbol: `{summary['config']['proxy_symbol']}`",
        f"- horizon_code: `{summary['config']['horizon_code']}`",
        "",
        "## Coverage",
        "",
        f"- events: {summary['coverage']['events']}",
        f"- outcomes: {summary['coverage']['outcomes']}",
        f"- metrics: {summary['coverage']['metrics']}",
        f"- replays: {summary['coverage']['replays']}",
        "",
        "## Event Timing",
        "",
        f"- sample_size: {summary['event_timing']['sample_size']}",
        f"- event_time_labels: {summary['event_timing']['event_time_labels']}",
        f"- proxy_symbols: {summary['event_timing']['proxy_symbols']}",
        f"- events_with_precise_timestamp: {summary['event_timing']['events_with_precise_timestamp']}",
        "",
        "## Realized Moves",
        "",
        f"- sample_size: {summary['realized_moves']['sample_size']}",
        f"- mean_abs_move_pct: {summary['realized_moves']['mean_abs_move_pct']}",
        f"- median_abs_move_pct: {summary['realized_moves']['median_abs_move_pct']}",
        f"- p75_abs_move_pct: {summary['realized_moves']['p75_abs_move_pct']}",
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

    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in summary["limitations"])
    return "\n".join(lines) + "\n"


def main() -> None:
    """CLI entry point for the macro workbook."""

    parser = argparse.ArgumentParser(description="Macro ETF event workbook")
    parser.add_argument("--db", default="data/options_intraday.db")
    parser.add_argument("--event-name", default="cpi")
    parser.add_argument("--proxy-symbol", default=None)
    parser.add_argument("--horizon", default="h1_close")
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--output-md", default=None)
    args = parser.parse_args()

    summary = build_workbook_summary(
        MacroWorkbookConfig(
            db_path=args.db,
            event_name=args.event_name,
            proxy_symbol=args.proxy_symbol,
            horizon_code=args.horizon,
        )
    )

    if args.output_json:
        Path(args.output_json).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if args.output_md:
        Path(args.output_md).write_text(render_markdown(summary), encoding="utf-8")

    if not args.output_json and not args.output_md:
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
