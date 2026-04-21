# User Guide

This is the canonical operator guide for EarningsVolAnalysis.

The product is one tool with two distinct functions:

- Analyze: generate pre-event regime and strategy reports.
- Research: persist event history and evaluate outcomes/replays.

## 1) Environment and Setup

Use the project-local interpreter for all commands:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python
```

Install dependencies:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python -m pip install -r event_vol_analysis/requirements.txt
```

## 2) Function A: Analyze

Use this when you need a fast event setup read and strategy ranking for one
name or a watchlist.

### Core Command

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python -m event_vol_analysis.main --help
```

### Most Common Runs

Synthetic test-data run:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  -m event_vol_analysis.main \
  --test-data \
  --output reports/test_report.html
```

Live-style run for one name:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  -m event_vol_analysis.main \
  --ticker NVDA \
  --event-date 2026-05-28 \
  --output reports/nvda_earnings_report.html
```

Batch run for multiple names:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  -m event_vol_analysis.main \
  --tickers NVDA TSLA MSFT \
  --test-data \
  --batch-output-dir reports/batch \
  --batch-summary-json reports/batch/summary.json
```

Batch from ticker file (comma or newline separated):

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  -m event_vol_analysis.main \
  --ticker-file data/watchlists/earnings.txt \
  --test-data
```

### Key CLI Options

- `--ticker`: single ticker run
- `--tickers`: multi-ticker batch run
- `--ticker-file`: batch run from file
- `--event-date`: explicit event date (`YYYY-MM-DD`)
- `--output`: report path for single run
- `--batch-output-dir`: output directory for batch reports
- `--batch-summary-json`: optional batch status summary
- `--test-data`: synthetic mode
- `--test-scenario`: synthetic scenario name
- `--cache-dir`, `--use-cache`, `--refresh-cache`: option chain cache controls
- `--seed`: reproducible simulation seed

If `--event-date` is omitted in live mode, the CLI auto-discovers from
yfinance and now enforces strict guardrails:

- ambiguous nearby dates (within 7 days) -> hard stop with action message
- stale calendars (only past dates, or implausibly far-next date) -> hard stop
- provider fetch failures -> hard stop with remediation (`--event-date`)

On success, the resolved auto date is logged explicitly.

### Data Source Notes

The auto-discovery feature uses yfinance earnings calendars. Key limitations:

- Dates are user-reported to yfinance, not official SEC filings
- Some tickers have stale or missing calendars
- Tickers without data will return "no dates found"
- When in doubt, provide explicit `--event-date`

`--use-cache` lookup order is now:

1. SQLite options store (`data/options_intraday.db`) for matching
   ticker + expiry (latest snapshot)
2. CSV cache under `--cache-dir`
3. live yfinance download

Use `--refresh-cache` to force live fetch and bypass both cache layers.

### Available Test Scenarios

- `baseline`
- `high_vol`
- `low_vol`
- `gamma_unbalanced`
- `term_inverted`

### What the Analyze Report Includes

- Regime classification summary
- Volatility and term-structure diagnostics
- Dealer gamma diagnostics
- Strategy rankings with risk and payoff metrics
- Generic bridge payloads:
  - `generic_event`
  - `generic_market_context`
  - `generic_playbook`

### Interpreting Rankings

Ranking is based on EV, convexity, CVaR, robustness, and capital normalization
metrics emitted by scoring.

Read in order:

1. Regime and confidence
2. Top structures and score separation
3. Capital-normalized context versus raw EV
4. Not-applicable structures and exclusion reasons

## 3) Function B: Research

Use this when you need repeatable event datasets, historical outcome analysis,
and replay/export workflows.

### 3.1 Collect Option Snapshots

Single ticker:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  scripts/download_options_chain.py NVDA \
  --db data/options_intraday.db
```

Ticker file batch:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  scripts/download_options_chain.py \
  --ticker-file data/watchlists/earnings.txt \
  --db data/options_intraday.db
```

### 3.2 Register/Backfill Events

Backfill a checked-in sample manifest:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  scripts/backfill_event_history.py \
  research/earnings/sample_event_manifest_nvda_q1.json \
  --db data/options_intraday.db
```

Auto-ingest upcoming earnings rows:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  scripts/backfill_event_history.py \
  --auto-earnings \
  --tickers NVDA,TSLA,MSFT \
  --limit 8 \
  --db data/options_intraday.db
```

### 3.3 Run Workbooks

Earnings workbook:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  research/earnings/earnings_event_workbook.py \
  --db data/options_intraday.db \
  --ticker NVDA \
  --horizon h1_close
```

Macro workbook:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  research/macro/macro_event_workbook.py \
  --db data/options_intraday.db \
  --event-name cpi \
  --proxy-symbol TLT \
  --horizon h1_close
```

### 3.4 Export QuantConnect Scaffold

JSON payload:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  research/quantconnect/quantconnect_replay_scaffold.py \
  --db data/options_intraday.db \
  --event-family earnings \
  --underlying-symbol NVDA \
  --format json
```

LEAN algorithm stub:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  research/quantconnect/quantconnect_replay_scaffold.py \
  --db data/options_intraday.db \
  --event-family earnings \
  --underlying-symbol NVDA \
  --format stub
```

Research notebook template:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  research/quantconnect/quantconnect_replay_scaffold.py \
  --db data/options_intraday.db \
  --event-family earnings \
  --underlying-symbol NVDA \
  --format research
```

## 4) Recommended End-to-End Operating Sequence

For one earnings name:

1. Collect/refresh option chain snapshots.
2. Run Analyze function for fast regime/structure read.
3. Register/backfill event rows and snapshot bindings.
4. Run workbook for realized/outcome context.
5. Export QC scaffold if cross-event research is needed.

For macro catalysts:

1. Choose catalyst and proxy explicitly.
2. Register event rows and snapshot bindings.
3. Run macro workbook summary.
4. Export QC scaffold for comparative research.

## 5) Failure Modes and Fixes

No options data for ticker:

- Cause: market/data source issue or unsupported symbol.
- Fix: retry, validate ticker options availability, or use test-data mode.

Backfill error about missing snapshot:

- Cause: manifest references a `(ticker, quote_ts)` not in store.
- Fix: collect the snapshot first or correct manifest timestamps.

Low workbook coverage:

- Cause: missing metrics/outcomes/replay rows.
- Fix: complete manifest payload and re-run backfill.

Batch scan partial failures:

- Cause: one or more tickers fail data/event-date paths.
- Fix: inspect batch summary JSON and rerun only failed names.

Batch summary JSON now includes per ticker:

- `ticker`, `event_date`, `regime`, `top_structure`, `score`
- `blocking_warnings` (if any)
- `ok`, `returncode`, and `error` on failures

## 6) Validation Commands

Quick smoke harness:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  scripts/regression_smoke_harness.py
```

Focused regression slice:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python -m pytest \
  event_vol_analysis/tests/test_alignment.py \
  event_vol_analysis/tests/test_main_ticker_agnostic.py \
  event_vol_analysis/tests/test_main_batch_mode.py \
  event_vol_analysis/tests/test_event_auto_ingestion.py
```

Research pipeline slice:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python -m pytest \
  event_vol_analysis/tests/test_event_backfill.py \
  event_vol_analysis/tests/test_earnings_event_workbook.py \
  event_vol_analysis/tests/test_macro_event_workbook.py \
  event_vol_analysis/tests/test_quantconnect_replay_scaffold.py
```

## 7) Canonical References

- Navigation hub: `docs/README.md`
- Feature map: `docs/FUNCTIONALITY.md`
- Daily checklist: `docs/OPERATOR_CHECKLIST.md`
- Roadmap: `docs/ROADMAP.md`
- Task backlog: `docs/TASKS.md`
