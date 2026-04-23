#!/usr/bin/env python3
"""CLI for storing/querying macro binary-event outcome records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from event_vol_analysis.macro_outcomes import (  # noqa: E402
    query_event_type_tail_rate,
    store_macro_event_outcome,
)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for macro outcomes operations."""
    parser = argparse.ArgumentParser(
        description="Store or query macro binary-event outcomes.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Store one macro outcome")
    add_parser.add_argument("--event-type", required=True)
    add_parser.add_argument("--event-date", required=True)
    add_parser.add_argument("--underlying", required=True)
    add_parser.add_argument("--implied-move", required=True, type=float)
    add_parser.add_argument("--realized-move", required=True, type=float)
    add_parser.add_argument("--ratio", type=float, default=None)
    add_parser.add_argument("--vix", required=True, type=float)
    add_parser.add_argument("--vvix-percentile", required=True, type=float)
    add_parser.add_argument("--gex-zone", required=True)
    add_parser.add_argument("--vol-crush", required=True, type=float)
    add_parser.add_argument("--vix-quartile", type=int, default=None)
    add_parser.add_argument("--notes", default="")
    add_parser.add_argument("--data-dir", default="data/macro_event_outcomes")

    query_parser = subparsers.add_parser(
        "query",
        help="Query tail-rate summary",
    )
    query_parser.add_argument("--event-type", required=True)
    query_parser.add_argument("--threshold", type=float, default=1.0)
    query_parser.add_argument("--vix-quartile", type=int, default=None)
    query_parser.add_argument(
        "--data-dir",
        default="data/macro_event_outcomes",
    )

    return parser


def run(argv: list[str] | None = None) -> int:
    """Execute CLI command and return process exit code."""
    args = build_parser().parse_args(argv)
    if args.command == "add":
        path = store_macro_event_outcome(
            event_type=args.event_type,
            event_date=args.event_date,
            underlying=args.underlying,
            implied_move_pct=args.implied_move,
            realized_move_pct=args.realized_move,
            move_vs_implied_ratio=args.ratio,
            vix_at_entry=args.vix,
            vvix_percentile_at_entry=args.vvix_percentile,
            gex_zone=args.gex_zone,
            vol_crush=args.vol_crush,
            notes=args.notes,
            vix_quartile=args.vix_quartile,
            data_dir=args.data_dir,
        )
        print(
            json.dumps(
                {
                    "status": "stored",
                    "path": str(path),
                },
                indent=2,
            )
        )
        return 0

    summary = query_event_type_tail_rate(
        event_type=args.event_type,
        threshold_sd=args.threshold,
        vix_quartile=args.vix_quartile,
        data_dir=args.data_dir,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def main() -> None:
    """Script entry point."""
    raise SystemExit(run())


if __name__ == "__main__":
    main()
