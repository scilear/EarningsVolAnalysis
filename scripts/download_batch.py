#!/usr/bin/env python3
"""Download options chains for multiple tickers in parallel.

Usage:
    python scripts/download_batch.py
    python scripts/download_batch.py --tickers NVDA TSLA AMD
    python scripts/download_batch.py --ticker-file tickers.txt
    python scripts/download_batch.py --db data/mydata.db --workers 3
"""

from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import yfinance as yf

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.option_data_store import create_store
from scripts.download_options_chain import download_options_chain

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
LOGGER = logging.getLogger(__name__)

# Default ticker list for earnings volatility analysis
DEFAULT_TICKERS = [
    "NVDA",
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "TSLA",
    "META",
    "AMD",
    "INTC",
    "CRM",
]


def load_tickers_from_file(filepath: str) -> list[str]:
    """Load tickers from a comma-separated file.
    
    Args:
        filepath: Path to file containing comma-separated tickers
        
    Returns:
        List of ticker symbols
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Ticker file not found: {filepath}")
    
    content = path.read_text().strip()
    tickers = [t.strip().upper() for t in content.split(",") if t.strip()]
    
    if not tickers:
        raise ValueError(f"No valid tickers found in {filepath}")
    
    LOGGER.info(f"Loaded {len(tickers)} tickers from {filepath}")
    return tickers


def download_single_ticker(
    args_tuple: tuple[str, Any, str | None]
) -> dict[str, Any]:
    """Download options for a single ticker (wrapper for parallel).
    
    Args:
        args_tuple: (ticker, store, specific_expiry)
        
    Returns:
        Download result dict
    """
    ticker, store, specific_expiry = args_tuple
    try:
        return download_options_chain(ticker, store, specific_expiry)
    except Exception as e:
        LOGGER.error(
            f"Unexpected error downloading {ticker}: {e}",
            exc_info=True,
        )
        return {
            "ticker": ticker,
            "status": "error",
            "error": str(e),
            "total_stored": 0,
        }


def download_batch(
    tickers: list[str],
    db_path: str = "data/options_intraday.db",
    specific_expiry: str | None = None,
    max_workers: int = 5,
) -> list[dict[str, Any]]:
    """Download options chains for multiple tickers in parallel.
    
    Args:
        tickers: List of ticker symbols
        db_path: Path to database file
        specific_expiry: Specific expiry to download (or None for all)
        max_workers: Number of parallel download threads
        
    Returns:
        List of download result dicts
    """
    store = create_store(db_path)
    
    LOGGER.info(f"Starting batch download for {len(tickers)} tickers")
    LOGGER.info(f"Database: {db_path}")
    LOGGER.info(f"Parallel workers: {max_workers}")
    
    download_args = [
        (ticker, store, specific_expiry)
        for ticker in tickers
    ]
    
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ticker = {
            executor.submit(download_single_ticker, args): args[0]
            for args in download_args
        }
        
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                result = future.result()
                results.append(result)
                
                status = result.get("status", "unknown")
                if status == "success":
                    LOGGER.info(
                        f"OK {ticker}: {result.get('total_stored', 0):,} records"
                    )
                else:
                    LOGGER.warning(
                        f"FAIL {ticker}: {status} - {result.get('error', 'Unknown')}"
                    )
                
            except Exception as e:
                LOGGER.error(f"FAIL {ticker}: Exception - {e}")
                results.append({
                    "ticker": ticker,
                    "status": "error",
                    "error": str(e),
                    "total_stored": 0,
                })
    
    return results


def print_summary(
    results: list[dict[str, Any]],
    tickers: list[str],
) -> None:
    """Print batch download summary.
    
    Args:
        results: List of download results
        tickers: Original list of tickers requested
    """
    total_stored = sum(r.get("total_stored", 0) for r in results)
    successful = sum(1 for r in results if r.get("status") == "success")
    failed = len(results) - successful
    
    print("\n" + "=" * 70)
    print("BATCH DOWNLOAD SUMMARY")
    print("=" * 70)
    print(f"Total tickers requested: {len(tickers)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Total records stored: {total_stored:,}")
    print("=" * 70)
    
    if failed > 0:
        print("\nFailed tickers:")
        for result in results:
            if result.get("status") != "success":
                print(f"  {result['ticker']}: {result.get('error', 'Unknown')}")
    
    print("\nSuccessful tickers:")
    for result in results:
        if result.get("status") == "success":
            stored = result.get("total_stored", 0)
            underlying = result.get("underlying_price", 0)
            print(f"  {result['ticker']}: ${underlying:.2f} -> {stored:,} records")
    
    print()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Download options chains for multiple tickers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download default tickers
  %(prog)s

  # Download specific tickers
  %(prog)s --tickers NVDA TSLA AMD

  # Download from comma-separated file
  %(prog)s --ticker-file tickers.txt

  # Download with custom database
  %(prog)s --db /path/to/mydata.db

  # Download with fewer workers
  %(prog)s --workers 3
""",
    )
    
    ticker_group = parser.add_mutually_exclusive_group()
    
    ticker_group.add_argument(
        "--tickers",
        nargs="+",
        default=None,
        help="List of ticker symbols from command line",
    )
    
    ticker_group.add_argument(
        "--ticker-file",
        default=None,
        help="Path to file with comma-separated tickers",
    )
    
    parser.add_argument(
        "--db",
        default="data/options_intraday.db",
        help="Path to SQLite database (default: data/options_intraday.db)",
    )
    
    parser.add_argument(
        "--expiry",
        help="Specific expiry date (YYYY-MM-DD) or 'all' for all expiries",
    )
    
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Number of parallel workers (default: 5)",
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
    
    # Determine tickers to download
    tickers = DEFAULT_TICKERS
    
    if args.ticker_file:
        try:
            tickers = load_tickers_from_file(args.ticker_file)
        except (FileNotFoundError, ValueError) as e:
            LOGGER.error(str(e))
            sys.exit(1)
    elif args.tickers:
        tickers = [t.upper() for t in args.tickers if t.isalnum()]
    
    if not tickers:
        LOGGER.error("No valid tickers provided")
        sys.exit(1)
    
    # Run batch download
    start_time = datetime.now()
    results = download_batch(
        tickers=tickers,
        db_path=args.db,
        specific_expiry=args.expiry,
        max_workers=args.workers,
    )
    duration = (datetime.now() - start_time).total_seconds()
    
    # Print summary
    print_summary(results, tickers)
    
    print(f"Total time: {duration:.1f} seconds")
    print(f"Database: {args.db}")
    print()
    
    # Exit with error code if any failed
    failed_count = sum(1 for r in results if r.get("status") != "success")
    sys.exit(0 if failed_count == 0 else 1)


if __name__ == "__main__":
    main()
