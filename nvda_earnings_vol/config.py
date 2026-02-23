"""Configuration constants for the NVDA earnings vol engine."""

from __future__ import annotations

TICKER: str = "NVDA"
HISTORY_YEARS: int = 5
MC_SIMULATIONS: int = 100_000

# Strike filtering
MONEYNESS_LOW: float = 0.80
MONEYNESS_HIGH: float = 1.20

# Liquidity filters
MIN_OI: int = 100
MAX_SPREAD_PCT: float = 0.05

# Slippage
SLIPPAGE_PCT: float = 0.10

# Calendar strategy
CALENDAR_LONG_MIN_DTE: int = 30

# Holding behavior
HOLD_TO_EXPIRY: bool = False

# IV scenarios
IV_SCENARIOS: dict[str, dict[str, float | str]] = {
    "base_crush": {"front": "collapse_to_back", "back": "collapse_to_back"},
    "hard_crush": {"front": -0.35, "back": -0.10},
    "expansion": {"front": 0.10, "back": 0.05},
}

# Vol-of-vol shocks
VOL_SHOCKS: list[int] = [-10, -5, 5, 10]

# Scoring weights
SCORING_WEIGHTS: dict[str, float] = {
    "ev": 0.4,
    "convexity": 0.3,
    "cvar": 0.2,
    "robustness": 0.1,
}

# Convexity guard
CONVEXITY_CAP: float = 10.0
CONVEXITY_EPS: float = 1e-6

# GEX
GEX_RANGE_PCT: float = 0.05
GEX_LARGE_ABS: float = 1e9

# Risk-free rate
RISK_FREE_RATE: float = 0.05

# Dividend yield
DIVIDEND_YIELD: float = 0.0003

# Time epsilon
TIME_EPSILON: float = 1e-6

# Contract size
CONTRACT_MULTIPLIER: int = 100
