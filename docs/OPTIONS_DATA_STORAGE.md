# Options Data Storage System

## Overview

SQLite-based storage solution for low-frequency intraday options data collection. Optimized for collecting options chains every 15 minutes across ~10 tickers.

## Storage Choice: SQLite

**Why SQLite:**
- Single file - easy to manage and backup
- No server required - runs anywhere Python runs
- Excellent for this scale (10 tickers × 96 samples/day × many strikes)
- Built-in Python support (sqlite3)
- Can handle millions of rows efficiently with proper indexing
- Easy to migrate to PostgreSQL later if needed

**Schema:**
```
option_quotes table
├── Primary data: timestamp, ticker, expiry, strike, option_type
├── Pricing: bid, ask, mid (computed), spread (computed)
├── Volume: volume, open_interest
├── Greeks: implied_volatility, delta, gamma, theta, vega
├── Metadata: underlying_price, days_to_expiry
└── Quality: data_quality (computed)

download_log table
├── Tracks all download attempts
├── Records: downloaded, valid, filtered counts
└── Metadata and error messages
```

## Database Location

Default: `data/options_intraday.db`

## Usage

### 1. Download Options Chain for a Single Ticker

```bash
# Download all available expiries
python scripts/download_options_chain.py NVDA

# Download specific expiry only
python scripts/download_options_chain.py NVDA --expiry 2026-03-21

# Use custom database
python scripts/download_options_chain.py AAPL --db /path/to/mydata.db

# Verbose output
python scripts/download_options_chain.py TSLA -v
```

### 2. Use in Python Code

```python
from data.option_data_store import create_store, OptionsDataStore

# Create/connect to database
store = create_store("data/options_intraday.db")

# Download and store data (using the download script or custom code)
# ... download logic here ...

# Query data
chain = store.query_chain(
    ticker="NVDA",
    as_of=datetime.now(),  # Get latest data
)

# Get specific expiry
march_chain = store.query_chain(
    ticker="NVDA",
    expiry="2026-03-21",
)

# Get available tickers
tickers = store.get_available_tickers()

# Get expiry dates
expiries = store.get_expiry_dates("NVDA")

# Get download statistics
stats = store.get_download_stats(ticker="NVDA")
```

## Data Quality Filtering

The system automatically filters out invalid data:

| Data Quality | Description | Action |
|-------------|-------------|--------|
| `missing` | bid or ask is NULL | Filtered out |
| `empty` | bid = 0 AND ask = 0 | Filtered out |
| `invalid` | bid ≤ 0 OR ask ≤ 0 | Filtered out |
| `inverted` | bid ≥ ask | Filtered out |
| `valid` | All checks pass | Stored |

Only records with `data_quality = 'valid'` are returned by default queries.

## Performance Considerations

- **Batch inserts**: Uses `method="multi"` for efficient bulk loading
- **Indexes**: Optimized for time-series queries and expiry lookups
- **Unique constraint**: Prevents duplicate entries (timestamp, ticker, expiry, strike, option_type)
- **Generated columns**: mid, spread, data_quality computed automatically

## Storage Size Estimate

For 10 tickers, 15-minute intervals, assuming:
- ~20 expiries per ticker
- ~100 strikes per expiry × 2 (calls + puts) = 200 contracts per expiry
- ~20 valid contracts per expiry (after filtering)

**Daily storage:**
- 10 tickers × 96 intervals × 20 contracts × 400 bytes ≈ 7.7 MB/day
- ~230 MB/month
- ~2.8 GB/year

Well within SQLite's capabilities (can handle up to 140 TB).

## Migration Path to PostgreSQL/TimescaleDB

If you need to scale beyond SQLite:

1. **Export SQLite data:**
   ```bash
   sqlite3 data/options_intraday.db .dump > options_export.sql
   ```

2. **Import to PostgreSQL:**
   ```bash
   psql -d mydb -f options_export.sql
   ```

3. **Convert to TimescaleDB hypertable:**
   ```sql
   SELECT create_hypertable('option_quotes', 'timestamp');
   ```

The Python code would need minimal changes - just switch the connection string.

## Future Enhancements

1. **Scheduler**: Add a cron job or systemd timer for automatic collection
2. **Multi-ticker script**: Download multiple tickers in parallel
3. **Data retention**: Archive old data to compressed files
4. **Backup**: Automated daily backups
5. **API**: REST API for querying stored data

## Troubleshooting

### No data for ticker
- Check if ticker has options: `yfinance.Ticker("SYM").options`
- Verify market is open
- Check yfinance connectivity

### Database locked
- SQLite doesn't support concurrent writes well
- Ensure only one process writes at a time
- Use connection pooling if needed

### Slow queries
- Indexes are created automatically
- For time-range queries, use `as_of` parameter
- Consider partitioning if database grows very large

## Example: Set Up Cron Job

```bash
# Edit crontab
crontab -e

# Add every-15-minutes job for NVDA
*/15 * * * * cd /path/to/EarningsVolAnalysis && python scripts/download_options_chain.py NVDA >> logs/nvda_download.log 2>&1

# Or download multiple tickers with a wrapper script
*/15 * * * * cd /path/to/EarningsVolAnalysis && python scripts/download_batch.py >> logs/batch.log 2>&1
```
