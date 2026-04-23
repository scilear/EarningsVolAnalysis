# T044 — EOD Cache Refresh + Overnight Analysis Mode

## Goal

Fix the structural gap where the morning cron (02:00 ET / 08:00 CET) runs with no valid option data because the market is closed. Add an end-of-day (EOD) cache refresh step that captures closing chains, enabling valid overnight analysis against last-close prices.

## Context

Current T032 flow has a fundamental flaw:

```
08:00 CET (2 AM ET) → fetch live data → market closed → bid/ask = 0 → all filtered → no output
```

Correct three-step flow:

```
22:30 CET (4:30 PM ET) → EOD cache refresh → store closing chains
08:00 CET (2 AM ET)    → overnight analysis → --use-cache against EOD snapshot → screening + TYPE
15:45 CET (9:45 AM ET) → live confirmation → --refresh-cache → confirm entry criteria
```

## Deliverable

### 1. New scan mode `--mode eod-refresh`

In `daily_scan.py`:

- Fetch option chains for universe using yfinance (within 30 min of 4 PM ET close, prices valid)
- Store in `options_intraday.db` with timestamp and quality tag (`"valid"` for non-zero bid/ask)
- Do NOT run 4-layer snapshot or TYPE classification (data capture only)
- Log: `logs/eod_refresh.log`

Quality tag:
- `"valid"`: snapshot has non-zero bid AND ask for ≥95% of strikes
- `"partial"`: non-zero for ≥50%
- `"stale"`: last update >24h ago
- `"zero"`: all bids are 0 (market closed at capture time)

### 2. Update overnight mode `--mode overnight` (replaces current T032 default)

- Explicitly requires `--use-cache` (fail loudly if no valid cache available)
- Reads from `options_intraday.db` filtered to most recent "valid" snapshot per ticker/expiry
- Runs full 4-layer snapshot + TYPE classification on cached chains
- Sends `telegram-send` alerts for non-TYPE-5 names
- Skips tickers with no valid EOD cache (warns + logs, no crash)

### 3. New confirmation mode `--mode open-confirmation`

- Runs at 9:45 AM ET (15 min after open) with `--refresh-cache`
- Compares live vol to overnight snapshot: surface shift, IV crush / expansion
- Flags if conditions changed materially vs. overnight TYPE classification
- Output: diff summary (NOT re-classification; operator reviews change and decides)
- Material change threshold: >10% shift in implied move OR >15% shift in IV regime bucket

### 4. New `--validate-cache` flag

- Reports: which tickers have valid EOD snapshot for a given date
- Reports: which tickers are missing (will need live fetch or test-data fallback)
- Operator can see coverage before overnight analysis runs
- Output: structured table to stdout + log

### 5. Cache loading helper

New function `_load_chain_from_database_cache(db_path, ticker, expiry, date)` in the data layer:

- Query `options_intraday.db` for the most recent snapshot of `ticker/expiry` on or before `date`
- Apply `min_quality="valid"` filter to exclude zero-bid snapshots
- Return chain data or `None` if no valid snapshot exists
- Add to `data/option_data_store.py`

### 6. Cron schedule update

Replace existing T032/T043 entries in `crontab.txt`:

```cron
# EOD cache refresh: 22:30 CET (4:30 PM ET)
30 22 * * 1-5 /path/to/run_eod_refresh.sh

# Overnight analysis: 08:00 CET (2 AM ET) — uses cached EOD data
0 2 * * 1-5 /path/to/run_overnight_scan.sh

# Open confirmation: 15:45 CET (9:45 AM ET) — live comparison
45 15 * * 1-5 /path/to/run_open_confirmation.sh
```

### 7. Wrapper scripts

- `scripts/run_eod_refresh.sh` — wraps `daily_scan --mode eod-refresh --date $(date +%Y-%m-%d)`
- `scripts/run_overnight_scan.sh` — wraps `daily_scan --mode overnight --use-cache --date $(date +%Y-%m-%d)`
- `scripts/run_open_confirmation.sh` — wraps `daily_scan --mode open-confirmation --refresh-cache --date $(date +%Y-%m-%d)`

## Acceptance Criteria

- [ ] EOD refresh (22:30 CET) fetches non-zero bid/ask for full universe (or logs clearly if market closed)
- [ ] Overnight analysis (08:00 CET) uses cached data without hitting yfinance live
- [ ] Overnight analysis outputs TYPE classification for all names with valid cache
- [ ] Open confirmation detects material vol surface changes (>10% shift in implied move)
- [ ] Telegram alerts fire at overnight step (not EOD step)
- [ ] `--validate-cache` shows per-ticker coverage summary
- [ ] If no EOD cache for a ticker: overnight skips it and logs warning (no crash)

## Dependencies

- T032 (daily_scan.py infrastructure)
- T043 (pre-market mode shares `--mode` flag pattern)
- `telegram-send` CLI
- `options_intraday.db` schema must support quality tags

## Schema Addition

The `options_intraday.db` snapshots table needs a `quality_tag` column. Add via ALTER TABLE in the cache refresh code:

```sql
ALTER TABLE snapshots ADD COLUMN quality_tag TEXT DEFAULT 'unknown';
```

## Important Design Notes

- EOD refresh and overnight analysis are separate cron entries — allows EOD refresh to run incrementally if some tickers fail
- `min_quality="valid"` filter in `_load_chain_from_database_cache` correctly excludes zero-bid/ask snapshots
- Open confirmation outputs a DIFF, not a new TYPE — avoids double-signaling; operator owns re-classification
- T043 pre-market scan should also use EOD cache (not live fetch at 3:45 AM ET) — integrate at end of this task