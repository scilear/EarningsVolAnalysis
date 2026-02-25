"""Synthetic test data generation for report validation without live market data.

This module provides deterministic, realistic option chain generation for testing
the earnings volatility analysis pipeline. Use via --test-data CLI flag.

Example usage:
    # Generate synthetic data
    python -m nvda_earnings_vol.main --test-data

    # Use specific test scenario
    python -m nvda_earnings_vol.main --test-data --test-scenario high_vol

    # Save test data for later use
    python -m nvda_earnings_vol.main --test-data --save-test-data
"""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from scipy.stats import norm

from nvda_earnings_vol import config

LOGGER = logging.getLogger(__name__)

# Default test parameters
DEFAULT_SPOT = 130.0
DEFAULT_RISK_FREE = 0.05
DEFAULT_STRIKE_STEP = 2.5
DEFAULT_STRIKES_COUNT = 41  # ~+/- 25% moneyness

# Test scenario presets
TEST_SCENARIOS = {
    "baseline": {
        "base_iv": 0.55,
        "iv_skew": 0.03,  # put skew
        "term_structure_slope": 0.02,  # upward sloping
        "net_gex_bias": 0.0,  # neutral
        "event_vol_premium": 0.10,  # 10% event vol premium
        "description": "Balanced market with normal vol structure",
    },
    "high_vol": {
        "base_iv": 0.85,
        "iv_skew": 0.05,
        "term_structure_slope": 0.01,
        "net_gex_bias": -0.3,  # negative (dealers short)
        "event_vol_premium": 0.15,
        "description": "Elevated vol environment with pronounced skew",
    },
    "low_vol": {
        "base_iv": 0.35,
        "iv_skew": 0.015,
        "term_structure_slope": 0.03,
        "net_gex_bias": 0.2,
        "event_vol_premium": 0.05,
        "description": "Complacent market with flat skew",
    },
    "gamma_unbalanced": {
        "base_iv": 0.50,
        "iv_skew": 0.025,
        "term_structure_slope": 0.015,
        "net_gex_bias": 0.5,  # strongly positive (dealers long)
        "event_vol_premium": 0.08,
        "description": "Strong positive gamma positioning",
    },
    "term_inverted": {
        "base_iv": 0.60,
        "iv_skew": 0.04,
        "term_structure_slope": -0.02,  # inverted
        "net_gex_bias": -0.1,
        "event_vol_premium": 0.20,
        "description": "Inverted term structure, high event premium",
    },
    "flat_term": {
        "base_iv": 0.55,
        "iv_skew": 0.02,
        "term_structure_slope": 0.0,  # flat: back_iv == front_iv - event_premium
        "net_gex_bias": 0.0,
        "event_vol_premium": 0.0,  # CRITICAL: set to 0 so front_iv == back_iv
        "description": "Flat term structure — event_var extraction must be non-zero",
    },
    "negative_event_var": {
        "base_iv": 0.55,
        "iv_skew": 0.02,
        "term_structure_slope": 0.08,  # back IV 8pts ABOVE base
        "net_gex_bias": 0.0,
        "event_vol_premium": 0.03,  # front IV only 3pts above base → back > front
        "description": "Back IV > front IV — negative event variance edge case",
    },
    "extreme_front_premium": {
        "base_iv": 0.40,
        "iv_skew": 0.02,
        "term_structure_slope": 0.00,
        "net_gex_bias": -0.4,
        "event_vol_premium": 0.60,  # front at 1.0, back at 0.40 → pure binary
        "description": "Pure binary event: >80% of front variance is earnings",
    },
    "sparse_chain": {
        "base_iv": 0.50,
        "iv_skew": 0.04,
        "term_structure_slope": 0.02,
        "net_gex_bias": 0.0,
        "event_vol_premium": 0.10,
        "description": "Thin option chain with wide spreads",
        "_chain_override": {
            "num_strikes": 15,  # only 15 strikes total
            "spread_multiplier": 2.0,  # 2x normal bid-ask spread
        },
    },
}


def generate_option_chain(
    spot: float,
    expiry: dt.date,
    base_iv: float = 0.55,
    iv_skew: float = 0.03,
    net_gex_bias: float = 0.0,
    strike_step: float = DEFAULT_STRIKE_STEP,
    num_strikes: int = DEFAULT_STRIKES_COUNT,
    seed: int | None = 42,
    spread_multiplier: float = 1.0,
) -> pd.DataFrame:
    """Generate synthetic option chain with realistic properties.

    Args:
        spot: Current spot price
        expiry: Option expiry date
        base_iv: Base implied volatility (at-the-money)
        iv_skew: Put skew parameter (higher IV for OTM puts)
        net_gex_bias: Bias for net gamma (-1 to 1, positive = dealers long puts)
        strike_step: Spacing between strikes
        num_strikes: Total number of strikes to generate
        seed: Random seed for reproducibility
        spread_multiplier: Multiplier for bid-ask spread (e.g., 4.0 for sparse chains)

    Returns:
        DataFrame with option chain data including all required columns
    """
    # Use local RNG instead of global seed for thread-safety
    rng = np.random.default_rng(seed)

    # Generate strikes centered around spot
    center_strike = round(spot / strike_step) * strike_step
    half_strikes = num_strikes // 2
    strikes = np.array([
        center_strike + (i - half_strikes) * strike_step
        for i in range(num_strikes)
    ])

    # Calculate actual time to expiry (not hardcoded 30 days)
    today = dt.date.today()
    t_expiry = max((expiry - today).days, 1) / 365.0

    rows = []
    for strike in strikes:
        for opt_type in ["call", "put"]:
            # Calculate moneyness
            moneyness = strike / spot

            # IV smile/skew: higher IV for OTM options, put skew
            if opt_type == "put":
                # Put skew: higher IV for OTM puts (higher strikes)
                iv_adjustment = iv_skew * (moneyness - 1.0)
            else:
                # Call skew: slightly lower IV for OTM calls
                iv_adjustment = -iv_skew * 0.5 * (moneyness - 1.0)

            # Smile effect: higher IV for wings
            smile_adjustment = 0.05 * (moneyness - 1.0) ** 2

            iv = base_iv + iv_adjustment + smile_adjustment
            iv = max(0.10, min(2.0, iv))  # Bound IV

            # Proper Black-Scholes pricing using scipy norm.cdf
            price = _bsm_price(spot, strike, t_expiry, iv, opt_type)

            # Generate bid/ask spread (wider for OTM, tighter for liquid)
            spread_pct = 0.02 + 0.01 * abs(moneyness - 1.0)
            spread = max(0.05, price * spread_pct * spread_multiplier)
            mid = price
            bid = max(0.01, mid - spread / 2)
            ask = mid + spread / 2

            # Open interest: highest near ATM, biased by gex_bias
            oi_base = 5000 * np.exp(-10 * (moneyness - 1.0) ** 2)

            # Add gex bias: positive bias = more put OI = positive net GEX
            # (dealers long puts = positive gamma exposure)
            if opt_type == "put":
                oi_multiplier = 1.0 + net_gex_bias * 0.5
            else:
                oi_multiplier = 1.0 - net_gex_bias * 0.5

            # Add some noise using local RNG
            oi_noise = rng.uniform(0.8, 1.2)
            open_interest = int(oi_base * oi_multiplier * oi_noise)
            open_interest = max(10, open_interest)  # Minimum OI

            rows.append({
                "strike": strike,
                "bid": round(bid, 4),
                "ask": round(ask, 4),
                "mid": round(mid, 4),
                "spread": round(spread, 4),
                "impliedVolatility": round(iv, 4),
                "openInterest": open_interest,
                "option_type": opt_type,
                "expiry": pd.Timestamp(expiry),
            })

    return pd.DataFrame(rows)


def _bsm_price(
    spot: float,
    strike: float,
    t: float,
    iv: float,
    option_type: str,
    r: float = DEFAULT_RISK_FREE,
) -> float:
    """Proper Black-Scholes option price calculation using scipy.

    More accurate than tanh approximation for realistic test data.
    Negative prices are not hidden with abs() - they surface as 0.01 min.
    """
    if t <= 1e-6:
        # At expiry, intrinsic value
        if option_type == "call":
            return max(0.0, spot - strike)
        return max(0.0, strike - spot)

    d1 = (np.log(spot / strike) + (r + 0.5 * iv ** 2) * t) / (iv * np.sqrt(t))
    d2 = d1 - iv * np.sqrt(t)

    if option_type == "call":
        price = spot * norm.cdf(d1) - strike * np.exp(-r * t) * norm.cdf(d2)
    else:
        price = strike * np.exp(-r * t) * norm.cdf(-d2) - spot * norm.cdf(-d1)

    # Don't hide negative prices with abs() - surface them at 0.01 minimum
    return max(0.01, price)


def generate_test_data_set(
    spot: float = DEFAULT_SPOT,
    event_date: dt.date | None = None,
    front_expiry: dt.date | None = None,
    back_expiry: dt.date | None = None,
    scenario: str = "baseline",
    seed: int | None = 42,
) -> dict:
    """Generate complete test data set for earnings vol analysis.

    Args:
        spot: Current spot price
        event_date: Earnings event date (defaults to 7 days from today)
        front_expiry: Front month expiry (defaults to 14 days from today)
        back_expiry: Back month expiry (defaults to 42 days from today)
        scenario: Test scenario name from TEST_SCENARIOS
        seed: Random seed for reproducibility

    Returns:
        Dictionary with all data needed for report generation
    """
    if scenario not in TEST_SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}. Valid: {list(TEST_SCENARIOS)}")

    params = TEST_SCENARIOS[scenario]
    LOGGER.info("Generating test data with scenario '%s': %s", scenario, params["description"])

    # Default dates
    today = dt.date.today()
    if event_date is None:
        event_date = today + dt.timedelta(days=7)
    if front_expiry is None:
        front_expiry = today + dt.timedelta(days=14)
    if back_expiry is None:
        back_expiry = today + dt.timedelta(days=42)

    # Apply chain overrides for special scenarios (e.g., sparse_chain)
    chain_params = {
        "spot": spot,
        "iv_skew": params["iv_skew"],
        "net_gex_bias": params["net_gex_bias"],
        "seed": seed,
    }
    if "_chain_override" in params:
        chain_params.update(params["_chain_override"])

    # Generate front chain with event vol premium
    front_chain = generate_option_chain(
        expiry=front_expiry,
        base_iv=params["base_iv"] + params["event_vol_premium"],
        **chain_params
    )

    # Generate back chain with term structure slope
    # Use local RNG for independent chain generation
    back_seed = (seed + 100) if seed is not None else None
    back_chain = generate_option_chain(
        spot=spot,
        expiry=back_expiry,
        base_iv=params["base_iv"] + params["term_structure_slope"],
        iv_skew=params["iv_skew"] * 0.8,  # Less skew in back month
        net_gex_bias=params["net_gex_bias"] * 0.7,  # Less concentrated
        seed=back_seed,
    )

    # Generate earnings dates (quarterly) - coordinated with price history
    earnings_dates = _generate_earnings_dates(today, num_quarters=12, seed=seed)

    # Generate price history with spikes aligned to earnings dates
    history = _generate_price_history(
        spot, years=config.HISTORY_YEARS,
        earnings_dates=earnings_dates,
        seed=seed
    )

    return {
        "spot": spot,
        "event_date": event_date,
        "front_expiry": front_expiry,
        "back_expiry": back_expiry,
        "front_chain": front_chain,
        "back_chain": back_chain,
        "history": history,
        "earnings_dates": earnings_dates,
        "scenario": scenario,
        "params": params,
    }


def _generate_price_history(
    spot: float,
    years: float,
    earnings_dates: list | None = None,
    seed: int | None = None,
) -> pd.DataFrame:
    """Generate synthetic price history with realistic properties.

    Includes earnings-driven volatility spikes aligned with earnings_dates.
    """
    rng = np.random.default_rng(seed)

    days = int(years * 252)
    dates = pd.bdate_range(
        end=dt.date.today(),
        periods=days,
        freq="B"  # Business days
    )

    # Random walk with drift and volatility clustering
    returns = rng.standard_normal(days) * 0.018 + 0.0003

    # Add earnings volatility spikes at earnings date positions
    if earnings_dates:
        for ed in earnings_dates:
            # Find the index of this earnings date in the date range
            idx = dates.searchsorted(pd.Timestamp(ed))
            if 0 <= idx < days:
                direction = rng.choice([-1, 1])
                magnitude = rng.uniform(0.04, 0.10)
                returns[idx] += direction * magnitude

    prices = spot * np.cumprod(1 + returns)

    return pd.DataFrame({
        "Date": dates,
        "Close": prices,
    })


def _generate_earnings_dates(
    end_date: dt.date,
    num_quarters: int = 12,
    seed: int | None = None,
) -> list[pd.Timestamp]:
    """Generate quarterly earnings dates with local RNG."""
    rng = np.random.default_rng(seed)
    dates = []
    current = end_date

    for _ in range(num_quarters):
        # Go back ~63 trading days (quarter)
        current = current - dt.timedelta(days=90)
        # Randomize within a week using local RNG
        offset = rng.integers(-3, 4)
        earnings_date = current + dt.timedelta(days=int(offset))
        dates.append(pd.Timestamp(earnings_date))

    return list(reversed(dates))


def save_test_data(
    data: dict,
    output_dir: Path,
    name: str = "test_data",
) -> None:
    """Save test data to files for later use.

    Args:
        data: Test data dictionary from generate_test_data_set
        output_dir: Directory to save files
        name: Base name for files
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save chains as CSV
    data["front_chain"].to_csv(
        output_dir / f"{name}_front_chain.csv", index=False
    )
    data["back_chain"].to_csv(
        output_dir / f"{name}_back_chain.csv", index=False
    )
    data["history"].to_csv(
        output_dir / f"{name}_history.csv", index=False
    )

    # Save metadata
    metadata = {
        "spot": data["spot"],
        "event_date": str(data["event_date"]),
        "front_expiry": str(data["front_expiry"]),
        "back_expiry": str(data["back_expiry"]),
        "scenario": data["scenario"],
        "earnings_dates": [str(d.date()) for d in data["earnings_dates"]],
    }

    pd.DataFrame([metadata]).to_json(
        output_dir / f"{name}_metadata.json", orient="records"
    )

    LOGGER.info("Saved test data to %s", output_dir)


def load_test_data(
    input_dir: Path,
    name: str = "test_data",
) -> dict:
    """Load previously saved test data.

    Args:
        input_dir: Directory containing saved files
        name: Base name for files

    Returns:
        Test data dictionary
    """
    input_dir = Path(input_dir)

    front_chain = pd.read_csv(
        input_dir / f"{name}_front_chain.csv", parse_dates=["expiry"]
    )
    back_chain = pd.read_csv(
        input_dir / f"{name}_back_chain.csv", parse_dates=["expiry"]
    )
    history = pd.read_csv(
        input_dir / f"{name}_history.csv", parse_dates=["Date"]
    )

    metadata = pd.read_json(
        input_dir / f"{name}_metadata.json", orient="records"
    ).iloc[0].to_dict()

    return {
        "spot": metadata["spot"],
        "event_date": dt.datetime.strptime(metadata["event_date"], "%Y-%m-%d").date(),
        "front_expiry": dt.datetime.strptime(metadata["front_expiry"], "%Y-%m-%d").date(),
        "back_expiry": dt.datetime.strptime(metadata["back_expiry"], "%Y-%m-%d").date(),
        "front_chain": front_chain,
        "back_chain": back_chain,
        "history": history,
        "earnings_dates": [pd.Timestamp(d) for d in metadata["earnings_dates"]],
        "scenario": metadata["scenario"],
    }


def generate_0dte_test_case(
    spot: float = DEFAULT_SPOT,
    seed: int | None = 42,
) -> dict:
    """Generate test case where front expiry == event_date (0 DTE).

    Front expiry == event_date. Engine must raise ValueError before BSM is called.
    Used with pytest.raises(ValueError).

    Args:
        spot: Current spot price
        seed: Random seed for reproducibility

    Returns:
        Test data dictionary with front_expiry == event_date
    """
    today = dt.date.today()
    event_date = today + dt.timedelta(days=7)

    return generate_test_data_set(
        spot=spot,
        event_date=event_date,
        front_expiry=event_date,  # INTENTIONAL: triggers 0 DTE guard
        back_expiry=today + dt.timedelta(days=42),
        scenario="baseline",
        seed=seed,
    )


def list_available_scenarios() -> list[str]:
    """Return list of available test scenarios."""
    return list(TEST_SCENARIOS.keys())


def get_scenario_description(scenario: str) -> str:
    """Get description for a test scenario."""
    if scenario not in TEST_SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}")
    return TEST_SCENARIOS[scenario]["description"]
