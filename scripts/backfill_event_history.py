#!/usr/bin/env python3
"""Backfill workbook-ready event rows from a JSON manifest."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from event_option_playbook.backfill import (
    auto_ingest_earnings_calendar_db,
    backfill_event_manifest,
)


DEFAULT_TICKERS = [
    "NVDA",
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "TSLA",
    "META",
    "AMD",
    "INTC",
    "CRM",
]


def _parse_ticker_list(value: str) -> list[str]:
    """Parse a comma-separated ticker string into uppercase symbols."""

    return [ticker.strip().upper() for ticker in value.split(",") if ticker.strip()]


def main() -> None:
    """CLI entry point."""

    parser = argparse.ArgumentParser(
        description="Register event samples and bindings from a JSON manifest.",
    )
    parser.add_argument(
        "manifest",
        nargs="?",
        default=None,
        help="Path to a JSON manifest.",
    )
    parser.add_argument(
        "--db",
        default="data/options_intraday.db",
        help="Path to the SQLite event/options store.",
    )
    parser.add_argument(
        "--auto-earnings",
        action="store_true",
        help="Auto-ingest upcoming earnings events from yfinance.",
    )
    parser.add_argument(
        "--tickers",
        default=",".join(DEFAULT_TICKERS),
        help="Comma-separated ticker list for --auto-earnings.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Max earnings dates to fetch per ticker in --auto-earnings mode.",
    )
    parser.add_argument(
        "--on-or-after",
        default=None,
        help="ISO date filter for --auto-earnings mode (default: today).",
    )
    args = parser.parse_args()

    if args.auto_earnings:
        tickers = _parse_ticker_list(args.tickers)
        if not tickers:
            raise ValueError("No tickers provided for --auto-earnings mode.")
        cutoff = dt.date.fromisoformat(args.on_or_after) if args.on_or_after else None
        summary = auto_ingest_earnings_calendar_db(
            tickers,
            db_path=args.db,
            limit=args.limit,
            on_or_after=cutoff,
        )
    else:
        if args.manifest is None:
            raise ValueError("manifest is required unless --auto-earnings is set")
        summary = backfill_event_manifest(args.manifest, db_path=args.db)

    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
