# Task 016: Ticker-Agnostic Audit

## Complexity

`strong`

## Objective

Remove or isolate remaining NVDA-shaped defaults so the engine can be trusted on any supported
earnings name.

## Scope

- Audit `config.py`, calibration paths, test data generation, and report defaults
- Identify every place where `NVDA` is still a behavioral assumption rather than just a default
  example
- Replace hardcoded behavior with explicit ticker parameters or neutral defaults
- Preserve backward compatibility for the CLI

## Deliverables

- Code changes that eliminate behavioral dependence on `config.TICKER = "NVDA"`
- A short audit note summarizing what was changed and what still remains ticker-sensitive by design
- Regression coverage for at least one non-NVDA ticker in test-data mode

## Acceptance Criteria

- Running the CLI with `--ticker TSLA` or `--ticker MSFT` does not use NVDA-specific calibration or
  scenario assumptions unless explicitly documented and parameterized
- Default output/report naming remains valid
- Test fixtures and synthetic data are not semantically labeled as NVDA-only unless intentionally so
- Any still-name-specific parameter is called out explicitly in docs

## Notes

This is broader than changing one constant. Treat it as a trust audit, not a cosmetic rename.
