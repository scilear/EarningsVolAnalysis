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
