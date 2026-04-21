id: T021
title: Fat-tailed move distribution

objective:
  Replace log-normal earnings move simulation with fat-tailed distribution better aligned to post-earnings behavior.

context:
  Earnings moves have fat tails (gaps). Need better distribution model.

inputs:
  - Historical earnings moves
  - Current simulation engine

outputs:
  - Fat-tailed simulation path (Laplace or jump-diffusion)
  - Calibration logic
  - Side-by-side comparison

prerequisites:
  - T022 (recommended)

dependencies:
  - T022

non_goals:
  - No skew dynamics work

requirements:
  - Explicit model selection (not silent swap)
  - Calibration from historical moves
  - Side-by-side output
  - Seeded reproducibility

acceptance_criteria:
  - Model selectable
  - Historical moves affect distribution
  - Comparison output exists
  - All 18 tests pass

tests:
  unit:
    - test_model_selection
    - test_calibration
    - test_seeded_determinism
  integration:
    - Side-by-side comparison

definition_of_done:
  - All 18 tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Completed in 2026
  - Laplace and jump-diffusion options
  - Explicit --distribution flag

failure_modes:
  - No historical data → fallback to log-normal