# Earnings Season Guide

Last updated: `2026-04-19`

## Purpose

This guide is the practical operator path for the current repo state.

Use it when you need to:

- generate a legacy earnings report quickly
- seed the new event store from a checked-in manifest
- run the earnings workbook on stored events
- export a QuantConnect research scaffold

Use the project-local interpreter for all Python commands:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python
```

## Fastest Path: Legacy Earnings Report

If you need a report now, the most mature path is still the legacy engine.

Test-data mode:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  -m nvda_earnings_vol.main \
  --test-data \
  --output reports/earnings_test_report.html
```

Live-style mode:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  -m nvda_earnings_vol.main \
  --event-date 2026-05-28 \
  --output reports/nvda_earnings_report.html
```

Use this path for:

- one-name earnings analysis
- HTML report output
- the most complete current operator workflow

## Event Store Workflow

The new research layer expects the event store to contain:

- event registry rows
- snapshot bindings
- surface metrics
- realized outcomes
- structure replay outcomes

There are two ways to get there:

1. seed manually using the backfill manifest helper
2. build your own ingestion path and write into `OptionsDataStore`

## Option Snapshot Collection

Download option chains into the SQLite store first:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  scripts/download_options_chain.py NVDA
```

Custom database path:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  scripts/download_options_chain.py NVDA \
  --db data/options_intraday.db
```

Important:

- the backfill helper validates that referenced snapshot timestamps already exist
- if your manifest references a timestamp that has no stored chain, backfill will fail

## Backfill One Sample Event

Checked-in earnings sample:

- `research/earnings/sample_event_manifest_nvda_q1.json`

Checked-in macro sample:

- `research/macro/sample_event_manifest_cpi_qqq.json`

Backfill the earnings sample:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  scripts/backfill_event_history.py \
  research/earnings/sample_event_manifest_nvda_q1.json \
  --db data/options_intraday.db
```

Backfill the macro sample:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  scripts/backfill_event_history.py \
  research/macro/sample_event_manifest_cpi_qqq.json \
  --db data/options_intraday.db
```

Manifest requirements:

- `event_family`
- `event_name`
- `underlying_symbol`
- `event_date`
- `source_system`
- `snapshot_bindings`

Usually you also want:

- `surface_metrics`
- `realized_outcomes`
- `structure_replays`

## Run The Earnings Workbook

Once event rows exist in the store:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  research/earnings/earnings_event_workbook.py \
  --db-path data/options_intraday.db \
  --ticker NVDA \
  --format markdown
```

Use JSON output when you want to pipe or save the result:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  research/earnings/earnings_event_workbook.py \
  --db-path data/options_intraday.db \
  --ticker NVDA \
  --format json
```

What it summarizes:

- coverage counts
- realized move distribution
- IV crush
- surface pricing
- structure replay outcomes

## Run The Macro Workbook

Example:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  research/macro/macro_event_workbook.py \
  --db-path data/options_intraday.db \
  --event-name cpi \
  --proxy-symbol TLT \
  --format markdown
```

Use this for:

- one macro catalyst at a time
- ETF proxy-based analysis
- structure comparisons on stored macro events

## Export The QuantConnect Scaffold

JSON export:

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

QuantConnect Research template:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  research/quantconnect/quantconnect_replay_scaffold.py \
  --db data/options_intraday.db \
  --event-family earnings \
  --underlying-symbol NVDA \
  --format research
```

What the scaffold now provides:

- normalized event payload
- primary pre-event snapshot label
- realized move and IV crush fields
- full structure rankings per event
- LEAN stub
- notebook-style research template

## Recommended Operating Sequence For Earnings Names

For a name you want to monitor:

1. collect or refresh option snapshots
2. generate a legacy report for a fast read
3. register the event in the additive store
4. attach pre-event and post-event snapshots
5. run the earnings workbook for sample-level context
6. export a QuantConnect payload if you want cross-event research or notebook work

## Recommended Operating Sequence For Macro Catalysts

For CPI, payrolls, or FOMC-style work:

1. choose the explicit catalyst
2. choose the explicit proxy ETF
3. collect snapshots around the event window
4. register the event with precise timestamp if available
5. run the macro workbook
6. export the QuantConnect research template if you want to analyze event families over time

## What To Trust Most Right Now

Highest confidence:

- legacy HTML report path
- additive event-store helpers
- workbook summaries on correctly seeded data

Medium confidence:

- generic playbook bridge objects
- QuantConnect payload export

Lower confidence:

- full end-to-end automation
- broad live batch operation without manual checks

## Common Failure Modes

Backfill fails with missing snapshot:

- cause: manifest timestamp has no stored option chain
- fix: collect the snapshot first or correct the manifest timestamp

Workbook returns low coverage:

- cause: store is missing outcomes, metrics, or replay rows
- fix: backfill a complete manifest or extend your ingestion path

QuantConnect scaffold looks thin:

- cause: replay rows are incomplete or assumptions filter is too narrow
- fix: inspect `structure_replay_outcome` coverage in the store

Legacy report imports but warns:

- current known warnings include matplotlib cache path and sqlite Python 3.12 deprecations

## Minimal Validation Commands

Manifest integrity:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python -m pytest \
  /home/fabien/Documents/EarningsVolAnalysis/nvda_earnings_vol/tests/test_sample_event_manifest.py
```

Backfill and QC scaffold:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python -m pytest \
  /home/fabien/Documents/EarningsVolAnalysis/nvda_earnings_vol/tests/test_event_backfill.py \
  /home/fabien/Documents/EarningsVolAnalysis/nvda_earnings_vol/tests/test_quantconnect_replay_scaffold.py
```

Broader research slice:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python -m pytest \
  /home/fabien/Documents/EarningsVolAnalysis/nvda_earnings_vol/tests/test_event_backfill.py \
  /home/fabien/Documents/EarningsVolAnalysis/nvda_earnings_vol/tests/test_quantconnect_replay_scaffold.py \
  /home/fabien/Documents/EarningsVolAnalysis/nvda_earnings_vol/tests/test_earnings_event_workbook.py \
  /home/fabien/Documents/EarningsVolAnalysis/nvda_earnings_vol/tests/test_macro_event_workbook.py \
  /home/fabien/Documents/EarningsVolAnalysis/nvda_earnings_vol/tests/test_event_replay.py \
  /home/fabien/Documents/EarningsVolAnalysis/nvda_earnings_vol/tests/test_option_data_store_extension.py \
  /home/fabien/Documents/EarningsVolAnalysis/nvda_earnings_vol/tests/test_snapshot_bridge.py \
  /home/fabien/Documents/EarningsVolAnalysis/nvda_earnings_vol/tests/test_sample_event_manifest.py
```

## Read This Too

- `docs/TOOL_STATE_2026-04-19.md`
- `docs/USER_GUIDE.md`
- `docs/OPTIONS_DATA_STORAGE.md`
- `docs/research/progress_log.md`
