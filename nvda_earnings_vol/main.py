"""CLI entrypoint for NVDA earnings volatility analysis."""

from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from nvda_earnings_vol import config
from nvda_earnings_vol.alignment import compute_all_alignments
from nvda_earnings_vol.analytics.bsm import (
    delta as bsm_delta,
    gamma as bsm_gamma,
    vega as bsm_vega,
    theta as bsm_theta,
)
from nvda_earnings_vol.analytics.event_vol import event_variance
from nvda_earnings_vol.analytics.gamma import gex_summary
from nvda_earnings_vol.analytics.historical import (
    compute_distribution_shape,
    earnings_move_p75,
    extract_earnings_moves,
)
from nvda_earnings_vol.analytics.implied_move import implied_move_from_chain
from nvda_earnings_vol.analytics.skew import skew_metrics
from nvda_earnings_vol.data.filters import (
    filter_by_liquidity,
    filter_by_moneyness,
)
from nvda_earnings_vol.data.loader import (
    get_earnings_dates,
    get_expiries_after,
    get_next_earnings_date,
    get_option_expiries,
    get_options_chain,
    get_price_history,
    get_spot_price,
)
from nvda_earnings_vol.data.test_data import (
    generate_test_data_set,
    list_available_scenarios,
    load_test_data,
    save_test_data,
)
from nvda_earnings_vol.regime import classify_regime
from nvda_earnings_vol.reports.reporter import write_report
from nvda_earnings_vol.simulation.monte_carlo import simulate_moves
from nvda_earnings_vol.strategies.backspreads import (
    build_call_backspread,
    build_put_backspread,
)
from nvda_earnings_vol.strategies.payoff import strategy_pnl_vec
from nvda_earnings_vol.strategies.post_event_calendar import (
    build_post_event_calendar,
    compute_post_event_calendar_scenarios,
)
from nvda_earnings_vol.strategies.registry import should_build_strategy
from nvda_earnings_vol.strategies.scoring import (
    compute_metrics,
    score_strategies,
)
from nvda_earnings_vol.strategies.structures import build_strategies
from nvda_earnings_vol.utils import business_days
from nvda_earnings_vol.viz.plots import (
    plot_move_comparison,
    plot_pnl_distribution,
)


LOGGER = logging.getLogger(__name__)

STRATEGY_RATIONALE: dict[str, str] = {
    "LONG_CALL": (
        "Directional bet on an upside move. Profits when the stock rallies "
        "beyond strike + premium paid. Maximum loss = premium. Best when "
        "implied vol is cheap relative to the expected earnings move."
    ),
    "LONG_PUT": (
        "Directional bet on a downside move. Profits when the stock drops "
        "below strike − premium paid. Maximum loss = premium. Best when "
        "implied vol is cheap and a sharp decline is expected."
    ),
    "LONG_STRADDLE": (
        "Pure long-volatility bet. Profits from a large move in either "
        "direction; break-evens at strike ± total premium. Best when "
        "implied move underprices the expected earnings reaction, "
        "regardless of direction."
    ),
    "LONG_STRANGLE": (
        "Lower-cost long-vol bet using OTM options. Wider break-evens "
        "than a straddle but cheaper entry. Best when a very large move "
        "is expected but direction is uncertain."
    ),
    "CALL_SPREAD": (
        "Debit spread with capped upside. Reduces premium outlay vs a "
        "naked call while maintaining a bullish directional view. Best in "
        "mildly-to-moderately bullish scenarios with moderate vol."
    ),
    "PUT_SPREAD": (
        "Debit spread with capped downside. Reduces premium outlay vs a "
        "naked put while maintaining a bearish directional view. Best in "
        "mildly-to-moderately bearish scenarios."
    ),
    "IRON_CONDOR": (
        "Short-vol structure. Collects premium by selling OTM strangles "
        "and buying wings for protection. Profits when the stock stays "
        "inside the break-even range. Best when vol is expensive relative "
        "to expected move and a muted earnings reaction is likely."
    ),
    "CALENDAR": (
        "Long time-value, short event vol. Sells near-term vol (expensive "
        "pre-earnings) and buys post-event vol (relatively cheaper). "
        "Profits from front vol crush after earnings while retaining "
        "back-month optionality. Defined risk = net debit."
    ),
    "CALL_BACKSPREAD": (
        "Convex upside structure: sell 1 near-ATM call, buy 2 OTM calls. "
        "Profits asymmetrically from a large rally. Entry gate requires "
        "significantly elevated front IV (ratio ≥ 1.40) so the short leg "
        "funds the two longs, creating a near-zero or credit entry. "
        "Risk: capped loss in the middle zone between the strikes."
    ),
    "PUT_BACKSPREAD": (
        "Convex downside structure: sell 1 near-ATM put, buy 2 OTM puts. "
        "Profits asymmetrically from a sharp decline. Same entry gate as "
        "call backspread. Risk: capped loss in the middle zone between "
        "the short and long strikes."
    ),
}


def _build_chain_lookup(
    chain: pd.DataFrame,
) -> dict[tuple, dict[str, float]]:
    """Build (expiry_date, option_type, strike) → {mid, iv} lookup."""
    lookup: dict[tuple, dict[str, float]] = {}
    for _, row in chain.iterrows():
        key = (row["expiry"].date(), row["option_type"], float(row["strike"]))
        lookup[key] = {
            "mid": float(row["mid"]),
            "iv": float(row["impliedVolatility"]),
        }
    return lookup


def _enrich_legs_with_greeks(
    legs: list[dict],
    lookup: dict[tuple, dict[str, float]],
    spot: float,
    t_front: float,
    t_back1: float,
    front_expiry: dt.date,
    front_iv: float,
    back_iv: float,
) -> dict[str, float]:
    """Compute per-leg BSM Greeks and inject into leg dicts.

    Returns net Greeks dict summed over all legs.
    """
    r = config.RISK_FREE_RATE
    q = config.DIVIDEND_YIELD
    net: dict[str, float] = {
        "delta": 0.0,
        "gamma": 0.0,
        "vega": 0.0,
        "theta": 0.0,
    }
    for leg in legs:
        leg_expiry = dt.date.fromisoformat(leg["expiry"])
        is_front = leg_expiry == front_expiry
        t = t_front if is_front else t_back1
        key = (leg_expiry, leg["option_type"], float(leg["strike"]))
        chain_data = lookup.get(key)
        iv = (
            chain_data["iv"]
            if chain_data
            else (front_iv if is_front else back_iv)
        )
        leg["iv"] = iv

        d = bsm_delta(
            spot, leg["strike"], t, r, q, iv, leg["option_type"]
        )
        g = bsm_gamma(
            spot, leg["strike"], t, r, q, iv, leg["option_type"]
        )
        v = bsm_vega(
            spot, leg["strike"], t, r, q, iv, leg["option_type"]
        )
        th = bsm_theta(
            spot, leg["strike"], t, r, q, iv, leg["option_type"]
        )
        leg["delta"] = d
        leg["gamma"] = g
        leg["vega"] = v
        leg["theta"] = th

        sign = 1.0 if leg["side"] == "BUY" else -1.0
        qty = leg["qty"] * sign
        net["delta"] += qty * d
        net["gamma"] += qty * g
        net["vega"] += qty * v
        net["theta"] += qty * th
    return net


def _not_applicable_reason(name: str, snapshot: dict) -> str:
    """Return a human-readable reason why a conditional strategy was skipped.
    """
    if name in ("CALL_BACKSPREAD", "PUT_BACKSPREAD"):
        reasons = []
        iv_ratio = snapshot.get("iv_ratio", 0.0)
        if iv_ratio < config.BACKSPREAD_MIN_IV_RATIO:
            reasons.append(
                f"IV ratio {iv_ratio:.2f} < "
                f"{config.BACKSPREAD_MIN_IV_RATIO} required"
            )
        evr = snapshot.get("event_variance_ratio", 0.0)
        if evr < config.BACKSPREAD_MIN_EVENT_VAR_RATIO:
            reasons.append(
                f"event var ratio {evr:.2f} < "
                f"{config.BACKSPREAD_MIN_EVENT_VAR_RATIO} required"
            )
        im = snapshot.get("implied_move", 0.0)
        p75 = snapshot.get("historical_p75", 0.0)
        if im > p75 * config.BACKSPREAD_MAX_IMPLIED_OVER_P75:
            reasons.append(
                f"implied move {im:.3f} > "
                f"P75×{config.BACKSPREAD_MAX_IMPLIED_OVER_P75} "
                f"(overpriced)"
            )
        sd = snapshot.get("short_delta", 0.0)
        if sd < config.BACKSPREAD_MIN_SHORT_DELTA:
            reasons.append(
                f"short delta {sd:.3f} < "
                f"{config.BACKSPREAD_MIN_SHORT_DELTA} required"
            )
        dte = snapshot.get("back_dte", 0)
        if not (
            config.BACKSPREAD_LONG_DTE_MIN
            <= dte
            <= config.BACKSPREAD_LONG_DTE_MAX
        ):
            reasons.append(
                f"back DTE {dte}d outside "
                f"[{config.BACKSPREAD_LONG_DTE_MIN}, "
                f"{config.BACKSPREAD_LONG_DTE_MAX}]"
            )
        return "; ".join(reasons) if reasons else "Conditions not met"
    if name == "POST_EVENT_CALENDAR":
        days = snapshot.get("days_after_event", 0)
        if days == 0:
            return (
                "Entry requires 1–3 days after earnings event "
                "(currently pre-event)"
            )
        return (
            f"{days}d after event exceeds the 3-day entry window"
        )
    return "Entry conditions not met"


def main() -> None:
    """Run earnings vol analysis pipeline."""
    parser = argparse.ArgumentParser(description="NVDA earnings vol analysis")
    parser.add_argument("--event-date", type=str, help="YYYY-MM-DD")
    parser.add_argument(
        "--output",
        type=str,
        default="reports/nvda_earnings_report.html",
        help="Output HTML report path",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default="data/cache",
        help="Directory for cached option chains",
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Use cached option chains when available",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Force refresh of cached option chains",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for Monte Carlo reproducibility",
    )
    parser.add_argument(
        "--test-data",
        action="store_true",
        help="Use synthetic test data instead of live market data",
    )
    parser.add_argument(
        "--test-scenario",
        type=str,
        default="baseline",
        choices=list_available_scenarios(),
        help="Test data scenario to use (only with --test-data)",
    )
    parser.add_argument(
        "--test-data-dir",
        type=str,
        default=None,
        help="Load test data from directory (instead of generating)",
    )
    parser.add_argument(
        "--save-test-data",
        type=str,
        default=None,
        help="Save generated test data to specified directory",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # Branch: test data vs live data
    if args.test_data:
        test_data = _load_test_data_mode(args)
        spot = test_data["spot"]
        event_date = test_data["event_date"]
        front_expiry = test_data["front_expiry"]
        back1_expiry = test_data["back_expiry"]
        back2_expiry = None  # Test data doesn't include back2
        front_chain = _filter_chain_for_test(test_data["front_chain"], spot)
        back1_chain = _filter_chain_for_test(test_data["back_chain"], spot)
        back2_chain = None
        history = test_data["history"]
        earnings_dates = test_data["earnings_dates"]
        LOGGER.info(
            "Test data loaded: spot=%.2f, event=%s, front_exp=%s, back_exp=%s",
            spot,
            event_date,
            front_expiry,
            back1_expiry,
        )
    else:
        # Live data mode (existing logic)
        event_date = _parse_event_date(args.event_date)
        if event_date is None:
            event_date = get_next_earnings_date(config.TICKER)
        if event_date is None:
            raise ValueError(
                "Event date not provided and could not "
                "be fetched."
            )
        event_date = _normalize_event_date(event_date)
        # Allow past event dates for test mode, but require future for live
        if not args.test_data and event_date <= dt.date.today():
            LOGGER.warning(
                "Event date %s is not in the future. "
                "Proceeding anyway for testing.",
                event_date,
            )

        try:
            spot = get_spot_price(config.TICKER)
            expiries = get_option_expiries(config.TICKER)
            post_event = get_expiries_after(expiries, event_date)
            if len(post_event) < 2:
                raise ValueError("Insufficient expiries after event date.")

            front_expiry = post_event[0]
            _validate_front_expiry(event_date, front_expiry)
            back1_expiry = post_event[1]
            back2_expiry = post_event[2] if len(post_event) > 2 else None

            cache_dir = Path(args.cache_dir)
            front_chain = _load_filtered_chain(
                front_expiry,
                spot,
                cache_dir,
                args.use_cache,
                args.refresh_cache,
            )
            back1_chain = _load_filtered_chain(
                back1_expiry,
                spot,
                cache_dir,
                args.use_cache,
                args.refresh_cache,
            )
            back2_chain = (
                _load_filtered_chain(
                    back2_expiry,
                    spot,
                    cache_dir,
                    args.use_cache,
                    args.refresh_cache,
                    allow_empty=True,
                )
                if back2_expiry
                else None
            )
            if back2_chain is None:
                back2_expiry = None
        except ValueError as exc:
            message = str(exc)
            if "market appears closed" in message.lower():
                LOGGER.error(
                    "Market appears closed or data unavailable; exiting (%s)",
                    exc,
                )
            else:
                LOGGER.error("%s", exc)
            return

        try:
            history = get_price_history(config.TICKER, config.HISTORY_YEARS)
            earnings_dates = get_earnings_dates(config.TICKER)
        except ValueError as exc:
            LOGGER.error("%s", exc)
            return

    # Compute implied move and historical stats (common to both modes)
    try:
        implied_move = implied_move_from_chain(
            front_chain,
            spot,
            config.SLIPPAGE_PCT,
        )
        hist_p75 = earnings_move_p75(history, earnings_dates)
    except ValueError as exc:
        LOGGER.error("%s", exc)
        return

    # Extract historical distribution shape
    signed_moves = extract_earnings_moves(history, earnings_dates)
    dist_shape = compute_distribution_shape(signed_moves)

    event_info = event_variance(
        front_chain,
        back1_chain,
        back2_chain,
        spot,
        event_date,
        front_expiry,
        back1_expiry,
        back2_expiry,
    )

    front_iv = (
        float(event_info["front_iv"])
        if event_info["front_iv"] is not None
        else 0.0
    )
    back_iv = (
        float(event_info["back_iv"])
        if event_info["back_iv"] is not None
        else 0.0
    )
    back2_iv = event_info.get("back2_iv")
    event_vol = float(np.sqrt(float(event_info["event_var"])))
    event_vol_ratio = event_vol / max(front_iv, config.TIME_EPSILON)

    # Get term structure note from event_info
    term_structure_note = event_info.get("term_structure_note")

    t_front = business_days(dt.date.today(), front_expiry) / 252.0
    t_front = max(t_front, config.TIME_EPSILON)
    gex = gex_summary(front_chain, spot, t_front)
    skew = skew_metrics(front_chain, spot, t_front)

    gex_note = None
    if (
        gex["abs_gex"] >= config.GEX_LARGE_ABS
        and abs(gex["net_gex"]) / gex["abs_gex"] < 0.1
    ):
        gex_note = "Positioning concentrated but direction uncertain"

    # ── Early snapshot fields for strategy condition gates ───────────
    today = dt.date.today()
    iv_ratio = front_iv / max(back_iv, config.TIME_EPSILON)
    days_after_event = max(0, (today - event_date).days)
    front_dte = (front_expiry - today).days
    back_dte = (back1_expiry - today).days

    # ATM strike for delta computation
    _fc = front_chain.copy()
    _fc["_dist"] = (_fc["strike"] - spot).abs()
    atm_strike = float(_fc.sort_values("_dist").iloc[0]["strike"])
    short_delta = abs(bsm_delta(
        spot, atm_strike, t_front,
        config.RISK_FREE_RATE, config.DIVIDEND_YIELD,
        front_iv, "call",
    ))

    early_snapshot = {
        "iv_ratio": iv_ratio,
        "event_variance_ratio": event_info.get(
            "event_variance_ratio", 0.0
        ),
        "implied_move": implied_move,
        "historical_p75": hist_p75,
        "short_delta": short_delta,
        "days_after_event": days_after_event,
        "front_dte": front_dte,
        "back_dte": back_dte,
    }

    scenarios = list(config.IV_SCENARIOS.keys())
    shock_levels = [0] + [shock for shock in config.VOL_SHOCKS if shock != 0]
    moves_by_shock = {}
    for shock in shock_levels:
        shock_vol = max(event_vol * (1 + shock / 100.0), 0.0)
        seed = None if args.seed is None else args.seed + shock + 1000
        moves_by_shock[shock] = simulate_moves(
            shock_vol,
            config.MC_SIMULATIONS,
            seed=seed,
        )

    strangle_offset = implied_move * 0.8
    strategies = build_strategies(
        front_chain,
        back1_chain,
        spot,
        strangle_offset_pct=strangle_offset,
    )

    # ── Conditionally add backspreads ─────────────────────────────
    front_expiry_ts = pd.Timestamp(front_expiry)
    if should_build_strategy("CALL_BACKSPREAD", early_snapshot):
        call_bs = build_call_backspread(
            front_chain, spot, front_expiry_ts,
        )
        if call_bs is not None:
            strategies.append(call_bs)
            LOGGER.info("Added call_backspread to strategy pool.")
    if should_build_strategy("PUT_BACKSPREAD", early_snapshot):
        put_bs = build_put_backspread(
            front_chain, spot, front_expiry_ts,
        )
        if put_bs is not None:
            strategies.append(put_bs)
            LOGGER.info("Added put_backspread to strategy pool.")
    combined_chain = pd.concat([front_chain, back1_chain], ignore_index=True)
    chain_lookup = _build_chain_lookup(combined_chain)

    # Collect conditional strategies that did NOT qualify (for report)
    not_applicable: list[dict] = []
    for cond_name in (
        "CALL_BACKSPREAD", "PUT_BACKSPREAD", "POST_EVENT_CALENDAR"
    ):
        if not should_build_strategy(cond_name, early_snapshot):
            not_applicable.append({
                "name": cond_name,
                "reason": _not_applicable_reason(cond_name, early_snapshot),
            })

    results = []
    for strategy in strategies:
        base_pnls = strategy_pnl_vec(
            strategy,
            combined_chain,
            spot,
            moves_by_shock[0],
            front_expiry,
            back1_expiry,
            event_date,
            front_iv,
            back_iv,
            config.SLIPPAGE_PCT,
            "base_crush",
        )

        # Compute scenario EVs for each strategy
        scenario_evs = {}
        for scenario in scenarios:
            pnls = strategy_pnl_vec(
                strategy,
                combined_chain,
                spot,
                moves_by_shock[0],
                front_expiry,
                back1_expiry,
                event_date,
                front_iv,
                back_iv,
                config.SLIPPAGE_PCT,
                scenario,
            )
            scenario_evs[scenario] = float(np.mean(pnls))

        evs = []
        for scenario in scenarios:
            for shock in shock_levels:
                pnls = strategy_pnl_vec(
                    strategy,
                    combined_chain,
                    spot,
                    moves_by_shock[shock],
                    front_expiry,
                    back1_expiry,
                    event_date,
                    front_iv,
                    back_iv,
                    config.SLIPPAGE_PCT,
                    scenario,
                )
                evs.append(float(np.mean(pnls)))

        scenario_ev_std = float(np.std(evs)) if len(evs) > 1 else 0.0
        robustness = 1.0 / (scenario_ev_std + 1e-9)

        metrics = compute_metrics(
            strategy,
            base_pnls,
            implied_move,
            hist_p75,
            spot,
            robustness,
            scenario_evs=scenario_evs,
        )
        metrics["scenario_evs"] = scenario_evs
        # Enrich legs with per-leg Greeks and compute net Greeks
        t_back1_years = max(back_dte / 365.0, config.TIME_EPSILON)
        net_greeks = _enrich_legs_with_greeks(
            metrics["legs"],
            chain_lookup,
            spot,
            t_front,
            t_back1_years,
            front_expiry,
            front_iv,
            back_iv,
        )
        metrics["net_delta"] = net_greeks["delta"]
        metrics["net_gamma"] = net_greeks["gamma"]
        metrics["net_vega"] = net_greeks["vega"]
        metrics["net_theta"] = net_greeks["theta"]
        pnls = base_pnls
        metrics["pnls"] = pnls
        results.append(metrics)

    ranked = score_strategies(results)
    top = ranked[0]
    top_strategy = top["strategy_obj"]

    ev_base = float(np.mean(top["pnls"]))
    ev_2x = float(
        np.mean(
            strategy_pnl_vec(
                top_strategy,
                combined_chain,
                spot,
                moves_by_shock[0],
                front_expiry,
                back1_expiry,
                event_date,
                front_iv,
                back_iv,
                config.SLIPPAGE_PCT * 2.0,
                "base_crush",
            )
        )
    )

    expected_move_dollar = max(implied_move, hist_p75) * spot * 100
    move_plot = plot_move_comparison(implied_move, hist_p75)
    pnl_plot = plot_pnl_distribution(
        top["pnls"],
        f"Top Strategy: {top['strategy']}",
    )
    rr25_value = f"{skew['rr25']:.4f}" if skew["rr25"] is not None else "N/A"
    bf25_value = f"{skew['bf25']:.4f}" if skew["bf25"] is not None else "N/A"

    # Build comprehensive snapshot (includes early_snapshot fields)
    snapshot = {
        "spot": spot,
        "event_date": event_date,
        "front_expiry": front_expiry,
        "back_expiry": back1_expiry,
        "implied_move": implied_move,
        "historical_p75": hist_p75,
        "front_iv": front_iv,
        "back_iv": back_iv,
        "back2_iv": back2_iv,
        "event_vol": event_vol,
        "event_vol_ratio": event_vol_ratio,
        "expected_move_dollar": expected_move_dollar,
        "raw_event_var": event_info["raw_event_var"],
        "event_variance_ratio": event_info.get(
            "event_variance_ratio", 0.0
        ),
        "front_back_spread": event_info.get(
            "front_back_spread", 0.0
        ),
        "back_slope": event_info.get("back_slope"),
        "t_front": event_info.get("t_front", t_front),
        "t_back1": event_info.get(
            "t_back1", t_front + 20 / 252
        ),
        "interpolation_method": event_info.get(
            "interpolation_method", "unknown"
        ),
        "negative_event_var": event_info.get(
            "negative_event_var", False
        ),
        "term_structure_note": term_structure_note,
        "warning_level": event_info["warning_level"],
        "assumption": event_info["assumption"],
        "gex_net": gex["net_gex"],
        "gex_abs": gex["abs_gex"],
        "gamma_flip": gex.get("gamma_flip"),
        "flip_distance_pct": gex.get("flip_distance_pct"),
        "top_gamma_strikes": gex.get(
            "top_gamma_strikes", []
        ),
        "gex_dealer_note": (
            "GEX sign assumes dealers are net short "
            "options. Interpret regime direction "
            "accordingly."
        ),
        "gex_note": gex_note,
        "mean_abs_move": dist_shape["mean_abs_move"],
        "median_abs_move": dist_shape["median_abs_move"],
        "skewness": dist_shape["skewness"],
        "kurtosis": dist_shape["kurtosis"],
        "tail_probs": dist_shape.get("tail_probs", {}),
        "rr25": rr25_value,
        "bf25": bf25_value,
        "ev_base": ev_base,
        "ev_2x": ev_2x,
    }
    # Merge early snapshot fields used by strategy gates
    snapshot.update(early_snapshot)

    # Classify regime
    regime = classify_regime(snapshot)
    snapshot["regime"] = regime

    # Compute alignment for all strategies
    compute_all_alignments(ranked, regime)

    # ── Post-event calendar (separate evaluation model) ───────────
    post_event_cal = None
    if should_build_strategy(
        "POST_EVENT_CALENDAR", early_snapshot
    ):
        t_back1 = max(back_dte / 365.0, config.TIME_EPSILON)
        pe_result = build_post_event_calendar(
            spot, atm_strike, front_iv, back_iv,
            t_front, t_back1,
            pd.Timestamp(front_expiry),
            pd.Timestamp(back1_expiry),
        )
        pe_scenarios = compute_post_event_calendar_scenarios(
            spot=spot, K=atm_strike,
            t_short=t_front, t_long=t_back1,
            iv_long=back_iv,
            net_cost=pe_result["net_cost"],
        )
        post_event_cal = {
            "strategy": pe_result["strategy"],
            "details": pe_result,
            "scenarios": pe_scenarios,
        }
        LOGGER.info(
            "Post-event calendar built: net_cost=%.2f",
            pe_result["net_cost"],
        )

    report_path = Path(args.output)
    write_report(
        report_path,
        {
            "snapshot": snapshot,
            "regime": regime,
            "rankings": ranked,
            "move_plot": move_plot,
            "pnl_plot": pnl_plot,
            "post_event_calendar": post_event_cal,
            "not_applicable": not_applicable,
            "strategy_rationale": STRATEGY_RATIONALE,
        },
    )

    _print_console_snapshot(
        implied_move,
        hist_p75,
        event_vol,
        event_vol_ratio,
        ev_base,
        ev_2x,
        gex,
        regime,
    )

    LOGGER.info("Report written to %s", report_path)


def _parse_event_date(value: str | None) -> dt.date | None:
    if value is None:
        return None
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def _normalize_event_date(event_date: dt.date | pd.Timestamp) -> dt.date:
    if isinstance(event_date, pd.Timestamp):
        return event_date.date()
    return event_date


def _validate_front_expiry(event_date: dt.date, front_expiry: dt.date) -> None:
    if front_expiry <= event_date:
        raise ValueError(
            f"Front expiry {front_expiry} must be strictly after event date "
            f"{event_date}. "
            "Check your event date or option chain data."
        )


def _load_test_data_mode(
    args: argparse.Namespace,
) -> dict:
    """Load or generate synthetic test data for validation."""
    if args.test_data_dir:
        LOGGER.info("Loading test data from %s", args.test_data_dir)
        return load_test_data(Path(args.test_data_dir))

    LOGGER.info(
        "Generating synthetic test data (scenario: %s)",
        args.test_scenario,
    )
    seed = args.seed if args.seed is not None else 42
    test_data = generate_test_data_set(
        scenario=args.test_scenario,
        seed=seed,
    )

    if args.save_test_data:
        save_test_data(test_data, Path(args.save_test_data))
        LOGGER.info("Saved test data to %s", args.save_test_data)

    return test_data


def _filter_chain_for_test(
    chain: pd.DataFrame,
    spot: float,
) -> pd.DataFrame:
    """Apply standard filters to test chain."""
    chain = filter_by_moneyness(
        chain,
        spot,
        config.MONEYNESS_LOW,
        config.MONEYNESS_HIGH,
    )
    chain = filter_by_liquidity(chain, config.MIN_OI, config.MAX_SPREAD_PCT)
    return chain


def _load_filtered_chain(
    expiry: dt.date | None,
    spot: float,
    cache_dir: Path,
    use_cache: bool,
    refresh_cache: bool,
    allow_empty: bool = False,
) -> pd.DataFrame | None:
    if expiry is None:
        return None
    chain = get_options_chain(
        config.TICKER,
        expiry,
        cache_dir=cache_dir,
        use_cache=use_cache,
        refresh_cache=refresh_cache,
    )
    LOGGER.info("Options rows pre-filter for %s: %d", expiry, len(chain))
    chain = filter_by_moneyness(
        chain,
        spot,
        config.MONEYNESS_LOW,
        config.MONEYNESS_HIGH,
    )
    chain = filter_by_liquidity(chain, config.MIN_OI, config.MAX_SPREAD_PCT)
    LOGGER.info("Options rows post-filter for %s: %d", expiry, len(chain))
    if chain.empty:
        if allow_empty:
            return None
        raise ValueError(
            f"No options remain after filtering for {expiry} "
            f"(OI>={config.MIN_OI}, spread<={config.MAX_SPREAD_PCT}, "
            f"moneyness {config.MONEYNESS_LOW}-{config.MONEYNESS_HIGH})."
        )
    return chain


def _print_console_snapshot(
    implied_move: float,
    hist_p75: float,
    event_vol: float,
    event_vol_ratio: float,
    ev_base: float,
    ev_2x: float,
    gex: dict,
    regime: dict | None = None,
) -> None:
    print("\n" + "="*60)
    print("VOLATILITY DIAGNOSTICS")
    print("="*60)
    print(f"ImpliedMove:        {implied_move:.4f}")
    print(f"Historical P75:       {hist_p75:.4f}")
    implied_ratio = implied_move / max(hist_p75, 1e-9)
    print(f"ImpliedMove / P75:    {implied_ratio:.4f}")
    print(f"EventVol:             {event_vol:.4f}")
    print(f"EventVol / FrontIV:   {event_vol_ratio:.4f}")

    if regime:
        print("\n" + "="*60)
        print("REGIME CLASSIFICATION")
        print("="*60)
        print(f"Vol Pricing:          {regime['vol_regime']}")
        print(f"Event Structure:      {regime['event_regime']}")
        print(f"Term Structure:       {regime['term_structure_regime']}")
        print(f"Gamma Regime:         {regime['gamma_regime']}")
        print(f"Composite Regime:     {regime['composite_regime']}")
        print(f"Composite Confidence: {regime['confidence']:.2f}")

    print("\n" + "="*60)
    print("MICROSTRUCTURE DIAGNOSTICS")
    print("="*60)
    print(f"Slippage sensitivity (EV delta): {ev_2x - ev_base:.2f}")
    print(f"GEX net:  {gex['net_gex']:.2f}")
    print(f"GEX abs:  {gex['abs_gex']:.2f}")
    if gex.get('gamma_flip'):
        print(f"Gamma Flip: {gex['gamma_flip']:.2f}")
    print("="*60)


if __name__ == "__main__":
    main()
