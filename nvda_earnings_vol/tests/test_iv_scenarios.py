"""Tests for IV scenario configuration and runtime paths."""

import datetime as dt

from nvda_earnings_vol.config import IV_SCENARIOS
from nvda_earnings_vol.strategies.payoff import _post_iv


def test_iv_scenarios_config() -> None:
    for name, cfg in IV_SCENARIOS.items():
        assert isinstance(cfg, dict), f"{name} must be a dict"
        assert "front" in cfg and "back" in cfg, (
            f"{name} missing front/back keys"
        )


def test_post_iv_runtime_path() -> None:
    front_expiry = dt.date(2026, 3, 21)
    back_expiry = dt.date(2026, 4, 18)

    for scenario in IV_SCENARIOS:
        result_front = _post_iv(
            expiry=front_expiry,
            front_expiry=front_expiry,
            back_expiry=back_expiry,
            scenario=scenario,
            front_iv=0.80,
            back_iv=0.50,
            leg_iv=0.82,
            expiry_atm_iv={front_expiry: 0.80},
        )
        assert result_front > 0.0

        result_back = _post_iv(
            expiry=back_expiry,
            front_expiry=front_expiry,
            back_expiry=back_expiry,
            scenario=scenario,
            front_iv=0.80,
            back_iv=0.50,
            leg_iv=0.51,
            expiry_atm_iv={back_expiry: 0.50},
        )
        assert result_back > 0.0
