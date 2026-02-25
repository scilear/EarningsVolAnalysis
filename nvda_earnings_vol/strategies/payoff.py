"""Strategy pricing and payoff logic."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from nvda_earnings_vol.analytics.bsm import option_price, option_price_vec
from nvda_earnings_vol.config import (
    CONTRACT_MULTIPLIER,
    DIVIDEND_YIELD,
    HOLD_TO_EXPIRY,
    IV_SCENARIOS,
    RISK_FREE_RATE,
    TIME_EPSILON,
)
from nvda_earnings_vol.data.filters import execution_price, execution_price_vec
from nvda_earnings_vol.strategies.structures import Strategy


# =============================================================================
# VECTORIZED VERSION (for Monte Carlo simulation)
# =============================================================================


def strategy_pnl_vec(
    strategy: Strategy,
    chain: pd.DataFrame,
    spot: float,
    moves: np.ndarray,
    front_expiry: dt.date,
    back_expiry: dt.date,
    event_date: dt.date,
    front_iv: float,
    back_iv: float,
    slippage_pct: float,
    scenario: str,
) -> np.ndarray:
    """Compute P&L distribution for a strategy (vectorized over moves).
    
    This is the optimized version that eliminates the Python loop over
    Monte Carlo simulations by vectorizing the BSM pricing.
    
    Args:
        strategy: Strategy with legs to price
        chain: Options chain DataFrame
        spot: Current spot price
        moves: Array of price moves (shape: (N,))
        front_expiry: Front month expiry
        back_expiry: Back month expiry
        event_date: Earnings event date
        front_iv: Front month ATM IV
        back_iv: Back month ATM IV
        slippage_pct: Slippage percentage
        scenario: IV scenario name
    
    Returns:
        Array of P&L values (shape: (N,))
    """
    moves = np.asarray(moves, dtype=np.float64)
    n_sims = len(moves)
    
    lookup = _build_lookup(chain)
    expiry_atm_iv = _expiry_atm_iv(chain, spot)
    entry_cost = _entry_cost(strategy, lookup, slippage_pct)
    
    # Vectorized: compute all new spot prices at once
    new_spots = spot * (1.0 + moves)  # shape: (N,)
    
    # Accumulate exit values across legs (small loop: 1-4 legs max)
    exit_values = np.zeros(n_sims, dtype=np.float64)
    
    for leg in strategy.legs:
        data = _get_leg_data(lookup, leg)
        
        if HOLD_TO_EXPIRY:
            # Vectorized intrinsic value
            prices = _intrinsic_vec(new_spots, leg.strike, leg.option_type)
        else:
            t_remaining = _time_remaining(event_date, leg.expiry.date())
            post_iv = _post_iv(
                leg.expiry.date(),
                front_expiry,
                back_expiry,
                scenario,
                front_iv,
                back_iv,
                data["iv"],
                expiry_atm_iv,
            )
            # Vectorized BSM pricing
            prices = option_price_vec(
                new_spots,
                leg.strike,
                t_remaining,
                RISK_FREE_RATE,
                DIVIDEND_YIELD,
                post_iv,
                leg.option_type,
            )
            # Apply slippage on exit (vectorized)
            exit_side = "sell" if leg.side == "buy" else "buy"
            prices = execution_price_vec(
                prices,
                data["spread"],
                exit_side,
                slippage_pct,
            )
        
        # Accumulate leg contribution
        sign = 1.0 if leg.side == "buy" else -1.0
        exit_values += sign * prices * leg.qty * CONTRACT_MULTIPLIER
    
    return exit_values - entry_cost


def _intrinsic_vec(
    spot_arr: np.ndarray, strike: float, option_type: str
) -> np.ndarray:
    """Vectorized intrinsic value calculation."""
    if option_type == "call":
        return np.maximum(spot_arr - strike, 0.0)
    if option_type == "put":
        return np.maximum(strike - spot_arr, 0.0)
    raise ValueError("option_type must be 'call' or 'put'")


# =============================================================================
# SCALAR VERSION (kept for reference/special cases)
# =============================================================================


def strategy_pnl(
    strategy: Strategy,
    chain: pd.DataFrame,
    spot: float,
    moves: np.ndarray,
    front_expiry: dt.date,
    back_expiry: dt.date,
    event_date: dt.date,
    front_iv: float,
    back_iv: float,
    slippage_pct: float,
    scenario: str,
) -> np.ndarray:
    """Compute P&L distribution for a strategy."""
    lookup = _build_lookup(chain)
    expiry_atm_iv = _expiry_atm_iv(chain, spot)
    entry_cost = _entry_cost(strategy, lookup, slippage_pct)

    pnls = []
    for move in moves:
        new_spot = spot * (1.0 + move)
        exit_value = _exit_value(
            strategy,
            lookup,
            new_spot,
            front_expiry,
            back_expiry,
            event_date,
            front_iv,
            back_iv,
            expiry_atm_iv,
            slippage_pct,
            scenario,
        )
        pnls.append(exit_value - entry_cost)
    return np.array(pnls)


def _build_lookup(chain: pd.DataFrame) -> dict[tuple, dict[str, float]]:
    lookup: dict[tuple, dict[str, float]] = {}
    for _, row in chain.iterrows():
        key = (row["expiry"].date(), row["option_type"], float(row["strike"]))
        lookup[key] = {
            "mid": float(row["mid"]),
            "spread": float(row["spread"]),
            "iv": float(row["impliedVolatility"]),
        }
    return lookup


def _entry_cost(
    strategy: Strategy,
    lookup: dict[tuple, dict[str, float]],
    slippage_pct: float,
) -> float:
    total = 0.0
    for leg in strategy.legs:
        data = _get_leg_data(lookup, leg)
        price = execution_price(
            data["mid"],
            data["spread"],
            leg.side,
            slippage_pct,
        )
        leg_value = price * leg.qty * CONTRACT_MULTIPLIER
        total += leg_value if leg.side == "buy" else -leg_value
    return total


def _exit_value(
    strategy: Strategy,
    lookup: dict[tuple, dict[str, float]],
    spot: float,
    front_expiry: dt.date,
    back_expiry: dt.date,
    event_date: dt.date,
    front_iv: float,
    back_iv: float,
    expiry_atm_iv: dict[dt.date, float],
    slippage_pct: float,
    scenario: str,
) -> float:
    total = 0.0
    for leg in strategy.legs:
        data = _get_leg_data(lookup, leg)
        if HOLD_TO_EXPIRY:
            price = _intrinsic(spot, leg.strike, leg.option_type)
        else:
            t_remaining = _time_remaining(event_date, leg.expiry.date())
            post_iv = _post_iv(
                leg.expiry.date(),
                front_expiry,
                back_expiry,
                scenario,
                front_iv,
                back_iv,
                data["iv"],
                expiry_atm_iv,
            )
            price = option_price(
                spot,
                leg.strike,
                t_remaining,
                RISK_FREE_RATE,
                DIVIDEND_YIELD,
                post_iv,
                leg.option_type,
            )
            exit_side = "sell" if leg.side == "buy" else "buy"
            price = execution_price(
                price,
                data["spread"],
                exit_side,
                slippage_pct,
            )

        leg_value = price * leg.qty * CONTRACT_MULTIPLIER
        total += leg_value if leg.side == "buy" else -leg_value
    return total


def _intrinsic(spot: float, strike: float, option_type: str) -> float:
    if option_type == "call":
        return max(spot - strike, 0.0)
    if option_type == "put":
        return max(strike - spot, 0.0)
    raise ValueError("option_type must be 'call' or 'put'")


def _time_remaining(event_date: dt.date, expiry: dt.date) -> float:
    business_days = pd.bdate_range(event_date, expiry).size
    return max((business_days - 1) / 252.0, TIME_EPSILON)


def _post_iv(
    expiry: dt.date,
    front_expiry: dt.date,
    back_expiry: dt.date,
    scenario: str,
    front_iv: float,
    back_iv: float,
    leg_iv: float,
    expiry_atm_iv: dict[dt.date, float],
) -> float:
    atm_iv = expiry_atm_iv.get(expiry, leg_iv)
    base_atm = front_iv if expiry == front_expiry else back_iv

    scenario_cfg = IV_SCENARIOS.get(scenario)
    if scenario_cfg is None:
        target_atm = base_atm
    else:
        side = "front" if expiry == front_expiry else "back"
        shift = scenario_cfg.get(side)
        if shift == "collapse_to_back":
            target_atm = back_iv
        elif shift == "unchanged" or shift is None:
            target_atm = base_atm
        else:
            target_atm = base_atm * (1 + float(shift))

    atm_iv = max(atm_iv, TIME_EPSILON)
    # Skew frozen: IV adjusted via proportional scaling relative to ATM only.
    # Post-event RR and BF are assumed unchanged (v3 spec section 4.5).
    # Do not add smile-level shift here without a spec change.
    return max(leg_iv * (target_atm / atm_iv), TIME_EPSILON)


def _expiry_atm_iv(chain: pd.DataFrame, spot: float) -> dict[dt.date, float]:
    output: dict[dt.date, float] = {}
    for expiry, subset in chain.groupby("expiry"):
        subset = subset.copy()
        subset["distance"] = (subset["strike"] - spot).abs()
        atm_strike = subset.sort_values("distance").iloc[0]["strike"]
        atm = subset[subset["strike"] == atm_strike]
        ivs = atm["impliedVolatility"].dropna()
        if not ivs.empty:
            output[expiry.date()] = float(ivs.mean())
    return output


def _get_leg_data(
    lookup: dict[tuple, dict[str, float]],
    leg,
) -> dict[str, float]:
    key = (leg.expiry.date(), leg.option_type, float(leg.strike))
    data = lookup.get(key)
    if data is None:
        raise ValueError(
            "Missing option data for leg: "
            f"{leg.option_type} {leg.strike} {leg.expiry.date()}"
        )
    return data
