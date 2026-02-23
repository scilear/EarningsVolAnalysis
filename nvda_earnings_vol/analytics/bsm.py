"""Black-Scholes-Merton pricing and Greeks."""

from __future__ import annotations

import math

from scipy.stats import norm


def _d1(
    spot: float,
    strike: float,
    t: float,
    r: float,
    q: float,
    vol: float,
) -> float:
    if t <= 0 or vol <= 0:
        return 0.0
    numerator = math.log(spot / strike) + (r - q + 0.5 * vol**2) * t
    return numerator / (vol * math.sqrt(t))


def _d2(
    spot: float,
    strike: float,
    t: float,
    r: float,
    q: float,
    vol: float,
) -> float:
    if t <= 0:
        return 0.0
    return _d1(spot, strike, t, r, q, vol) - vol * math.sqrt(t)


def option_price(
    spot: float,
    strike: float,
    t: float,
    r: float,
    q: float,
    vol: float,
    option_type: str,
) -> float:
    """Return BSM option price for call or put."""
    if t <= 0:
        if option_type == "call":
            return max(spot - strike, 0.0)
        if option_type == "put":
            return max(strike - spot, 0.0)
        raise ValueError("option_type must be 'call' or 'put'")

    d1 = _d1(spot, strike, t, r, q, vol)
    d2 = _d2(spot, strike, t, r, q, vol)

    if option_type == "call":
        discounted_spot = math.exp(-q * t) * spot
        discounted_strike = math.exp(-r * t) * strike
        value = (
            discounted_spot * norm.cdf(d1)
            - discounted_strike * norm.cdf(d2)
        )
        return value
    if option_type == "put":
        discounted_spot = math.exp(-q * t) * spot
        discounted_strike = math.exp(-r * t) * strike
        value = (
            discounted_strike * norm.cdf(-d2)
            - discounted_spot * norm.cdf(-d1)
        )
        return value
    raise ValueError("option_type must be 'call' or 'put'")


def option_delta(
    spot: float,
    strike: float,
    t: float,
    r: float,
    q: float,
    vol: float,
    option_type: str,
) -> float:
    """Return BSM delta for call or put."""
    if t <= 0:
        if option_type == "call":
            return 1.0 if spot > strike else 0.0
        if option_type == "put":
            return -1.0 if spot < strike else 0.0
        raise ValueError("option_type must be 'call' or 'put'")

    d1 = _d1(spot, strike, t, r, q, vol)
    if option_type == "call":
        return math.exp(-q * t) * norm.cdf(d1)
    if option_type == "put":
        return math.exp(-q * t) * (norm.cdf(d1) - 1.0)
    raise ValueError("option_type must be 'call' or 'put'")


def option_gamma(
    spot: float,
    strike: float,
    t: float,
    r: float,
    q: float,
    vol: float,
) -> float:
    """Return BSM gamma."""
    if t <= 0 or vol <= 0:
        return 0.0
    d1 = _d1(spot, strike, t, r, q, vol)
    return (math.exp(-q * t) * norm.pdf(d1)) / (spot * vol * math.sqrt(t))
