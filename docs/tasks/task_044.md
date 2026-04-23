# Task 044 — EOD Cache Refresh + Overnight Analysis Mode

**Priority:** P1  
**Status:** pending  
**Depends On:** T032  
**Blocks:** T043 (pre-market mode should use EOD cache, not live fetch)  
**Estimated Effort:** 3–4 hours  

---

## Summary

Fix a structural gap in T032: the morning cron runs at 2 AM ET when the market is closed, so all option chains have bid/ask = 0 and the entire universe gets hard-filtered. Add a three-step workflow: EOD cache refresh → overnight analysis → open confirmation.

---

## Problem Statement

**Current broken flow:**
```
08:00 CET (2 AM ET) → fetch from yfinance → market closed → bid/ask = 0 → 55 names filtered → no output
```

**Root cause:** `daily_scan.py` fetches option data at analysis time. At 2 AM ET, yfinance returns bid/ask = 0 because market is closed. The `_raise_if_market_closed()` hard filter correctly rejects this stale data — but the cron is scheduled during closed hours.

**Evidence from 2026-04-23 session:**
- T032 cron ran at 09:07 CET (3:07 AM ET): all 55 universe names filtered, 0 actionable
- `options_intraday.db` contains XOM/VZ data from 09:49 CET with bid = 0 (stored stale)
- TSLA cache (`TSLA_20260424_20260421.csv`) has all-zero prices — captured pre-market

---

## Correct Three-Step Workflow

```
Step 1: 22:30 CET (4:30 PM ET, 30 min after close)
   EOD cache refresh: fetch closing chains → store in DB with valid prices
   No analysis, no alerts. Data capture only.

Step 2: 00:30 CET (next day, 6:30 PM ET prev day, 2h after EOD step)
   Overnight analysis: --use-cache → full 4-layer snapshot → TYPE classification
   telegram-send alerts for non-TYPE-5 names.

Step 3: 15:45 CET (9:45 AM ET, 15 min after open)
   Open confirmation: --refresh-cache → compare live vol to overnight snapshot
   Output: diff summary. Operator reviews before entry.
```

---

## Detailed Deliverables

### 1. Scan Mode `--mode eod-refresh`

**File:** `event_vol_analysis/workflow/daily_scan.py`

Purpose: fetch and store closing option chains for universe. No analysis.

Logic:
```python
if args.mode == 'eod-refresh':
    for ticker in universe:
        try:
            chain = get_options_chain(ticker, front_expiry, refresh_cache=True)
            store.save_chain(ticker, front_expiry, chain)
            if chain has back_expiry:
                store.save_chain(ticker, back_expiry, chain_back)
        except ValueError as e:
            if 'market appears closed' in str(e):
                LOGGER.warning(f"{ticker}: Skipped — market closed or stale data")
            else:
                raise
    LOGGER.info(f"EOD refresh complete: {n_saved} tickers cached, {n_skipped} skipped")
    # No telegram alert for EOD step
```

Accepts: same `--tickers`, `--ticker-file`, `--db` flags as full scan.

### 2. Scan Mode `--mode overnight`

**File:** `event_vol_analysis/workflow/daily_scan.py`

Purpose: run full 4-layer snapshot + TYPE classification against EOD cache.

Changes to existing default behavior:
- Force `use_cache=True` (error if no cache available for a ticker, log and skip)
- Never call yfinance (prevent accidental live fetch during overnight run)
- Alert via `telegram-send` for non-TYPE-5 names (same as current T032 behavior)

```python
if args.mode == 'overnight':
    if not args.db or not Path(args.db).exists():
        LOGGER.error("No cache DB found; run EOD refresh first")
        sys.exit(1)
    # Force use_cache=True, disable live fetch
    use_cache = True
    allow_live_fetch = False
```

Add `allow_live_fetch` guard in `get_options_chain`:
```python
if not use_cache and not allow_live_fetch:
    raise RuntimeError(f"Live fetch disabled in overnight mode for {ticker}")
```

### 3. Scan Mode `--mode open-confirmation`

**File:** `event_vol_analysis/workflow/daily_scan.py`

Purpose: compare live vol at market open vs. overnight snapshot. NOT re-classification.

```python
if args.mode == 'open-confirmation':
    for ticker in overnight_screened_names:
        overnight_snapshot = load_from_db(ticker)
        live_chain = get_options_chain(ticker, refresh_cache=True)
        
        diff = compare_snapshots(overnight_snapshot, live_chain)
        # diff contains: implied_move_change_pct, ivr_shift, edge_ratio_shift
        
        if diff.implied_move_change_pct > 0.10:  # >10% shift
            status = "MATERIAL_CHANGE"
        else:
            status = "CONFIRMED"
        
        msg = f"[OPEN CONFIRM] {ticker}: {status} | IV move: {diff.implied_move_change_pct:+.1%}"
        telegram_send(msg)
```

Output: confirmation or material-change alert per ticker. Does NOT re-run TYPE classifier.

### 4. Cache Validation Helper

**File:** `event_vol_analysis/workflow/daily_scan.py`

```python
if args.validate_cache:
    for ticker in universe:
        chain = load_from_db(ticker, date=args.date)
        if chain is not None and not chain.empty:
            print(f"  {ticker}: OK ({len(chain)} rows, as_of={chain.timestamp.max()})")
        else:
            print(f"  {ticker}: MISSING — will skip in overnight mode")
```

CLI: `daily_scan --validate-cache --date 2026-04-23`

### 5. Shell Scripts

**`scripts/run_eod_refresh.sh`:**
```bash
${VENV_PYTHON} -m event_vol_analysis.workflow.daily_scan \
  --mode eod-refresh \
  --days-ahead 14 \
  "$@"
```

**`scripts/run_overnight_scan.sh`:**
```bash
${VENV_PYTHON} -m event_vol_analysis.workflow.daily_scan \
  --mode overnight \
  "$@"
```

**`scripts/run_open_confirmation.sh`:**
```bash
${VENV_PYTHON} -m event_vol_analysis.workflow.daily_scan \
  --mode open-confirmation \
  "$@"
```

### 6. Cron Schedule (Full Three-Step)

**File:** `crontab.txt` (replace current T032 entry)

```cron
# Step 1: EOD cache refresh — 22:30 CET (4:30 PM ET), after US close
30 22 * * 1-5 /home/fabien/Documents/EarningsVolAnalysis/scripts/run_eod_refresh.sh

# Step 2: Overnight analysis — 00:30 CET (uses Step 1 cache)
30 0 * * 2-6 /home/fabien/Documents/EarningsVolAnalysis/scripts/run_overnight_scan.sh

# Step 3: Open confirmation — 15:45 CET (9:45 AM ET, 15 min after open)
45 15 * * 1-5 /home/fabien/Documents/EarningsVolAnalysis/scripts/run_open_confirmation.sh
```

Note: Step 2 runs Tue–Sat 00:30 (covering Mon–Fri analysis; Sat covers Fri EOD).

---

## Acceptance Criteria

- [ ] `--mode eod-refresh` fetches valid (non-zero) bid/ask for full universe at 22:30 CET
- [ ] `options_intraday.db` stores chains with valid prices after EOD refresh
- [ ] `--mode overnight` reads from DB without hitting yfinance
- [ ] Overnight mode outputs TYPE classification for all cached tickers
- [ ] `telegram-send` fires for non-TYPE-5 names from overnight mode
- [ ] `--mode open-confirmation` flags tickers with >10% implied move shift
- [ ] `--validate-cache --date <date>` shows per-ticker coverage correctly
- [ ] If EOD cache missing for ticker: overnight skips with WARNING (no crash)
- [ ] Cron entries for all 3 steps installed and dry-run verified

---

## Testing Strategy

```bash
# Test EOD refresh (run during market hours, 15:30-21:00 CET)
python -m event_vol_analysis.workflow.daily_scan --mode eod-refresh --dry-run

# Validate cache after EOD
python -m event_vol_analysis.workflow.daily_scan --validate-cache --date $(date +%Y-%m-%d)

# Test overnight analysis (run after EOD refresh)
python -m event_vol_analysis.workflow.daily_scan --mode overnight --dry-run

# Test open confirmation (run during market hours)
python -m event_vol_analysis.workflow.daily_scan --mode open-confirmation --dry-run
```

---

## Implementation Checklist

- [ ] Add `--mode` choices: `eod-refresh`, `overnight`, `open-confirmation` (alongside `full-window`)
- [ ] Implement EOD refresh logic (fetch + store, no analysis)
- [ ] Implement overnight mode (cache-only, no live fetch guard)
- [ ] Implement open confirmation (compare_snapshots diff)
- [ ] Add `--validate-cache` flag
- [ ] Add `allow_live_fetch` guard in `get_options_chain`
- [ ] Create `scripts/run_eod_refresh.sh`
- [ ] Create `scripts/run_overnight_scan.sh`
- [ ] Create `scripts/run_open_confirmation.sh`
- [ ] Update `crontab.txt` with 3-step schedule (replace T032 entry)
- [ ] Manual test: all 3 modes pass dry-run
- [ ] Regression: T032 default mode unaffected
- [ ] Document in USER_GUIDE.md (replace T032 scheduling section)

---

## Dependency Note for T043

T043 (pre-market same-day scan) should also use EOD cache, not live fetch at 3:45 AM ET. T043 implementation should wait for T044 to be complete, then reuse the EOD cache infrastructure for its own overnight prep step.

---

## References

- **Roadmap:** `docs/ROADMAP.md` (T044 section)
- **Root cause evidence:** `logs/daily_scan.log` (2026-04-23, all 55 filtered)
- **DB schema:** `data/option_data_store.py` (`query_chain`, `min_quality="valid"`)
- **Loader:** `event_vol_analysis/data/loader.py` (`_load_chain_from_database_cache`, `_raise_if_market_closed`)
- **T032:** `event_vol_analysis/workflow/daily_scan.py`
