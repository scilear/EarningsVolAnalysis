"""Options data storage and retrieval module.

Provides SQLite-based storage for intraday options chain data
with automatic table creation and efficient querying.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
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
"""


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
            conn.commit()
            LOGGER.info(f"Database initialized: {self.db_path}")
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
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
        
        df = chain_df.rename(columns={k: v for k, v in column_map.items() 
                                      if k in chain_df.columns}).copy()
        
        # Ensure required columns exist
        required = ["strike", "option_type", "bid", "ask", "expiry"]
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Required column '{col}' not found in chain data. "
                               f"Available: {list(df.columns)}")
        
        # Convert expiry to date - handle strings, datetimes, or Timestamp objects
        if df["expiry"].dtype == "object":
            # String expiry dates (from yfinance)
            df["expiry"] = pd.to_datetime(df["expiry"]).dt.date
        elif pd.api.types.is_datetime64_any_dtype(df["expiry"]):
            # Already datetime
            df["expiry"] = df["expiry"].dt.date
        else:
            # Fallback: try to convert
            df["expiry"] = pd.to_datetime(df["expiry"]).dt.date
        
        # Calculate days to expiry
        df["days_to_expiry"] = (df["expiry"] - timestamp.date()).dt.days
        
        # Add metadata
        df["timestamp"] = timestamp
        df["ticker"] = ticker
        df["underlying_price"] = underlying_price
        
        # Filter invalid data
        total_records = len(df)
        
        # Remove rows with bid=ask=0 or missing bid/ask
        valid_mask = (
            df["bid"].notna() & 
            df["ask"].notna() & 
            ((df["bid"] != 0) | (df["ask"] != 0))
        )
        
        valid_df = df[valid_mask].copy()
        invalid_df = df[~valid_mask]
        
        # Additional quality filters
        quality_mask = (
            (valid_df["bid"] > 0) & 
            (valid_df["ask"] > 0) & 
            (valid_df["bid"] < valid_df["ask"])
        )
        
        high_quality_df = valid_df[quality_mask].copy()
        low_quality_df = valid_df[~quality_mask]
        
        # Insert valid records
        records_inserted = 0
        if not high_quality_df.empty:
            # Select only columns that exist in the table
            table_cols = [
                "timestamp", "ticker", "expiry", "strike", "option_type",
                "bid", "ask", "volume", "open_interest", "implied_volatility",
                "underlying_price", "days_to_expiry"
            ]
            
            insert_df = high_quality_df[[col for col in table_cols 
                                          if col in high_quality_df.columns]]
            
            with self._get_connection() as conn:
                insert_df.to_sql("option_quotes", conn, if_exists="append", 
                                index=False, method="multi")
                records_inserted = len(insert_df)
        
        # Log download
        filtered_count = total_records - records_inserted
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO download_log 
                (ticker, records_downloaded, records_valid, records_filtered, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (
                ticker, 
                total_records, 
                records_inserted, 
                filtered_count,
                f"timestamp={timestamp}, expiry_range={df['expiry'].min()} to {df['expiry'].max()}"
            ))
            conn.commit()
        
        result = {
            "total": total_records,
            "valid": records_inserted,
            "filtered": filtered_count,
            "reasons": {
                "missing_or_zero_bid_ask": len(invalid_df),
                "inverted_spread": len(low_quality_df),
            }
        }
        
        LOGGER.info(f"Stored {ticker}: {records_inserted}/{total_records} valid records "
                   f"({filtered_count} filtered)")
        
        return result
    
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
            params.append(timestamp)
        elif as_of:
            query += " AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1"
            params.append(as_of)
        else:
            query += " AND timestamp = (SELECT MAX(timestamp) FROM option_quotes WHERE ticker = ?)"
            params.append(ticker)
        
        if expiry:
            query += " AND expiry = ?"
            params.append(expiry.date() if hasattr(expiry, 'date') else expiry)
        
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
                    (ticker,)
                )
            else:
                cursor = conn.execute("SELECT MAX(timestamp) FROM option_quotes")
            
            result = cursor.fetchone()
            if result and result[0]:
                return datetime.fromisoformat(result[0])
        return None
    
    def get_download_stats(self, ticker: str | None = None, 
                          since: datetime | None = None) -> pd.DataFrame:
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
            params.append(since)
        
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
    
    def get_expiry_dates(self, ticker: str, 
                        since: datetime | None = None) -> list[str]:
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
            params.append(since.date() if hasattr(since, 'date') else since)
        
        query += " ORDER BY expiry"
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [row[0] for row in cursor.fetchall()]


def create_store(db_path: str | Path = "data/options_intraday.db") -> OptionsDataStore:
    """Factory function to create a data store.
    
    Args:
        db_path: Path to database file
        
    Returns:
        Initialized OptionsDataStore instance
    """
    return OptionsDataStore(db_path)


if __name__ == "__main__":
    # Demo usage
    logging.basicConfig(level=logging.INFO)
    
    store = create_store("data/demo_options.db")
    print(f"Database created: {store.db_path}")
    print(f"Available tickers: {store.get_available_tickers()}")
