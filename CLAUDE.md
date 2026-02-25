# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Run the analysis (live market data):**
```sh
cd nvda_earnings_vol
python main.py --event-date 2026-02-26 --output reports/nvda_earnings_report.html
python main.py --use-cache --event-date 2026-02-26   # use cached option chains
python main.py --refresh-cache --event-date 2026-02-26  # force refresh cache
```

**Run with synthetic test data:**
```sh
python main.py --test-data --test-scenario baseline --seed 42
python main.py --test-data --test-scenario baseline --save-test-data reports/test_scenarios/
# Available scenarios (14 total):
#   baseline, high_vol, low_vol, gamma_unbalanced, term_inverted,
#   flat_term, negative_event_var, extreme_front_premium, sparse_chain,
#   backspread_favorable, backspread_unfavorable, backspread_overpriced,
#   post_event_entry, post_event_flat
```

**Run all 14 scenarios (HTML reports + acceptance criterion validation):**
```sh
./run_all_scenarios.sh
```

**Run tests:**
```sh
pytest                                          # all tests
pytest nvda_earnings_vol/tests/test_bsm.py     # single file
pytest nvda_earnings_vol/tests/test_bsm.py::TestClassName::test_func_name  # single test
```

**Lint:**
```sh
flake8 .
```

**Install dependencies:**
```sh
pip install -r nvda_earnings_vol/requirements.txt
```

## Architecture

The package lives entirely under `nvda_earnings_vol/`. `main.py` is the CLI entrypoint and orchestration layer — it wires together all subsystems and writes the HTML report.

**Data layer (`data/`):**
- `loader.py` — fetches live market data via `yfinance` (spot price, option chains, expiries, price history, earnings dates). Supports CSV caching under `data/cache/` with `--use-cache` / `--refresh-cache` flags.
- `filters.py` — filters option chains by moneyness (80–120% of spot) and liquidity (OI ≥ 100, spread ≤ 5%).
- `test_data.py` — generates synthetic option chains and price history for offline validation via named scenarios (e.g., `baseline`).

**Analytics layer (`analytics/`):**
- `event_vol.py` — extracts the event-specific variance component from the vol term structure using total-variance interpolation across front/back1/back2 expiries.
- `implied_move.py` — computes implied move from the ATM straddle on the front-expiry chain.
- `historical.py` — computes historical earnings move distribution (P75, distribution shape, signed moves).
- `skew.py` — computes 25-delta risk reversal (`rr25`) and butterfly (`bf25`).
- `gamma.py` — computes dealer GEX (net/abs), gamma-flip level, and top gamma strikes.
- `bsm.py` — Black-Scholes-Merton pricing and Greeks.

**Strategy layer (`strategies/`):**
- `structures.py` — defines `OptionLeg` and `Strategy` dataclasses; `build_strategies()` constructs candidate structures (straddle, strangle, calendar, etc.) from the front/back chains.
- `backspreads.py` — 1×2 call/put backspread builder with 4-condition entry gate: `iv_ratio ≥ 1.40`, `event_variance_ratio ≥ 0.50`, `implied_move ≤ P75 × 0.90`, `short_delta ≥ 0.08`.
- `calendar.py` — calendar spread builder preferring back3 (21-45 DTE) over back1; uses `abs()` on term spread to handle inverted structures.
- `post_event_calendar.py` — post-event calendar (1-3 days after earnings); `compute_post_event_calendar_scenarios()` evaluates stock-movement P&L (no `iv_short` param — short leg settles at intrinsic).
- `registry.py` — `STRATEGY_CONDITIONS` / `STRATEGY_BUILDERS` dicts with module-level assertion enforcing key parity; `should_build_strategy(name, snapshot)` raises `KeyError` for unregistered names.
- `payoff.py` — vectorized P&L simulation (`strategy_pnl_vec`) across Monte Carlo move samples under a given IV scenario.
- `scoring.py` — `compute_metrics()` calculates EV, CVaR, convexity, and robustness; `score_strategies()` ranks by weighted composite score using weights from `config.SCORING_WEIGHTS`.

**Regime & Alignment:**
- `regime.py` — `classify_regime()` classifies the market into five regime axes (vol pricing, event structure, term structure, dealer gamma, composite) from the data snapshot.
- `alignment.py` — `compute_all_alignments()` scores each ranked strategy's structural fit against the classified regime (orthogonal to the EV-based ranking).

**Simulation (`simulation/`):**
- `monte_carlo.py` — `simulate_moves()` draws log-normal spot move samples given event vol and optional vol-of-vol shocks.

**Visualization (`viz/`):**
- `plots.py` — generates matplotlib base64-encoded inline plots for the HTML report.

**Reports (`reports/`):**
- `reporter.py` — `write_report()` renders the Jinja2 HTML template and writes to the output path. All HTML is self-contained (no external assets).

**Key config (`config.py`):**
- `MC_SIMULATIONS = 100_000` — Monte Carlo sample count.
- `IV_SCENARIOS` — three vol crush/expansion scenarios applied during strategy scoring.
- `VOL_SHOCKS` — vol-of-vol shocks (±5%, ±10%) applied for robustness scoring.
- `SCORING_WEIGHTS` — EV (0.4), convexity (0.3), CVaR (0.2), robustness (0.1).
- `BACK3_DTE_MIN = 21`, `BACK3_DTE_MAX = 45` — single source of truth for back3 expiry window; shared by loader, backspread builder, and calendar builder.
- `BACKSPREAD_*` — backspread entry thresholds (`BACKSPREAD_LONG_DTE_MIN/MAX` are aliases for `BACK3_DTE_MIN/MAX`).
- `CALENDAR_*` — calendar IV factors: `BACK3_POST_EVENT_IV_FACTOR = 0.92` (pre-event entry), `BACK1_POST_EVENT_IV_FACTOR = 0.85`.
- `POST_EVENT_CALENDAR_*` — post-event calendar thresholds; `LONG_IV_COMPRESSION = 0.97` (distinct from calendar factor 0.92).

## Code Style

Follow the conventions in `AGENTS.md`: PEP 8, 79-char line limit, 4-space indent, type hints on all new/modified functions, f-strings, `logging` (not `print`) for progress. Docstrings required at file, class, and function level.
