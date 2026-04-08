"""Compatibility bridge from the legacy earnings engine to generic domain objects."""

from __future__ import annotations

import datetime as dt
from typing import Any

from event_option_playbook.context import LiquidityProfile, MarketContext
from event_option_playbook.events import EventFamily, EventSchedule, EventSpec
from event_option_playbook.playbook import (
    PlaybookCandidate,
    PlaybookRecommendation,
    PlaybookRiskNote,
)


def snapshot_to_event_spec(
    ticker: str,
    snapshot: dict[str, Any],
    *,
    family: EventFamily = EventFamily.EARNINGS,
    event_name: str | None = None,
    proxy_symbol: str | None = None,
) -> EventSpec:
    """Convert a legacy snapshot into a generic event specification."""

    event_date = _coerce_date(_require(snapshot, "event_date"))
    return EventSpec(
        family=family,
        name=event_name or _default_event_name(family, ticker, event_date),
        underlying=ticker.upper(),
        schedule=EventSchedule(
            event_date=event_date,
            event_time_label=snapshot.get("event_time_label"),
        ),
        proxy_symbol=proxy_symbol,
        notes=(
            "Bridged from nvda_earnings_vol legacy snapshot. "
            "Event identity remains earnings-oriented until a generic event loader is added."
        ),
    )


def snapshot_to_market_context(snapshot: dict[str, Any]) -> MarketContext:
    """Convert a legacy snapshot into a generic market-context object."""

    required = (
        "spot",
        "implied_move",
        "historical_p75",
        "front_iv",
        "back_iv",
        "event_vol_ratio",
        "iv_ratio",
    )
    values = {key: float(_require(snapshot, key)) for key in required}
    liquidity = None
    if any(key in snapshot for key in ("min_oi", "max_spread_pct", "atm_width_pct")):
        liquidity = LiquidityProfile(
            min_open_interest=int(snapshot.get("min_oi", 0)),
            max_spread_pct=float(snapshot.get("max_spread_pct", 0.0)),
            atm_width_pct=_optional_float(snapshot.get("atm_width_pct")),
        )

    return MarketContext(
        spot=values["spot"],
        implied_move=values["implied_move"],
        historical_p75=values["historical_p75"],
        front_iv=values["front_iv"],
        back_iv=values["back_iv"],
        event_vol_ratio=values["event_vol_ratio"],
        iv_ratio=values["iv_ratio"],
        skew_rr25=_optional_float(snapshot.get("rr25")),
        skew_bf25=_optional_float(snapshot.get("bf25")),
        net_gex=_optional_float(snapshot.get("gex_net")),
        abs_gex=_optional_float(snapshot.get("gex_abs")),
        gamma_flip=_optional_float(snapshot.get("gamma_flip")),
        liquidity=liquidity,
    )


def ranked_results_to_candidates(
    ranked: list[dict[str, Any]],
    *,
    rationale_map: dict[str, str] | None = None,
    top_n: int = 3,
) -> list[PlaybookCandidate]:
    """Convert ranked legacy strategy rows into generic playbook candidates."""

    candidates: list[PlaybookCandidate] = []
    for row in ranked[:top_n]:
        strategy_name = str(_require(row, "strategy")).upper()
        candidates.append(
            PlaybookCandidate(
                structure_name=strategy_name,
                thesis=_thesis_from_strategy(strategy_name, rationale_map),
                expected_edge=_expected_edge_from_row(row),
                entry_timing=_entry_timing_from_legs(row.get("legs", [])),
                max_risk=_max_risk_from_row(row),
                score=_optional_float(row.get("score")),
            )
        )
    return candidates


def build_playbook_recommendation(
    event_spec: EventSpec,
    market_context: MarketContext,
    ranked: list[dict[str, Any]],
    *,
    rationale_map: dict[str, str] | None = None,
    top_n: int = 3,
    regime: dict[str, Any] | None = None,
    not_applicable: list[dict[str, Any]] | None = None,
) -> PlaybookRecommendation:
    """Create a generic playbook recommendation from legacy engine outputs."""

    if not ranked:
        return PlaybookRecommendation(
            event_key=event_spec.key,
            no_trade_reason="No viable structures were produced by the legacy strategy engine.",
            risk_notes=_base_risk_notes(market_context, regime=regime, not_applicable=not_applicable),
        )

    return PlaybookRecommendation(
        event_key=event_spec.key,
        recommended=ranked_results_to_candidates(
            ranked,
            rationale_map=rationale_map,
            top_n=top_n,
        ),
        risk_notes=_base_risk_notes(
            market_context,
            ranked=ranked,
            regime=regime,
            not_applicable=not_applicable,
        ),
        key_levels=_key_levels_from_context(market_context),
        management_rules=_management_rules_from_context(market_context, ranked[0], regime=regime),
    )


def _base_risk_notes(
    market_context: MarketContext,
    *,
    ranked: list[dict[str, Any]] | None = None,
    regime: dict[str, Any] | None = None,
    not_applicable: list[dict[str, Any]] | None = None,
) -> list[PlaybookRiskNote]:
    notes: list[PlaybookRiskNote] = []
    if market_context.implied_vs_history_ratio > 1.1:
        notes.append(
            PlaybookRiskNote(
                category="expensive_event_premium",
                detail="Implied move is rich versus historical event distribution.",
                mitigation="Favor defined-risk structures or require stronger directional edge.",
            )
        )
    if market_context.implied_vs_history_ratio < 0.85:
        notes.append(
            PlaybookRiskNote(
                category="underpriced_tail",
                detail="Implied move screens cheap versus historical event behavior.",
                mitigation="Keep convex exposure if follow-through and liquidity remain intact.",
            )
        )
    if market_context.gamma_flip is not None:
        notes.append(
            PlaybookRiskNote(
                category="gamma_flip",
                detail=f"Dealer gamma flip is estimated near {market_context.gamma_flip:.2f}.",
                mitigation="Monitor price behavior around the flip level for acceleration or pinning.",
            )
        )
    if ranked:
        top = ranked[0]
        if top.get("undefined_risk"):
            notes.append(
                PlaybookRiskNote(
                    category="undefined_risk",
                    detail="Top-ranked structure contains uncovered short optionality.",
                    mitigation="Down-rank for production use or add a covering hedge before execution.",
                )
            )
    if regime and regime.get("composite_regime"):
        notes.append(
            PlaybookRiskNote(
                category="regime",
                detail=f"Detected setup: {regime['composite_regime']}.",
                mitigation="Use the regime as a filter, not as a substitute for price confirmation.",
            )
        )
    if not_applicable:
        blocked = ", ".join(str(item["name"]) for item in not_applicable[:3] if "name" in item)
        if blocked:
            notes.append(
                PlaybookRiskNote(
                    category="blocked_structures",
                    detail=f"Some structures were explicitly excluded: {blocked}.",
                    mitigation="Treat exclusions as evidence about regime or surface quality, not just missing features.",
                )
            )
    return notes


def _key_levels_from_context(market_context: MarketContext) -> list[str]:
    levels: list[str] = []
    if market_context.gamma_flip is not None:
        levels.append(f"Gamma flip: {market_context.gamma_flip:.2f}")
    return levels


def _management_rules_from_context(
    market_context: MarketContext,
    top_row: dict[str, Any],
    *,
    regime: dict[str, Any] | None = None,
) -> list[str]:
    rules = [
        "Reduce or exit if the opening move stalls and premium decay overtakes realized movement.",
        "Reassess if bid-ask spreads widen materially beyond the pre-trade liquidity profile.",
    ]
    if market_context.gamma_flip is not None:
        rules.append("Watch for acceleration or pin behavior as spot approaches the gamma-flip level.")
    if top_row.get("undefined_risk"):
        rules.append("Do not leave uncovered short optionality unmanaged through the catalyst.")
    if regime and regime.get("gamma_regime") == "Pin Risk Regime":
        rules.append("If spot compresses into the event, take profits faster on short-vol exposure.")
    return rules


def _thesis_from_strategy(
    strategy_name: str,
    rationale_map: dict[str, str] | None,
) -> str:
    if rationale_map and strategy_name in rationale_map:
        return rationale_map[strategy_name]
    defaults = {
        "LONG_CALL": "Directional upside expression around the event.",
        "LONG_PUT": "Directional downside expression around the event.",
        "LONG_STRADDLE": "Two-sided convex expression for a large move.",
        "LONG_STRANGLE": "Lower-cost two-sided convex expression for an outsized move.",
        "CALL_SPREAD": "Defined-risk upside expression with capped payoff.",
        "PUT_SPREAD": "Defined-risk downside expression with capped payoff.",
        "IRON_CONDOR": "Premium-harvest expression when realized move is expected to stay contained.",
        "CALENDAR": "Term-structure expression targeting event-vol compression.",
        "CALL_BACKSPREAD": "Convex upside expression funded partly by rich front volatility.",
        "PUT_BACKSPREAD": "Convex downside expression funded partly by rich front volatility.",
    }
    return defaults.get(strategy_name, "Legacy strategy bridged into generic playbook format.")


def _expected_edge_from_row(row: dict[str, Any]) -> str:
    drivers: list[str] = []
    if _optional_float(row.get("ev")) not in (None, 0.0):
        drivers.append(f"positive EV {float(row['ev']):.2f}")
    if _optional_float(row.get("convexity")) not in (None, 0.0):
        drivers.append(f"convexity {float(row['convexity']):.2f}")
    risk_classification = row.get("risk_classification")
    if risk_classification == "defined_risk":
        drivers.append("defined risk")
    elif risk_classification == "undefined_risk":
        drivers.append("higher unmanaged tail risk")
    score = _optional_float(row.get("score"))
    if score is not None:
        drivers.append(f"composite score {score:.3f}")
    return ", ".join(drivers) if drivers else "Legacy strategy ranked without explicit edge decomposition."


def _entry_timing_from_legs(legs: list[dict[str, Any]]) -> str:
    expiries = sorted({str(leg.get("expiry")) for leg in legs if leg.get("expiry")})
    if not expiries:
        return "legacy_runtime_unknown"
    if len(expiries) == 1:
        return f"pre_event_single_expiry:{expiries[0]}"
    return f"pre_event_multi_expiry:{'/'.join(expiries)}"


def _max_risk_from_row(row: dict[str, Any]) -> str:
    if row.get("risk_classification") == "undefined_risk":
        return "Undefined tail risk in current legacy classification."
    max_loss = _optional_float(row.get("max_loss"))
    capital_required = _optional_float(row.get("capital_required"))
    if max_loss is not None:
        return f"Estimated max loss {abs(max_loss):.2f}"
    if capital_required is not None:
        return f"Estimated capital required {capital_required:.2f}"
    return "Defined-risk estimate unavailable in legacy output."


def _default_event_name(
    family: EventFamily,
    ticker: str,
    event_date: dt.date,
) -> str:
    if family == EventFamily.EARNINGS:
        return f"{ticker.lower()}_earnings_{event_date.isoformat()}"
    return f"{ticker.lower()}_{family.value}_{event_date.isoformat()}"


def _require(payload: dict[str, Any], key: str) -> Any:
    if key not in payload:
        raise KeyError(f"Missing required snapshot field: '{key}'")
    return payload[key]


def _coerce_date(value: Any) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if hasattr(value, "date"):
        return value.date()
    if isinstance(value, str):
        return dt.date.fromisoformat(value)
    raise TypeError(f"Unsupported event_date value: {value!r}")


def _optional_float(value: Any) -> float | None:
    if value in (None, "N/A", ""):
        return None
    return float(value)
