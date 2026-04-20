# Getting Started

This guide gets you from clone to first successful output with the current,
supported workflow.

## Product Model

The repo is one tool with two functions:

- Analyze: generate a pre-event strategy report for a ticker.
- Research: register events and analyze stored outcomes over time.

## Environment

Use the project-local interpreter:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python
```

Do not rely on system `python` for this repository.

## Install Dependencies

From the repository root:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python -m pip install -r event_vol_analysis/requirements.txt
```

## Quick Success Path (Analyze Function)

Generate a synthetic report with no live market dependency:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  -m event_vol_analysis.main \
  --test-data \
  --output reports/test_report.html
```

Expected outcome:

- CLI prints diagnostics and regime classification.
- HTML report is written to `reports/test_report.html`.

## Quick Success Path (Research Function)

Backfill the checked-in sample event payload:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  scripts/backfill_event_history.py \
  research/earnings/sample_event_manifest_nvda_q1.json \
  --db data/options_intraday.db
```

Then run the earnings workbook summary:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  research/earnings/earnings_event_workbook.py \
  --db data/options_intraday.db \
  --ticker NVDA
```

Expected outcome:

- JSON summary prints coverage, realized move stats, IV crush, and replay stats.

## Where To Go Next

- Full operator guide: `docs/USER_GUIDE.md`
- Daily checklist: `docs/OPERATOR_CHECKLIST.md`
- Feature catalog and trust levels: `docs/FUNCTIONALITY.md`
- Roadmap and priorities: `docs/ROADMAP.md`
- Task backlog: `docs/TASKS.md`
