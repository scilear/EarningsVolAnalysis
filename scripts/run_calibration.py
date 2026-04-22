#!/usr/bin/env python3
"""Manual/cron trigger for weekly calibration report generation (T031)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from event_vol_analysis.reports.calibration import (  # noqa: E402
    run_calibration_report,
)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for weekly calibration report generation."""

    parser = argparse.ArgumentParser(
        description="Run weekly calibration report from earnings outcomes.",
    )
    parser.add_argument(
        "--db",
        default="data/options_intraday.db",
        help="Path to SQLite database file.",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/calibration",
        help="Directory where markdown report will be written.",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    """Execute calibration report generation and return process exit code."""

    args = build_parser().parse_args(argv)
    run_calibration_report(db_path=args.db, output_dir=args.output_dir)
    return 0


def main() -> None:
    """Script entry point."""

    raise SystemExit(run())


if __name__ == "__main__":
    main()
