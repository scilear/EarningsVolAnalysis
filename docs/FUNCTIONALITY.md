# Functionality

This document describes what the product does today, grouped by the two
official functions.

## Function A: Analyze

Purpose: run event-centric options analysis and generate report artifacts for
trade idea review.

### Capabilities

- Single-ticker report generation (live or synthetic test mode)
- Multi-ticker batch mode with per-name report output
- Regime classification (vol pricing, event structure, term structure, gamma)
- Strategy construction, Monte Carlo EV/CVaR/convexity scoring, ranking
- Generic playbook payload emission through the bridge layer

### Primary Entry Point

- `python -m event_vol_analysis.main`
- `./earningsvol query`
- `python -m event_vol_analysis.workflow.daily_scan --mode pre-market`

### Common Commands

Synthetic run:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  -m event_vol_analysis.main \
  --test-data \
  --output reports/test_report.html
```

Live-style run:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  -m event_vol_analysis.main \
  --ticker NVDA \
  --event-date 2026-05-28 \
  --output reports/nvda_earnings_report.html
```

Batch run:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  -m event_vol_analysis.main \
  --tickers NVDA TSLA MSFT \
  --test-data \
  --batch-output-dir reports/batch
```

Structure Advisor query:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python earningsvol query \
  --payoff crash \
  --ticker GLD \
  --expiry 2026-05-15 \
  --spot 429.57
```

Pre-market same-day scan:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  -m event_vol_analysis.workflow.daily_scan \
  --mode pre-market \
  --date 2026-05-01
```

### Inputs

- Ticker(s), optional event date, option chain data (live or cached), config
  and simulation settings

### Outputs

- HTML report in `reports/`
- Ranked strategies and diagnostics in rendered report sections
- Generic event/context/playbook payload embedded in report context

### Trust Level

- High: one-name report generation and ranking workflow
- Medium: batch scans for watchlists
- Lower: fully unattended live orchestration without manual checks

### Known Limits

- Runtime is still anchored in `event_vol_analysis.main`
- Some assumptions remain earnings-first by design

## Function B: Research

Purpose: persist event datasets and evaluate realized outcomes/replay behavior
across samples.

### Capabilities

- Manifest-driven event registration and backfill into additive store tables
- Auto-ingest upcoming earnings dates from yfinance
- Event replay context loading and replay summary helpers
- Earnings workbook and macro workbook summaries from stored data
- QuantConnect scaffold export (JSON payload, LEAN stub, research template)

### Primary Entry Points

- `python scripts/backfill_event_history.py`
- `python research/earnings/earnings_event_workbook.py`
- `python research/macro/macro_event_workbook.py`
- `python research/quantconnect/quantconnect_replay_scaffold.py`

### Common Commands

Backfill manifest:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  scripts/backfill_event_history.py \
  research/earnings/sample_event_manifest_nvda_q1.json \
  --db data/options_intraday.db
```

Auto-ingest earnings calendar rows:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  scripts/backfill_event_history.py \
  --auto-earnings \
  --tickers NVDA,TSLA,MSFT \
  --db data/options_intraday.db
```

Earnings workbook:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  research/earnings/earnings_event_workbook.py \
  --db data/options_intraday.db \
  --ticker NVDA
```

Macro workbook:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  research/macro/macro_event_workbook.py \
  --db data/options_intraday.db \
  --event-name cpi \
  --proxy-symbol TLT
```

QuantConnect scaffold:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  research/quantconnect/quantconnect_replay_scaffold.py \
  --db data/options_intraday.db \
  --event-family earnings \
  --underlying-symbol NVDA \
  --format json
```

### Inputs

- Event manifests, stored option snapshots, event/outcome/replay rows

### Outputs

- Event-store records, workbook summaries (JSON/markdown), replay exports

### Trust Level

- High: store-backed workbook summaries on complete data
- Medium: replay/QC scaffold outputs as research artifacts
- Lower: fully automated end-to-end ingestion and lifecycle updates

### Known Limits

- Research layer is data-store driven and does not fetch all missing data on
  demand
- Output quality depends on completeness of snapshot bindings and outcomes

## Analyze <> Research Handoff

The two functions are connected, not separate products:

- Analyze can emit generic event/context/playbook objects through the bridge.
- Research persists and evaluates event outcomes over time.
- Together they form one workflow: pre-event decision support plus post-event
  learning.

## Related Docs

- Operator guide: `docs/USER_GUIDE.md`
- Daily checklist: `docs/OPERATOR_CHECKLIST.md`
- Storage details: `docs/OPTIONS_DATA_STORAGE.md`
