"""
Black-Scholes-Merton option pricing with vectorized implementation.

Provides both scalar and vectorized versions of option pricing functions.
Vectorized versions use NumPy arrays for ~100x performance improvement
in Monte Carlo simulations.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import norm


def option_price(
    spot: float,
    strike: float,
    t: float,
    r: float,
    q: float,
    iv: float,
    option_type: str,
) -> float:
    """Calculate Black-Scholes-Merton option price (scalar version).
    
    Args:
        spot: Current underlying price
        strike: Option strike price
        t: Time to expiration (in years)
        r: Risk-free interest rate
        q: Dividend yield
        iv: Implied volatility
        option_type: 'call' or 'put'
    
    Returns:
        Option price
    """
    if t <= 0:
        if option_type == 'call':
            return max(spot - strike, 0.0)
        elif option_type == 'put':
            return max(strike - spot, 0.0)
        else:
            raise ValueError("option_type must be 'call' or 'put'")
    
    d1 = (np.log(spot / strike) + (r - q + 0.5 * iv ** 2) * t) / (iv * np.sqrt(t))
    d2 = d1 - iv * np.sqrt(t)
    
    if option_type == 'call':
        return spot * np.exp(-q * t) * norm.cdf(d1) - strike * np.exp(-r * t) * norm.cdf(d2)
    elif option_type == 'put':
        return strike * np.exp(-r * t) * norm.cdf(-d2) - spot * np.exp(-q * t) * norm.cdf(-d1)
    else:
        raise ValueError("option_type must be 'call' or 'put'")


def option_price_vec(
    spot_arr: np.ndarray,
    strike: float,
    t: float,
    r: float,
    q: float,
    iv: float,
    option_type: str,
) -> np.ndarray:
    """Vectorized Black-Scholes-Merton option pricing.
    
    Args:
        spot_arr: Array of spot prices (shape: (N,))
        strike: Option strike price (scalar)
        t: Time to expiration (in years, scalar)
        r: Risk-free interest rate (scalar)
        q: Dividend yield (scalar)
        iv: Implied volatility (scalar)
        option_type: 'call' or 'put'
    
    Returns:
        Array of option prices (shape: (N,))
    """
    spot_arr = np.asarray(spot_arr, dtype=np.float64)
    
    # Handle zero time to expiration
    if t <= 0:
        if option_type == 'call':
            return np.maximum(spot_arr - strike, 0.0)
        elif option_type == 'put':
            return np.maximum(strike - spot_arr, 0.0)
        else:
            raise ValueError("option_type must be 'call' or 'put'")
    
    # Vectorized BSM calculations
    sqrt_t = np.sqrt(t)
    d1 = (np.log(spot_arr / strike) + (r - q + 0.5 * iv ** 2) * t) / (iv * sqrt_t)
    d2 = d1 - iv * sqrt_t
    
    if option_type == 'call':
        return (
            spot_arr * np.exp(-q * t) * norm.cdf(d1) 
            - strike * np.exp(-r * t) * norm.cdf(d2)
        )
    elif option_type == 'put':
        return (
            strike * np.exp(-r * t) * norm.cdf(-d2) 
            - spot_arr * np.exp(-q * t) * norm.cdf(-d1)
        )
    else:
        raise ValueError("option_type must be 'call' or 'put'")


def delta(
    spot: float,
    strike: float,
    t: float,
    r: float,
    q: float,
    iv: float,
    option_type: str,
) -> float:
    """Calculate Black-Scholes-Merton option delta (scalar version).
    
    Args:
        spot: Current underlying price
        strike: Option strike price
        t: Time to expiration (in years)
        r: Risk-free interest rate
        q: Dividend yield
        iv: Implied volatility
        option_type: 'call' or 'put'
    
    Returns:
        Option delta
    """
    if t <= 0:
        if option_type == 'call':
            return 1.0 if spot > strike else 0.0
        elif option_type == 'put':
            return -1.0 if spot < strike else 0.0
        else:
            raise ValueError("option_type must be 'call' or 'put'")
    
    d1 = (np.log(spot / strike) + (r - q + 0.5 * iv ** 2) * t) / (iv * np.sqrt(t))
    
    if option_type == 'call':
        return np.exp(-q * t) * norm.cdf(d1)
    elif option_type == 'put':
        return -np.exp(-q * t) * norm.cdf(-d1)
    else:
        raise ValueError("option_type must be 'call' or 'put'")


def delta_vec(
    spot_arr: np.ndarray,
    strike: float,
    t: float,
    r: float,
    q: float,
    iv: float,
    option_type: str,
) -> np.ndarray:
    """Vectorized Black-Scholes-Merton option delta.
    
    Args:
        spot_arr: Array of spot prices (shape: (N,))
        strike: Option strike price (scalar)
        t: Time to expiration (in years, scalar)
        r: Risk-free interest rate (scalar)
        q: Dividend yield (scalar)
        iv: Implied volatility (scalar)
        option_type: 'call' or 'put'
    
    Returns:
        Array of option deltas (shape: (N,))
    """
    spot_arr = np.asarray(spot_arr, dtype=np.float64)
    
    # Handle zero time to expiration
    if t <= 0:
        if option_type == 'call':
            return np.where(spot_arr > strike, 1.0, 0.0)
        elif option_type == 'put':
            return np.where(spot_arr < strike, -1.0, 0.0)
        else:
            raise ValueError("option_type must be 'call' or 'put'")
    
    # Vectorized delta calculation
    sqrt_t = np.sqrt(t)
    d1 = (np.log(spot_arr / strike) + (r - q + 0.5 * iv ** 2) * t) / (iv * sqrt_t)
    
    if option_type == 'call':
        return np.exp(-q * t) * norm.cdf(d1)
    elif option_type == 'put':
        return -np.exp(-q * t) * norm.cdf(-d1)
    else:
        raise ValueError("option_type must be 'call' or 'put'")


def delta(
    spot: float,
    strike: float,
    t: float,
    r: float,
    q: float,
    iv: float,
    option_type: str,
) -> float:
    """Calculate Black-Scholes-Merton option delta (scalar version).
    
    Args:
        spot: Current underlying price
        strike: Option strike price
        t: Time to expiration (in years)
        r: Risk-free interest rate
        q: Dividend yield
        iv: Implied volatility
        option_type: 'call' or 'put'
    
    Returns:
        Option delta
    """
    if t <= 0:
        if option_type == 'call':
            return 1.0 if spot > strike else 0.0
        elif option_type == 'put':
            return -1.0 if spot < strike else 0.0
        else:
            raise ValueError("option_type must be 'call' or 'put'")
    
    d1 = (np.log(spot / strike) + (r - q + 0.5 * iv ** 2) * t) / (iv * np.sqrt(t))
    
    if option_type == 'call':
        return np.exp(-q * t) * norm.cdf(d1)
    elif option_type == 'put':
        return -np.exp(-q * t) * norm.cdf(-d1)
    else:
        raise ValueError("option_type must be 'call' or 'put'")


def gamma(
    spot: float,
    strike: float,
    t: float,
    r: float,
    q: float,
    iv: float,
    option_type: str,
) -> float:
    """Calculate Black-Scholes-Merton option gamma (scalar version).
    
    Args:
        spot: Current underlying price
        strike: Option strike price
        t: Time to expiration (in years)
        r: Risk-free interest rate
        q: Dividend yield
        iv: Implied volatility
        option_type: 'call' or 'put'
    
    Returns:
        Option gamma
    """
    if t <= 0:
        return 0.0
    
    d1 = (np.log(spot / strike) + (r - q + 0.5 * iv ** 2) * t) / (iv * np.sqrt(t))
    
    return np.exp(-q * t) * norm.pdf(d1) / (spot * iv * np.sqrt(t))


def gamma_vec(
    spot_arr: np.ndarray,
    strike: float,
    t: float,
    r: float,
    q: float,
    iv: float,
    option_type: str,
) -> np.ndarray:
    """Vectorized Black-Scholes-Merton option gamma.
    
    Args:
        spot_arr: Array of spot prices (shape: (N,))
        strike: Option strike price (scalar)
        t: Time to expiration (in years, scalar)
        r: Risk-free interest rate (scalar)
        q: Dividend yield (scalar)
        iv: Implied volatility (scalar)
        option_type: 'call' or 'put'
    
    Returns:
        Array of option gammas (shape: (N,))
    """
    spot_arr = np.asarray(spot_arr, dtype=np.float64)
    
    # Handle zero time to expiration
    if t <= 0:
        return np.zeros_like(spot_arr)
    
    # Vectorized gamma calculation
    sqrt_t = np.sqrt(t)
    d1 = (np.log(spot_arr / strike) + (r - q + 0.5 * iv ** 2) * t) / (iv * sqrt_t)
    
    return np.exp(-q * t) * norm.pdf(d1) / (spot_arr * iv * sqrt_t)