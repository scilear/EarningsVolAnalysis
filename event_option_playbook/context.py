"""Market-context domain objects for event options playbooks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LiquidityProfile:
    """Compact liquidity summary for a candidate event setup."""

    min_open_interest: int
    max_spread_pct: float
    atm_width_pct: float | None = None

    def __post_init__(self) -> None:
        if self.min_open_interest < 0:
            raise ValueError("min_open_interest must be non-negative.")
        if self.max_spread_pct < 0:
            raise ValueError("max_spread_pct must be non-negative.")


@dataclass(frozen=True)
class MarketContext:
    """Minimal reusable market-context snapshot for playbook selection."""

    spot: float
    implied_move: float
    historical_p75: float
    front_iv: float
    back_iv: float
    event_vol_ratio: float
    iv_ratio: float
    skew_rr25: float | None = None
    skew_bf25: float | None = None
    net_gex: float | None = None
    abs_gex: float | None = None
    gamma_flip: float | None = None
    liquidity: LiquidityProfile | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "spot",
            "implied_move",
            "historical_p75",
            "front_iv",
            "back_iv",
            "event_vol_ratio",
            "iv_ratio",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be non-negative.")

    @property
    def implied_vs_history_ratio(self) -> float:
        """Relative pricing of implied move versus historical event move."""

        if self.historical_p75 == 0:
            return 0.0
        return self.implied_move / self.historical_p75

    def to_dict(self) -> dict[str, float | None | dict[str, float | int | None]]:
        """Serialize the market context for reporting or storage."""

        return {
            "spot": self.spot,
            "implied_move": self.implied_move,
            "historical_p75": self.historical_p75,
            "front_iv": self.front_iv,
            "back_iv": self.back_iv,
            "event_vol_ratio": self.event_vol_ratio,
            "iv_ratio": self.iv_ratio,
            "skew_rr25": self.skew_rr25,
            "skew_bf25": self.skew_bf25,
            "net_gex": self.net_gex,
            "abs_gex": self.abs_gex,
            "gamma_flip": self.gamma_flip,
            "implied_vs_history_ratio": self.implied_vs_history_ratio,
            "liquidity": None if self.liquidity is None else {
                "min_open_interest": self.liquidity.min_open_interest,
                "max_spread_pct": self.liquidity.max_spread_pct,
                "atm_width_pct": self.liquidity.atm_width_pct,
            },
        }
