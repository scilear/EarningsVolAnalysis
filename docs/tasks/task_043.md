# Task 043 — Pre-Market Same-Day Earnings Window

**Priority:** P1  
**Status:** pending  
**Depends On:** T032  
**Estimated Effort:** 2–3 hours  

---

## Summary

Add a pre-market (3:45 AM ET) scan mode for same-day earnings names that complements T032's 10–14 day forward window. Use `telegram-send` CLI tool for alert delivery.

---

## Problem Statement

T032 covers earnings 10–14 days in the future. During earnings season, 7–10 companies report earnings at market open every trading day. Currently:

- No playbook snapshot for same-day names until market open (when options data available)
- Operators must wait until 09:30 ET to run analysis on today's earnings
- Early names can gap significantly at open; pre-market preview enables faster decision-making

**Solution:** Run T032 logic against today's earnings only, at 3:45 AM ET, before market opens.

---

## Scope

### In Scope
- New CLI mode `--mode pre-market` in `daily_scan.py`
- Pre-market cron job (08:45 CET / 3:45 AM ET)
- Integration with `telegram-send` CLI (not Python library)
- Separate report directory for pre-market vs. full-window scans
- Graceful fallback if `telegram-send` unavailable

### Out of Scope
- Real market data at 3:45 AM (won't exist; test-data only for validation)
- Modifying core 4-layer snapshot or filtering logic
- Automatic trade execution
- Intraday rebalancing or monitoring

---

## Detailed Deliverables

### 1. CLI Enhancement: `daily_scan --mode pre-market`

**File:** `event_vol_analysis/workflow/daily_scan.py`

Add argument:
```python
parser.add_argument(
    '--mode',
    choices=['full-window', 'pre-market'],
    default='full-window',
    help='Scan mode: full-window (10-14 DTE) or pre-market (same-day only)'
)
```

Logic:
```python
if args.mode == 'pre-market':
    # Calendar query: earnings_date == TODAY (exact match)
    # Not: earnings_date >= TODAY
    calendar_df = calendar_df[calendar_df['earnings_date'] == today_iso]
else:
    # T032 behavior: earnings_date in [TODAY, TODAY + 14 days]
    calendar_df = calendar_df[
        (calendar_df['earnings_date'] >= today_iso) & 
        (calendar_df['earnings_date'] <= forward_iso)
    ]
```

### 2. New Shell Script: `scripts/run_pre_market_scan.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/fabien/Documents/EarningsVolAnalysis"
VENV_PYTHON="${PROJECT_DIR}/venv/bin/python"
LOG_PATH="${PROJECT_DIR}/logs/pre_market_scan.log"
REPORT_DIR="${PROJECT_DIR}/reports/pre-market"

mkdir -p "${LOG_PATH%/*}" "${REPORT_DIR}"

# Load telegram-send config if available
if command -v telegram-send &> /dev/null; then
  HAS_TELEGRAM=true
else
  HAS_TELEGRAM=false
fi

timestamp="$(date -Iseconds)"
echo "${timestamp} pre_market_scan start mode=pre-market" >> "${LOG_PATH}"

set +e
"${VENV_PYTHON}" -m event_vol_analysis.workflow.daily_scan \
  --mode pre-market \
  --date "$(date +%Y-%m-%d)" \
  --output-dir "${REPORT_DIR}" \
  "$@"
exit_code=$?
set -e

if [[ $exit_code -eq 0 && "$HAS_TELEGRAM" == "true" ]]; then
  # Parse report and send alerts (see section 3 below)
  :
fi

timestamp_end="$(date -Iseconds)"
echo "${timestamp_end} pre_market_scan exit_code=${exit_code}" >> "${LOG_PATH}"

exit "${exit_code}"
```

### 3. Telegram Integration via `telegram-send`

**File:** `event_vol_analysis/workflow/daily_scan.py` (function addition)

```python
def send_telegram_alert(ticker: str, type_num: int, vol_regime: str, edge_ratio: str):
    """Send pre-market scan alert via telegram-send CLI."""
    import subprocess
    
    msg = f"[PRE-MARKET SCAN] {ticker}: TYPE {type_num} | Vol: {vol_regime} | Edge: {edge_ratio}"
    
    try:
        subprocess.run(['telegram-send', msg], check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        # telegram-send not available or failed; log and continue
        logging.warning(f"telegram-send unavailable; alert not sent for {ticker}")
```

Call `send_telegram_alert()` in the scan loop for each non-TYPE-5 name:
```python
if classification.type_num != 5:
    send_telegram_alert(
        ticker=name,
        type_num=classification.type_num,
        vol_regime=classification.vol_regime.label,
        edge_ratio=classification.edge_ratio.label
    )
```

### 4. Report Path: `reports/pre-market/YYYY-MM-DD_pre_market_scan.html`

Modify report writer to check `--mode` flag and save to appropriate directory:
```python
if args.mode == 'pre-market':
    report_path = args.output_dir / f"{today}_pre_market_scan.html"
else:
    report_path = args.output_dir / f"{today}_playbook_scan.html"
```

### 5. Cron Entry

**File:** `crontab.txt` (or `/etc/cron.d/earnings-vol-pre-market`)

```cron
# Pre-market earnings scan: 08:45 CET (03:45 AM ET)
45 8 * * 1-5 /home/fabien/Documents/EarningsVolAnalysis/scripts/run_pre_market_scan.sh >> /dev/null 2>&1
```

Install via:
```bash
(crontab -l 2>/dev/null || true; echo "45 8 * * 1-5 /path/to/run_pre_market_scan.sh") | crontab -
```

---

## Acceptance Criteria

- [ ] `daily_scan --mode pre-market --date 2026-04-24` runs without error
- [ ] Output includes exactly the names with `earnings_date == 2026-04-24` (not >=)
- [ ] 4-layer snapshot structure identical to T032 output
- [ ] Report saved to `reports/pre-market/2026-04-24_pre_market_scan.html`
- [ ] For each non-TYPE-5 name, `telegram-send` invoked (or logged as unavailable)
- [ ] Log entry in `logs/pre_market_scan.log` with exit code
- [ ] Cron job can be installed via `./install_cron_pre_market.sh` (or manual instruction)
- [ ] Dry-run test succeeds: `./scripts/run_pre_market_scan.sh --dry-run`
- [ ] Graceful fallback: script succeeds even if `telegram-send` not installed

---

## Testing Strategy

### Manual (before cron)
```bash
cd ~/Documents/EarningsVolAnalysis
source venv/bin/activate

# Test 1: Dry-run against today
python -m event_vol_analysis.workflow.daily_scan \
  --mode pre-market \
  --date $(date +%Y-%m-%d) \
  --dry-run

# Test 2: Dry-run against a known earnings date
python -m event_vol_analysis.workflow.daily_scan \
  --mode pre-market \
  --date 2026-04-24 \
  --output-dir reports/pre-market \
  --dry-run

# Test 3: Shell script wrapper
./scripts/run_pre_market_scan.sh --dry-run
```

### Automated
- Regression smoke tests: ensure full-window mode still works (T032 regression)
- Calendar filter test: verify only same-date earnings included in pre-market mode
- Report generation test: validate HTML output structure matches T029 spec

---

## Implementation Checklist

- [ ] Add `--mode` argument to `daily_scan.py`
- [ ] Implement calendar filter logic (exact date match vs. range)
- [ ] Add `send_telegram_alert()` function
- [ ] Update report path logic based on mode
- [ ] Create `scripts/run_pre_market_scan.sh`
- [ ] Create `install_cron_pre_market.sh` (optional; manual cron edit acceptable)
- [ ] Update crontab.txt with new entry
- [ ] Manual testing: all 3 test cases pass
- [ ] Regression test: T032 full-window mode unaffected
- [ ] Document usage in USER_GUIDE.md
- [ ] Log sample pre-market alerts to `logs/pre_market_scan.log`

---

## References

- **Roadmap:** `docs/ROADMAP.md` (Section: T043)
- **T032 Implementation:** `event_vol_analysis/workflow/daily_scan.py`
- **Cron Reference:** `crontab.txt`
- **Telegram CLI:** `telegram-send --help`
- **Report Spec:** `docs/STRUCTURE_ADVISOR_SPEC.md` (report format, via T029)

---

## Notes

- **Pre-market data limitation:** Real market options data unavailable at 3:45 AM ET. Validation should use `--test-data` flag or cached chain from prior close.
- **Operator flexibility:** Pre-market scan is optional. T032 still captures same names 10–14 days forward. Operator can skip both if market data unavailable.
- **Cron timing:** 08:45 CET chosen to run before market open (09:30 ET) with buffer for execution time (~1–2 min). If slow, adjust to 08:40 or earlier.
