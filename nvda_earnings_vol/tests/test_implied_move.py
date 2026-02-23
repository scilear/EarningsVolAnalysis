"""Tests for implied move calculation."""

import pandas as pd

from nvda_earnings_vol.analytics.implied_move import implied_move_from_chain


def test_implied_move_atm_straddle() -> None:
    chain = pd.DataFrame(
        {
            "strike": [100.0, 100.0],
            "option_type": ["call", "put"],
            "mid": [5.0, 4.0],
            "spread": [1.0, 1.0],
        }
    )
    implied = implied_move_from_chain(chain, 100.0, 0.10)
    assert abs(implied - 0.091) < 1e-6
