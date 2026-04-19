# Task 021: Fat-Tailed Earnings Move Model

## Complexity

`strong`

## Objective

Replace the current pure log-normal earnings move simulation with a distribution better aligned to
gap-heavy post-earnings behavior.

## Scope

- Evaluate at least one candidate model:
  - Laplace
  - jump-diffusion mixture
- Calibrate the chosen model from historical earnings moves already in the pipeline
- Add comparison hooks versus the current log-normal engine

## Deliverables

- New simulation path
- Calibration logic
- Regression comparison output
- Tests for deterministic seeded behavior

## Acceptance Criteria

- The model can be selected explicitly, not silently swapped in
- Historical move inputs materially affect simulation shape
- Side-by-side output exists for log-normal vs fat-tailed simulation on the same snapshot
- Seeded runs remain reproducible

## Notes

Do not mix this with skew-dynamics work. Keep the first modeling upgrade isolated.
