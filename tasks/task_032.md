id: T032
title: Automated Earnings Season Workflow

objective:
  Implement a daily cron job that pulls the earnings calendar for the next 10-14
  days, applies hard liquidity filters, runs the 4-layer playbook-scan on all
  names that pass filters, and sends a Telegram alert for any non-TYPE-5
  classification. Morning-scan reports are saved daily to reports/daily/.

context:
  Manual runs of the analysis are sufficient during development. In production
  (earnings season), the operator needs this to run automatically each morning
  before market open. The workflow is a wrapper around the existing batch mode
  with playbook-scan output (T029) plus Telegram notification for non-TYPE-5
  names. The human-in-the-loop constraint is preserved: the cron fires alerts
  and saves reports; no trade is placed automatically.

inputs:
  - Earnings calendar auto-fetch for next 10-14 days (from T020 infrastructure)
  - Liquidity filter thresholds from config (bid-ask <15%, OI >500, vol >1000)
  - Telegram bot token and chat ID from config/secrets (environment variable)
  - DB path for event store

outputs:
  - scripts/run_daily_earnings_scan.sh (shell wrapper for cron)
  - event_vol_analysis/workflow/daily_scan.py (Python orchestration)
  - Telegram message for each non-TYPE-5 name: compact format with TYPE,
    confidence, and action guidance
  - Daily report saved to reports/daily/YYYY-MM-DD_playbook_scan.html
  - Run log saved to logs/daily_scan.log

prerequisites:
  - T029 (playbook-scan report format)
  - T031 (calibration loop; recommended to run weekly after daily scan accumulates data)

dependencies:
  - T029
  - T031

non_goals:
  - No automated order placement
  - No live option pricing during cron (uses last-available chain data from loader)
  - No intraday re-scan (once per day, morning only)
  - No email alerting (Telegram only; consistent with existing paper-trading cron)

requirements:
  - daily_scan.py orchestration:
    - Step 1: fetch earnings calendar for next 10-14 days (get_earnings_dates
      or auto-ingestion from T020)
    - Step 2: apply hard filters; drop names that fail; log filtered names
    - Step 3: run playbook-scan batch (--mode playbook-scan) on remaining names
    - Step 4: collect TypeClassification results
    - Step 5: for each non-TYPE-5 name, send Telegram alert
    - Step 6: save HTML report to reports/daily/
    - Step 7: append summary line to logs/daily_scan.log
  - Telegram alert format per non-TYPE-5 name:
    [EARNINGS SCAN] {YYYY-MM-DD}
    {TICKER} | TYPE {N} | {CONFIDENCE} confidence
    Vol: {label} | Edge: {label} ({ratio:.2f}x)
    Action: {action_guidance}
    [PHASE 2 CHECKLIST — see report]  (TYPE 4 only)
  - Telegram summary message (sent after individual alerts):
    [EARNINGS SCAN COMPLETE] {YYYY-MM-DD}
    Universe: {N} names | Filtered: {K} | Actionable: {M} non-TYPE-5
    Report: reports/daily/{date}_playbook_scan.html
  - If no non-TYPE-5 names: send single summary message only (no individual alerts)
  - Telegram credentials: read from environment variables
    TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (same as paper-trading cron)
  - If Telegram unavailable: log alert content to logs/daily_scan.log and
    continue (do not abort run)
  - scripts/run_daily_earnings_scan.sh:
    - Activates .venv
    - Exports required env vars (sources from .env file if present)
    - Calls python -m event_vol_analysis.workflow.daily_scan
    - Logs exit code and timestamp
  - Cron schedule: 08:00 CET (02:00 ET) during earnings season
    (operator manually activates/deactivates via cron; no auto-detection of
    earnings season)
  - Manual trigger: python -m event_vol_analysis.workflow.daily_scan --dry-run
    (--dry-run runs analysis and prints alerts to console without sending Telegram)

acceptance_criteria:
  - daily_scan.py runs end-to-end without error on a 5-name test universe
  - Telegram alert sent for each non-TYPE-5 name (or logged if unavailable)
  - Summary message sent after individual alerts
  - HTML report saved to reports/daily/ with date in filename
  - Log entry appended to logs/daily_scan.log on each run
  - --dry-run flag suppresses Telegram and prints to console instead
  - Filtered names logged with reason at start of run

tests:
  unit:
    - test_telegram_alert_format_type1
    - test_telegram_alert_format_type4_includes_checklist_note
    - test_telegram_summary_message
    - test_no_alerts_when_all_type5
    - test_telegram_unavailable_falls_back_to_log
    - test_dry_run_suppresses_telegram
    - test_log_entry_appended
  integration:
    - Full dry-run on 5-name synthetic universe → console output, report saved,
      no Telegram sent

definition_of_done:
  - workflow/daily_scan.py implemented with all 7 steps
  - scripts/run_daily_earnings_scan.sh working with cron-compatible shebang
  - Telegram alerting with dry-run fallback
  - Daily report saved to reports/daily/
  - Run log written to logs/daily_scan.log
  - All unit and integration tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Cron timing (08:00 CET) is chosen to be before market open but after any
    significant AMC earnings from the prior day are available in price history.
  - The operator activates the cron manually at the start of earnings season
    and deactivates at the end. This is intentional — do not auto-detect seasons.
  - Telegram credentials use environment variables (same pattern as paper-trading
    system, consistent with existing setup). Do not hardcode credentials.
  - The daily_scan.py is a thin orchestration wrapper. All analysis logic lives
    in the modules it calls (T023-T029). Keep this script simple and auditable.

failure_modes:
  - Earnings calendar fetch returns zero names → log "No names found for
    window", send Telegram summary with N=0, exit 0
  - All names filtered out → log "All names filtered", send summary, exit 0
  - One ticker fails analysis → log error, skip ticker, continue with rest
  - Report write fails → log error, continue with Telegram (partial report ok)
  - Telegram send fails → log full alert content to log file, continue
  - --dry-run mode: all Telegram calls replaced with console print; no side
    effects to external systems
