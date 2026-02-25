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
IMPLIED_MOVE_MAX_SPREAD_PCT: float = 0.20

# Calendar strategy (legacy; superseded by BACK3_DTE_MIN/MAX below)
CALENDAR_LONG_MIN_DTE: int = 30

# Holding behavior
HOLD_TO_EXPIRY: bool = False

# ── Back3 expiry selection ─────────────────────────────────────────────────
# Shared by data loader + all strategies that use a back3 leg.
# Change here once; applies everywhere.
BACK3_DTE_MIN: int = 21   # minimum DTE for back3 expiry selection
BACK3_DTE_MAX: int = 45   # maximum DTE for back3 expiry selection

# ── Calendar ──────────────────────────────────────────────────────────────
CALENDAR_PREFERRED_BACK: str = "back3"
CALENDAR_FALLBACK_BACK: str = "back1"
CALENDAR_MIN_TERM_SPREAD_DAYS: int = 14
CALENDAR_BACK3_POST_EVENT_IV_FACTOR: float = 0.92
CALENDAR_BACK1_POST_EVENT_IV_FACTOR: float = 0.85

# ── Backspreads ────────────────────────────────────────────────────────────
BACKSPREAD_RATIO: tuple[int, int] = (1, 2)   # sell 1, buy 2
BACKSPREAD_MAX_DEBIT_FRACTION: float = 0.15
BACKSPREAD_MIN_WING_WIDTH: float = 2.5       # min strike distance (dollars)
# Aliases — keep in sync with BACK3_DTE_MIN/MAX (single source of truth).
BACKSPREAD_LONG_DTE_MIN: int = BACK3_DTE_MIN
BACKSPREAD_LONG_DTE_MAX: int = BACK3_DTE_MAX
BACKSPREAD_POST_EVENT_IV_FACTOR: float = 0.85
BACKSPREAD_MIN_IV_RATIO: float = 1.40        # front_iv / back_iv gate
BACKSPREAD_MIN_EVENT_VAR_RATIO: float = 0.50  # event dominance gate
BACKSPREAD_MAX_IMPLIED_OVER_P75: float = 0.90  # not overpriced gate
BACKSPREAD_MIN_SHORT_DELTA: float = 0.08     # short leg must have premium

# ── IV compression factors: two different contexts ─────────────────────────
# CALENDAR_BACK3_POST_EVENT_IV_FACTOR = 0.92
#   Used in: pre-event calendar scenario evaluation
#   Meaning: how much the back3 IV drops when the event resolves
#   (entry is pre-event, evaluation simulates post-event crush)
#
# POST_EVENT_CALENDAR_LONG_IV_COMPRESSION = 0.97
#   Used in: post-event calendar scenario evaluation
#   Meaning: mild further compression on back3 IV during the holding period
#   (entry is already post-event, IV has already largely normalised)
#
# These are NOT interchangeable. Do not use one where the other belongs.

# ── Post-event calendar ────────────────────────────────────────────────────
POST_EVENT_CALENDAR_ENTRY_MIN_DAYS: int = 1
POST_EVENT_CALENDAR_ENTRY_MAX_DAYS: int = 3
POST_EVENT_CALENDAR_MIN_IV_RATIO: float = 1.10
POST_EVENT_CALENDAR_MIN_SHORT_DTE: int = 3
# Mild compression on back leg after event settlement.
# The back leg (21-45 DTE) retains most of its IV post-event.
# 0.97 = 3% compression, conservative estimate from NVDA historical surfaces.
# This is NOT the same as CALENDAR_BACK3_POST_EVENT_IV_FACTOR (0.92).
POST_EVENT_CALENDAR_LONG_IV_COMPRESSION: float = 0.97

# IV scenarios
IV_SCENARIOS: dict[str, dict[str, float | str]] = {
    "base_crush": {"front": "collapse_to_back", "back": "unchanged"},
    "hard_crush": {"front": -0.35, "back": -0.10},
    "expansion": {"front": 0.10, "back": 0.05},
}

# Strangle construction
STRANGLE_OFFSET_PCT: float = 0.05

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
# Placeholder threshold; calibrate to OI scale if needed.
GEX_LARGE_ABS: float = 1e9

# Risk-free rate
RISK_FREE_RATE: float = 0.05

# Dividend yield
DIVIDEND_YIELD: float = 0.0003

# Time epsilon
TIME_EPSILON: float = 1e-6

# Contract size
CONTRACT_MULTIPLIER: int = 100
