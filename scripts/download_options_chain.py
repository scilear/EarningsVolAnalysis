#!/usr/bin/env python3
"""Download options chain data and store in database.

Usage:
    python scripts/download_options_chain.py AAPL
    python scripts/download_options_chain.py NVDA --db data/options.db
    python scripts/download_options_chain.py TSLA --expiry 2026-03-21
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.option_data_store import OptionsDataStore, create_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
LOGGER = logging.getLogger(__name__)


def download_options_chain(
    ticker: str,
    store: OptionsDataStore,
    specific_expiry: str | None = None,
) -> dict[str, Any]:
    """Download options chain for a ticker and store in database.
    
    Args:
        ticker: Stock ticker symbol (e.g., "AAPL", "NVDA")
        store: OptionsDataStore instance
        specific_expiry: Specific expiry date to download (YYYY-MM-DD format),
                        or None for all available expiries
    
    Returns:
        Dict with download statistics
    """
    timestamp = datetime.now()
    LOGGER.info(f"Starting download for {ticker} at {timestamp}")
    
    try:
        # Get underlying ticker info
        stock = yf.Ticker(ticker)
        
        # Get current price
        try:
            underlying_price = stock.info.get("regularMarketPrice") or stock.fast_info.get("lastPrice")
            if underlying_price is None:
                # Fallback: try to get from history
                hist = stock.history(period="1d")
                if not hist.empty:
                    underlying_price = hist["Close"].iloc[-1]
            
            if underlying_price is None:
                raise ValueError(f"Could not get underlying price for {ticker}")
                
            LOGGER.info(f"{ticker} underlying price: ${underlying_price:.2f}")
        except Exception as e:
            LOGGER.error(f"Failed to get underlying price for {ticker}: {e}")
            return {
                "ticker": ticker,
                "timestamp": timestamp,
                "status": "error",
                "error": f"Underlying price fetch failed: {e}",
                "total_stored": 0,
            }
        
        # Get available expiry dates
        try:
            available_expiries = stock.options
            if not available_expiries:
                LOGGER.warning(f"No options data available for {ticker}")
                return {
                    "ticker": ticker,
                    "timestamp": timestamp,
                    "status": "no_data",
                    "error": "No options available",
                    "total_stored": 0,
                }
            LOGGER.info(f"Found {len(available_expiries)} expiry dates for {ticker}")
        except Exception as e:
            LOGGER.error(f"Failed to get expiry dates for {ticker}: {e}")
            return {
                "ticker": ticker,
                "timestamp": timestamp,
                "status": "error",
                "error": f"Expiry fetch failed: {e}",
                "total_stored": 0,
            }
        
        # Filter to specific expiry if requested
        if specific_expiry:
            if specific_expiry not in available_expiries:
                LOGGER.error(f"Expiry {specific_expiry} not available for {ticker}")
                LOGGER.info(f"Available: {available_expiries}")
                return {
                    "ticker": ticker,
                    "timestamp": timestamp,
                    "status": "error",
                    "error": f"Expiry {specific_expiry} not found",
                    "total_stored": 0,
                }
            expiries_to_download = [specific_expiry]
        else:
            expiries_to_download = list(available_expiries)
        
        total_stats = {
            "total_records": 0,
            "valid_records": 0,
            "filtered_records": 0,
            "expiry_count": 0,
        }
        
        # Download each expiry
        for expiry in expiries_to_download:
            LOGGER.info(f"Downloading {ticker} {expiry}...")
            
            try:
                # Get options chain for this expiry
                chain = stock.option_chain(expiry)
                
                # Process calls
                if hasattr(chain, 'calls') and not chain.calls.empty:
                    calls_df = chain.calls.copy()
                    calls_df["optionType"] = "call"
                    calls_df["expiration"] = expiry
                    
                    stats = store.store_chain(
                        ticker=ticker,
                        timestamp=timestamp,
                        chain_df=calls_df,
                        underlying_price=underlying_price,
                    )
                    
                    total_stats["total_records"] += stats["total"]
                    total_stats["valid_records"] += stats["valid"]
                    total_stats["filtered_records"] += stats["filtered"]
                    total_stats["expiry_count"] += 1
                    
                    LOGGER.info(f"  Calls: {stats['valid']}/{stats['total']} valid")
                
                # Process puts
                if hasattr(chain, 'puts') and not chain.puts.empty:
                    puts_df = chain.puts.copy()
                    puts_df["optionType"] = "put"
                    puts_df["expiration"] = expiry
                    
                    stats = store.store_chain(
                        ticker=ticker,
                        timestamp=timestamp,
                        chain_df=puts_df,
                        underlying_price=underlying_price,
                    )
                    
                    total_stats["total_records"] += stats["total"]
                    total_stats["valid_records"] += stats["valid"]
                    total_stats["filtered_records"] += stats["filtered"]
                    
                    LOGGER.info(f"  Puts: {stats['valid']}/{stats['total']} valid")
                
            except Exception as e:
                LOGGER.warning(f"Failed to download {ticker} {expiry}: {e}")
                continue
        
        LOGGER.info(
            f"Download complete for {ticker}: "
            f"{total_stats['valid_records']}/{total_stats['total_records']} valid "
            f"({total_stats['filtered_records']} filtered)"
        )
        
        return {
            "ticker": ticker,
            "timestamp": timestamp,
            "status": "success",
            "total_stored": total_stats["valid_records"],
            "total_downloaded": total_stats["total_records"],
            "total_filtered": total_stats["filtered_records"],
            "expiries_processed": total_stats["expiry_count"],
            "underlying_price": underlying_price,
        }
        
    except Exception as e:
        LOGGER.error(f"Fatal error downloading {ticker}: {e}", exc_info=True)
        return {
            "ticker": ticker,
            "timestamp": timestamp,
            "status": "error",
            "error": str(e),
            "total_stored": 0,
        }


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Download options chain data for a ticker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s NVDA                    # Download all expiries for NVDA
  %(prog)s AAPL --db mydata.db     # Use custom database
  %(prog)s TSLA --expiry 2026-03-21 # Download specific expiry only
  %(prog)s --ticker-file tickers.txt # Download all tickers in file
        """,
    )
    
    parser.add_argument(
        "ticker",
        nargs="?",
        help="Stock ticker symbol (e.g., NVDA, AAPL, TSLA)",
    )
    
    parser.add_argument(
        "--ticker-file",
        help="Path to file with comma-separated tickers to download",
    )
    
    parser.add_argument(
        "--db",
        default="data/options_intraday.db",
        help="Path to SQLite database (default: data/options_intraday.db)",
    )
    
    parser.add_argument(
        "--expiry",
        help="Specific expiry date to download (YYYY-MM-DD format). "
             "If not specified, downloads all available expiries.",
    )
    
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Handle ticker file option
    if args.ticker_file:
        # Import batch download for file handling
        try:
            from scripts.download_batch import load_tickers_from_file, download_batch
            tickers = load_tickers_from_file(args.ticker_file)
            results = download_batch(
                tickers=tickers,
                db_path=args.db,
                specific_expiry=args.expiry,
            )
            failed = sum(1 for r in results if r.get("status") != "success")
            sys.exit(0 if failed == 0 else 1)
        except Exception as e:
            LOGGER.error(f"Failed to process ticker file: {e}")
            sys.exit(1)
    
    # Validate single ticker
    if not args.ticker:
        LOGGER.error("Must provide ticker or --ticker-file")
        sys.exit(1)
    
    if not args.ticker.isalnum():
        LOGGER.error(f"Invalid ticker format: {args.ticker}")
        sys.exit(1)
    
    # Initialize store
    store = create_store(args.db)
    
    # Download data
    result = download_options_chain(
        ticker=args.ticker.upper(),
        store=store,
        specific_expiry=args.expiry,
    )
    
    # Print summary
    print("\n" + "=" * 60)
    print("DOWNLOAD SUMMARY")
    print("=" * 60)
    print(f"Ticker: {result['ticker']}")
    print(f"Timestamp: {result['timestamp']}")
    print(f"Status: {result['status']}")
    
    if result['status'] == "success":
        print(f"Underlying Price: ${result['underlying_price']:.2f}")
        print(f"Records Stored: {result['total_stored']:,}")
        print(f"Records Downloaded: {result['total_downloaded']:,}")
        print(f"Records Filtered: {result['total_filtered']:,}")
        print(f"Expiries Processed: {result['expiries_processed']}")
        print(f"\nDatabase: {args.db}")
        sys.exit(0)
    else:
        print(f"Error: {result.get('error', 'Unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
