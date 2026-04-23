id: T043
title: Pre-Market Same-Day Earnings Window

objective:
  Add a pre-market same-day scan mode that runs the existing 4-layer snapshot
  and TYPE classification for earnings scheduled on an exact date, sends
  non-TYPE-5 alerts, and writes a dedicated pre-market HTML report.

context:
  T032 covers a forward earnings window scan. T043 adds a same-day pre-market
  operator workflow so names reporting at the open can be reviewed before the
  bell using the same playbook logic and hard liquidity gates.

inputs:
  - T032 daily scan workflow infrastructure (`daily_scan.py`)
  - Existing 4-layer snapshot + TYPE classification output pipeline
  - Telegram CLI tool `telegram-send` (operator-provided)

outputs:
  - `daily_scan.py --mode pre-market --date YYYY-MM-DD`
  - `scripts/run_pre_market_scan.sh`
  - Cron entry for pre-market schedule in `crontab.txt`
  - Report path: `reports/pre-market/YYYY-MM-DD_pre_market_scan.html`
  - Log path: `logs/pre_market_scan.log`

prerequisites:
  - T032

dependencies:
  - T032

non_goals:
  - No automated order placement
  - No changes to playbook logic or liquidity thresholds
  - No replacement of T032 forward-window mode

requirements:
  - Add `--mode` flag to daily scan workflow with values:
      - `full-window` (default, T032 behavior)
      - `pre-market` (exact-date scan)
  - Add `--date YYYY-MM-DD` support for explicit scan date selection
  - In `pre-market` mode:
      - Calendar filter is exact date match (`event_date == scan_date`)
      - Alerts use `telegram-send` CLI (not bot HTTP API)
      - If `telegram-send` is unavailable/fails, log alert content and continue
      - Report file is named `YYYY-MM-DD_pre_market_scan.html`
  - Add wrapper script `scripts/run_pre_market_scan.sh`:
      - Sources `.env` if present
      - Calls `python -m event_vol_analysis.workflow.daily_scan --mode pre-market`
      - Logs start/end and exit code to `logs/pre_market_scan.log`
  - Add pre-market cron entry to `crontab.txt` at 03:45 ET / 08:45 CET

acceptance_criteria:
  - `python -m event_vol_analysis.workflow.daily_scan --mode pre-market --date
    YYYY-MM-DD` runs without changing full-window behavior
  - Pre-market alert format includes:
    `[PRE-MARKET EARNINGS SCAN] TICKER: TYPE X | IV Regime: ... | Edge Ratio: ...`
  - `telegram-send` path works and fallback path is graceful
  - Pre-market report saves to `reports/pre-market/` with expected filename
  - Wrapper script exists and is executable

tests:
  unit:
    - test_pre_market_alert_format_single_line
    - test_pre_market_summary_message_title
    - test_notify_pre_market_uses_telegram_send
    - test_notify_pre_market_fallback_when_cli_missing
    - test_fetch_upcoming_events_pre_market_exact_date
    - test_safe_save_report_pre_market_filename
    - test_resolve_output_dir_by_mode
  integration:
    - daily scan workflow tests remain green with pre-market mode added

definition_of_done:
  - Pre-market mode implemented and tested
  - Wrapper script and cron entry added
  - Documentation updated (roadmap/tasks/operator functionality)
  - Task marked completed in `docs/TASKS.md`

failure_modes:
  - Invalid `--date` format: print error to stderr and return exit code 2
  - `telegram-send` missing/failing: log fallback alert and continue
  - No events on exact date: summary only, exit 0
