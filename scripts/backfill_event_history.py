#!/usr/bin/env python3
"""Backfill workbook-ready event rows from a JSON manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from event_option_playbook.backfill import backfill_event_manifest


def main() -> None:
    """CLI entry point."""

    parser = argparse.ArgumentParser(
        description="Register event samples and bindings from a JSON manifest.",
    )
    parser.add_argument("manifest", help="Path to a JSON manifest.")
    parser.add_argument(
        "--db",
        default="data/options_intraday.db",
        help="Path to the SQLite event/options store.",
    )
    args = parser.parse_args()

    summary = backfill_event_manifest(args.manifest, db_path=args.db)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
