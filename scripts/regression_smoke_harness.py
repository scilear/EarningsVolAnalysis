#!/usr/bin/env python3
"""Run a fast regression smoke suite for trust-critical behavior.

This harness is intentionally small and deterministic. It executes a
curated subset of pytest node IDs that guard known trust blockers:

- gamma alignment directionality
- ticker-agnostic main-path behavior
- core event-variance and gate invariants

Usage examples
--------------
python scripts/regression_smoke_harness.py
python scripts/regression_smoke_harness.py --verbose --fail-fast
python scripts/regression_smoke_harness.py --test nvda_earnings_vol/tests/test_alignment.py
"""

from __future__ import annotations

import argparse
import logging
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence


LOGGER = logging.getLogger(__name__)

DEFAULT_TESTS: tuple[str, ...] = (
    "nvda_earnings_vol/tests/test_alignment.py",
    "nvda_earnings_vol/tests/test_main_ticker_agnostic.py",
    (
        "nvda_earnings_vol/tests/test_business_invariants.py::"
        "TestEventVarianceRatioBounds"
    ),
    (
        "nvda_earnings_vol/tests/test_business_invariants.py::"
        "TestBackspreadGateIndependence"
    ),
)


def resolve_tests(requested_tests: Sequence[str] | None) -> list[str]:
    """Return explicit tests when provided, otherwise smoke defaults."""
    if requested_tests:
        return list(requested_tests)
    return list(DEFAULT_TESTS)


def build_pytest_command(
    python_executable: str,
    tests: Sequence[str],
    *,
    verbose: bool,
    fail_fast: bool,
    extra_pytest_args: Sequence[str] | None,
) -> list[str]:
    """Build the subprocess command used to execute smoke tests."""
    command = [python_executable, "-m", "pytest"]
    if not verbose:
        command.append("-q")
    if fail_fast:
        command.append("-x")
    command.extend(tests)
    if extra_pytest_args:
        command.extend(extra_pytest_args)
    return command


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments for the smoke harness."""
    parser = argparse.ArgumentParser(
        description="Run trust-critical regression smoke tests.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable used to run pytest (default: current Python)",
    )
    parser.add_argument(
        "--test",
        action="append",
        default=None,
        help=("Specific pytest node id to run. Repeat to run multiple nodes."),
    )
    parser.add_argument(
        "--extra-pytest-arg",
        action="append",
        default=None,
        help="Extra raw argument to pass through to pytest.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first test failure.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Run pytest in verbose mode (disables -q).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the command and selected tests without executing.",
    )
    parser.add_argument(
        "--list-defaults",
        action="store_true",
        help="Print default smoke test nodes and exit.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the regression smoke harness CLI."""
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    tests = resolve_tests(args.test)
    if args.list_defaults:
        for node in DEFAULT_TESTS:
            print(node)
        return 0

    command = build_pytest_command(
        python_executable=args.python,
        tests=tests,
        verbose=args.verbose,
        fail_fast=args.fail_fast,
        extra_pytest_args=args.extra_pytest_arg,
    )
    command_str = shlex.join(command)

    LOGGER.info("Regression smoke nodes: %d", len(tests))
    for node in tests:
        LOGGER.info("- %s", node)
    LOGGER.info("Command: %s", command_str)

    if args.dry_run:
        return 0

    start = time.perf_counter()
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(command, cwd=repo_root, check=False)
    elapsed = time.perf_counter() - start
    LOGGER.info("Smoke harness completed in %.2fs", elapsed)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
