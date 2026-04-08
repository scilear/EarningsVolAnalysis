# Event Dataset And Outcomes Schema (Task 002)

## Objective

Define an additive SQLite storage model that can reconstruct what was known before an event, what
happened after the event, and how standardized structures performed across multiple horizons.

## Design Principles

- Additive only: no destructive changes to existing `option_quotes` / `download_log`
- Replay-first: every event record must link to concrete pre/post quote timestamps
- Horizon-normalized: all outcomes and PnL are keyed by a shared horizon dimension
- Versioned assumptions: replay outputs include policy/assumption versions for reproducibility

## Existing Base (Unchanged)

- `option_quotes` remains the canonical contract-level chain store
- `download_log` remains the ingestion audit trail

The new event dataset references these existing snapshots by `(ticker, quote_ts)`.

## Proposed Tables

### 1) `event_registry`

One row per concrete catalyst instance (for example: NVDA earnings on 2026-02-26).

```sql
CREATE TABLE IF NOT EXISTS event_registry (
    event_id TEXT PRIMARY KEY,                    -- stable key, e.g. earnings:nvda:2026-02-26
    event_family TEXT NOT NULL,                   -- earnings, macro, other
    event_name TEXT NOT NULL,                     -- nvda_earnings, cpi, fomc
    underlying_symbol TEXT NOT NULL,              -- NVDA
    proxy_symbol TEXT,                            -- optional (e.g. QQQ for macro contexts)
    event_date DATE NOT NULL,                     -- scheduled calendar date
    event_ts_utc DATETIME,                        -- optional precise release timestamp
    event_time_label TEXT,                        -- bmo, am, intraday, ah, unknown
    source_system TEXT NOT NULL,                  -- yfinance, manual, econ-calendar
    source_ref TEXT,                              -- URL or provider key for audit
    event_status TEXT NOT NULL DEFAULT 'scheduled', -- scheduled, completed, canceled, revised
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_event_registry_lookup
    ON event_registry(event_family, event_name, underlying_symbol, event_date);
```

### 2) `event_snapshot_binding`

Maps an event to concrete chain captures in `option_quotes`, covering pre and post snapshots.

```sql
CREATE TABLE IF NOT EXISTS event_snapshot_binding (
    binding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL REFERENCES event_registry(event_id),
    snapshot_label TEXT NOT NULL,                 -- pre_close_d1, pre_close_d0, post_open_d0, post_close_d1
    timing_bucket TEXT NOT NULL,                  -- pre_event, event_day, post_event
    quote_ts DATETIME NOT NULL,                   -- timestamp in option_quotes
    ticker TEXT NOT NULL,                         -- usually underlying_symbol
    rel_trade_days_to_event INTEGER NOT NULL,     -- negative/zero/positive
    is_primary INTEGER NOT NULL DEFAULT 0,        -- primary anchor for replay calculations
    selection_method TEXT NOT NULL,               -- nearest_before_close, nearest_after_open, manual
    selection_tolerance_minutes INTEGER NOT NULL DEFAULT 30,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, snapshot_label)
);

CREATE INDEX IF NOT EXISTS idx_event_snapshot_binding_event
    ON event_snapshot_binding(event_id, timing_bucket, rel_trade_days_to_event);
```

Notes:
- This is additive and does not require an `ALTER` on `option_quotes`.
- `quote_ts` + `ticker` selects the full option surface snapshot from existing storage.

### 3) `event_surface_metrics`

Stores derived snapshot-level metrics used by screening, replay normalization, and outcome baselines.

```sql
CREATE TABLE IF NOT EXISTS event_surface_metrics (
    metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL REFERENCES event_registry(event_id),
    snapshot_label TEXT NOT NULL,
    quote_ts DATETIME NOT NULL,
    ticker TEXT NOT NULL,
    spot REAL NOT NULL,
    front_expiry DATE,
    back_expiry DATE,
    front_dte INTEGER,
    back_dte INTEGER,
    atm_iv_front REAL,
    atm_iv_back REAL,
    iv_ratio REAL,
    implied_move_pct REAL,
    event_variance_ratio REAL,
    skew_25d_rr REAL,
    skew_25d_bf REAL,
    gex_proxy REAL,
    liquidity_score REAL,
    metric_version TEXT NOT NULL DEFAULT 'v1',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, snapshot_label, metric_version)
);

CREATE INDEX IF NOT EXISTS idx_event_surface_metrics_event
    ON event_surface_metrics(event_id, snapshot_label);
```

### 4) `event_evaluation_horizon`

Shared horizon dimension for realized outcomes and structure replay exits.

```sql
CREATE TABLE IF NOT EXISTS event_evaluation_horizon (
    horizon_code TEXT PRIMARY KEY,                -- h0_close, h1_close, h3_close, h5_close
    horizon_days INTEGER NOT NULL,                -- 0, 1, 3, 5
    anchor_type TEXT NOT NULL,                    -- event_date, first_post_close
    description TEXT NOT NULL
);
```

### 5) `event_realized_outcome`

Realized movement and IV normalization results per event and horizon.

```sql
CREATE TABLE IF NOT EXISTS event_realized_outcome (
    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL REFERENCES event_registry(event_id),
    horizon_code TEXT NOT NULL REFERENCES event_evaluation_horizon(horizon_code),
    pre_snapshot_label TEXT NOT NULL,             -- baseline snapshot (usually pre_close_d0)
    post_snapshot_label TEXT NOT NULL,            -- snapshot used for horizon
    spot_pre REAL NOT NULL,
    spot_post REAL NOT NULL,
    realized_move_signed_pct REAL NOT NULL,
    realized_move_abs_pct REAL NOT NULL,
    rv_window_days INTEGER,                       -- optional realized vol window
    realized_vol_pct REAL,                        -- optional annualized RV
    iv_front_pre REAL,
    iv_front_post REAL,
    iv_change_abs REAL,                           -- post - pre
    iv_change_pct REAL,                           -- (post/pre)-1
    iv_crush_abs REAL,                            -- pre - post
    iv_crush_pct REAL,                            -- (pre-post)/pre
    outcome_version TEXT NOT NULL DEFAULT 'v1',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, horizon_code, outcome_version)
);

CREATE INDEX IF NOT EXISTS idx_event_realized_outcome_event
    ON event_realized_outcome(event_id, horizon_code);
```

### 6) `structure_replay_outcome`

Standardized structure-level replay output under fixed entry/exit assumptions.

```sql
CREATE TABLE IF NOT EXISTS structure_replay_outcome (
    replay_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL REFERENCES event_registry(event_id),
    structure_code TEXT NOT NULL,                 -- long_straddle_atm, short_strangle_16d, call_calendar_atm
    entry_snapshot_label TEXT NOT NULL,           -- where structure was initiated
    exit_horizon_code TEXT NOT NULL REFERENCES event_evaluation_horizon(horizon_code),
    quantity_scale REAL NOT NULL DEFAULT 1.0,     -- standardized notional scaling
    assumptions_version TEXT NOT NULL,            -- slippage/fees/exit policy version
    pricing_model_version TEXT NOT NULL,          -- bsm_v1, midmark_v1
    entry_cost REAL NOT NULL,                     -- signed cashflow
    exit_value REAL NOT NULL,                     -- signed mark at exit
    realized_pnl REAL NOT NULL,                   -- exit_value - entry_cost
    realized_pnl_pct REAL,                        -- optional normalized by debit/width/risk
    max_risk_at_entry REAL,                       -- risk normalization
    status TEXT NOT NULL DEFAULT 'ok',            -- ok, missing_quotes, invalid_structure
    status_detail TEXT,                           -- reason when not ok
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, structure_code, entry_snapshot_label, exit_horizon_code, assumptions_version)
);

CREATE INDEX IF NOT EXISTS idx_structure_replay_outcome_event
    ON structure_replay_outcome(event_id, structure_code, exit_horizon_code);
```

## Core Query Patterns (Acceptance Coverage)

### What was known before the event?

1. Resolve event: `event_registry` row for `(family, name, symbol, date)`.
2. Get primary pre-event binding: `event_snapshot_binding` where `timing_bucket='pre_event'` and
   `is_primary=1`.
3. Pull full chain snapshot from `option_quotes` by `(ticker, quote_ts)`.
4. Pull normalized metrics from `event_surface_metrics` for that `snapshot_label`.

### What happened after the event?

1. Read post-event bindings from `event_snapshot_binding` (`event_day` / `post_event`).
2. Read realized results from `event_realized_outcome` by `horizon_code`.
3. Compare realized move and IV crush against pre-event baseline labels.

### Multiple evaluation horizons

- Managed by `event_evaluation_horizon`; one event may have N rows in `event_realized_outcome`
  and N×M rows in `structure_replay_outcome` (M structures).

### Structure-level PnL replay under standardized exits

- `structure_replay_outcome` stores both PnL values and assumption versions, so replay comparisons
  are stable and reproducible across events.

## Incremental Implementation Plan

1. Add new tables and indexes only (`CREATE TABLE IF NOT EXISTS`).
2. Seed `event_evaluation_horizon` with a minimal set: `h0_close`, `h1_close`, `h3_close`.
3. Register events in `event_registry` as they are analyzed.
4. Bind existing quote captures to events through `event_snapshot_binding`.
5. Compute/store derived snapshot metrics in `event_surface_metrics`.
6. Compute/store realized outcomes in `event_realized_outcome`.
7. Add standardized strategy replay writes into `structure_replay_outcome`.

No existing table rewrite is required; this can ship in phases without breaking current ingestion.

## Out-of-Scope for Task 002

- Runtime migration code
- Backfill scripts
- Playbook policy logic and rule engine integration
