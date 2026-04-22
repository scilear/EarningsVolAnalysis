"""Options data storage and retrieval module.

Provides SQLite-based storage for intraday options chain data
with automatic table creation and efficient querying.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

LOGGER = logging.getLogger(__name__)

# Schema definition
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS option_quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    ticker TEXT NOT NULL,
    expiry DATE NOT NULL,
    strike REAL NOT NULL,
    option_type TEXT NOT NULL CHECK(option_type IN ('call', 'put')),
    bid REAL,
    ask REAL,
    mid REAL GENERATED ALWAYS AS ((bid + ask) / 2) STORED,
    spread REAL GENERATED ALWAYS AS (ask - bid) STORED,
    volume INTEGER,
    open_interest INTEGER,
    implied_volatility REAL,
    underlying_price REAL NOT NULL,
    days_to_expiry INTEGER NOT NULL,
    data_quality TEXT GENERATED ALWAYS AS (
        CASE
            WHEN bid IS NULL OR ask IS NULL THEN 'missing'
            WHEN bid = 0 AND ask = 0 THEN 'empty'
            WHEN bid <= 0 OR ask <= 0 THEN 'invalid'
            WHEN bid >= ask THEN 'inverted'
            ELSE 'valid'
        END
    ) STORED,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(timestamp, ticker, expiry, strike, option_type)
);

CREATE INDEX IF NOT EXISTS idx_time_ticker 
    ON option_quotes(timestamp, ticker);
    
CREATE INDEX IF NOT EXISTS idx_expiry_lookup 
    ON option_quotes(expiry, strike, option_type, timestamp);
    
CREATE INDEX IF NOT EXISTS idx_dte_quality
    ON option_quotes(days_to_expiry, data_quality, timestamp);

CREATE TABLE IF NOT EXISTS download_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    ticker TEXT NOT NULL,
    records_downloaded INTEGER NOT NULL,
    records_valid INTEGER NOT NULL,
    records_filtered INTEGER NOT NULL,
    download_duration_seconds REAL,
    error_message TEXT,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_download_log_ticker
    ON download_log(ticker, timestamp);

CREATE TABLE IF NOT EXISTS event_registry (
    event_id TEXT PRIMARY KEY,
    event_family TEXT NOT NULL,
    event_name TEXT NOT NULL,
    underlying_symbol TEXT NOT NULL,
    proxy_symbol TEXT,
    event_date DATE NOT NULL,
    event_ts_utc DATETIME,
    event_time_label TEXT,
    source_system TEXT NOT NULL,
    source_ref TEXT,
    event_status TEXT NOT NULL DEFAULT 'scheduled',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_event_registry_lookup
    ON event_registry(event_family, event_name, underlying_symbol, event_date);

CREATE TABLE IF NOT EXISTS event_snapshot_binding (
    binding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL REFERENCES event_registry(event_id),
    snapshot_label TEXT NOT NULL,
    timing_bucket TEXT NOT NULL,
    quote_ts DATETIME NOT NULL,
    ticker TEXT NOT NULL,
    rel_trade_days_to_event INTEGER NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0,
    selection_method TEXT NOT NULL,
    selection_tolerance_minutes INTEGER NOT NULL DEFAULT 30,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, snapshot_label)
);

CREATE INDEX IF NOT EXISTS idx_event_snapshot_binding_event
    ON event_snapshot_binding(event_id, timing_bucket, rel_trade_days_to_event);

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

CREATE TABLE IF NOT EXISTS event_evaluation_horizon (
    horizon_code TEXT PRIMARY KEY,
    horizon_days INTEGER NOT NULL,
    anchor_type TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_realized_outcome (
    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL REFERENCES event_registry(event_id),
    horizon_code TEXT NOT NULL REFERENCES event_evaluation_horizon(horizon_code),
    pre_snapshot_label TEXT NOT NULL,
    post_snapshot_label TEXT NOT NULL,
    spot_pre REAL NOT NULL,
    spot_post REAL NOT NULL,
    realized_move_signed_pct REAL NOT NULL,
    realized_move_abs_pct REAL NOT NULL,
    rv_window_days INTEGER,
    realized_vol_pct REAL,
    iv_front_pre REAL,
    iv_front_post REAL,
    iv_change_abs REAL,
    iv_change_pct REAL,
    iv_crush_abs REAL,
    iv_crush_pct REAL,
    outcome_version TEXT NOT NULL DEFAULT 'v1',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, horizon_code, outcome_version)
);

CREATE INDEX IF NOT EXISTS idx_event_realized_outcome_event
    ON event_realized_outcome(event_id, horizon_code);

CREATE TABLE IF NOT EXISTS structure_replay_outcome (
    replay_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL REFERENCES event_registry(event_id),
    structure_code TEXT NOT NULL,
    entry_snapshot_label TEXT NOT NULL,
    exit_horizon_code TEXT NOT NULL REFERENCES event_evaluation_horizon(horizon_code),
    quantity_scale REAL NOT NULL DEFAULT 1.0,
    assumptions_version TEXT NOT NULL,
    pricing_model_version TEXT NOT NULL,
    entry_cost REAL NOT NULL,
    exit_value REAL NOT NULL,
    realized_pnl REAL NOT NULL,
    realized_pnl_pct REAL,
    max_risk_at_entry REAL,
    status TEXT NOT NULL DEFAULT 'ok',
    status_detail TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(
        event_id,
        structure_code,
        entry_snapshot_label,
        exit_horizon_code,
        assumptions_version
    )
);

CREATE INDEX IF NOT EXISTS idx_structure_replay_outcome_event
    ON structure_replay_outcome(event_id, structure_code, exit_horizon_code);

CREATE TABLE IF NOT EXISTS earnings_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    event_date DATE NOT NULL,
    timing TEXT NOT NULL CHECK(timing IN ('AMC', 'BMO', 'UNKNOWN')),
    analysis_timestamp DATETIME NOT NULL,
    predicted_type INTEGER NOT NULL CHECK(predicted_type BETWEEN 1 AND 5),
    predicted_confidence TEXT NOT NULL,
    edge_ratio_label TEXT NOT NULL,
    edge_ratio_value REAL NOT NULL,
    edge_ratio_confidence TEXT NOT NULL,
    vol_regime_label TEXT NOT NULL,
    implied_move REAL NOT NULL,
    conditional_expected_move REAL NOT NULL,
    realized_move REAL,
    realized_move_direction TEXT CHECK(realized_move_direction IN ('UP', 'DOWN')),
    realized_vs_implied_ratio REAL,
    phase1_category TEXT CHECK(
        phase1_category IN (
            'HELD_REPRICING',
            'POTENTIAL_OVERSHOOT',
            'NOT_ASSESSED'
        )
    ),
    entry_taken INTEGER,
    pnl_if_entered REAL,
    outcome_complete INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ticker, event_date)
);

CREATE INDEX IF NOT EXISTS idx_earnings_outcomes_lookup
    ON earnings_outcomes(ticker, event_date);
"""

DEFAULT_EVALUATION_HORIZONS = (
    ("h0_close", 0, "event_date", "Same-day close after the event"),
    ("h1_close", 1, "event_date", "First close after the event"),
    ("h3_close", 3, "event_date", "Third close after the event"),
)


class OptionsDataStore:
    """SQLite-based storage for options chain data.

    Designed for low-frequency intraday collection (e.g., every 15 minutes)
    across multiple tickers. Efficiently handles filtering of invalid quotes.

    Attributes:
        db_path: Path to SQLite database file
        connection: Active database connection (context manager)
    """

    def __init__(self, db_path: str | Path = "data/options_intraday.db"):
        """Initialize the data store.

        Args:
            db_path: Path to SQLite database file. Creates parent dirs if needed.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self) -> None:
        """Create tables and indexes if they don't exist."""
        with self._get_connection() as conn:
            conn.executescript(CREATE_TABLES_SQL)
            conn.executemany(
                """
                INSERT OR IGNORE INTO event_evaluation_horizon
                (horizon_code, horizon_days, anchor_type, description)
                VALUES (?, ?, ?, ?)
                """,
                DEFAULT_EVALUATION_HORIZONS,
            )
            conn.commit()
            LOGGER.info(f"Database initialized: {self.db_path}")

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def store_chain(
        self,
        ticker: str,
        timestamp: datetime,
        chain_df: pd.DataFrame,
        underlying_price: float,
    ) -> dict[str, int]:
        """Store an options chain snapshot, filtering invalid data.

        Args:
            ticker: Stock ticker symbol
            timestamp: When the data was captured
            chain_df: DataFrame with columns matching the schema
            underlying_price: Current underlying spot price

        Returns:
            Dict with counts: total, valid, filtered by reason
        """
        if chain_df.empty:
            LOGGER.warning(f"Empty chain for {ticker} at {timestamp}")
            return {"total": 0, "valid": 0, "filtered": 0, "reasons": {}}

        # Standardize column names
        column_map = {
            "strike": "strike",
            "optionType": "option_type",
            "option_type": "option_type",
            "bid": "bid",
            "ask": "ask",
            "volume": "volume",
            "openInterest": "open_interest",
            "open_interest": "open_interest",
            "impliedVolatility": "implied_volatility",
            "implied_volatility": "implied_volatility",
            "expiration": "expiry",
            "expiry": "expiry",
            "lastTradeDate": "last_trade_date",
            "contractSymbol": "contract_symbol",
        }

        df = chain_df.rename(
            columns={k: v for k, v in column_map.items() if k in chain_df.columns}
        ).copy()

        # Ensure required columns exist
        required = ["strike", "option_type", "bid", "ask", "expiry"]
        for col in required:
            if col not in df.columns:
                raise ValueError(
                    f"Required column '{col}' not found in chain data. "
                    f"Available: {list(df.columns)}"
                )

        # Convert expiry to datetime - handle strings, datetimes, or Timestamp objects
        if df["expiry"].dtype == "object":
            # String expiry dates (from yfinance)
            df["expiry"] = pd.to_datetime(df["expiry"])
        elif not pd.api.types.is_datetime64_any_dtype(df["expiry"]):
            # Fallback: try to convert
            df["expiry"] = pd.to_datetime(df["expiry"])

        # Calculate days to expiry using datetime arithmetic
        df["days_to_expiry"] = (df["expiry"] - pd.Timestamp(timestamp.date())).dt.days

        # Now convert expiry to date for storage
        df["expiry"] = df["expiry"].dt.strftime("%Y-%m-%d")

        # Add metadata
        df["timestamp"] = _serialize_datetime(timestamp)
        df["ticker"] = ticker
        df["underlying_price"] = underlying_price

        # Filter invalid data
        total_records = len(df)

        # Remove rows with bid=ask=0 or missing bid/ask
        valid_mask = (
            df["bid"].notna()
            & df["ask"].notna()
            & ((df["bid"] != 0) | (df["ask"] != 0))
        )

        valid_df = df[valid_mask].copy()
        invalid_df = df[~valid_mask]

        # Additional quality filters
        quality_mask = (
            (valid_df["bid"] > 0)
            & (valid_df["ask"] > 0)
            & (valid_df["bid"] < valid_df["ask"])
        )

        high_quality_df = valid_df[quality_mask].copy()
        low_quality_df = valid_df[~quality_mask]

        # Insert valid records
        records_inserted = 0
        if not high_quality_df.empty:
            # Select only columns that exist in the table
            table_cols = [
                "timestamp",
                "ticker",
                "expiry",
                "strike",
                "option_type",
                "bid",
                "ask",
                "volume",
                "open_interest",
                "implied_volatility",
                "underlying_price",
                "days_to_expiry",
            ]

            insert_df = high_quality_df[
                [col for col in table_cols if col in high_quality_df.columns]
            ]

            with self._get_connection() as conn:
                insert_df.to_sql(
                    "option_quotes",
                    conn,
                    if_exists="append",
                    index=False,
                    method="multi",
                )
                records_inserted = len(insert_df)

        # Log download
        filtered_count = total_records - records_inserted
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO download_log 
                (ticker, records_downloaded, records_valid, records_filtered, metadata)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    ticker,
                    total_records,
                    records_inserted,
                    filtered_count,
                    (
                        f"timestamp={_serialize_datetime(timestamp)}, "
                        f"expiry_range={df['expiry'].min()} to {df['expiry'].max()}"
                    ),
                ),
            )
            conn.commit()

        result = {
            "total": total_records,
            "valid": records_inserted,
            "filtered": filtered_count,
            "reasons": {
                "missing_or_zero_bid_ask": len(invalid_df),
                "inverted_spread": len(low_quality_df),
            },
        }

        LOGGER.info(
            f"Stored {ticker}: {records_inserted}/{total_records} valid records "
            f"({filtered_count} filtered)"
        )

        return result

    def register_event(
        self,
        event_id: str,
        event_family: str,
        event_name: str,
        underlying_symbol: str,
        event_date: date | datetime | str,
        source_system: str,
        proxy_symbol: str | None = None,
        event_ts_utc: datetime | None = None,
        event_time_label: str | None = None,
        source_ref: str | None = None,
        event_status: str = "scheduled",
    ) -> None:
        """Create or update one event in the additive event registry."""
        normalized_event_date = _normalize_date(event_date)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO event_registry (
                    event_id, event_family, event_name, underlying_symbol,
                    proxy_symbol, event_date, event_ts_utc, event_time_label,
                    source_system, source_ref, event_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    event_family = excluded.event_family,
                    event_name = excluded.event_name,
                    underlying_symbol = excluded.underlying_symbol,
                    proxy_symbol = excluded.proxy_symbol,
                    event_date = excluded.event_date,
                    event_ts_utc = excluded.event_ts_utc,
                    event_time_label = excluded.event_time_label,
                    source_system = excluded.source_system,
                    source_ref = excluded.source_ref,
                    event_status = excluded.event_status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    event_id,
                    event_family,
                    event_name,
                    underlying_symbol.upper(),
                    proxy_symbol.upper() if proxy_symbol else None,
                    _serialize_date(normalized_event_date),
                    _serialize_datetime(event_ts_utc),
                    event_time_label,
                    source_system,
                    source_ref,
                    event_status,
                ),
            )
            conn.commit()

    def bind_snapshot_to_event(
        self,
        event_id: str,
        snapshot_label: str,
        timing_bucket: str,
        quote_ts: datetime,
        ticker: str,
        rel_trade_days_to_event: int,
        selection_method: str,
        *,
        is_primary: bool = False,
        selection_tolerance_minutes: int = 30,
    ) -> None:
        """Bind an existing chain snapshot timestamp to an event timeline position."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO event_snapshot_binding (
                    event_id, snapshot_label, timing_bucket, quote_ts, ticker,
                    rel_trade_days_to_event, is_primary, selection_method,
                    selection_tolerance_minutes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id, snapshot_label) DO UPDATE SET
                    timing_bucket = excluded.timing_bucket,
                    quote_ts = excluded.quote_ts,
                    ticker = excluded.ticker,
                    rel_trade_days_to_event = excluded.rel_trade_days_to_event,
                    is_primary = excluded.is_primary,
                    selection_method = excluded.selection_method,
                    selection_tolerance_minutes = excluded.selection_tolerance_minutes
                """,
                (
                    event_id,
                    snapshot_label,
                    timing_bucket,
                    _serialize_datetime(quote_ts),
                    ticker.upper(),
                    rel_trade_days_to_event,
                    int(is_primary),
                    selection_method,
                    selection_tolerance_minutes,
                ),
            )
            conn.commit()

    def store_surface_metrics(
        self,
        event_id: str,
        snapshot_label: str,
        quote_ts: datetime,
        ticker: str,
        metrics: dict[str, Any],
        *,
        metric_version: str = "v1",
    ) -> None:
        """Store derived snapshot-level metrics tied to one event snapshot."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO event_surface_metrics (
                    event_id, snapshot_label, quote_ts, ticker, spot,
                    front_expiry, back_expiry, front_dte, back_dte,
                    atm_iv_front, atm_iv_back, iv_ratio, implied_move_pct,
                    event_variance_ratio, skew_25d_rr, skew_25d_bf,
                    gex_proxy, liquidity_score, metric_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id, snapshot_label, metric_version) DO UPDATE SET
                    quote_ts = excluded.quote_ts,
                    ticker = excluded.ticker,
                    spot = excluded.spot,
                    front_expiry = excluded.front_expiry,
                    back_expiry = excluded.back_expiry,
                    front_dte = excluded.front_dte,
                    back_dte = excluded.back_dte,
                    atm_iv_front = excluded.atm_iv_front,
                    atm_iv_back = excluded.atm_iv_back,
                    iv_ratio = excluded.iv_ratio,
                    implied_move_pct = excluded.implied_move_pct,
                    event_variance_ratio = excluded.event_variance_ratio,
                    skew_25d_rr = excluded.skew_25d_rr,
                    skew_25d_bf = excluded.skew_25d_bf,
                    gex_proxy = excluded.gex_proxy,
                    liquidity_score = excluded.liquidity_score
                """,
                (
                    event_id,
                    snapshot_label,
                    _serialize_datetime(quote_ts),
                    ticker.upper(),
                    metrics["spot"],
                    _serialize_date(_optional_date(metrics.get("front_expiry"))),
                    _serialize_date(_optional_date(metrics.get("back_expiry"))),
                    metrics.get("front_dte"),
                    metrics.get("back_dte"),
                    metrics.get("atm_iv_front"),
                    metrics.get("atm_iv_back"),
                    metrics.get("iv_ratio"),
                    metrics.get("implied_move_pct"),
                    metrics.get("event_variance_ratio"),
                    metrics.get("skew_25d_rr"),
                    metrics.get("skew_25d_bf"),
                    metrics.get("gex_proxy"),
                    metrics.get("liquidity_score"),
                    metric_version,
                ),
            )
            conn.commit()

    def store_realized_outcome(
        self,
        event_id: str,
        horizon_code: str,
        pre_snapshot_label: str,
        post_snapshot_label: str,
        outcome: dict[str, Any],
        *,
        outcome_version: str = "v1",
    ) -> None:
        """Store realized move and IV normalization results for one event/horizon."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO event_realized_outcome (
                    event_id, horizon_code, pre_snapshot_label, post_snapshot_label,
                    spot_pre, spot_post, realized_move_signed_pct, realized_move_abs_pct,
                    rv_window_days, realized_vol_pct, iv_front_pre, iv_front_post,
                    iv_change_abs, iv_change_pct, iv_crush_abs, iv_crush_pct,
                    outcome_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id, horizon_code, outcome_version) DO UPDATE SET
                    pre_snapshot_label = excluded.pre_snapshot_label,
                    post_snapshot_label = excluded.post_snapshot_label,
                    spot_pre = excluded.spot_pre,
                    spot_post = excluded.spot_post,
                    realized_move_signed_pct = excluded.realized_move_signed_pct,
                    realized_move_abs_pct = excluded.realized_move_abs_pct,
                    rv_window_days = excluded.rv_window_days,
                    realized_vol_pct = excluded.realized_vol_pct,
                    iv_front_pre = excluded.iv_front_pre,
                    iv_front_post = excluded.iv_front_post,
                    iv_change_abs = excluded.iv_change_abs,
                    iv_change_pct = excluded.iv_change_pct,
                    iv_crush_abs = excluded.iv_crush_abs,
                    iv_crush_pct = excluded.iv_crush_pct
                """,
                (
                    event_id,
                    horizon_code,
                    pre_snapshot_label,
                    post_snapshot_label,
                    outcome["spot_pre"],
                    outcome["spot_post"],
                    outcome["realized_move_signed_pct"],
                    outcome["realized_move_abs_pct"],
                    outcome.get("rv_window_days"),
                    outcome.get("realized_vol_pct"),
                    outcome.get("iv_front_pre"),
                    outcome.get("iv_front_post"),
                    outcome.get("iv_change_abs"),
                    outcome.get("iv_change_pct"),
                    outcome.get("iv_crush_abs"),
                    outcome.get("iv_crush_pct"),
                    outcome_version,
                ),
            )
            conn.commit()

    def store_structure_replay_outcome(
        self,
        event_id: str,
        structure_code: str,
        entry_snapshot_label: str,
        exit_horizon_code: str,
        replay: dict[str, Any],
    ) -> None:
        """Store standardized structure-level replay results for one event/horizon."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO structure_replay_outcome (
                    event_id, structure_code, entry_snapshot_label, exit_horizon_code,
                    quantity_scale, assumptions_version, pricing_model_version,
                    entry_cost, exit_value, realized_pnl, realized_pnl_pct,
                    max_risk_at_entry, status, status_detail
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(
                    event_id, structure_code, entry_snapshot_label,
                    exit_horizon_code, assumptions_version
                ) DO UPDATE SET
                    quantity_scale = excluded.quantity_scale,
                    pricing_model_version = excluded.pricing_model_version,
                    entry_cost = excluded.entry_cost,
                    exit_value = excluded.exit_value,
                    realized_pnl = excluded.realized_pnl,
                    realized_pnl_pct = excluded.realized_pnl_pct,
                    max_risk_at_entry = excluded.max_risk_at_entry,
                    status = excluded.status,
                    status_detail = excluded.status_detail
                """,
                (
                    event_id,
                    structure_code,
                    entry_snapshot_label,
                    exit_horizon_code,
                    replay.get("quantity_scale", 1.0),
                    replay["assumptions_version"],
                    replay["pricing_model_version"],
                    replay["entry_cost"],
                    replay["exit_value"],
                    replay["realized_pnl"],
                    replay.get("realized_pnl_pct"),
                    replay.get("max_risk_at_entry"),
                    replay.get("status", "ok"),
                    replay.get("status_detail"),
                ),
            )
            conn.commit()

    def query_chain(
        self,
        ticker: str,
        timestamp: datetime | None = None,
        expiry: datetime | None = None,
        as_of: datetime | None = None,
        min_quality: str = "valid",
    ) -> pd.DataFrame:
        """Query options chain data with flexible filtering.

        Args:
            ticker: Stock ticker symbol
            timestamp: Specific timestamp (or None for latest)
            expiry: Filter by specific expiry date
            as_of: Get data as of a specific time (latest before this time)
            min_quality: Minimum data quality ('valid', 'all')

        Returns:
            DataFrame with chain data
        """
        query = "SELECT * FROM option_quotes WHERE ticker = ?"
        params: list[Any] = [ticker]

        if timestamp:
            query += " AND timestamp = ?"
            params.append(_serialize_datetime(timestamp))
        elif as_of:
            query += " AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1"
            params.append(_serialize_datetime(as_of))
        else:
            query += " AND timestamp = (SELECT MAX(timestamp) FROM option_quotes WHERE ticker = ?)"
            params.append(ticker)

        if expiry:
            query += " AND expiry = ?"
            params.append(_serialize_date(_optional_date(expiry)))

        if min_quality == "valid":
            query += " AND data_quality = 'valid'"

        query += " ORDER BY expiry, strike, option_type"

        with self._get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=params)

        if not df.empty and "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        if not df.empty and "expiry" in df.columns:
            df["expiry"] = pd.to_datetime(df["expiry"]).dt.date

        return df

    def get_latest_timestamp(self, ticker: str | None = None) -> datetime | None:
        """Get the most recent data timestamp.

        Args:
            ticker: Specific ticker or None for any ticker

        Returns:
            Latest timestamp or None if no data
        """
        with self._get_connection() as conn:
            if ticker:
                cursor = conn.execute(
                    "SELECT MAX(timestamp) FROM option_quotes WHERE ticker = ?",
                    (ticker,),
                )
            else:
                cursor = conn.execute("SELECT MAX(timestamp) FROM option_quotes")

            result = cursor.fetchone()
            if result and result[0]:
                return datetime.fromisoformat(result[0])
        return None

    def get_download_stats(
        self, ticker: str | None = None, since: datetime | None = None
    ) -> pd.DataFrame:
        """Get download statistics.

        Args:
            ticker: Filter by specific ticker
            since: Only return records since this time

        Returns:
            DataFrame with download statistics
        """
        query = "SELECT * FROM download_log WHERE 1=1"
        params: list[Any] = []

        if ticker:
            query += " AND ticker = ?"
            params.append(ticker)
        if since:
            query += " AND timestamp >= ?"
            params.append(_serialize_datetime(since))

        query += " ORDER BY timestamp DESC"

        with self._get_connection() as conn:
            return pd.read_sql_query(query, conn, params=params)

    def get_available_tickers(self) -> list[str]:
        """Get list of tickers with data in the database.

        Returns:
            List of ticker symbols
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT DISTINCT ticker FROM option_quotes ORDER BY ticker"
            )
            return [row[0] for row in cursor.fetchall()]

    def get_expiry_dates(self, ticker: str, since: datetime | None = None) -> list[str]:
        """Get available expiry dates for a ticker.

        Args:
            ticker: Stock ticker symbol
            since: Only return expiries on or after this date

        Returns:
            List of expiry dates (YYYY-MM-DD format)
        """
        query = "SELECT DISTINCT expiry FROM option_quotes WHERE ticker = ?"
        params: list[Any] = [ticker]

        if since:
            query += " AND expiry >= ?"
            params.append(_serialize_date(_optional_date(since)))

        query += " ORDER BY expiry"

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [row[0] for row in cursor.fetchall()]

    def get_event_registry(self, event_id: str | None = None) -> pd.DataFrame:
        """Return registered events, optionally filtered to one event id."""
        query = "SELECT * FROM event_registry"
        params: list[Any] = []
        if event_id:
            query += " WHERE event_id = ?"
            params.append(event_id)
        query += " ORDER BY event_date, underlying_symbol"
        with self._get_connection() as conn:
            frame = pd.read_sql_query(query, conn, params=params)
        if frame.empty:
            return frame
        if "event_date" in frame.columns:
            frame["event_date"] = pd.to_datetime(frame["event_date"]).dt.date
        if "event_ts_utc" in frame.columns:
            frame["event_ts_utc"] = pd.to_datetime(frame["event_ts_utc"])
        for column in ("created_at", "updated_at"):
            if column in frame.columns:
                frame[column] = pd.to_datetime(frame[column])
        return frame

    def get_event_snapshot_bindings(self, event_id: str) -> pd.DataFrame:
        """Return event snapshot bindings ordered by timing and label."""
        with self._get_connection() as conn:
            frame = pd.read_sql_query(
                """
                SELECT * FROM event_snapshot_binding
                WHERE event_id = ?
                ORDER BY rel_trade_days_to_event, snapshot_label
                """,
                conn,
                params=[event_id],
            )
        if frame.empty:
            return frame
        if "quote_ts" in frame.columns:
            frame["quote_ts"] = pd.to_datetime(frame["quote_ts"])
        if "created_at" in frame.columns:
            frame["created_at"] = pd.to_datetime(frame["created_at"])
        return frame

    def get_earnings_outcomes(
        self,
        ticker: str | None = None,
        event_date: date | datetime | str | None = None,
    ) -> pd.DataFrame:
        """Return earnings outcome rows, optionally filtered by key fields."""

        query = "SELECT * FROM earnings_outcomes"
        params: list[Any] = []
        clauses: list[str] = []

        if ticker is not None:
            clauses.append("ticker = ?")
            params.append(ticker.upper())
        if event_date is not None:
            clauses.append("event_date = ?")
            params.append(_serialize_date(_normalize_date(event_date)))

        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY event_date, ticker"

        with self._get_connection() as conn:
            frame = pd.read_sql_query(query, conn, params=params)

        if frame.empty:
            return frame

        frame["event_date"] = pd.to_datetime(frame["event_date"]).dt.date
        for column in ("analysis_timestamp", "created_at", "updated_at"):
            if column in frame.columns:
                frame[column] = pd.to_datetime(frame[column])
        if "entry_taken" in frame.columns:
            frame["entry_taken"] = frame["entry_taken"].apply(
                lambda value: None if pd.isna(value) else bool(int(value))
            )
        if "outcome_complete" in frame.columns:
            frame["outcome_complete"] = frame["outcome_complete"].astype(bool)
        return frame

    def get_earnings_outcome(
        self,
        ticker: str,
        event_date: date | datetime | str,
    ) -> dict[str, Any] | None:
        """Return one earnings outcome row for (ticker, event_date)."""

        frame = self.get_earnings_outcomes(ticker=ticker, event_date=event_date)
        if frame.empty:
            return None
        return dict(frame.iloc[0])

    def store_earnings_prediction(
        self,
        *,
        ticker: str,
        event_date: date | datetime | str,
        timing: str,
        analysis_timestamp: datetime,
        predicted_type: int,
        predicted_confidence: str,
        edge_ratio_label: str,
        edge_ratio_value: float,
        edge_ratio_confidence: str,
        vol_regime_label: str,
        implied_move: float,
        conditional_expected_move: float,
    ) -> int:
        """Insert one ex-ante prediction row for a ticker/event date."""

        normalized_ticker = ticker.upper()
        normalized_date = _serialize_date(_normalize_date(event_date))
        normalized_timing = timing.upper()

        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO earnings_outcomes (
                        ticker,
                        event_date,
                        timing,
                        analysis_timestamp,
                        predicted_type,
                        predicted_confidence,
                        edge_ratio_label,
                        edge_ratio_value,
                        edge_ratio_confidence,
                        vol_regime_label,
                        implied_move,
                        conditional_expected_move,
                        outcome_complete
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        normalized_ticker,
                        normalized_date,
                        normalized_timing,
                        _serialize_datetime(analysis_timestamp),
                        predicted_type,
                        predicted_confidence,
                        edge_ratio_label,
                        edge_ratio_value,
                        edge_ratio_confidence,
                        vol_regime_label,
                        implied_move,
                        conditional_expected_move,
                    ),
                )
                conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"Prediction already exists for {normalized_ticker} {normalized_date}."
            ) from exc

        return int(cursor.lastrowid)

    def update_earnings_outcome(
        self,
        *,
        ticker: str,
        event_date: date | datetime | str,
        phase1_category: str,
        entry_taken: bool,
        pnl_if_entered: float | None,
        force: bool = False,
    ) -> None:
        """Update post-event manual fields for one stored outcome row."""

        existing = self.get_earnings_outcome(ticker, event_date)
        if existing is None:
            raise ValueError(
                "No outcome row found for "
                f"{ticker.upper()} {_normalize_date(event_date).isoformat()}."
            )

        current_phase1 = existing.get("phase1_category")
        current_entry = existing.get("entry_taken")
        current_pnl = existing.get("pnl_if_entered")

        no_change = (
            current_phase1 == phase1_category
            and current_entry == entry_taken
            and current_pnl == pnl_if_entered
        )
        if no_change:
            return

        if bool(existing.get("outcome_complete")) and not force:
            raise ValueError(
                "Outcome already complete; use force=True to override manual fields."
            )

        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE earnings_outcomes
                SET phase1_category = ?,
                    entry_taken = ?,
                    pnl_if_entered = ?,
                    outcome_complete = CASE
                        WHEN realized_move IS NOT NULL AND ? IS NOT NULL THEN 1
                        ELSE 0
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE ticker = ? AND event_date = ?
                """,
                (
                    phase1_category,
                    int(entry_taken),
                    pnl_if_entered,
                    phase1_category,
                    ticker.upper(),
                    _serialize_date(_normalize_date(event_date)),
                ),
            )
            conn.commit()

    def set_earnings_realized_move(
        self,
        *,
        ticker: str,
        event_date: date | datetime | str,
        realized_move: float,
        realized_move_direction: str,
        realized_vs_implied_ratio: float | None,
        force: bool = False,
    ) -> bool:
        """Update realized move fields; return False if skipped."""

        existing = self.get_earnings_outcome(ticker, event_date)
        if existing is None:
            raise ValueError(
                "No outcome row found for "
                f"{ticker.upper()} {_normalize_date(event_date).isoformat()}."
            )

        if existing.get("realized_move") is not None and not force:
            return False

        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE earnings_outcomes
                SET realized_move = ?,
                    realized_move_direction = ?,
                    realized_vs_implied_ratio = ?,
                    outcome_complete = CASE
                        WHEN ? IS NOT NULL AND phase1_category IS NOT NULL THEN 1
                        ELSE 0
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE ticker = ? AND event_date = ?
                """,
                (
                    realized_move,
                    realized_move_direction,
                    realized_vs_implied_ratio,
                    realized_move,
                    ticker.upper(),
                    _serialize_date(_normalize_date(event_date)),
                ),
            )
            conn.commit()
        return True


def create_store(db_path: str | Path = "data/options_intraday.db") -> OptionsDataStore:
    """Factory function to create a data store.

    Args:
        db_path: Path to database file

    Returns:
        Initialized OptionsDataStore instance
    """
    return OptionsDataStore(db_path)


def _normalize_date(value: date | datetime | str) -> date:
    """Normalize incoming date-like values to `datetime.date`."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(value).date()


def _optional_date(value: date | datetime | str | None) -> date | None:
    """Normalize optional date-like values to `datetime.date`."""
    if value is None:
        return None
    return _normalize_date(value)


def _serialize_datetime(value: datetime | str | None) -> str | None:
    """Serialize a datetime-like value to an ISO string for sqlite."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return value


def _serialize_date(value: date | str | None) -> str | None:
    """Serialize a date-like value to an ISO string for sqlite."""
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return value


if __name__ == "__main__":
    # Demo usage
    logging.basicConfig(level=logging.INFO)

    store = create_store("data/demo_options.db")
    print(f"Database created: {store.db_path}")
    print(f"Available tickers: {store.get_available_tickers()}")
