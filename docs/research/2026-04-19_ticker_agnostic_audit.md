# Ticker-Agnostic Audit

Date: 2026-04-19
Task: `016_ticker_agnostic_audit`

## Conclusion

The engine is less NVDA-coupled than the package name suggests. Most live behavior is already
ticker-relative through market data, calibration, and the CLI `--ticker` path.

## Real Behavioral Coupling Found

### 1. Hidden helper default in `main.py`

- `_load_filtered_chain()` defaulted `ticker=config.TICKER`
- Risk: any future internal caller that omitted the ticker would silently fall back to `NVDA`
- Fix: helper now accepts `ticker: str | None = None` and resolves explicitly at call time

### 2. Missing non-NVDA regression coverage

- The code path for `--ticker TSLA` or `--ticker MSFT` was not pinned by tests
- Risk: a later refactor could reintroduce ticker leakage without detection
- Fix: added a focused main-path regression test using `TSLA` in `--test-data` mode

## Cosmetic, Not Behavioral

These items are still worth cleaning eventually, but they are not current output-contamination
sources:

- package name `event_vol_analysis`
- `config.TICKER = "NVDA"` as the CLI default example
- comments referencing NVDA-derived historical intuition

## Already Ticker-Relative

The following paths are already parameterized enough for current multi-name use:

- spot and dividend lookup
- option expiry discovery
- chain loading
- liquidity calibration
- GEX threshold calibration
- wing-width calibration
- IV scenario calibration from front/back structure
- synthetic scenario generation for most test-data workflows

## Remaining Recommendation

Do not rename the package before earnings season. That is a wide cosmetic change with low operator
value. Keep the trust fix targeted:

1. retain the CLI `--ticker` path
2. keep non-NVDA regression coverage
3. avoid hidden `config.TICKER` fallbacks in helper internals
