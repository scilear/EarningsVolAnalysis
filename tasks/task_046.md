id: T046
title: Rate Limiting + Dynamic Earnings Universe for EOD Refresh
status: completed

objective:
  Add rate limiting to yfinance-based option chain fetching, and implement
  a dynamic universe filter that only fetches chains for tickers with earnings
  in the past 2 weeks or next month (instead of the full static universe).

context:
  Current EOD refresh fetches option chains for all ~80 tickers in the static
  ticker_list.csv. This triggers yfinance rate limiting (429 Too Many Requests).
  Additionally, most of those tickers don't have earnings soon - fetching their
  chains is wasteful.

  Also, daily_scan fetches from yfinance for the full universe calendar, which hits
  rate limits when running multiple times per day.

inputs:
  - Current ticker_list.csv (static universe)
  - event_registry table (has earnings dates)
  - yfinance option chain fetch code in data/loader.py and workflow/daily_scan.py

outputs:
  - Rate-limited yfinance fetch with retry logic (configurable delay)
  - Dynamic universe filter: only tickers with earnings in [today-14 days, today+30 days]
  - Updated EOD refresh to use dynamic universe
  - Updated daily_scan calendar fetch to be more efficient

prerequisites:
  - T044 (EOD workflow) must be working

dependencies:
  - None

non_goals:
  - Not replacing yfinance as primary source (IB is primary, this is fallback)
  - Not adding paid data provider integration

requirements:
  - Rate limiter: add configurable delay between yfinance requests (default 200ms)
  - Rate limiter: retry logic with exponential backoff (max 3 retries, 1s/2s/4s delays)
  - Rate limiter: only apply delay to yfinance paths, not IB or cached data
  - Dynamic universe: query event_registry for tickers with events in window
  - Dynamic universe: window = [scan_date - 14 days, scan_date + 30 days]
  - Dynamic universe: fallback to static list if event_registry is empty
  - EOD refresh uses dynamic universe by default
  - Document rate limiter config in config.py (YF_RATE_LIMIT_MS, YF_MAX_RETRIES)

acceptance_criteria:
  - EOD refresh completes for 10 tickers without 429 errors
  - Rate limiter adds ~200ms delay between yfinance calls (observable in logs)
  - Retry logic kicks in and succeeds on temporary 429 errors
  - Dynamic universe returns at most ~20 tickers on typical day
  - Full static universe still works if dynamic returns empty

tests:
  unit:
    - test_rate_limiter_applies_delay
    - test_rate_limiter_retries_on_429
    - test_dynamic_universe_filters_earnings_window
    - test_dynamic_universe_falls_back_to_static
  integration:
    - EOD refresh on 10-name test set completes without 429 (actual yfinance)

definition_of_done:
  - Rate limiter implemented with config
  - Dynamic universe implemented
  - Integration tests pass
  - Task marked complete in docs/TASKS.md

completion_notes:
  - Added yfinance throttle + 429 retry backoff in loader and calendar backfill paths.
  - Added config controls `YF_RATE_LIMIT_MS` and `YF_MAX_RETRIES`.
  - Added dynamic universe selection from `event_registry` using
    `[scan_date-14d, scan_date+30d]` with static fallback.
  - Wired EOD refresh and daily calendar ingestion to dynamic universe.
  - Added tests for rate limiter behavior and dynamic universe fallback/filtering.

notes:
  - IB is the primary source during market hours - yfinance fallback only runs
    during EOD refresh or when IB data is unavailable
  - Rate limiting should NOT apply to cached data (option_quotes) queries
  - The 14M rows in option_quotes provide historical coverage - dynamic fetch
    primarily captures NEW data for upcoming earnings

failure_modes:
  - Rate limiter too aggressive - EOD takes too long
    Fix: reduce YF_RATE_LIMIT_MS
  - Dynamic universe returns empty - market holiday or no events
    Fix: falls back to static list automatically
  - yfinance completely blocked - need alternative data provider
    Defer to future task if persistent
