"""CLI entrypoint for NVDA earnings volatility analysis."""

from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from nvda_earnings_vol import config
from nvda_earnings_vol.analytics.event_vol import event_variance
from nvda_earnings_vol.analytics.gamma import gex_summary
from nvda_earnings_vol.analytics.historical import earnings_move_p75
from nvda_earnings_vol.analytics.implied_move import implied_move_from_chain
from nvda_earnings_vol.analytics.skew import skew_metrics
from nvda_earnings_vol.data.filters import filter_by_liquidity, filter_by_moneyness
from nvda_earnings_vol.data.loader import (
    get_earnings_dates,
    get_expiries_after,
    get_next_earnings_date,
    get_option_expiries,
    get_options_chain,
    get_price_history,
    get_spot_price,
)
from nvda_earnings_vol.reports.reporter import write_report
from nvda_earnings_vol.simulation.monte_carlo import simulate_moves
from nvda_earnings_vol.strategies.payoff import strategy_pnl
from nvda_earnings_vol.strategies.scoring import compute_metrics, score_strategies
from nvda_earnings_vol.strategies.structures import build_strategies
from nvda_earnings_vol.viz.plots import plot_move_comparison, plot_pnl_distribution


LOGGER = logging.getLogger(__name__)


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
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    event_date = _parse_event_date(args.event_date)
    if event_date is None:
        event_date = get_next_earnings_date(config.TICKER)
    if event_date is None:
        raise ValueError("Event date not provided and could not be fetched.")
    if event_date <= dt.date.today():
        raise ValueError("Event date must be in the future.")

    try:
        spot = get_spot_price(config.TICKER)
        expiries = get_option_expiries(config.TICKER)
        post_event = get_expiries_after(expiries, event_date)
        if len(post_event) < 2:
            raise ValueError("Insufficient expiries after event date.")

        front_expiry = post_event[0]
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
            LOGGER.error("Market appears closed or data unavailable; exiting (%s)", exc)
        else:
            LOGGER.error("%s", exc)
        return

    try:
        implied_move = implied_move_from_chain(
            front_chain, spot, config.SLIPPAGE_PCT
        )
        history = get_price_history(config.TICKER, config.HISTORY_YEARS)
        earnings_dates = get_earnings_dates(config.TICKER)
        hist_p75 = earnings_move_p75(history, earnings_dates)
    except ValueError as exc:
        LOGGER.error("%s", exc)
        return

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

    front_iv = float(event_info["front_iv"])
    back_iv = float(event_info["back_iv"])
    event_vol = float(np.sqrt(event_info["event_var"]))
    event_vol_ratio = event_vol / max(front_iv, config.TIME_EPSILON)

    t_front = _business_days(dt.date.today(), front_expiry) / 252.0
    t_front = max(t_front, config.TIME_EPSILON)
    gex = gex_summary(front_chain, spot, t_front)
    skew = skew_metrics(front_chain, spot, t_front)
    gex_note = None
    if (
        gex["abs_gex"] >= config.GEX_LARGE_ABS
        and abs(gex["net_gex"]) / gex["abs_gex"] < 0.1
    ):
        gex_note = "Positioning concentrated but direction uncertain"

    scenarios = list(config.IV_SCENARIOS.keys())
    shock_levels = [0] + [shock for shock in config.VOL_SHOCKS if shock != 0]
    moves_by_shock = {}
    for shock in shock_levels:
        shock_vol = max(event_vol * (1 + shock / 100.0), 0.0)
        moves_by_shock[shock] = simulate_moves(shock_vol, config.MC_SIMULATIONS)

    strategies = build_strategies(front_chain, back1_chain, spot)
    combined_chain = pd.concat([front_chain, back1_chain], ignore_index=True)

    results = []
    for strategy in strategies:
        base_pnls = strategy_pnl(
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
        evs = []
        for scenario in scenarios:
            for shock in shock_levels:
                pnls = strategy_pnl(
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
        robustness = 1.0 / (float(np.std(evs)) + 1e-9)
        metrics = compute_metrics(
            strategy, base_pnls, implied_move, hist_p75, spot, robustness
        )
        metrics["scenario_evs"] = evs
        pnls = base_pnls
        metrics["pnls"] = pnls
        results.append(metrics)

    ranked = score_strategies(results)
    top = ranked[0]
    top_strategy = top["strategy_obj"]

    ev_base = float(np.mean(top["pnls"]))
    ev_2x = float(
        np.mean(
            strategy_pnl(
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

    move_plot = plot_move_comparison(implied_move, hist_p75)
    pnl_plot = plot_pnl_distribution(top["pnls"], f"Top Strategy: {top['strategy']}")
    rr25_value = f"{skew['rr25']:.4f}" if skew["rr25"] is not None else "N/A"
    bf25_value = f"{skew['bf25']:.4f}" if skew["bf25"] is not None else "N/A"

    report_path = Path(args.output)
    write_report(
        report_path,
        {
            "spot": f"{spot:.2f}",
            "event_date": event_date,
            "front_expiry": front_expiry,
            "implied_move": f"{implied_move:.4f}",
            "historical_p75": f"{hist_p75:.4f}",
            "event_vol": f"{event_vol:.4f}",
            "event_vol_ratio": f"{event_vol_ratio:.4f}",
            "raw_event_var": f"{event_info['raw_event_var']:.6f}",
            "event_var_ratio": f"{event_info['ratio']:.4f}",
            "warning_level": event_info["warning_level"],
            "assumption": event_info["assumption"],
            "ev_base": f"{ev_base:.2f}",
            "ev_2x": f"{ev_2x:.2f}",
            "net_gex": f"{gex['net_gex']:.2f}",
            "abs_gex": f"{gex['abs_gex']:.2f}",
            "gex_note": gex_note,
            "rankings": ranked,
            "move_plot": move_plot,
            "pnl_plot": pnl_plot,
            "rr25": rr25_value,
            "bf25": bf25_value,
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
    )

    LOGGER.info("Report written to %s", report_path)


def _parse_event_date(value: str | None) -> dt.date | None:
    if value is None:
        return None
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


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
    chain = filter_by_moneyness(chain, spot, config.MONEYNESS_LOW, config.MONEYNESS_HIGH)
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


def _business_days(start: dt.date, end: dt.date) -> int:
    if end <= start:
        return 0
    return pd.bdate_range(start, end).size - 1


def _print_console_snapshot(
    implied_move: float,
    hist_p75: float,
    event_vol: float,
    event_vol_ratio: float,
    ev_base: float,
    ev_2x: float,
    gex: dict,
) -> None:
    print("\nVol Diagnostics")
    print(f"ImpliedMove: {implied_move:.4f}")
    print(f"Historical P75: {hist_p75:.4f}")
    print(f"ImpliedMove / P75: {implied_move / max(hist_p75, 1e-9):.4f}")
    print(f"EventVol: {event_vol:.4f}")
    print(f"EventVol / FrontIV: {event_vol_ratio:.4f}")

    print("\nMicrostructure Diagnostics")
    print(f"Slippage sensitivity (EV delta): {ev_2x - ev_base:.2f}")
    print(f"GEX net: {gex['net_gex']:.2f}, abs: {gex['abs_gex']:.2f}")


if __name__ == "__main__":
    main()
