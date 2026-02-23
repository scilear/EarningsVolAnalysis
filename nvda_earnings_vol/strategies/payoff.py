"""Strategy pricing and payoff logic."""

from __future__ import annotations

import datetime as dt
from typing import Iterable

import numpy as np
import pandas as pd

from nvda_earnings_vol.analytics.bsm import option_price
from nvda_earnings_vol.config import (
    CONTRACT_MULTIPLIER,
    DIVIDEND_YIELD,
    HOLD_TO_EXPIRY,
    IV_SCENARIOS,
    RISK_FREE_RATE,
    TIME_EPSILON,
)
from nvda_earnings_vol.data.filters import execution_price
from nvda_earnings_vol.strategies.structures import Strategy


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
    strategy: Strategy, lookup: dict[tuple, dict[str, float]], slippage_pct: float
) -> float:
    total = 0.0
    for leg in strategy.legs:
        key = (leg.expiry.date(), leg.option_type, float(leg.strike))
        data = _get_leg_data(lookup, leg)
        price = execution_price(data["mid"], data["spread"], leg.side, slippage_pct)
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
        key = (leg.expiry.date(), leg.option_type, float(leg.strike))
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
            price = execution_price(price, data["spread"], exit_side, slippage_pct)

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
    business_days = pd.bdate_range(event_date, expiry).size - 1
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
    elif scenario_cfg.get("front") == "collapse_to_back":
        target_atm = back_iv
    else:
        shift = (
            float(scenario_cfg["front"])
            if expiry == front_expiry
            else float(scenario_cfg["back"])
        )
        target_atm = base_atm * (1 + shift)

    if atm_iv <= 0:
        return max(target_atm, TIME_EPSILON)
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


def _get_leg_data(lookup: dict[tuple, dict[str, float]], leg) -> dict[str, float]:
    key = (leg.expiry.date(), leg.option_type, float(leg.strike))
    data = lookup.get(key)
    if data is None:
        raise ValueError(
            "Missing option data for leg: "
            f"{leg.option_type} {leg.strike} {leg.expiry.date()}"
        )
    return data
