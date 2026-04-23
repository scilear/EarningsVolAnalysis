"""Tests for Structure Advisor core and CLI query mode."""

from __future__ import annotations

import json
import subprocess

import pytest

from event_vol_analysis import main as main_module
from event_vol_analysis.structure_advisor import (
    ScoredStructure,
    StructureAdvisorResult,
    _annualized_carry,
    _loss_zone,
    _parse_validate_structure,
    _ranking_key,
    _resolve_leg_prices,
    query_structures,
)
from event_vol_analysis.strategies.payoff_map import PayoffType
from event_vol_analysis.strategies.structures import OptionLeg, Strategy


def test_annualized_carry_calculation() -> None:
    value = _annualized_carry(342.0, 429.57, 23)
    assert value == pytest.approx(12.6, rel=0.03)


def test_loss_zone_none_for_debit_spread() -> None:
    strategy = Strategy(
        name="put_spread",
        legs=(
            OptionLeg("put", 96.0, 1, "buy", _ts("2030-05-17")),
            OptionLeg("put", 90.0, 1, "sell", _ts("2030-05-17")),
        ),
    )
    spots = [80.0, 90.0, 100.0]
    pnls = [-200.0, -100.0, 100.0]
    assert _loss_zone(strategy, spots, pnls, 150.0) is None


def test_loss_zone_diagonal_between_strikes() -> None:
    strategy = Strategy(
        name="diagonal_put_backspread",
        legs=(
            OptionLeg("put", 96.0, 1, "sell", _ts("2030-05-17")),
            OptionLeg("put", 93.0, 2, "buy", _ts("2030-06-21")),
        ),
    )
    spots = [88.0, 92.0, 94.0, 96.0, 100.0]
    pnls = [50.0, -250.0, -300.0, -210.0, 40.0]
    loss_zone = _loss_zone(strategy, spots, pnls, 200.0)
    assert loss_zone == (92.0, 96.0)


def test_ranking_cheaper_first() -> None:
    left = ScoredStructure(
        structure_name="a",
        net_debit=100.0,
        annualized_carry_pct=9.0,
        max_loss=100.0,
        breakeven=None,
        loss_zone=None,
        rank=0,
    )
    right = ScoredStructure(
        structure_name="b",
        net_debit=200.0,
        annualized_carry_pct=14.0,
        max_loss=200.0,
        breakeven=None,
        loss_zone=None,
        rank=0,
    )
    assert _ranking_key(left) < _ranking_key(right)


def test_to_table_line_count_under_60() -> None:
    result = StructureAdvisorResult(
        payoff_type="crash",
        ticker="GLD",
        expiry="2030-05-17",
        spot=100.0,
        ranked_structures=[
            ScoredStructure(
                structure_name=f"s{i}",
                net_debit=100.0 + i,
                annualized_carry_pct=10.0 + i,
                max_loss=100.0 + i,
                breakeven=95.0,
                loss_zone=None,
                rank=i,
            )
            for i in range(1, 8)
        ],
    )
    output = result.to_table()
    assert len(output.splitlines()) <= 60


def test_diagonal_conditional_cost_note_present(monkeypatch) -> None:
    _patch_chain_fetch(monkeypatch)
    result = query_structures(
        payoff_type=PayoffType.CRASH,
        ticker="GLD",
        expiry="2030-05-17",
        spot=100.0,
        context={"iv_percentile": 50.0, "dte": 23},
    )
    diagonal = next(
        item for item in result.ranked_structures if "diagonal" in item.structure_name
    )
    assert diagonal.note is not None
    assert "conditional" in diagonal.note.lower()


def test_fitness_gate_ivp_warning_not_blocking(monkeypatch) -> None:
    _patch_chain_fetch(monkeypatch)
    result = query_structures(
        payoff_type=PayoffType.CRASH,
        ticker="GLD",
        expiry="2030-05-17",
        spot=100.0,
        context={"iv_percentile": 85.0, "dte": 23},
    )
    assert any("IV percentile >80" in flag for flag in result.fitness_flags)
    assert result.ranked_structures


def test_fitness_gate_naked_short_hard_block(monkeypatch) -> None:
    _patch_chain_fetch(monkeypatch)
    result = query_structures(
        payoff_type=PayoffType.VOL_COMPRESSION,
        ticker="GLD",
        expiry="2030-05-17",
        spot=100.0,
        context={"iv_percentile": 50.0, "dte": 23},
    )
    blocked = [item for item in result.excluded if item.reason == "CHARTER_BLOCKED"]
    assert blocked


def test_budget_filter_excludes_over_budget(monkeypatch) -> None:
    _patch_chain_fetch(monkeypatch, expensive=True)
    result = query_structures(
        payoff_type=PayoffType.CRASH,
        ticker="GLD",
        expiry="2030-05-17",
        spot=100.0,
        budget=50.0,
        context={"iv_percentile": 50.0, "dte": 23},
    )
    assert any(item.reason == "BUDGET_EXCEEDED" for item in result.excluded)


def test_context_optional_graceful_degradation(monkeypatch) -> None:
    _patch_chain_fetch(monkeypatch)
    result = query_structures(
        payoff_type=PayoffType.RALLY,
        ticker="GLD",
        expiry="2030-05-17",
        spot=100.0,
    )
    assert "IV percentile unavailable" in result.vol_regime_summary


def test_strike_targeting_crash_puts(monkeypatch) -> None:
    seen_commands: list[list[str]] = []

    def _fake_run(command, check=False, capture_output=True, text=True):
        seen_commands.append(command)
        return _completed_process(_fake_chain_payload(command))

    monkeypatch.setattr(subprocess, "run", _fake_run)
    query_structures(
        payoff_type=PayoffType.CRASH,
        ticker="GLD",
        expiry="2030-05-17",
        spot=100.0,
        context={"dte": 23},
    )
    assert any("--strikes" in cmd for cmd in seen_commands)
    strike_args = [
        cmd[cmd.index("--strikes") + 1] for cmd in seen_commands if "--strikes" in cmd
    ]
    combined = ",".join(strike_args)
    assert "96.00" in combined
    assert "90.00" in combined


def test_strike_targeting_diagonal_two_expiries(monkeypatch) -> None:
    seen_expiries: list[str] = []

    def _fake_run(command, check=False, capture_output=True, text=True):
        seen_expiries.append(command[command.index("--expiry") + 1])
        return _completed_process(_fake_chain_payload(command))

    monkeypatch.setattr(subprocess, "run", _fake_run)
    query_structures(
        payoff_type=PayoffType.CRASH,
        ticker="GLD",
        expiry="2030-05-17",
        spot=100.0,
        context={"dte": 23},
    )
    assert len(set(seen_expiries)) >= 2


def test_query_structures_with_mocked_subprocess(monkeypatch) -> None:
    _patch_chain_fetch(monkeypatch)
    result = query_structures(
        payoff_type=PayoffType.CRASH,
        ticker="GLD",
        expiry="2030-05-17",
        spot=100.0,
        context={"iv_percentile": 69.2, "dte": 23},
    )
    assert result.data_unavailable is False
    assert len(result.ranked_structures) >= 3
    assert all(not hasattr(item, "rows") for item in result.ranked_structures)


def test_cli_query_table_output_under_60_lines(monkeypatch, capsys) -> None:
    _patch_chain_fetch(monkeypatch)
    exit_code = main_module._run_query_cli(
        [
            "--payoff",
            "crash",
            "--ticker",
            "GLD",
            "--expiry",
            "2030-05-17",
            "--spot",
            "100.0",
        ]
    )
    output = capsys.readouterr().out
    assert exit_code == 0
    assert len(output.splitlines()) <= 60


def test_cli_query_json_output_valid(monkeypatch, capsys) -> None:
    _patch_chain_fetch(monkeypatch)
    exit_code = main_module._run_query_cli(
        [
            "--payoff",
            "crash",
            "--ticker",
            "GLD",
            "--expiry",
            "2030-05-17",
            "--spot",
            "100.0",
            "--output",
            "json",
        ]
    )
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert exit_code == 0
    assert payload["payoff_type"] == "crash"


def test_cli_query_invalid_payoff_exits_2(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main_module._run_query_cli(
            [
                "--payoff",
                "invalid",
                "--ticker",
                "GLD",
                "--expiry",
                "2030-05-17",
                "--spot",
                "100.0",
            ]
        )
    assert exc_info.value.code == 2
    assert capsys.readouterr().err


def test_cli_query_validate_flag_adds_structure(monkeypatch, capsys) -> None:
    _patch_chain_fetch(monkeypatch)
    exit_code = main_module._run_query_cli(
        [
            "--payoff",
            "crash",
            "--ticker",
            "GLD",
            "--expiry",
            "2030-05-17",
            "--spot",
            "100.0",
            "--validate",
            "diagonal:short-May15-96P/long-2x-Jul17-93P",
        ]
    )
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "MANUALLY_SPECIFIED" in output


def test_cli_query_budget_flag_passed_to_advisor(monkeypatch) -> None:
    captured: dict = {}

    def _fake_query(**kwargs):
        captured.update(kwargs)
        return StructureAdvisorResult(
            payoff_type="crash",
            ticker="GLD",
            expiry="2030-05-17",
            spot=100.0,
        )

    monkeypatch.setattr(main_module, "query_structures", _fake_query)
    exit_code = main_module._run_query_cli(
        [
            "--payoff",
            "crash",
            "--ticker",
            "GLD",
            "--expiry",
            "2030-05-17",
            "--spot",
            "100.0",
            "--budget",
            "500",
        ]
    )
    assert exit_code == 0
    assert captured["budget"] == 500.0


def test_cli_query_chain_unavailable_exits_1(monkeypatch, capsys) -> None:
    def _fake_query(**kwargs):
        return StructureAdvisorResult(
            payoff_type="crash",
            ticker="GLD",
            expiry="2030-05-17",
            spot=100.0,
            data_unavailable=True,
        )

    monkeypatch.setattr(main_module, "query_structures", _fake_query)
    exit_code = main_module._run_query_cli(
        [
            "--payoff",
            "crash",
            "--ticker",
            "GLD",
            "--expiry",
            "2030-05-17",
            "--spot",
            "100.0",
        ]
    )
    assert exit_code == 1
    assert "DATA UNAVAILABLE" in capsys.readouterr().err


def test_validate_parse_error_exits_2(monkeypatch) -> None:
    _patch_chain_fetch(monkeypatch)
    exit_code = main_module._run_query_cli(
        [
            "--payoff",
            "crash",
            "--ticker",
            "GLD",
            "--expiry",
            "2030-05-17",
            "--spot",
            "100.0",
            "--validate",
            "bad-format",
        ]
    )
    assert exit_code == 2


def test_validate_parser_direct() -> None:
    strategy = _parse_validate_structure(
        "diagonal:short-May15-96P/long-2x-Jul17-93P",
        _date("2030-05-17"),
    )
    assert strategy.name == "diagonal_put_backspread_manual"
    assert len(strategy.legs) == 2


def test_resolve_leg_prices_requires_bid_ask_mid() -> None:
    strategy = Strategy(
        name="long_put",
        legs=(OptionLeg("put", 96.0, 1, "buy", _ts("2030-05-17")),),
    )
    lookup = {(_date("2030-05-17"), "put", 96.0): {"bid": 0.0, "ask": 1.0, "mid": 0.5}}
    assert _resolve_leg_prices(strategy, lookup) is None


def _patch_chain_fetch(monkeypatch, expensive: bool = False) -> None:
    """Patch subprocess.run for option chain calls."""

    def _fake_run(command, check=False, capture_output=True, text=True):
        payload = _fake_chain_payload(command, expensive=expensive)
        return _completed_process(payload)

    monkeypatch.setattr(subprocess, "run", _fake_run)


def _fake_chain_payload(command: list[str], expensive: bool = False) -> str:
    strike_csv = command[command.index("--strikes") + 1]
    strikes = [float(item) for item in strike_csv.split(",") if item]
    expiry = command[command.index("--expiry") + 1]
    rows = []
    for strike in strikes:
        base = 1.2 if not expensive else 8.0
        call_mid = max(base - max(strike - 100.0, 0.0) * 0.03, 0.25)
        put_mid = max(base + max(100.0 - strike, 0.0) * 0.03, 0.25)
        for right, mid in (("C", call_mid), ("P", put_mid)):
            rows.append(
                {
                    "expiry": expiry,
                    "strike": strike,
                    "right": right,
                    "bid": round(mid * 0.95, 4),
                    "ask": round(mid * 1.05, 4),
                    "mid": round(mid, 4),
                    "iv": 0.35,
                    "delta": 0.25,
                    "vega": 0.12,
                }
            )
    return json.dumps({"rows": rows})


def _completed_process(stdout: str):
    return subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=stdout,
        stderr="",
    )


def _date(value: str):
    return _ts(value).date()


def _ts(value: str):
    return pytest.importorskip("pandas").Timestamp(value)
