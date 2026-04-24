"""Tests for playbook scan report generation."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from event_vol_analysis.reports.playbook_scan import (
    PLAYBOOK_MAX_SPREAD_PCT,
    PLAYBOOK_MIN_DAILY_VOLUME,
    PLAYBOOK_MIN_OI,
    PlaybookScanResult,
    PlaybookScanRow,
    check_playbook_liquidity,
    create_scan_row_from_snapshot,
    format_console_table,
    render_playbook_scan_html,
    save_playbook_scan_report,
    sort_playbook_rows,
)

# Sample data for testing
SAMPLE_VOL_REGIME = {
    "vol_regime": "CHEAP",
    "vol_regime_legacy": "Low IV Setup",
    "ivr": 25.0,
    "ivp": 30.0,
    "vol_confidence": 0.75,
    "vol_confidence_label": "MEDIUM",
    "event_regime": "Event Dominant Setup",
    "term_structure_regime": "Contango",
    "gamma_regime": "Net Short Gamma",
    "composite_regime": "Mixed / Transitional Setup",
    "confidence": 0.65,
}

SAMPLE_EDGE_RATIO = {
    "implied": 0.045,
    "conditional_expected_primary": 0.055,
    "ratio": 0.818,
    "label": "CHEAP",
    "confidence": "MEDIUM",
    "secondary_ratio": 0.85,
    "label_disagreement": False,
    "note": "denominator=recency_weighted; timing=amc",
}

SAMPLE_POSITIONING = {
    "label": "BALANCED",
    "direction": None,
    "confidence": "LOW",
    "available_count": 2,
    "note": "available=2/4; oi=NEUTRAL...",
    "signals": {
        "oi": {"signal": "NEUTRAL", "is_available": True, "note": "no concentration"},
        "pc": {"signal": "NEUTRAL", "is_available": False, "note": "missing inputs"},
        "drift": {"signal": "NEUTRAL", "is_available": False, "note": "missing inputs"},
        "max_pain": {
            "signal": "NEUTRAL",
            "is_available": True,
            "note": "within 3% of spot",
        },
    },
}

SAMPLE_SIGNAL_GRAPH = {
    "edges": [],
    "nodes": {},
    "tradeable_followers": ["AMD", "INTC"],
    "absorbed_followers": [],
}

SAMPLE_TYPE_CLASSIFICATION = {
    "type": 1,
    "rationale": [
        "PASS: TYPE 1: event not printed",
        "PASS: TYPE 1: vol regime is CHEAP",
    ],
    "action_guidance": "Buy straddle or strangle with 7-10 DTE.",
    "phase2_checklist": None,
    "confidence": "HIGH",
    "is_no_trade": False,
    "frequency_warning": True,
}


class TestTypeColors:
    """Test TYPE color definitions."""

    def test_type_colors_exist(self) -> None:
        """Verify TYPE color mappings defined correctly."""
        from event_vol_analysis.reports.playbook_scan import TYPE_COLORS

        assert TYPE_COLORS[1] == "#22c55e"  # green
        assert TYPE_COLORS[2] == "#eab308"  # yellow
        assert TYPE_COLORS[3] == "#3b82f6"  # blue
        assert TYPE_COLORS[4] == "#f97316"  # orange
        assert TYPE_COLORS[5] == "#9ca3af"  # grey


class TestSortOrder:
    """Test summary table sort order by TYPE."""

    def test_type1_first(self) -> None:
        """TYPE 1 should sort first."""
        rows = [
            PlaybookScanRow(
                ticker="A",
                earnings_date="",
                vol_regime="",
                edge_ratio="",
                positioning="",
                signal="",
                type_=2,
                confidence="",
                action="",
                is_type5=False,
            ),
            PlaybookScanRow(
                ticker="B",
                earnings_date="",
                vol_regime="",
                edge_ratio="",
                positioning="",
                signal="",
                type_=1,
                confidence="",
                action="",
                is_type5=False,
            ),
        ]
        sorted_rows = sort_playbook_rows(rows)
        assert sorted_rows[0].type_ == 1

    def test_type5_last(self) -> None:
        """TYPE 5 should sort last."""
        rows = [
            PlaybookScanRow(
                ticker="A",
                earnings_date="",
                vol_regime="",
                edge_ratio="",
                positioning="",
                signal="",
                type_=1,
                confidence="",
                action="",
                is_type5=False,
            ),
            PlaybookScanRow(
                ticker="B",
                earnings_date="",
                vol_regime="",
                edge_ratio="",
                positioning="",
                signal="",
                type_=5,
                confidence="",
                action="",
                is_type5=True,
            ),
        ]
        sorted_rows = sort_playbook_rows(rows)
        assert sorted_rows[-1].type_ == 5

    def test_types_sorted_12345(self) -> None:
        """All types should sort 1,2,3,4,5."""
        rows = [
            PlaybookScanRow(
                ticker=str(t),
                earnings_date="",
                vol_regime="",
                edge_ratio="",
                positioning="",
                signal="",
                type_=t,
                confidence="",
                action="",
                is_type5=(t == 5),
            )
            for t in [3, 5, 1, 4, 2]
        ]
        sorted_rows = sort_playbook_rows(rows)
        types = [r.type_ for r in sorted_rows]
        assert types == [1, 2, 3, 4, 5]


class TestType5DeEmphasis:
    """Test TYPE 5 de-emphasis in HTML and console."""

    def test_type5_flag_true_for_type5(self) -> None:
        """TYPE 5 row should have is_type5=True."""
        row = PlaybookScanRow(
            ticker="X",
            earnings_date="",
            vol_regime="",
            edge_ratio="",
            positioning="",
            signal="",
            type_=5,
            confidence="",
            action="",
        )
        assert row.is_type5 is True
        assert row.type_ == 5

    def test_non_type5_flag_false(self) -> None:
        """Non-TYPE 5 row should have is_type5=False."""
        row = PlaybookScanRow(
            ticker="X",
            earnings_date="",
            vol_regime="",
            edge_ratio="",
            positioning="",
            signal="",
            type_=1,
            confidence="",
            action="",
        )
        assert row.is_type5 is False
        assert row.type_ == 1


class TestConsoleOutput:
    """Test console ASCII table formatting."""

    def test_non_type5_prefixed(self) -> None:
        """Non-TYPE-5 rows should have >>> prefix."""
        rows = [
            PlaybookScanRow(
                ticker="A",
                earnings_date="2026-05-01",
                vol_regime="CHEAP",
                edge_ratio="CHEAP (MEDIUM)",
                positioning="BALANCED",
                signal="No signal",
                type_=1,
                confidence="HIGH",
                action="Buy straddle",
                is_type5=False,
            ),
        ]
        output = format_console_table(rows)
        assert ">>> " in output

    def test_type5_bracketed(self) -> None:
        """TYPE-5 rows should have [ ] brackets."""
        rows = [
            PlaybookScanRow(
                ticker="B",
                earnings_date="2026-05-02",
                vol_regime="EXPENSIVE",
                edge_ratio="RICH (LOW)",
                positioning="BALANCED",
                signal="No signal",
                type_=5,
                confidence="LOW",
                action="No trade",
                is_type5=True,
            ),
        ]
        output = format_console_table(rows)
        assert "[ ] " in output

    def test_phase2_checklist_type4(self) -> None:
        """TYPE 4 rows should print phase 2 checklist."""
        rows = [
            PlaybookScanRow(
                ticker="C",
                earnings_date="2026-05-03",
                vol_regime="FAIR",
                edge_ratio="FAIR (MEDIUM)",
                positioning="CROWDED",
                signal="Followers: AMD",
                type_=4,
                confidence="HIGH",
                action="Potential fade",
                is_type5=False,
                phase2_checklist=[
                    "Pre-market: price reversal continuing?",
                    "IV: crushing toward normal levels?",
                ],
            ),
        ]
        output = format_console_table(rows)
        assert "Pre-market" in output
        assert "IV:" in output


class TestPlaybookScanResult:
    """Test PlaybookScanResult summary computation."""

    def test_frequency_warning_fires_above_10pct(self) -> None:
        """Frequency warning should fire when >10% are TYPE 1."""
        rows = [
            PlaybookScanRow(
                ticker=str(i),
                earnings_date="",
                vol_regime="",
                edge_ratio="",
                positioning="",
                signal="",
                type_=i,
                confidence="",
                action="",
                is_type5=(i == 5),
            )
            for i in [1, 1, 2, 3, 4, 5, 5, 5, 5, 5]
        ]
        result = PlaybookScanResult(
            rows=rows,
            filtered_out=[],
            frequency_warning_fired=False,
        )
        result.compute_summary()
        assert result.frequency_warning_fired is True
        assert result.type1_count == 2
        assert result.total_analyzed == 10

    def test_frequency_warning_absent_below_10pct(self) -> None:
        """Frequency warning should not fire when <=10% are TYPE 1."""
        rows = [
            PlaybookScanRow(
                ticker=str(i),
                earnings_date="",
                vol_regime="",
                edge_ratio="",
                positioning="",
                signal="",
                type_=i,
                confidence="",
                action="",
                is_type5=(i == 5),
            )
            for i in [1, 2, 3, 4, 5, 5, 5, 5, 5, 5]
        ]
        result = PlaybookScanResult(
            rows=rows,
            filtered_out=[],
            frequency_warning_fired=False,
        )
        result.compute_summary()
        assert result.frequency_warning_fired is False
        assert result.type1_count == 1

    def test_filtered_out_listed(self) -> None:
        """Filtered out names should be in filtered_out list."""
        filtered = [
            PlaybookScanRow(
                ticker="A",
                earnings_date="N/A",
                vol_regime="N/A",
                edge_ratio="N/A",
                positioning="N/A",
                signal="N/A",
                type_=5,
                confidence="N/A",
                action="FILTERED",
                is_type5=True,
                filter_reason="max spread >= 15%",
            ),
        ]
        result = PlaybookScanResult(
            rows=[],
            filtered_out=filtered,
            frequency_warning_fired=False,
        )
        result.compute_summary()
        assert result.total_filtered == 1
        assert "max spread" in filtered[0].filter_reason


class TestCreateScanRow:
    """Test creating scan rows from snapshots."""

    def test_create_from_snapshot(self) -> None:
        """Create row from complete snapshot."""
        snapshot = {
            "event_date": "2026-05-28",
            "vol_regime": SAMPLE_VOL_REGIME,
            "edge_ratio": SAMPLE_EDGE_RATIO,
            "positioning": SAMPLE_POSITIONING,
            "signal_graph": SAMPLE_SIGNAL_GRAPH,
            "type_classification": SAMPLE_TYPE_CLASSIFICATION,
        }
        row = create_scan_row_from_snapshot("NVDA", snapshot)
        assert row.ticker == "NVDA"
        assert row.earnings_date == "2026-05-28"
        assert row.type_ == 1
        assert row.confidence == "HIGH"
        assert row.action == "Buy straddle or strangle with 7-10 DTE."

    def test_missing_type_classification_defaults_to_5(self) -> None:
        """Missing TYPE defaults to 5."""
        snapshot = {
            "event_date": "2026-05-28",
            "vol_regime": SAMPLE_VOL_REGIME,
            "edge_ratio": SAMPLE_EDGE_RATIO,
            "positioning": SAMPLE_POSITIONING,
            "signal_graph": SAMPLE_SIGNAL_GRAPH,
            "type_classification": None,
        }
        row = create_scan_row_from_snapshot("NVDA", snapshot)
        assert row.type_ == 5
        assert row.is_type5 is True


class TestPlaybookFilters:
    """Test playbook liquidity filters."""

    def test_filter_thresholds(self) -> None:
        """Verify filter thresholds match spec."""
        assert PLAYBOOK_MAX_SPREAD_PCT == 0.15
        assert PLAYBOOK_MIN_OI == 500
        assert PLAYBOOK_MIN_DAILY_VOLUME == 1000


class TestHtmlOutput:
    """Test HTML report generation."""

    def test_html_contains_type_colors(self) -> None:
        """HTML should include TYPE color classes."""
        rows = [
            PlaybookScanRow(
                ticker="NVDA",
                earnings_date="2026-05-01",
                vol_regime="CHEAP",
                edge_ratio="CHEAP (MEDIUM)",
                positioning="BALANCED",
                signal="No signal",
                type_=1,
                confidence="HIGH",
                action="Buy",
                is_type5=False,
            ),
        ]
        result = PlaybookScanResult(
            rows=rows,
            filtered_out=[],
            frequency_warning_fired=False,
        )
        result.compute_summary()
        html = render_playbook_scan_html(result, "2026-04-22")
        assert "type-1" in html
        assert ".type-2" in html or "type-2" in html

    def test_frequency_warning_in_html(self) -> None:
        """Frequency warning banner in HTML when triggered."""
        rows = [
            PlaybookScanRow(
                ticker=str(i),
                earnings_date="",
                vol_regime="",
                edge_ratio="",
                positioning="",
                signal="",
                type_=i,
                confidence="",
                action="",
                is_type5=(i == 5),
            )
            for i in [1, 1, 2, 3, 4, 5, 5, 5, 5, 5]
        ]
        result = PlaybookScanResult(
            rows=rows,
            filtered_out=[],
            frequency_warning_fired=False,
        )
        result.compute_summary()
        html = render_playbook_scan_html(result, "2026-04-22")
        assert "FREQUENCY WARNING" in html


class TestReportSave:
    """Test report saving."""

    def test_report_saved_to_daily_dir(
        self,
        tmp_path: Path,
    ) -> None:
        """Report should be saved to daily directory."""
        rows = [
            PlaybookScanRow(
                ticker="NVDA",
                earnings_date="2026-05-01",
                vol_regime="CHEAP",
                edge_ratio="CHEAP (MEDIUM)",
                positioning="BALANCED",
                signal="No signal",
                type_=1,
                confidence="HIGH",
                action="Buy",
                is_type5=False,
            ),
        ]
        result = PlaybookScanResult(
            rows=rows,
            filtered_out=[],
            frequency_warning_fired=False,
        )
        result.compute_summary()
        output_dir = tmp_path / "reports"
        path = save_playbook_scan_report(result, output_dir)
        expected_name = f"{dt.date.today().isoformat()}_playbook_scan.html"
        assert expected_name in str(path)
        assert path.exists()


class TestPlaybookScanIntegration:
    """Integration tests for playbook scan CLI."""

    def test_playbook_scan_cli_integration(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Full playbook-scan mode run with test data."""
        # Use test tickers with baseline scenario
        analysis_payloads: dict[str, dict[str, Any]] = {
            "NVDA": {
                "event_date": "2026-05-28",
                "regime": {
                    "vol_regime": "CHEAP",
                    "vol_regime_legacy": "Low IV Setup",
                    "ivr": 25.0,
                    "ivp": 30.0,
                    "vol_confidence": 0.75,
                    "vol_confidence_label": "MEDIUM",
                    "event_regime": "Event Dominant Setup",
                    "term_structure_regime": "Contango",
                    "gamma_regime": "Net Short Gamma",
                    "composite_regime": "Mixed / Transitional Setup",
                    "confidence": 0.65,
                },
                "edge_ratio": {
                    "implied": 0.045,
                    "conditional_expected_primary": 0.055,
                    "ratio": 0.818,
                    "label": "CHEAP",
                    "confidence": "MEDIUM",
                    "note": "denominator=recency_weighted",
                },
                "positioning": {
                    "label": "BALANCED",
                    "direction": None,
                    "confidence": "LOW",
                    "available_count": 2,
                },
                "signal_graph": {
                    "tradeable_followers": [],
                    "absorbed_followers": [],
                },
                "type_classification": {
                    "type": 1,
                    "confidence": "HIGH",
                    "action_guidance": "Buy straddle",
                    "rationale": ["PASS"],
                    "is_no_trade": False,
                    "frequency_warning": True,
                },
            },
        }

        commands: list[list[str]] = []

        class _Result:
            def __init__(self, returncode: int) -> None:
                self.returncode = returncode
                self.stdout = ""
                self.stderr = ""

        def _fake_run(
            command: list[str],
            check: bool = False,
            capture_output: bool = False,
            text: bool = False,
        ):
            commands.append(command)
            ticker = command[command.index("--ticker") + 1]
            summary_path = Path(command[command.index("--analysis-summary-json") + 1])
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(analysis_payloads.get(ticker, {})),
                encoding="utf-8",
            )
            return _Result(0)

        # Patch subprocess.run
        monkeypatch.setattr(subprocess, "run", _fake_run)

        # Build args
        args = argparse.Namespace(
            ticker="NVDA",
            tickers=["NVDA"],
            ticker_file=None,
            event_date="2026-05-28",
            output=None,
            cache_dir="data/cache",
            use_cache=False,
            refresh_cache=False,
            seed=42,
            move_model="lognormal",
            test_data=True,
            test_scenario="baseline",
            test_data_dir=None,
            save_test_data=None,
            batch_output_dir=str(tmp_path),
            batch_summary_json=None,
            analysis_summary_json=None,
            mode="playbook-scan",
        )

        # Run the function
        from event_vol_analysis.main import _run_playbook_scan_mode

        ok = _run_playbook_scan_mode(args, ["NVDA"])

        assert ok is True
        # Verify console output was formatted
        # (function prints to stdout, so we just verify it ran)
