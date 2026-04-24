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
    get_option_expiries,
    get_options_chain,
    get_spot_price,
    load_cached_chain_at_date,
    select_front_expiry,
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
IMPLIED_MOVE_MATERIAL_SHIFT_PCT = 10.0
IV_REGIME_MATERIAL_SHIFT_PCT = 15.0


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
    use_cache: bool
    refresh_cache: bool
    validate_cache: bool


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
        choices=[
            "full-window",
            "pre-market",
            "eod-refresh",
            "overnight",
            "open-confirmation",
        ],
        help=(
            "Scan mode: full-window (today to days-ahead), pre-market (exact date), "
            "eod-refresh (capture EOD chains), overnight (analysis from cache), "
            "open-confirmation (live vs cached comparison)."
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
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help=(
            "Use cached EOD data instead of fetching live. Required for overnight mode."
        ),
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help=(
            "Force-refresh cached data with live fetch. "
            "Used by open-confirmation to get current market snapshot."
        ),
    )
    parser.add_argument(
        "--validate-cache",
        action="store_true",
        help=(
            "Validate cache coverage for universe and exit. "
            "Shows which tickers have valid EOD snapshots for --date."
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
        use_cache=args.use_cache,
        refresh_cache=args.refresh_cache,
        validate_cache=args.validate_cache,
    )

    LOGGER.info(
        "daily_scan start date=%s mode=%s dry_run=%s use_cache=%s",
        scan_date,
        cfg.mode,
        cfg.dry_run,
        cfg.use_cache,
    )

    if cfg.validate_cache:
        return _run_validate_cache(cfg)

    if cfg.mode == "eod-refresh":
        return _run_eod_refresh(cfg)

    if cfg.mode == "overnight":
        return _run_overnight_analysis(cfg)

    if cfg.mode == "open-confirmation":
        return _run_open_confirmation(cfg)

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


def _run_validate_cache(cfg: ScanConfig) -> int:
    """Check which tickers have valid EOD snapshots and print coverage summary."""
    LOGGER.info("Validating cache for date=%s", cfg.scan_date)
    store = create_store(cfg.db_path)
    coverage = store.validate_cache_coverage(cfg.tickers, cfg.scan_date)
    total = len(coverage)
    covered = sum(1 for r in coverage if r["has_cache"])
    print(f"\n=== Cache Validation: {cfg.scan_date} ===")
    print(
        f"Total tickers: {total} | Valid cache: {covered} | Missing: {total - covered}"
    )
    print(
        f"{'Ticker':<8} {'Has Cache':<12} {'Quality':<10} {'Valid Records':<14} {'Snapshot Time'}"
    )
    print("-" * 65)
    for r in coverage:
        ts = r["snapshot_ts"].strftime("%Y-%m-%d %H:%M") if r["snapshot_ts"] else "N/A"
        print(
            f"{r['ticker']:<8} "
            f"{'YES' if r['has_cache'] else 'NO':<12} "
            f"{str(r['quality_tag'] or 'N/A'):<10} "
            f"{r['records_valid']:<14} "
            f"{ts}"
        )
    LOGGER.info("Cache validation complete: %d/%d with valid snapshots", covered, total)
    return 0


def _run_eod_refresh(cfg: ScanConfig) -> int:
    """Fetch and cache EOD option chains for the full universe."""
    import time

    LOGGER.info("EOD refresh start date=%s", cfg.scan_date)
    store = create_store(cfg.db_path)
    results: list[dict[str, Any]] = []
    capture_ts = dt.datetime.now(dt.timezone.utc)
    capture_date = cfg.scan_date

    for ticker in cfg.tickers:
        LOGGER.info("EOD refresh: fetching %s", ticker)
        try:
            previous_snapshot = store.query_eod_snapshot(ticker.upper(), None, "all")
            spot = get_spot_price(ticker)
            expiries = get_option_expiries(ticker)
            if not expiries:
                LOGGER.warning("No expiries for %s at EOD refresh", ticker)
                quality = "stale"
                store.store_eod_snapshot(
                    ticker=ticker,
                    timestamp=capture_ts,
                    quality_tag=quality,
                    records_total=0,
                    records_valid=0,
                    records_invalid=0,
                    expiry_set=[],
                    spot_price=spot,
                )
                results.append(_eod_result(ticker, quality, 0, 0, 0, spot))
                continue

            records_total = 0
            records_valid = 0
            records_invalid = 0
            market_closed_detected = False

            for expiry in expiries[:3]:
                try:
                    chain = get_options_chain(
                        ticker,
                        expiry,
                        cache_dir=None,
                        use_cache=False,
                        refresh_cache=True,
                    )
                    stats = store.store_chain(
                        ticker=ticker,
                        timestamp=capture_ts,
                        chain_df=chain,
                        underlying_price=spot,
                    )
                    records_total += int(stats.get("total", 0))
                    records_valid += int(stats.get("valid", 0))
                    records_invalid += int(stats.get("filtered", 0))
                except ValueError as exc:
                    if "market appears closed" in str(exc).lower():
                        market_closed_detected = True
                    LOGGER.warning(
                        "Chain fetch failed for %s %s: %s", ticker, expiry, exc
                    )
                except Exception as exc:
                    LOGGER.warning(
                        "Chain fetch failed for %s %s: %s", ticker, expiry, exc
                    )

                time.sleep(0.3)

            if records_total > 0:
                quality = _derive_eod_quality_tag(records_total, records_valid)
            elif market_closed_detected:
                quality = "zero"
            elif _is_snapshot_stale(previous_snapshot, capture_ts):
                quality = "stale"
            else:
                quality = "stale"

            expiry_strs = [e.strftime("%Y-%m-%d") for e in expiries[:3]]
            store.store_eod_snapshot(
                ticker=ticker,
                timestamp=capture_ts,
                quality_tag=quality,
                records_total=records_total,
                records_valid=records_valid,
                records_invalid=records_invalid,
                expiry_set=expiry_strs,
                spot_price=spot,
            )
            results.append(
                _eod_result(
                    ticker, quality, records_total, records_valid, records_invalid, spot
                )
            )
            LOGGER.info(
                "EOD refresh %s: quality=%s valid=%d/%d",
                ticker,
                quality,
                records_valid,
                records_total,
            )
        except Exception as exc:
            LOGGER.error("EOD refresh failed for %s: %s", ticker, exc)
            results.append(_eod_result(ticker, "unknown", 0, 0, 0, None))

    print(f"\n=== EOD Refresh: {capture_date} ===")
    print(
        f"{'Ticker':<8} {'Quality':<10} {'Total':<8} {'Valid':<8} {'Invalid':<8} {'Spot'}"
    )
    print("-" * 55)
    for r in results:
        spot_str = f"{r['spot']:.2f}" if r["spot"] else "N/A"
        print(
            f"{r['ticker']:<8} {r['quality_tag']:<10} "
            f"{r['records_total']:<8} {r['records_valid']:<8} "
            f"{r['records_invalid']:<8} {spot_str}"
        )

    valid_count = sum(1 for r in results if r["quality_tag"] in ("valid", "partial"))
    LOGGER.info(
        "EOD refresh complete: %d/%d tickers captured", valid_count, len(results)
    )
    return 0


def _eod_result(
    ticker: str,
    quality_tag: str,
    records_total: int,
    records_valid: int,
    records_invalid: int,
    spot: float | None,
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "quality_tag": quality_tag,
        "records_total": records_total,
        "records_valid": records_valid,
        "records_invalid": records_invalid,
        "spot": spot,
    }


def _derive_eod_quality_tag(records_total: int, records_valid: int) -> str:
    """Classify EOD capture quality from valid/total counts."""
    if records_total <= 0:
        return "stale"
    if records_valid <= 0:
        return "zero"
    valid_pct = records_valid / records_total
    if valid_pct >= 0.95:
        return "valid"
    if valid_pct >= 0.50:
        return "partial"
    return "partial"


def _is_snapshot_stale(
    snapshot: dict[str, Any] | None,
    as_of: dt.datetime,
    *,
    max_age_hours: int = 24,
) -> bool:
    """Return True when latest snapshot is older than max_age_hours."""
    if snapshot is None:
        return True
    ts = snapshot.get("timestamp")
    if ts is None:
        return True
    if isinstance(ts, str):
        try:
            ts = dt.datetime.fromisoformat(ts)
        except ValueError:
            return True
    if not isinstance(ts, dt.datetime):
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    as_of_utc = (
        as_of if as_of.tzinfo is not None else as_of.replace(tzinfo=dt.timezone.utc)
    )
    return (as_of_utc - ts) > dt.timedelta(hours=max_age_hours)


def _extract_snapshot_expiries(snapshot: dict[str, Any]) -> list[str]:
    """Parse expiry_set payload from option_snapshots row."""
    expiry_strs_raw = snapshot.get("expiry_set")
    if not expiry_strs_raw:
        return []
    if isinstance(expiry_strs_raw, str):
        try:
            parsed = json.loads(expiry_strs_raw)
        except Exception:
            return []
    else:
        parsed = expiry_strs_raw
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if isinstance(item, str)]


def _resolve_snapshot_expiry_tuple(
    snapshot: dict[str, Any],
) -> tuple[dt.date | None, dt.date | None, dt.date | None]:
    """Resolve up to front/back1/back2 expiries from snapshot metadata."""
    expiry_strs = _extract_snapshot_expiries(snapshot)
    dates: list[dt.date] = []
    for item in expiry_strs:
        try:
            parsed = dt.date.fromisoformat(item)
        except ValueError:
            continue
        dates.append(parsed)
    if not dates:
        return None, None, None
    dates = sorted(set(dates))
    front = dates[0]
    back1 = dates[1] if len(dates) > 1 else front
    back2 = dates[2] if len(dates) > 2 else None
    return front, back1, back2


def _run_overnight_analysis(cfg: ScanConfig) -> int:
    """Run 4-layer analysis using cached EOD data (no live fetch)."""
    if not cfg.use_cache:
        print(
            "ERROR: overnight mode requires --use-cache flag. "
            "Run: daily_scan --mode overnight --use-cache --date YYYY-MM-DD",
            file=sys.stderr,
        )
        LOGGER.error("overnight mode called without --use-cache")
        return 2

    LOGGER.info("overnight analysis start date=%s", cfg.scan_date)
    store = create_store(cfg.db_path)

    rows: list[PlaybookScanRow] = []
    skipped: list[PlaybookScanRow] = []

    for ticker in cfg.tickers:
        snapshot = store.query_eod_snapshot(ticker.upper(), cfg.scan_date, "valid")

        # Fallback: if no snapshot, use latest from option_quotes directly
        if snapshot is None:
            latest_ts = store.get_latest_timestamp(ticker.upper())
            if latest_ts is not None:
                LOGGER.info(
                    "overnight: using fallback quote for %s from %s", ticker, latest_ts
                )
                chain_sample = store.query_chain(
                    ticker=ticker.upper(),
                    timestamp=latest_ts,
                    min_quality="all",
                )
                if not chain_sample.empty:
                    expiries = sorted(set(chain_sample["expiry"]))
                    front_expiry = expiries[0] if len(expiries) > 0 else None
                    back1_expiry = expiries[1] if len(expiries) > 1 else None
                    back2_expiry = expiries[2] if len(expiries) > 2 else None
                    spot = chain_sample["underlying_price"].iloc[0] if "underlying_price" in chain_sample.columns else None
                    ts = latest_ts
                else:
                    skipped.append(_error_row(ticker, "no fallback quotes"))
                    continue
            else:
                LOGGER.warning(
                    "overnight: no valid EOD cache for %s on %s", ticker, cfg.scan_date
                )
                skipped.append(
                    _error_row(ticker, f"no valid EOD cache for {cfg.scan_date}")
                )
                continue
        else:
            ts = snapshot.get("timestamp")
            LOGGER.info("overnight: using cache for %s from %s", ticker, ts)

            expiry_strs = _extract_snapshot_expiries(snapshot)

            if not expiry_strs:
                LOGGER.warning("overnight: no expiry data for %s in snapshot", ticker)
                skipped.append(_error_row(ticker, "no expiry data in snapshot"))
                continue

            front_expiry, back1_expiry, back2_expiry = _resolve_snapshot_expiry_tuple(
                snapshot
            )
            if front_expiry is None or back1_expiry is None:
                LOGGER.warning("overnight: could not parse expiries for %s", ticker)
                skipped.append(_error_row(ticker, "invalid cached expiry set"))
                continue

            spot = snapshot.get("spot_price")
            if spot is None or float(spot) <= 0:
                LOGGER.warning("overnight: no valid spot in snapshot for %s", ticker)
                skipped.append(_error_row(ticker, "no valid spot price in snapshot"))
                continue

            # Continue to chain loading (original path)

        chain = load_cached_chain_at_date(
            ticker.upper(),
            front_expiry,
            Path(cfg.db_path),
            cfg.scan_date,
            min_quality="valid",
        )
        if chain is None or chain.empty:
            LOGGER.warning("overnight: no valid chain for %s %s", ticker, front_expiry)
            skipped.append(
                _error_row(ticker, f"no valid chain for expiry {front_expiry}")
            )
            continue

        passes, reason = check_playbook_liquidity(chain, spot)
        if not passes:
            skipped.append(_error_row(ticker, f"liquidity filter: {reason}"))
            continue

        output_dir = cfg.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{ticker.lower()}_overnight_temp.html"
        summary_path = output_dir / f"{ticker.lower()}_overnight_analysis_summary.json"

        if summary_path.exists():
            summary_path.unlink()

        event_date = cfg.scan_date
        args_ns = argparse.Namespace(
            cache_dir="data/cache",
            event_date=event_date.isoformat(),
            use_cache=True,
            refresh_cache=False,
            cache_only=True,
            cache_spot=float(spot),
            cache_front_expiry=front_expiry.isoformat(),
            cache_back1_expiry=back1_expiry.isoformat(),
            cache_back2_expiry=(back2_expiry.isoformat() if back2_expiry else None),
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
        if result.returncode != 0 or not summary_path.exists():
            skipped.append(_error_row(ticker, "analysis pipeline failed"))
            continue

        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            skipped.append(_error_row(ticker, "failed to parse analysis_summary.json"))
            continue

        row = create_scan_row_from_snapshot(ticker, payload)
        rows.append(row)

    rows = sort_playbook_rows(rows)
    result_obj = PlaybookScanResult(
        rows=rows,
        filtered_out=skipped,
        frequency_warning_fired=False,
    )
    result_obj.compute_summary()

    report_path = _safe_save_report(result_obj, cfg.output_dir, cfg.mode, cfg.scan_date)

    actionable = [row for row in rows if row.type_ != 5]
    for row in actionable:
        alert = _format_telegram_alert(row, cfg.scan_date, cfg.mode)
        _notify(alert, dry_run=cfg.dry_run, mode=cfg.mode)

    summary_message = _summary_message(
        cfg.scan_date,
        universe=len(cfg.tickers),
        filtered=len(skipped),
        actionable=len(actionable),
        report_path=report_path,
        mode=cfg.mode,
    )
    _notify(summary_message, dry_run=cfg.dry_run, mode=cfg.mode)

    LOGGER.info("overnight analysis complete: %d actionable", len(actionable))
    return 0


def _run_open_confirmation(cfg: ScanConfig) -> int:
    """Compare live vol surface to overnight snapshot and report material changes."""
    LOGGER.info("open confirmation start date=%s", cfg.scan_date)

    print(f"\n=== Open Confirmation: {cfg.scan_date} ===")
    print("(Diff vs overnight snapshot — operator reviews)")
    print()
    print(
        f"{'Ticker':<8} {'O/N IM%':<10} {'Live IM%':<10} {'IM Shift%':<10} {'IV Shift%':<10} {'Status':<22}"
    )
    print("-" * 86)

    total = 0
    material_changes = 0
    for ticker in cfg.tickers:
        overnight_summary = _load_overnight_analysis_summary(cfg.scan_date, ticker)
        if overnight_summary is None:
            LOGGER.warning("open-confirmation: no overnight summary for %s", ticker)
            print(
                f"{ticker:<8} {'N/A':<10} {'N/A':<10} {'N/A':<10} {'N/A':<10} {'NO OVERNIGHT DATA':<22}"
            )
            continue

        live_summary = _run_live_confirmation_summary(cfg, ticker)
        if live_summary is None:
            LOGGER.warning("open-confirmation: live analysis failed for %s", ticker)
            print(
                f"{ticker:<8} {'N/A':<10} {'N/A':<10} {'N/A':<10} {'N/A':<10} {'LIVE ANALYSIS FAILED':<22}"
            )
            continue

        overnight_implied, overnight_front_iv = _extract_confirmation_metrics(
            overnight_summary
        )
        live_implied, live_front_iv = _extract_confirmation_metrics(live_summary)

        implied_shift_pct = _pct_shift(live_implied, overnight_implied)
        iv_shift_pct = _pct_shift(live_front_iv, overnight_front_iv)

        status = "OK"
        implied_material = (
            implied_shift_pct is not None
            and implied_shift_pct > IMPLIED_MOVE_MATERIAL_SHIFT_PCT
        )
        iv_material = (
            iv_shift_pct is not None and iv_shift_pct > IV_REGIME_MATERIAL_SHIFT_PCT
        )
        if implied_material or iv_material:
            status = "MATERIAL SHIFT"
            material_changes += 1
        elif implied_shift_pct is None or iv_shift_pct is None:
            status = "INSUFFICIENT DATA"

        overnight_implied_text = (
            f"{overnight_implied * 100:.2f}" if overnight_implied is not None else "N/A"
        )
        live_implied_text = (
            f"{live_implied * 100:.2f}" if live_implied is not None else "N/A"
        )
        implied_shift_text = (
            f"{implied_shift_pct:.2f}" if implied_shift_pct is not None else "N/A"
        )
        iv_shift_text = f"{iv_shift_pct:.2f}" if iv_shift_pct is not None else "N/A"

        total += 1
        print(
            f"{ticker:<8} "
            f"{overnight_implied_text:<10} "
            f"{live_implied_text:<10} "
            f"{implied_shift_text:<10} "
            f"{iv_shift_text:<10} "
            f"{status:<22}"
        )

    print()
    if material_changes > 0:
        print(
            f"WARNING: {material_changes}/{total} names have material shifts "
            f"(implied move >{IMPLIED_MOVE_MATERIAL_SHIFT_PCT:.0f}% or "
            f"front IV >{IV_REGIME_MATERIAL_SHIFT_PCT:.0f}%)."
        )
        print("Review overnight TYPE classifications before entry.")
    else:
        print(f"No material changes detected across {total} names.")

    LOGGER.info("open confirmation complete: %d material changes", material_changes)
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
    cache_store = create_store(cfg.db_path) if cfg.mode == "pre-market" else None

    for event in events:
        ticker = str(event["ticker"])
        event_date = event["event_date"]
        output_path = cfg.output_dir / f"{ticker.lower()}_daily_scan_temp.html"
        summary_path = cfg.output_dir / f"{ticker.lower()}_analysis_summary.json"
        if summary_path.exists():
            summary_path.unlink()

        cache_only = False
        cache_spot: float | None = None
        cache_front_expiry: str | None = None
        cache_back1_expiry: str | None = None
        cache_back2_expiry: str | None = None
        if cfg.mode == "pre-market" and cache_store is not None:
            snapshot = cache_store.query_eod_snapshot(
                ticker.upper(), cfg.scan_date, "valid"
            )
            if snapshot is None:
                filtered_rows.append(
                    _error_row(ticker, "no valid EOD cache for pre-market")
                )
                continue

            front_expiry, back1_expiry, back2_expiry = _resolve_snapshot_expiry_tuple(
                snapshot
            )
            if front_expiry is None or back1_expiry is None:
                filtered_rows.append(_error_row(ticker, "no valid expiry in EOD cache"))
                continue

            spot_value = _safe_float(snapshot.get("spot_price"))
            if spot_value is None or spot_value <= 0:
                filtered_rows.append(
                    _error_row(ticker, "no valid spot price in EOD cache")
                )
                continue

            cache_only = True
            cache_spot = float(spot_value)
            cache_front_expiry = front_expiry.isoformat()
            cache_back1_expiry = back1_expiry.isoformat()
            cache_back2_expiry = back2_expiry.isoformat() if back2_expiry else None

        args_ns = argparse.Namespace(
            cache_dir="data/cache",
            event_date=event_date.isoformat(),
            use_cache=True,
            refresh_cache=False,
            cache_only=cache_only,
            cache_spot=cache_spot,
            cache_front_expiry=cache_front_expiry,
            cache_back1_expiry=cache_back1_expiry,
            cache_back2_expiry=cache_back2_expiry,
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
    store = create_store(cfg.db_path) if cfg.mode == "pre-market" else None

    for event in events:
        ticker = str(event["ticker"])
        event_date = event["event_date"]
        try:
            if cfg.mode == "pre-market" and store is not None:
                snapshot = store.query_eod_snapshot(
                    ticker.upper(), cfg.scan_date, "valid"
                )
                if snapshot is None:
                    filtered.append(
                        _error_row(ticker, "no valid EOD cache for pre-market")
                    )
                    continue

                spot = snapshot.get("spot_price")
                if spot is None or float(spot) <= 0:
                    filtered.append(
                        _error_row(ticker, "no valid spot price in EOD cache")
                    )
                    continue

                front_expiry, _, _ = _resolve_snapshot_expiry_tuple(snapshot)
                if front_expiry is None:
                    filtered.append(_error_row(ticker, "no valid expiry in EOD cache"))
                    continue

                chain = load_cached_chain_at_date(
                    ticker.upper(),
                    front_expiry,
                    Path(cfg.db_path),
                    cfg.scan_date,
                    min_quality="valid",
                )
                if chain is None or chain.empty:
                    filtered.append(_error_row(ticker, "no valid chain in EOD cache"))
                    continue
            else:
                spot = get_spot_price(ticker)
                expiries = get_option_expiries(ticker)
                try:
                    front_expiry = select_front_expiry(
                        expiries,
                        event_date,
                        ticker=ticker,
                        event_time_label=event.get("event_time_label"),
                    )
                except ValueError:
                    filtered.append(
                        _error_row(
                            ticker=ticker,
                            reason="no valid expiry on/after event date",
                        )
                    )
                    continue
                chain = get_options_chain(
                    ticker,
                    front_expiry,
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


def _load_overnight_analysis_summary(
    scan_date: dt.date,
    ticker: str,
    overnight_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Load prior overnight summary payload for one ticker/date."""
    base_dir = overnight_dir or Path("reports/overnight")
    path = base_dir / f"{ticker.lower()}_overnight_analysis_summary.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if str(payload.get("event_date")) != scan_date.isoformat():
        return None
    return payload


def _run_live_confirmation_summary(
    cfg: ScanConfig,
    ticker: str,
) -> dict[str, Any] | None:
    """Run one live analysis summary for open-confirmation diffing."""
    output_dir = cfg.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{ticker.lower()}_open_confirmation_temp.html"
    summary_path = output_dir / f"{ticker.lower()}_open_confirmation_summary.json"
    if summary_path.exists():
        summary_path.unlink()

    args_ns = argparse.Namespace(
        cache_dir="data/cache",
        event_date=cfg.scan_date.isoformat(),
        use_cache=False,
        refresh_cache=cfg.refresh_cache,
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
    if result.returncode != 0 or not summary_path.exists():
        return None

    try:
        return json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _extract_confirmation_metrics(
    summary: dict[str, Any],
) -> tuple[float | None, float | None]:
    """Return (implied_move, front_iv) from analysis summary payload."""
    implied_move = _safe_float(summary.get("implied_move"))
    front_iv = _safe_float(summary.get("front_iv"))
    return implied_move, front_iv


def _safe_float(value: Any) -> float | None:
    """Convert value to float when possible; otherwise return None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct_shift(current: float | None, baseline: float | None) -> float | None:
    """Return absolute percent shift between two scalar values."""
    if current is None or baseline is None:
        return None
    if baseline == 0:
        return None
    return abs((current - baseline) / baseline) * 100.0


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
        elif mode == "overnight":
            output_dir.mkdir(parents=True, exist_ok=True)
            today = scan_date.isoformat()
            filename = f"{today}_overnight_scan.html"
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

    if mode == "overnight":
        return (
            "[OVERNIGHT EARNINGS ANALYSIS] "
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
        else "[OVERNIGHT EARNINGS ANALYSIS COMPLETE]"
        if mode == "overnight"
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

    if mode in ("pre-market", "overnight"):
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
    if mode == "overnight":
        return Path("reports/overnight")
    if mode == "open-confirmation":
        return Path("reports/confirmation")
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
