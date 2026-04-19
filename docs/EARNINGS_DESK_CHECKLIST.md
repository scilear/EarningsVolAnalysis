# Earnings Desk Checklist

Last updated: `2026-04-19`

## Purpose

This is the short operator checklist for active earnings-season use.

Use it with:

- `docs/EARNINGS_SEASON_GUIDE.md`
- `docs/TOOL_STATE_2026-04-19.md`

Default interpreter:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python
```

## Pre-Event Checklist

Use this on the day before the event or before the close if the event is after hours.

1. Confirm the event date and timing label.
   - You need: ticker, event date, and whether the event is `am` or `ah`.
2. Refresh option snapshots for the name.

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  scripts/download_options_chain.py NVDA \
  --db data/options_intraday.db
```

3. Generate the legacy earnings report for the fastest read.

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  -m nvda_earnings_vol.main \
  --event-date 2026-05-28 \
  --output reports/nvda_earnings_report.html
```

4. Review:
   - implied move vs historical move
   - term structure slope
   - gamma regime / dealer positioning
   - top-ranked structures
5. Decide whether the name is worth deeper tracking.
   - If no: stop here.
   - If yes: move it into the additive event-store workflow.
6. Backfill or register the event in the event store.
   - Use an existing manifest if one already exists.
   - Otherwise create a new manifest based on the checked-in sample format.

Sample backfill command:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  scripts/backfill_event_history.py \
  research/earnings/sample_event_manifest_nvda_q1.json \
  --db data/options_intraday.db
```

7. Sanity-check completeness before the event.
   - Confirm pre-event snapshot exists.
   - Confirm surface metrics are populated.
   - If using replay comparisons, confirm structure replay rows exist.

## Event-Day Checklist

Use this on event day around the event window.

1. Confirm the event is still on schedule.
   - If the date or timing changed, update the manifest or registry inputs before analysis.
2. Refresh the option chain again if you want the latest pre-event surface.

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  scripts/download_options_chain.py NVDA \
  --db data/options_intraday.db
```

3. Re-run the legacy report if you need a fresh read.

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  -m nvda_earnings_vol.main \
  --event-date 2026-05-28 \
  --output reports/nvda_earnings_report_refresh.html
```

4. Check:
   - Has implied move expanded materially?
   - Has term structure steepened or flattened?
   - Has the top-ranked structure changed?
   - Are spreads or open interest too poor for practical execution?
5. If using the generic event/research path:
   - confirm the pre-event snapshot timestamp you intend to bind
   - do not assume the original manifest timestamp is still the best one
6. If using QuantConnect research export:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  research/quantconnect/quantconnect_replay_scaffold.py \
  --db data/options_intraday.db \
  --event-family earnings \
  --underlying-symbol NVDA \
  --format research
```

7. Record desk notes outside the tool for:
   - practical liquidity
   - whether the market is one-sided
   - whether the suggested structure is actually executable at acceptable slippage

## Post-Event Checklist

Use this after the event once the first meaningful post-event snapshot exists.

1. Capture or confirm the post-event option snapshot.
   - This is required if you want realized-outcome and replay analysis to mean anything.
2. Update the event payload if needed.
   - add or correct post-event snapshot label
   - add realized outcome fields
   - add IV crush fields
   - add structure replay outcomes if you computed them
3. Re-run backfill if you are working from a manifest.

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  scripts/backfill_event_history.py \
  path/to/updated_event_manifest.json \
  --db data/options_intraday.db
```

4. Run the earnings workbook.

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  research/earnings/earnings_event_workbook.py \
  --db-path data/options_intraday.db \
  --ticker NVDA \
  --format markdown
```

5. Review:
   - realized move
   - IV crush
   - structure replay ranking
   - whether the chosen trade idea would actually have worked
6. Decide whether the event should remain in the reusable sample set.
   - Keep it if the data is complete.
   - Exclude it if snapshots or outcomes are too incomplete.

## Desk Rules

Use these rules during the current season:

- Prefer the legacy report path for fast live reads.
- Prefer the workbook path for sample-level review and post-mortem.
- Do not treat the generic event engine as a fully automated recommender yet.
- Do not trust any backfilled event if the referenced snapshot was not actually stored.
- Do not trust low-liquidity names just because the report ranked a structure highly.

## Red Flags

Stop and review manually if any of these happen:

- manifest timestamp does not match any stored option chain
- event date changed after the manifest was prepared
- live report and workbook story differ materially
- spreads are too wide for practical execution
- replay rows are missing for the structures you care about
- outcome coverage is partial but being treated as complete

## Minimal Command Set

Refresh option chain:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  scripts/download_options_chain.py NVDA \
  --db data/options_intraday.db
```

Run legacy report:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  -m nvda_earnings_vol.main \
  --event-date 2026-05-28 \
  --output reports/nvda_earnings_report.html
```

Backfill event sample:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  scripts/backfill_event_history.py \
  research/earnings/sample_event_manifest_nvda_q1.json \
  --db data/options_intraday.db
```

Run workbook:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  research/earnings/earnings_event_workbook.py \
  --db-path data/options_intraday.db \
  --ticker NVDA \
  --format markdown
```

Export QuantConnect research template:

```bash
/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python \
  research/quantconnect/quantconnect_replay_scaffold.py \
  --db data/options_intraday.db \
  --event-family earnings \
  --underlying-symbol NVDA \
  --format research
```
