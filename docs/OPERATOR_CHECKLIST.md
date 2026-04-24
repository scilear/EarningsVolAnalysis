# Operator Checklist

Use this checklist for active event-season operation.

## Global Rules

- Use `/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python`.
- Treat Analyze output as decision support, not auto-execution.
- Validate data completeness before trusting Research summaries.

## Pre-Event

1. Confirm ticker, event date, and timing label (`am` or `ah` if known).
2. Refresh option chain snapshots.
3. Run Analyze report and review regime, ranking, and blocked structures.
4. Decide if the name should enter Research tracking.
5. Register/backfill event payload if the name is in scope.
6. Verify pre-event binding and required metrics exist in store.

Reference commands:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python scripts/download_options_chain.py NVDA --db data/options_intraday.db
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python -m event_vol_analysis.main --ticker NVDA --event-date 2026-05-28 --output reports/nvda_earnings_report.html
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python scripts/backfill_event_history.py research/earnings/sample_event_manifest_nvda_q1.json --db data/options_intraday.db
```

## Event Day

1. Re-confirm event schedule; update inputs if timing moved.
2. Refresh pre-event snapshot close to decision window.
3. Re-run Analyze if surface changed materially.
4. Check liquidity and spread quality before acting on top-ranked structures.
5. Log execution reality separately from modeled assumptions.

## Post-Event

1. Capture/confirm a post-event snapshot.
2. Update outcomes and replay rows in manifest/store.
3. Re-run backfill if using manifest workflow.
4. Run workbook summary for realized move, IV crush, and replay outcomes.
5. Keep only complete events in reusable sample sets.

For macro binary catalysts, additionally:

6. Append macro outcome via `scripts/update_macro_event_outcome.py add`.
7. Verify activation evidence via
   `scripts/update_macro_event_outcome.py query --event-type <type>`.

Reference commands:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python research/earnings/earnings_event_workbook.py --db data/options_intraday.db --ticker NVDA --horizon h1_close
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python research/macro/macro_event_workbook.py --db data/options_intraday.db --event-name cpi --proxy-symbol TLT --horizon h1_close
```

## Red Flags (Stop and Review)

- Manifest timestamp has no matching snapshot in store.
- Event date changed after payload preparation.
- Analyze narrative and workbook narrative diverge materially.
- Spread/oi quality makes suggested structures non-executable.
- Replay coverage is partial but interpreted as complete.

## Minimal Daily Validation

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python scripts/regression_smoke_harness.py
```

## Scheduled Workflows

The system uses shell wrappers in `scripts/` for cron scheduling. All scripts use the project venv python.

### Workflow Types

| Mode | When to Run | Purpose |
|------|-------------|---------|
| `--mode eod-refresh` | 4:30 PM ET (16:30) | Capture closing option chains for overnight analysis |
| `--mode overnight` | 8:00 AM ET (08:00) | Run analysis using cached EOD data (fallback to option_quotes if needed) |
| `--mode pre-market` | 9:00 AM ET (09:00) | Same-day earnings before market open |
| `--mode open-confirmation` | 9:45 AM ET (09:45) | Compare live vs overnight snapshot |

### EOD Refresh (End of Day)

Captures closing option chains. Critical for overnight mode to work.

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  -m event_vol_analysis.workflow.daily_scan \
  --mode eod-refresh \
  --date 2026-04-24
```

Wrapper script:

```bash
./scripts/run_eod_refresh.sh
```

**Note**: If yfinance rate-limits, the script logs errors but continues. EOD data
is stored in `option_quotes` table (not just snapshot metadata). The overnight
fallback can use option_quotes directly if no snapshot metadata exists.

### Overnight Analysis

Runs analysis using cached data from prior EOD refresh. Falls back to latest
available quotes from option_quotes if snapshot metadata is missing.

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  -m event_vol_analysis.workflow.daily_scan \
  --mode overnight \
  --use-cache \
  --date 2026-04-24
```

Wrapper script:

```bash
./scripts/run_overnight_scan.sh
```

### Cron Schedule (Recommended)

Add to crontab for automated execution:

```crontab
# EOD refresh: capture closing chains at 4:30 PM ET (Mon-Fri)
30 16 * * 1-5 cd /home/fabien/Documents/EarningsVolAnalysis && ./scripts/run_eod_refresh.sh >> logs/cron_eod.log 2>&1

# Overnight analysis: 8:00 AM ET (Mon-Fri)
0 8 * * 1-5 cd /home/fabien/Documents/EarningsVolAnalysis && ./scripts/run_overnight_scan.sh >> logs/cron_overnight.log 2>&1

# Pre-market scan: 9:00 AM ET (Mon-Fri)
0 9 * * 1-5 cd /home/fabien/Documents/EarningsVolAnalysis && ./scripts/run_pre_market_scan.sh >> logs/cron_premarket.log 2>&1
```

### Cache Validation

Check which tickers have valid EOD snapshots before running overnight:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  -m event_vol_analysis.workflow.daily_scan \
  --validate-cache \
  --date 2026-04-24
```

Wrapper script includes `--validate-cache` automatically.

## Pre-Market Same-Day Scan (T043)

Use when you want same-day earnings coverage before market open.

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  -m event_vol_analysis.workflow.daily_scan \
  --mode pre-market \
  --date 2026-05-01
```

Wrapper script:

```bash
./scripts/run_pre_market_scan.sh
```

If smoke fails, stop roadmap changes and restore trust path first.
