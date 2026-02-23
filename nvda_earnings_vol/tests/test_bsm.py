"""Tests for BSM pricing."""

from nvda_earnings_vol.analytics.bsm import option_price


def test_bsm_call_put_parity_atm() -> None:
    spot = 100.0
    strike = 100.0
    t = 0.5
    r = 0.01
    q = 0.0
    vol = 0.2
    call = option_price(spot, strike, t, r, q, vol, "call")
    put = option_price(spot, strike, t, r, q, vol, "put")
    parity = call - put
    assert abs(parity - (spot - strike * (1 + r * t))) < 2.0
