# Event Option Tool State

Last updated: `2026-04-19`

## Executive Summary

The repository is now in a hybrid state:

- the legacy `nvda_earnings_vol` pipeline still works as the main report generator
- a new generic event-engine layer exists beside it
- the new layer already supports event registration, replay context loading, workbook summaries,
  manifest-driven backfill, and QuantConnect export scaffolding
- the project is not yet a fully automated event playbook generator for live earnings season use

The practical meaning is:

- you can use the legacy report path today
- you can use the new research/workbook path today if you seed the event store correctly
- you should still treat the new generic layer as research infrastructure, not a finished
  production trading system

## What Exists

### Legacy report engine

Primary path:

- `nvda_earnings_vol/main.py`

Purpose:

- live or test-data event report generation
- strategy construction
- Monte Carlo and scoring
- HTML report generation

Status:

- usable
- still earnings-first in design
- still the most complete single-command operator workflow

### Generic event domain

Primary path:

- `event_option_playbook/`

Key modules:

- `events.py`: generic event schema
- `context.py`: market context schema
- `playbook.py`: recommendation and risk-note schema
- `bridge.py`: compatibility bridge from legacy snapshot/ranking output
- `replay.py`: replay context loader and replay summary helpers
- `backfill.py`: manifest-driven event registration helper

Status:

- materially usable for research
- not yet the sole runtime entrypoint for the project

### Additive event storage

Primary path:

- `data/option_data_store.py`

Now supports:

- raw option snapshot storage
- event registry
- event snapshot bindings
- surface metrics
- realized outcomes
- structure replay outcomes

Status:

- working and covered by focused tests
- still carries Python 3.12 sqlite adapter/converter deprecation warnings

### Research workbooks

Primary paths:

- `research/earnings/earnings_event_workbook.py`
- `research/macro/macro_event_workbook.py`

Purpose:

- summarize stored event samples
- quantify realized move, IV crush, surface metrics, and structure outcomes

Status:

- working on stored data
- no automatic market-data fetch inside workbook code

### QuantConnect scaffold

Primary path:

- `research/quantconnect/quantconnect_replay_scaffold.py`

Outputs:

- normalized event payload JSON
- LEAN algorithm stub
- QuantConnect Research notebook-style template

Status:

- good research scaffold
- not yet a complete end-to-end LEAN strategy implementation

## What Is Tested

Focused passing tests currently include:

- `nvda_earnings_vol/tests/test_snapshot_bridge.py`
  - legacy snapshot -> generic event/context/playbook bridge
- `nvda_earnings_vol/tests/test_option_data_store_extension.py`
  - additive event-store schema and helper methods
- `nvda_earnings_vol/tests/test_event_replay.py`
  - replay context loading and resolution rules
- `nvda_earnings_vol/tests/test_earnings_event_workbook.py`
  - earnings workbook summary generation
- `nvda_earnings_vol/tests/test_macro_event_workbook.py`
  - macro workbook summary generation
- `nvda_earnings_vol/tests/test_event_backfill.py`
  - manifest-driven backfill path
- `nvda_earnings_vol/tests/test_quantconnect_replay_scaffold.py`
  - QuantConnect scaffold export, algorithm stub, research template
- `nvda_earnings_vol/tests/test_sample_event_manifest.py`
  - checked-in sample manifest integrity

Most recent validated command set:

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

## What Is Done

Done and usable now:

- legacy report pipeline
- generic event schema
- generic playbook schema
- compatibility bridge from legacy output into generic output
- additive event-store schema
- replay context resolution
- earnings workbook
- macro workbook
- manifest-driven backfill helper
- checked-in sample manifests
- QuantConnect export scaffold

## What Is Not Done

Still incomplete:

- one unified live workflow that starts from event selection and ends with a finished event
  playbook recommendation under the generic engine
- automatic event ingestion from authoritative earnings / macro calendars
- automatic realized-outcome backfill from live stored snapshots
- formal portfolio/risk-constraint layer for actual capital deployment
- hardened LEAN / QuantConnect production integration
- complete migration of all operator usage away from `nvda_earnings_vol/main.py`

## What Is Known To Be Weak

Current known weak points:

- the legacy engine remains NVDA/earnings shaped in several assumptions
- the generic layer still depends on explicit seeded data rather than automated historical event
  ingestion
- sqlite date/datetime adapters emit Python 3.12 deprecation warnings
- the repo mixes mature operator code with in-progress research infrastructure
- HTML report path is more mature than the generic event-engine output path

## What Is Not Well Tested Yet

Areas with weak or missing coverage:

- end-to-end live market download -> event registration -> workbook -> playbook flow
- real market data quality across broad earnings-season ticker sets
- broad regression coverage for `nvda_earnings_vol/main.py`
- operational failure handling for stale quotes, missing expiries, and malformed event manifests
- full QuantConnect import/execution workflow inside LEAN
- multi-event batch orchestration

## Recommended Usage Right Now

Use the tool in this order of trust:

1. legacy report engine for a one-name earnings report
2. event-store plus workbook path for structured research summaries
3. QuantConnect scaffold for research export and notebook setup
4. generic event-engine outputs as supporting artifacts, not yet the only decision surface

## Files To Watch During Earnings Season

High-value operator files:

- `nvda_earnings_vol/main.py`
- `docs/USER_GUIDE.md`
- `docs/EARNINGS_SEASON_GUIDE.md`
- `data/option_data_store.py`
- `scripts/download_options_chain.py`
- `scripts/backfill_event_history.py`
- `research/earnings/earnings_event_workbook.py`
- `research/quantconnect/quantconnect_replay_scaffold.py`

## Sample Inputs Available

Checked-in manifest samples:

- `research/earnings/sample_event_manifest_nvda_q1.json`
- `research/macro/sample_event_manifest_cpi_qqq.json`

These are examples of the additive event payload format expected by:

- `event_option_playbook.backfill`
- `scripts/backfill_event_history.py`

## Bottom Line

For this earnings season, the repo is good enough for:

- report generation on a legacy earnings workflow
- structured event research if you seed the store correctly
- preparing QuantConnect research payloads

It is not yet good enough to trust as a fully automated live event playbook generator without
manual oversight.
