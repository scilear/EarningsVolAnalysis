"""Tests for scripts.regression_smoke_harness."""

from __future__ import annotations

from scripts.regression_smoke_harness import (
    DEFAULT_TESTS,
    build_pytest_command,
    parse_args,
    resolve_tests,
)


def test_resolve_tests_uses_defaults_when_no_override() -> None:
    tests = resolve_tests(None)
    assert tests == list(DEFAULT_TESTS)


def test_resolve_tests_prefers_explicit_selection() -> None:
    explicit = ["nvda_earnings_vol/tests/test_alignment.py"]
    assert resolve_tests(explicit) == explicit


def test_build_pytest_command_defaults_to_quiet_mode() -> None:
    command = build_pytest_command(
        python_executable="python3",
        tests=["nvda_earnings_vol/tests/test_alignment.py"],
        verbose=False,
        fail_fast=False,
        extra_pytest_args=None,
    )
    assert command[:4] == ["python3", "-m", "pytest", "-q"]
    assert "nvda_earnings_vol/tests/test_alignment.py" in command


def test_build_pytest_command_respects_verbose_and_fail_fast() -> None:
    command = build_pytest_command(
        python_executable="python3",
        tests=["nvda_earnings_vol/tests/test_alignment.py"],
        verbose=True,
        fail_fast=True,
        extra_pytest_args=["-k", "alignment"],
    )
    assert command[:3] == ["python3", "-m", "pytest"]
    assert "-q" not in command
    assert "-x" in command
    assert command[-2:] == ["-k", "alignment"]


def test_parse_args_accepts_repeated_test_flags() -> None:
    args = parse_args(
        [
            "--test",
            "nvda_earnings_vol/tests/test_alignment.py",
            "--test",
            "nvda_earnings_vol/tests/test_main_ticker_agnostic.py",
        ]
    )
    assert args.test == [
        "nvda_earnings_vol/tests/test_alignment.py",
        "nvda_earnings_vol/tests/test_main_ticker_agnostic.py",
    ]
