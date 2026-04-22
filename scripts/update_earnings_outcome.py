#!/usr/bin/env python3
"""CLI for post-earnings outcome updates and realized-move population."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from event_vol_analysis.outcomes import (  # noqa: E402
    ALLOWED_PHASE1,
    auto_populate_realized_move,
    get_outcome_record,
    update_outcome,
)


def build_parser() -> argparse.ArgumentParser:
    """Build argparse parser for outcome update operations."""

    parser = argparse.ArgumentParser(
        description="Update post-earnings outcome fields for one event.",
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol")
    parser.add_argument("--event-date", required=True, help="Event date YYYY-MM-DD")
    parser.add_argument(
        "--phase1",
        required=True,
        choices=sorted(ALLOWED_PHASE1),
        help="Confirmed Phase 1 category",
    )
    parser.add_argument(
        "--entry",
        required=True,
        choices=["yes", "no"],
        help="Whether an entry was taken",
    )
    parser.add_argument(
        "--pnl",
        type=float,
        default=None,
        help="Optional PnL for entered trade",
    )
    parser.add_argument(
        "--db",
        default="data/options_intraday.db",
        help="Path to SQLite store",
    )
    parser.add_argument(
        "--auto-realized",
        action="store_true",
        help="Populate realized move before applying manual update",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow overriding already-complete outcome rows",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    """Execute CLI operation; return process exit code."""

    args = build_parser().parse_args(argv)
    ticker = args.ticker.upper()

    current = get_outcome_record(ticker, args.event_date, db_path=args.db)
    if current is None:
        print(f"No outcome record found for {ticker} {args.event_date}")
        return 1

    print("Current outcome record:")
    print(json.dumps(asdict(current), indent=2, default=str))

    if args.auto_realized:
        auto_populate_realized_move(
            ticker,
            args.event_date,
            db_path=args.db,
            force=args.force,
        )

    updated = update_outcome(
        ticker,
        args.event_date,
        phase1_category=args.phase1,
        entry_taken=(args.entry == "yes"),
        pnl=args.pnl,
        force=args.force,
        db_path=args.db,
    )

    print("\nUpdated outcome record:")
    print(json.dumps(asdict(updated), indent=2, default=str))
    return 0


def main() -> None:
    """Script entry point."""

    raise SystemExit(run())


if __name__ == "__main__":
    main()
