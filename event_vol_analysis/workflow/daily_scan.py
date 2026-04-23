"""Daily earnings scan orchestration with Telegram alert integration (T032)."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from data.option_data_store import create_store
from event_option_playbook.backfill import auto_ingest_earnings_calendar_db
from event_vol_analysis import config
from event_vol_analysis.main import _batch_command_for_ticker
from event_vol_analysis.data.loader import (
    get_expiries_after,
    get_option_expiries,
    get_options_chain,
    get_spot_price,
)
from event_vol_analysis.reports.playbook_scan import (
    PlaybookScanResult,
    PlaybookScanRow,
    check_playbook_liquidity,
    create_scan_row_from_snapshot,
    render_playbook_scan_html,
    save_playbook_scan_report,
    sort_playbook_rows,
)


LOGGER = logging.getLogger(__name__)
LOG_PATH = Path("logs/daily_scan.log")


@dataclass(frozen=True)
class ScanConfig:
    """Runtime config for daily workflow orchestration."""

    tickers: list[str]
    db_path: str
    output_dir: Path
    mode: str
    scan_date: dt.date
    days_ahead: int
    limit_per_ticker: int
    dry_run: bool


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for daily scan workflow."""

    parser = argparse.ArgumentParser(
        description=(
            "Run daily earnings playbook scan and send Telegram alerts "
            "for non-TYPE-5 names."
        )
    )
    parser.add_argument(
        "--tickers",
        default="",
        help=(
            "Comma-separated ticker override. If omitted, uses "
            "ticker_list.csv "
            "(or fallback defaults)."
        ),
    )
    parser.add_argument(
        "--ticker-file",
        default="ticker_list.csv",
        help="Ticker file path (comma/newline separated).",
    )
    parser.add_argument(
        "--db",
        default="data/options_intraday.db",
        help="SQLite db path for event/options store.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Directory for scan HTML report. Defaults to reports/daily for "
            "full-window mode and reports/pre-market for pre-market mode."
        ),
    )
    parser.add_argument(
        "--days-ahead",
        type=int,
        default=14,
        help="Forward calendar window for scheduled events.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Max earnings dates pulled per ticker from yfinance.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run analysis and print alerts without Telegram sends.",
    )
    parser.add_argument(
        "--mode",
        default="full-window",
        choices=["full-window", "pre-market"],
        help=(
            "Scan mode: full-window keeps T032 behavior (today to days-ahead), "
            "pre-market scans one exact date."
        ),
    )
    parser.add_argument(
        "--date",
        default=None,
        help=(
            "Scan date in YYYY-MM-DD. Defaults to today. In pre-market mode "
            "this date is matched exactly."
        ),
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    """Run daily scan orchestration and return process exit code."""

    args = build_parser().parse_args(argv)
    _ensure_log_file()
    _configure_logging()

    tickers = _resolve_tickers(args.tickers, args.ticker_file)
    try:
        scan_date = _resolve_scan_date(args.date)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    output_dir = _resolve_output_dir(args.output_dir, args.mode)
    cfg = ScanConfig(
        tickers=tickers,
        db_path=args.db,
        output_dir=output_dir,
        mode=args.mode,
        scan_date=scan_date,
        days_ahead=args.days_ahead,
        limit_per_ticker=args.limit,
        dry_run=args.dry_run,
    )

    LOGGER.info("daily_scan start date=%s dry_run=%s", scan_date, cfg.dry_run)
    summary: dict[str, Any] = {
        "scan_date": scan_date.isoformat(),
        "universe": 0,
        "filtered": 0,
        "actionable": 0,
        "report": None,
        "mode": cfg.mode,
    }

    events = _fetch_upcoming_earnings_events(cfg)
    summary["universe"] = len(events)

    if not events:
        message = _summary_message(
            scan_date,
            0,
            0,
            0,
            report_path=None,
            mode=cfg.mode,
        )
        _notify(message, dry_run=cfg.dry_run, mode=cfg.mode)
        _append_run_log(summary)
        return 0

    eligible_events, prefiltered_rows = _apply_hard_filters(cfg, events)
    for row in prefiltered_rows:
        LOGGER.info(
            "Filtered %s: %s",
            row.ticker,
            row.filter_reason or "unknown reason",
        )

    if not eligible_events:
        summary["filtered"] = len(prefiltered_rows)
        summary_message = _summary_message(
            scan_date,
            universe=len(events),
            filtered=len(prefiltered_rows),
            actionable=0,
            report_path=None,
            mode=cfg.mode,
        )
        _notify(summary_message, dry_run=cfg.dry_run, mode=cfg.mode)
        _append_run_log(summary)
        return 0

    rows, analysis_filtered = _run_playbook_scan_rows(cfg, eligible_events)
    filtered_rows = [*prefiltered_rows, *analysis_filtered]
    rows = sort_playbook_rows(rows)
    result = PlaybookScanResult(
        rows=rows,
        filtered_out=filtered_rows,
        frequency_warning_fired=False,
    )
    result.compute_summary()

    report_path = _safe_save_report(result, cfg.output_dir, cfg.mode, scan_date)
    summary["filtered"] = len(filtered_rows)

    actionable = [row for row in rows if row.type_ != 5]
    summary["actionable"] = len(actionable)
    summary["report"] = str(report_path) if report_path else None

    for row in actionable:
        alert = _format_telegram_alert(row, scan_date, cfg.mode)
        _notify(alert, dry_run=cfg.dry_run, mode=cfg.mode)

    summary_message = _summary_message(
        scan_date,
        universe=len(events),
        filtered=len(filtered_rows),
        actionable=len(actionable),
        report_path=report_path,
        mode=cfg.mode,
    )
    _notify(summary_message, dry_run=cfg.dry_run, mode=cfg.mode)

    _append_run_log(summary)
    return 0


def _resolve_tickers(cli_tickers: str, ticker_file: str) -> list[str]:
    """Resolve ticker universe from CLI override, file, or defaults."""

    if cli_tickers.strip():
        return _normalize_ticker_tokens(cli_tickers.split(","))

    path = Path(ticker_file)
    if path.exists():
        tokens = path.read_text(encoding="utf-8").replace("\n", ",").split(",")
        resolved = _normalize_ticker_tokens(tokens)
        if resolved:
            return resolved

    return list(dict.fromkeys(config.TICKER.upper() for _ in range(1)))


def _normalize_ticker_tokens(tokens: list[str]) -> list[str]:
    """Normalize tokens to de-duplicated uppercase tickers."""

    normalized: list[str] = []
    for token in tokens:
        ticker = token.strip().upper()
        if not ticker:
            continue
        if ticker in normalized:
            continue
        normalized.append(ticker)
    return normalized


def _fetch_upcoming_earnings_events(cfg: ScanConfig) -> list[dict[str, Any]]:
    """Fetch calendar events and return unique ticker/date pairs in window."""

    start_date = cfg.scan_date
    horizon = start_date + dt.timedelta(days=cfg.days_ahead)
    ingest = auto_ingest_earnings_calendar_db(
        cfg.tickers,
        db_path=cfg.db_path,
        limit=cfg.limit_per_ticker,
        on_or_after=start_date,
    )
    LOGGER.info(
        "calendar_ingest processed=%s created=%s updated=%s errors=%s",
        ingest.get("tickers_processed", 0),
        ingest.get("events_created", 0),
        ingest.get("events_updated", 0),
        len(ingest.get("fetch_errors", [])),
    )

    store = create_store(cfg.db_path)
    registry = store.get_event_registry()
    if registry.empty:
        LOGGER.info("No events found in event_registry after ingestion")
        return []

    base_mask = (registry["event_family"].astype(str).str.lower() == "earnings") & (
        registry["event_status"].astype(str).str.lower() == "scheduled"
    )
    if cfg.mode == "pre-market":
        window_mask = registry["event_date"] == start_date
    else:
        window_mask = (registry["event_date"] >= start_date) & (
            registry["event_date"] <= horizon
        )
    frame = registry[base_mask & window_mask].copy()
    if frame.empty:
        if cfg.mode == "pre-market":
            LOGGER.info("No names found for exact scan date %s", start_date)
        else:
            LOGGER.info("No names found for window %s to %s", start_date, horizon)
        return []

    frame = frame.sort_values(["event_date", "underlying_symbol"])
    events: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        events.append(
            {
                "ticker": str(row["underlying_symbol"]).upper(),
                "event_date": row["event_date"],
            }
        )
    return events


def _run_playbook_scan_rows(
    cfg: ScanConfig,
    events: list[dict[str, Any]],
) -> tuple[list[PlaybookScanRow], list[PlaybookScanRow]]:
    """Run single-ticker pipeline and convert snapshots to scan rows."""

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[PlaybookScanRow] = []
    filtered_rows: list[PlaybookScanRow] = []

    for event in events:
        ticker = str(event["ticker"])
        event_date = event["event_date"]
        output_path = cfg.output_dir / f"{ticker.lower()}_daily_scan_temp.html"
        summary_path = cfg.output_dir / f"{ticker.lower()}_analysis_summary.json"
        if summary_path.exists():
            summary_path.unlink()

        args_ns = argparse.Namespace(
            cache_dir="data/cache",
            event_date=event_date.isoformat(),
            use_cache=True,
            refresh_cache=False,
            seed=None,
            move_model=config.MOVE_MODEL_DEFAULT,
            test_data=False,
            test_scenario="baseline",
            test_data_dir=None,
            save_test_data=None,
        )
        cmd = _batch_command_for_ticker(
            args_ns,
            ticker,
            output_path,
            analysis_summary_path=summary_path,
        )

        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            filtered_rows.append(
                _error_row(
                    ticker=ticker,
                    reason=(
                        result.stderr or result.stdout or "analysis failed"
                    ).strip(),
                )
            )
            LOGGER.error(
                "Ticker %s failed analysis (rc=%s)",
                ticker,
                result.returncode,
            )
            continue

        if not summary_path.exists():
            filtered_rows.append(
                _error_row(
                    ticker=ticker,
                    reason="analysis_summary.json not generated",
                )
            )
            continue

        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            filtered_rows.append(
                _error_row(
                    ticker=ticker,
                    reason="failed to parse analysis_summary.json",
                )
            )
            continue

        row = create_scan_row_from_snapshot(ticker, payload)
        rows.append(row)

    return rows, filtered_rows


def _apply_hard_filters(
    cfg: ScanConfig,
    events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[PlaybookScanRow]]:
    """Apply strict liquidity filters before running analysis pipeline."""

    passed: list[dict[str, Any]] = []
    filtered: list[PlaybookScanRow] = []

    for event in events:
        ticker = str(event["ticker"])
        event_date = event["event_date"]
        try:
            spot = get_spot_price(ticker)
            expiries = get_option_expiries(ticker)
            valid_expiries = get_expiries_after(expiries, event_date)
            if not valid_expiries:
                filtered.append(
                    _error_row(
                        ticker=ticker,
                        reason="no valid expiry on/after event date",
                    )
                )
                continue

            expiry = valid_expiries[0]
            chain = get_options_chain(
                ticker,
                expiry,
                cache_dir=Path("data/cache"),
                use_cache=True,
                refresh_cache=False,
            )
            passes, reason = check_playbook_liquidity(chain, spot)
            if not passes:
                filtered.append(
                    _error_row(
                        ticker=ticker,
                        reason=(reason or "failed hard liquidity filter"),
                    )
                )
                continue
        except Exception as exc:  # pragma: no cover
            filtered.append(
                _error_row(
                    ticker=ticker,
                    reason=f"hard filter error: {exc}",
                )
            )
            continue

        passed.append(event)

    return passed, filtered


def _error_row(ticker: str, reason: str) -> PlaybookScanRow:
    """Construct one filtered/error row for logging and report context."""

    return PlaybookScanRow(
        ticker=ticker,
        earnings_date="N/A",
        vol_regime="N/A",
        edge_ratio="N/A",
        positioning="N/A",
        signal="N/A",
        type_=5,
        confidence="N/A",
        action="FILTERED",
        filter_reason=reason,
    )


def _safe_save_report(
    result: PlaybookScanResult,
    output_dir: Path,
    mode: str,
    scan_date: dt.date,
) -> Path | None:
    """Save report and swallow IO failures per task failure-mode policy."""

    try:
        if mode == "pre-market":
            output_dir.mkdir(parents=True, exist_ok=True)
            today = scan_date.isoformat()
            filename = f"{today}_pre_market_scan.html"
            path = output_dir / filename
            html_content = render_playbook_scan_html(result, today)
            path.write_text(html_content, encoding="utf-8")
        else:
            path = save_playbook_scan_report(result, output_dir=output_dir)
    except OSError as exc:
        LOGGER.error("Report write failed: %s", exc)
        return None
    LOGGER.info("Daily scan report saved: %s", path)
    return path


def _format_telegram_alert(
    row: PlaybookScanRow,
    scan_date: dt.date,
    mode: str = "full-window",
) -> str:
    """Build per-ticker actionable Telegram alert message."""

    edge_ratio = row.edge_ratio_detail.get("ratio") if row.edge_ratio_detail else None
    edge_ratio_text = f"{float(edge_ratio):.2f}x" if edge_ratio is not None else "N/A"
    vol_label = row.vol_regime
    edge_label = row.edge_ratio_detail.get("label") if row.edge_ratio_detail else "N/A"

    if mode == "pre-market":
        return (
            "[PRE-MARKET EARNINGS SCAN] "
            f"{row.ticker}: TYPE {row.type_} | "
            f"IV Regime: {vol_label} | "
            f"Edge Ratio: {edge_label} ({edge_ratio_text})"
        )

    lines = [
        f"[EARNINGS SCAN] {scan_date.isoformat()}",
        f"{row.ticker} | TYPE {row.type_} | {row.confidence} confidence",
        f"Vol: {vol_label} | Edge: {edge_label} ({edge_ratio_text})",
        f"Action: {row.action}",
    ]
    if row.type_ == 4:
        lines.append("[PHASE 2 CHECKLIST - see report]")
    return "\n".join(lines)


def _summary_message(
    scan_date: dt.date,
    universe: int,
    filtered: int,
    actionable: int,
    report_path: Path | None,
    mode: str = "full-window",
) -> str:
    """Build daily scan completion summary message."""

    report_label = (
        str(report_path) if report_path is not None else "(report unavailable)"
    )
    title = (
        "[PRE-MARKET EARNINGS SCAN COMPLETE]"
        if mode == "pre-market"
        else "[EARNINGS SCAN COMPLETE]"
    )
    return "\n".join(
        [
            f"{title} {scan_date.isoformat()}",
            (
                f"Universe: {universe} names | Filtered: {filtered} "
                f"| Actionable: {actionable} non-TYPE-5"
            ),
            f"Report: {report_label}",
        ]
    )


def _notify(
    message: str,
    *,
    dry_run: bool,
    mode: str = "full-window",
) -> None:
    """Send Telegram notification or fallback to console/log output."""

    if dry_run:
        print(message)
        LOGGER.info("DRY RUN ALERT:\n%s", message)
        return

    if mode == "pre-market":
        _notify_via_telegram_send(message)
        return

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        LOGGER.warning("Telegram env vars missing; logging alert instead")
        LOGGER.info("ALERT (fallback):\n%s", message)
        return

    try:
        _send_telegram_message(token, chat_id, message)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.error("Telegram unavailable; logging alert instead: %s", exc)
        LOGGER.info("ALERT (fallback):\n%s", message)


def _notify_via_telegram_send(message: str) -> None:
    """Send message through telegram-send CLI with graceful fallback."""

    binary = shutil.which("telegram-send")
    if binary is None:
        LOGGER.warning("telegram-send not found; logging alert instead")
        LOGGER.info("ALERT (fallback):\n%s", message)
        return

    result = subprocess.run(
        [binary, message],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        LOGGER.warning(
            "telegram-send failed (rc=%s): %s",
            result.returncode,
            (result.stderr or "").strip() or "no stderr",
        )
        LOGGER.info("ALERT (fallback):\n%s", message)


def _send_telegram_message(token: str, chat_id: str, text: str) -> None:
    """Send one Telegram message via bot HTTP API."""

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
        }
    ).encode("utf-8")
    request = urllib.request.Request(url=url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status >= 400:
                raise RuntimeError(f"telegram_http_status={response.status}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"telegram_send_failed: {exc}") from exc


def _ensure_log_file() -> None:
    """Ensure logs directory and daily log file exist."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not LOG_PATH.exists():
        LOG_PATH.write_text("", encoding="utf-8")


def _configure_logging() -> None:
    """Configure logger to file + stderr once per run."""

    if LOGGER.handlers:
        return

    LOGGER.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    LOGGER.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    LOGGER.addHandler(stream_handler)


def _append_run_log(summary: dict[str, Any]) -> None:
    """Append one compact JSON run-line to daily scan log."""

    line = json.dumps(summary, sort_keys=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _resolve_output_dir(output_dir: str | None, mode: str) -> Path:
    """Resolve report output directory by mode and optional override."""

    if output_dir:
        return Path(output_dir)
    if mode == "pre-market":
        return Path("reports/pre-market")
    return Path("reports/daily")


def _resolve_scan_date(value: str | None) -> dt.date:
    """Resolve scan date from CLI value or default to today."""

    if not value:
        return dt.date.today()
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("--date must be YYYY-MM-DD") from exc


def main() -> None:
    """Script entrypoint."""

    raise SystemExit(run())


if __name__ == "__main__":
    main()
