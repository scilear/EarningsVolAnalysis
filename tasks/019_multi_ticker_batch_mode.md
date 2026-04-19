# Task 019: Multi-Ticker Batch Mode

## Complexity

`strong`

## Objective

Turn the CLI into a watchlist scanner that can evaluate multiple earnings names in one run and emit
operator-friendly summary output.

## Scope

- Define watchlist input contract
- Add batch CLI entry path
- Reuse the existing single-name engine without duplicating pricing logic
- Emit a summary table plus optional per-name reports

## Deliverables

- Batch CLI mode
- Watchlist input parser
- Batch summary output
- Per-name failure reporting that does not abort the full batch

## Acceptance Criteria

- One command can process a list of tickers with associated event dates or auto-discovered dates
- A single bad ticker does not kill the whole batch
- Output contains at minimum:
  - ticker
  - event date
  - detected regime
  - top structure
  - score
  - blocking warnings
- The batch path reuses the same ranking/report pipeline as the single-ticker path

## Notes

This should probably extract a callable analysis function out of `main()` before layering the batch
CLI on top.
