"""CLI entrypoint for NVDA earnings volatility analysis."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from event_option_playbook import (
    build_playbook_recommendation,
    snapshot_to_event_spec,
    snapshot_to_market_context,
)
from event_vol_analysis import config
from event_vol_analysis.alignment import compute_all_alignments
from event_vol_analysis.calibration import (
    calibrate_ticker_params,
    calibrate_iv_scenarios,
)
from event_vol_analysis.analytics.bsm import (
    delta as bsm_delta,
    gamma as bsm_gamma,
    vega as bsm_vega,
    theta as bsm_theta,
)
from event_vol_analysis.analytics.event_vol import event_variance
from event_vol_analysis.analytics.edge_ratio import (
    EDGE_RATIO_LOW_CONFIDENCE_CAVEAT,
    compute_edge_ratio,
)
from event_vol_analysis.analytics.gamma import gex_summary
from event_vol_analysis.analytics.historical import (
    calibrate_fat_tail_inputs,
    conditional_expected_move,
    compute_distribution_shape,
    earnings_move_p75,
    extract_earnings_moves_with_dates,
    split_by_timing,
)
from event_vol_analysis.analytics.implied_move import implied_move_from_chain
from event_vol_analysis.analytics.positioning import (
    classify_positioning,
    drift_vs_sector,
    max_pain_distance,
    oi_concentration,
    pc_ratio_signal,
)
from event_vol_analysis.analytics.signal_graph import (
    SignalGraphResult,
    build_signal_graph_result,
    load_signal_graph_config,
)
from event_vol_analysis.analytics.skew import skew_metrics
from event_vol_analysis.analytics.vol_regime import load_atm_iv_history_from_store
from event_vol_analysis.data.filters import (
    filter_by_liquidity,
    filter_by_moneyness,
)
from event_vol_analysis.data.loader import (
    EventDateResolution,
    get_dividend_yield,
    get_earnings_dates,
    get_expiries_after,
    get_option_expiries,
    get_options_chain,
    get_price_history,
    get_spot_price,
    resolve_next_earnings_date,
    select_front_expiry,
)
from event_vol_analysis.data.test_data import (
    generate_test_data_set,
    list_available_scenarios,
    load_test_data,
    save_test_data,
)
from event_vol_analysis.outcomes import store_prediction
from event_vol_analysis.regime import classify_regime
from event_vol_analysis.reports.reporter import write_report
from event_vol_analysis.simulation.monte_carlo import simulate_moves
from event_vol_analysis.structure_advisor import query_structures
from event_vol_analysis.strategies.backspreads import (
    build_call_backspread,
    build_put_backspread,
)
from event_vol_analysis.strategies.payoff_map import PayoffType
from event_vol_analysis.strategies.payoff import strategy_pnl_vec
from event_vol_analysis.strategies.post_event_calendar import (
    build_post_event_calendar,
    compute_post_event_calendar_scenarios,
)
from event_vol_analysis.strategies.registry import should_build_strategy
from event_vol_analysis.strategies.scoring import (
    compute_metrics,
    score_strategies,
)
from event_vol_analysis.strategies.structures import build_strategies
from event_vol_analysis.strategies.type_classifier import classify_type
from event_vol_analysis.utils import business_days
from event_vol_analysis.viz.plots import (
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
    "SYMMETRIC_BUTTERFLY": (
        "Defined-risk short-volatility structure: long one lower-strike call, "
        "short two ATM calls, and long one higher-strike call with symmetric "
        "wings. Profits most if spot settles near the body strike and limits "
        "losses to the net debit paid."
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

_SHORT_VOL_STRATEGY_NAMES = {"iron_condor", "calendar"}


def _run_query_cli(argv: list[str]) -> int:
    """Run `query` subcommand for the Structure Advisor."""
    parser = argparse.ArgumentParser(
        prog="earningsvol query",
        description="Price and compare structures by payoff intent",
    )
    parser.add_argument(
        "--payoff",
        type=str,
        required=True,
        choices=[item.value for item in PayoffType],
        help="Payoff intent to query",
    )
    parser.add_argument("--ticker", type=str, required=True, help="Underlying ticker")
    parser.add_argument(
        "--expiry",
        type=str,
        required=True,
        help="Front expiry date in YYYY-MM-DD format",
    )
    parser.add_argument("--spot", type=float, required=True, help="Spot price")
    parser.add_argument(
        "--budget",
        type=float,
        default=None,
        help="Optional max net debit budget",
    )
    parser.add_argument(
        "--max-notional",
        type=float,
        default=None,
        help="Optional max estimated notional in dollars",
    )
    parser.add_argument(
        "--iv-percentile",
        type=float,
        default=None,
        help="Optional IV percentile context",
    )
    parser.add_argument(
        "--dte",
        type=int,
        default=None,
        help="Optional DTE context override",
    )
    parser.add_argument(
        "--vix",
        type=float,
        default=None,
        help="Optional VIX context",
    )
    parser.add_argument(
        "--validate",
        type=str,
        default=None,
        help="Optional manual structure string to include",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="table",
        choices=["table", "json"],
        help="Output format",
    )
    args = parser.parse_args(argv)

    context: dict[str, float | int | bool] = {}
    if args.iv_percentile is not None:
        context["iv_percentile"] = float(args.iv_percentile)
    if args.dte is not None:
        context["dte"] = int(args.dte)
    if args.vix is not None:
        context["vix"] = float(args.vix)

    try:
        result = query_structures(
            payoff_type=args.payoff,
            ticker=args.ticker,
            expiry=args.expiry,
            spot=float(args.spot),
            budget=args.budget,
            max_notional=args.max_notional,
            context=context,
            validate=args.validate,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if result.data_unavailable:
        print("DATA UNAVAILABLE: option chain fetch failed", file=sys.stderr)
        return 1

    if args.output == "json":
        print(result.to_json())
    else:
        print(result.to_table())
    return 0


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
    div_yield: float = config.DIVIDEND_YIELD,
) -> dict[str, float]:
    """Compute per-leg BSM Greeks and inject into leg dicts.

    Returns net Greeks dict summed over all legs.
    """
    r = config.RISK_FREE_RATE
    q = div_yield
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
        iv = chain_data["iv"] if chain_data else (front_iv if is_front else back_iv)
        leg["iv"] = iv

        d = bsm_delta(spot, leg["strike"], t, r, q, iv, leg["option_type"])
        g = bsm_gamma(spot, leg["strike"], t, r, q, iv, leg["option_type"])
        v = bsm_vega(spot, leg["strike"], t, r, q, iv, leg["option_type"])
        th = bsm_theta(spot, leg["strike"], t, r, q, iv, leg["option_type"])
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
    """Return a human-readable reason why a conditional strategy was skipped."""
    if name in ("CALL_BACKSPREAD", "PUT_BACKSPREAD"):
        reasons = []
        iv_ratio = snapshot.get("iv_ratio", 0.0)
        if iv_ratio < config.BACKSPREAD_MIN_IV_RATIO:
            reasons.append(
                f"IV ratio {iv_ratio:.2f} < {config.BACKSPREAD_MIN_IV_RATIO} required"
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
                f"short delta {sd:.3f} < {config.BACKSPREAD_MIN_SHORT_DELTA} required"
            )
        dte = snapshot.get("back_dte", 0)
        if not (
            config.BACKSPREAD_LONG_DTE_MIN <= dte <= config.BACKSPREAD_LONG_DTE_MAX
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
            return "Entry requires 1–3 days after earnings event (currently pre-event)"
        return f"{days}d after event exceeds the 3-day entry window"
    return "Entry conditions not met"


def _safe_abs_quantile(values: np.ndarray, q: float) -> float:
    """Return quantile of absolute moves, robust to empty vectors."""
    if values.size == 0:
        return 0.0
    return float(np.quantile(np.abs(values), q))


def _compute_quantile_deviation(
    implied_move: float,
    simulated_abs_quantiles: dict[str, float],
) -> dict[str, object]:
    """Compare implied absolute-move quantiles to simulated quantiles."""
    implied_scale = max(float(implied_move), config.TIME_EPSILON)
    quantile_deviation: dict[str, dict[str, float | str]] = {}
    deviation_vals: list[float] = []

    for label in ("p10", "p50", "p90"):
        sim_val = float(simulated_abs_quantiles.get(label, 0.0) or 0.0)
        abs_dev = abs(sim_val - implied_scale)
        rel_dev = abs_dev / implied_scale
        if sim_val > implied_scale:
            direction = "simulation_over"
        elif sim_val < implied_scale:
            direction = "simulation_under"
        else:
            direction = "matched"
        quantile_deviation[label] = {
            "simulated": sim_val,
            "implied_proxy": implied_scale,
            "abs_deviation": abs_dev,
            "relative_deviation": rel_dev,
            "direction": direction,
        }
        deviation_vals.append(rel_dev)

    max_dev = max(deviation_vals) if deviation_vals else 1.0
    mean_dev = float(np.mean(deviation_vals)) if deviation_vals else 1.0
    score = max(0.0, min(100.0, 100.0 * (1.0 - (0.6 * mean_dev + 0.4 * max_dev))))
    if score >= config.TRUST_SCORE_PASS_THRESHOLD:
        status = "PASS"
        confidence = "HIGH"
    elif score >= config.TRUST_SCORE_WARN_THRESHOLD:
        status = "WARN"
        confidence = "MEDIUM"
    else:
        status = "FAIL"
        confidence = "LOW"

    dominant_dir = "matched"
    if quantile_deviation:
        dominant_q = max(
            quantile_deviation.items(),
            key=lambda item: float(item[1]["abs_deviation"]),
        )[0]
        dominant_dir = str(quantile_deviation[dominant_q]["direction"])

    return {
        "quantile_deviation": quantile_deviation,
        "trust_score": float(score),
        "status": status,
        "confidence": confidence,
        "mismatch_direction": dominant_dir,
    }


def _compute_trust_metrics(
    *,
    implied_move: float,
    simulation_comparison: dict[str, dict[str, float]],
) -> dict[str, float | str | bool | dict[str, object]]:
    """Compute trust diagnostics using quantile deviation and continuous score."""
    selected = simulation_comparison.get("fat_tailed", {})
    selected_mean_abs = float(selected.get("mean_abs_move", 0.0) or 0.0)
    ratio = implied_move / max(selected_mean_abs, config.TIME_EPSILON)
    quantiles = {
        "p10": float(selected.get("abs_q10", 0.0) or 0.0),
        "p50": float(selected.get("abs_q50", 0.0) or 0.0),
        "p90": float(selected.get("abs_q90", 0.0) or 0.0),
    }
    qdiag = _compute_quantile_deviation(implied_move, quantiles)
    ks_pvalue = float(selected.get("ks_pvalue", 0.0) or 0.0)
    ks_score = max(0.0, min(100.0, ks_pvalue * 100.0))
    trust_score = 0.7 * float(qdiag["trust_score"]) + 0.3 * ks_score
    if trust_score >= config.TRUST_SCORE_PASS_THRESHOLD:
        status = "PASS"
        confidence = "HIGH"
    elif trust_score >= config.TRUST_SCORE_WARN_THRESHOLD:
        status = "WARN"
        confidence = "MEDIUM"
    else:
        status = "FAIL"
        confidence = "LOW"

    return {
        "implied_move": float(implied_move),
        "simulated_mean_abs_move": selected_mean_abs,
        "simulated_abs_quantiles": quantiles,
        "mismatch_ratio": float(ratio),
        "status": status,
        "confidence": confidence,
        "trust_score": float(trust_score),
        "ks_pvalue": ks_pvalue,
        "ks_score": ks_score,
        "quantile_deviation": qdiag["quantile_deviation"],
        "mismatch_direction": str(qdiag["mismatch_direction"]),
        "ranking_allowed": status != "FAIL",
        "fat_tail_active": bool(
            simulation_comparison.get("fat_tailed", {}).get("tail_prob_gt_6pct", 0.0)
            > simulation_comparison.get("lognormal", {}).get("tail_prob_gt_6pct", 0.0)
        ),
    }


def _short_vol_dte_weight(front_dte: int) -> float:
    """Return continuous short-vol risk weight for front DTE."""
    lower = int(config.SHORT_VOL_DTE_MIN)
    upper = int(config.SHORT_VOL_DTE_MAX)
    if lower <= int(front_dte) <= upper:
        return 1.0

    if int(front_dte) < lower:
        distance = float(lower - int(front_dte))
    else:
        distance = float(int(front_dte) - upper)

    window = max(float(upper - lower + 1), 1.0)
    penalty = min(distance / window, 1.0)
    return float(max(0.35, 1.0 - 0.65 * penalty))


def _short_vol_evidence_gate(
    ticker: str,
    *,
    db_path: Path = Path("data/options_intraday.db"),
    lookback: int = 8,
) -> dict[str, object]:
    """Evaluate whether short-vol has historical implied-over-realized support."""
    if not db_path.exists():
        return {
            "allowed": False,
            "wins": 0,
            "samples": 0,
            "note": "earnings outcomes db missing",
        }
    try:
        from data.option_data_store import create_store

        store = create_store(db_path)
        outcomes = store.get_earnings_outcomes(ticker=ticker.upper())
    except Exception:
        return {
            "allowed": False,
            "wins": 0,
            "samples": 0,
            "note": "earnings outcomes query failed",
        }

    if outcomes.empty or "realized_vs_implied_ratio" not in outcomes.columns:
        return {
            "allowed": False,
            "wins": 0,
            "samples": 0,
            "note": "no realized_vs_implied history",
        }

    frame = outcomes.sort_values("event_date", ascending=False).copy()
    ratios = pd.to_numeric(frame["realized_vs_implied_ratio"], errors="coerce")
    valid = ratios.dropna().head(lookback)
    samples = int(len(valid))
    if samples <= 0:
        return {
            "allowed": False,
            "wins": 0,
            "samples": 0,
            "note": "no completed outcomes",
        }
    wins = int((valid < 1.0).sum())
    allowed = wins > (samples / 2.0)
    return {
        "allowed": bool(allowed),
        "wins": wins,
        "samples": samples,
        "note": f"implied>realized in {wins}/{samples} events",
    }


def _resolve_simulation_event_vol(
    *,
    event_vol: float,
    implied_move: float,
) -> float:
    """Calibrate simulation sigma to avoid under-scaled move distributions."""
    if implied_move <= 0:
        return max(float(event_vol), 0.0)
    implied_sigma_proxy = implied_move / math.sqrt(2.0 / math.pi)
    return max(float(event_vol), float(implied_sigma_proxy))


def _implied_abs_move_reference(
    implied_move: float,
    sample_size: int,
    *,
    seed: int,
) -> np.ndarray:
    """Sample implied-reference absolute moves from a half-normal proxy."""
    sigma = max(float(implied_move), config.TIME_EPSILON) / math.sqrt(2.0 / math.pi)
    rng = np.random.default_rng(seed)
    return np.abs(rng.normal(0.0, sigma, size=sample_size))


def _load_tickers_from_file(file_path: str) -> list[str]:
    """Load ticker symbols from a comma/newline separated file."""
    path = Path(file_path)
    if not path.exists():
        raise ValueError(f"Ticker file not found: {file_path}")

    content = path.read_text(encoding="utf-8")
    tokens = content.replace("\n", ",").split(",")
    tickers = [token.strip().upper() for token in tokens if token.strip()]
    unique_tickers = list(dict.fromkeys(tickers))
    if not unique_tickers:
        raise ValueError(f"No valid tickers found in {file_path}")
    return unique_tickers


def _batch_command_for_ticker(
    args: argparse.Namespace,
    ticker: str,
    output_path: Path,
    analysis_summary_path: Path | None = None,
) -> list[str]:
    """Build batch subprocess command for one ticker run."""
    move_model = getattr(args, "move_model", config.MOVE_MODEL_DEFAULT)
    command = [
        sys.executable,
        "-m",
        "event_vol_analysis.main",
        "--ticker",
        ticker,
        "--output",
        str(output_path),
        "--cache-dir",
        args.cache_dir,
    ]

    if args.event_date:
        command.extend(["--event-date", args.event_date])
    if args.use_cache:
        command.append("--use-cache")
    if args.refresh_cache:
        command.append("--refresh-cache")
    if getattr(args, "cache_only", False):
        command.append("--cache-only")
    cache_spot = getattr(args, "cache_spot", None)
    if cache_spot is not None:
        command.extend(["--cache-spot", str(cache_spot)])
    cache_front_expiry = getattr(args, "cache_front_expiry", None)
    if cache_front_expiry:
        command.extend(["--cache-front-expiry", str(cache_front_expiry)])
    cache_back1_expiry = getattr(args, "cache_back1_expiry", None)
    if cache_back1_expiry:
        command.extend(["--cache-back1-expiry", str(cache_back1_expiry)])
    cache_back2_expiry = getattr(args, "cache_back2_expiry", None)
    if cache_back2_expiry:
        command.extend(["--cache-back2-expiry", str(cache_back2_expiry)])
    if args.seed is not None:
        command.extend(["--seed", str(args.seed)])
    if move_model:
        command.extend(["--move-model", move_model])
    if args.test_data:
        command.append("--test-data")
    if args.test_scenario:
        command.extend(["--test-scenario", args.test_scenario])
    if args.test_data_dir:
        command.extend(["--test-data-dir", args.test_data_dir])
    if args.save_test_data:
        command.extend(["--save-test-data", args.save_test_data])
    if analysis_summary_path is not None:
        command.extend(["--analysis-summary-json", str(analysis_summary_path)])
    return command


def _extract_failure_reason(result: subprocess.CompletedProcess[str]) -> str:
    """Return one compact failure reason from subprocess output."""
    for stream in (result.stderr, result.stdout):
        if stream:
            lines = [line.strip() for line in stream.splitlines() if line.strip()]
            if lines:
                return lines[-1]
    return "analysis subprocess failed without stderr/stdout details"


def _run_batch_mode(args: argparse.Namespace, tickers: list[str]) -> bool:
    """Run the full analysis once per ticker and write a batch summary."""
    output_dir = Path(args.batch_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, object] = {
        "tickers_requested": len(tickers),
        "tickers_succeeded": 0,
        "tickers_failed": 0,
        "results": [],
    }

    for ticker in tickers:
        output_path = output_dir / f"{ticker.lower()}_earnings_report.html"
        analysis_summary_path = output_dir / f"{ticker.lower()}_analysis_summary.json"
        if analysis_summary_path.exists():
            analysis_summary_path.unlink()
        command = _batch_command_for_ticker(
            args,
            ticker,
            output_path,
            analysis_summary_path=analysis_summary_path,
        )
        LOGGER.info("Batch run for %s -> %s", ticker, output_path)
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )

        ok = result.returncode == 0
        if ok:
            summary["tickers_succeeded"] += 1
        else:
            summary["tickers_failed"] += 1
        result_row: dict[str, object] = {
            "ticker": ticker,
            "output": str(output_path),
            "returncode": int(result.returncode),
            "ok": ok,
            "event_date": None,
            "regime": None,
            "top_structure": None,
            "score": None,
            "blocking_warnings": [],
        }

        if analysis_summary_path.exists():
            try:
                analysis_summary = json.loads(
                    analysis_summary_path.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                analysis_summary = {}
            result_row["event_date"] = analysis_summary.get("event_date")
            result_row["regime"] = analysis_summary.get("regime")
            result_row["top_structure"] = analysis_summary.get("top_structure")
            result_row["score"] = analysis_summary.get("score")
            result_row["blocking_warnings"] = analysis_summary.get(
                "blocking_warnings", []
            )

        if not ok:
            result_row["error"] = _extract_failure_reason(result)
            LOGGER.error(
                "Batch failed for %s (rc=%d): %s",
                ticker,
                result.returncode,
                result_row["error"],
            )

        summary["results"].append(result_row)

    LOGGER.info(
        "%-8s %-12s %-28s %-18s %-8s %s",
        "Ticker",
        "Event",
        "Regime",
        "Top",
        "Score",
        "Warnings",
    )
    for row in summary["results"]:
        event_label = str(row.get("event_date") or "-")
        regime_label = str(row.get("regime") or "-")
        top_label = str(row.get("top_structure") or "-")
        score_raw = row.get("score")
        score_label = f"{float(score_raw):.4f}" if score_raw is not None else "-"
        warnings = row.get("blocking_warnings") or []
        warning_label = ",".join(str(item) for item in warnings) if warnings else "-"
        if not row.get("ok", False):
            warning_label = str(row.get("error") or warning_label)
        LOGGER.info(
            "%-8s %-12s %-28s %-18s %-8s %s",
            str(row.get("ticker")),
            event_label,
            regime_label[:28],
            top_label[:18],
            score_label,
            warning_label,
        )

    if args.batch_summary_json:
        summary_path = Path(args.batch_summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )
        LOGGER.info("Batch summary written to %s", summary_path)

    LOGGER.info(
        "Batch complete: %d succeeded, %d failed",
        summary["tickers_succeeded"],
        summary["tickers_failed"],
    )
    return bool(summary["tickers_failed"] == 0)


def _run_playbook_scan_mode(args: argparse.Namespace, tickers: list[str]) -> bool:
    """Run playbook scan mode: condensed morning review with TYPE summary."""
    from event_vol_analysis.reports.playbook_scan import (
        # check_playbook_liquidity,  # Reserved for future pre-filtering
        create_scan_row_from_snapshot,
        sort_playbook_rows,
        format_console_table,
        save_playbook_scan_report,
        PlaybookScanResult,
        PlaybookScanRow,
    )

    output_dir = Path(args.batch_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[PlaybookScanRow] = []
    filtered_out: list[PlaybookScanRow] = []

    for ticker in tickers:
        LOGGER.info("Playbook scan for %s", ticker)
        analysis_summary_path = output_dir / f"{ticker.lower()}_analysis_summary.json"

        # Build command for single ticker analysis
        command = _batch_command_for_ticker(
            args,
            ticker,
            Path(f"{ticker.lower()}_temp.html"),
            analysis_summary_path=analysis_summary_path,
        )

        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            # Analysis failed - add to filtered with error
            err_row = PlaybookScanRow(
                ticker=ticker,
                earnings_date="N/A",
                vol_regime="N/A",
                edge_ratio="N/A",
                positioning="N/A",
                signal="N/A",
                type_=5,
                confidence="N/A",
                action="ANALYSIS ERROR",
                is_type5=True,
                error_message=f"rc={result.returncode}: {_extract_failure_reason(result)}",
            )
            filtered_out.append(err_row)
            LOGGER.error(
                "Playbook scan failed for %s: rc=%d", ticker, result.returncode
            )
            continue

        # Load the generated snapshot JSON
        if not analysis_summary_path.exists():
            err_row = PlaybookScanRow(
                ticker=ticker,
                earnings_date="N/A",
                vol_regime="N/A",
                edge_ratio="N/A",
                positioning="N/A",
                signal="N/A",
                type_=5,
                confidence="N/A",
                action="NO SNAPSHOT",
                is_type5=True,
                error_message="analysis_summary.json not generated",
            )
            filtered_out.append(err_row)
            continue

        try:
            snapshot = json.loads(analysis_summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            err_row = PlaybookScanRow(
                ticker=ticker,
                earnings_date="N/A",
                vol_regime="N/A",
                edge_ratio="N/A",
                positioning="N/A",
                signal="N/A",
                type_=5,
                confidence="N/A",
                action="JSON ERROR",
                is_type5=True,
                error_message="failed to parse analysis_summary.json",
            )
            filtered_out.append(err_row)
            continue

        # Check TYPE classification in snapshot
        # (type_val extracted via create_scan_row_from_snapshot)

        # Create a PlaybookScanRow from the snapshot
        scan_row = create_scan_row_from_snapshot(ticker, snapshot)
        rows.append(scan_row)

    # Sort by TYPE (non-TYPE5 first)
    rows = sort_playbook_rows(rows)

    # Build result and compute summary
    playbook_result = PlaybookScanResult(
        rows=rows,
        filtered_out=filtered_out,
        frequency_warning_fired=False,
    )
    playbook_result.compute_summary()

    # Print console table
    console_output = format_console_table(rows)
    print("\n" + console_output)

    # Print filtered out section
    if filtered_out:
        print("\n" + "=" * 40)
        print("FILTERED OUT")
        print("=" * 40)
        for frow in filtered_out:
            reason = frow.filter_reason or frow.error_message or "unknown"
            print(f"  {frow.ticker}: {reason}")

    # Print frequency warning if present
    if playbook_result.frequency_warning_fired:
        print("\n" + "!" * 40)
        print("FREQUENCY WARNING: >10% of universe is TYPE 1")
        print("Cheapness metric may be miscalibrated.")
        print("!" * 40)

    # Save report
    report_path = save_playbook_scan_report(playbook_result, output_dir)
    LOGGER.info("Playbook scan report saved to %s", report_path)

    return True


def main() -> None:
    """Run earnings vol analysis pipeline."""
    if len(sys.argv) > 1 and sys.argv[1] == "query":
        raise SystemExit(_run_query_cli(sys.argv[2:]))

    parser = argparse.ArgumentParser(description="Earnings vol analysis")
    ticker_group = parser.add_mutually_exclusive_group()
    ticker_group.add_argument(
        "--ticker",
        type=str,
        default=config.TICKER,
        help="Underlying ticker symbol (default: %(default)s)",
    )
    ticker_group.add_argument(
        "--tickers",
        nargs="+",
        default=None,
        help="Run in batch mode for explicit ticker list",
    )
    ticker_group.add_argument(
        "--ticker-file",
        type=str,
        default=None,
        help="Run in batch mode from comma/newline ticker file",
    )
    parser.add_argument("--event-date", type=str, help="YYYY-MM-DD")
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help=(
            "Output HTML report path (default: reports/<ticker>_earnings_report.html)"
        ),
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
        "--cache-only",
        action="store_true",
        help="Fail if required cache data is missing; do not fetch live options.",
    )
    parser.add_argument(
        "--cache-spot",
        type=float,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--cache-front-expiry",
        type=str,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--cache-back1-expiry",
        type=str,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--cache-back2-expiry",
        type=str,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for Monte Carlo reproducibility",
    )
    parser.add_argument(
        "--move-model",
        type=str,
        default=config.MOVE_MODEL_DEFAULT,
        choices=list(config.MOVE_MODELS),
        help=("Monte Carlo move model (lognormal or fat_tailed; default: %(default)s)"),
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
    parser.add_argument(
        "--batch-output-dir",
        type=str,
        default="reports/batch",
        help="Directory for per-ticker reports in batch mode",
    )
    parser.add_argument(
        "--batch-summary-json",
        type=str,
        default=None,
        help="Optional JSON summary output path for batch runs",
    )
    parser.add_argument(
        "--analysis-summary-json",
        type=str,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="deep-dive",
        choices=["deep-dive", "playbook-scan"],
        help=(
            "Report mode: 'deep-dive' for full per-ticker HTML, "
            "'playbook-scan' for condensed morning scan table (default: %(default)s)"
        ),
    )
    args = parser.parse_args()
    if not hasattr(args, "move_model"):
        args.move_model = config.MOVE_MODEL_DEFAULT

    batch_requested = args.tickers is not None or args.ticker_file is not None
    if batch_requested:
        if args.ticker_file:
            tickers = _load_tickers_from_file(args.ticker_file)
        else:
            tickers = [ticker.upper() for ticker in args.tickers if ticker]
            tickers = list(dict.fromkeys(tickers))
        if not tickers:
            raise ValueError("No valid tickers provided for batch mode.")
    else:
        tickers = [args.ticker.upper()]
    ticker = tickers[0]

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if batch_requested:
        mode = getattr(args, "mode", "deep-dive")
        if mode == "playbook-scan":
            ok = _run_playbook_scan_mode(args, tickers)
            if not ok:
                raise SystemExit(1)
            return
        if args.output is not None:
            LOGGER.warning(
                "--output is ignored in batch mode; using --batch-output-dir"
            )
        ok = _run_batch_mode(args, tickers)
        if not ok:
            raise SystemExit(1)
        return

    if args.output is None:
        args.output = f"reports/{ticker.lower()}_earnings_report.html"

    event_date_source = "provided"

    # Branch: test data vs live data
    if args.test_data:
        event_date_source = "test_data"
        test_data = _load_test_data_mode(args)
        spot = test_data["spot"]
        div_yield = config.DIVIDEND_YIELD
        cal: dict = {}  # no calibration in test mode; use config defaults
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
        event_date_source = "provided" if event_date is not None else "auto"
        if event_date is None:
            resolution: EventDateResolution = resolve_next_earnings_date(ticker)
            if resolution.status != "resolved" or resolution.event_date is None:
                message = (
                    "Event date not provided and auto-discovery failed for "
                    f"{ticker}: {resolution.message}"
                )
                LOGGER.error("%s", message)
                raise SystemExit(2)
            event_date = resolution.event_date
            LOGGER.info("%s", resolution.message)
        event_date = _normalize_event_date(event_date)
        # Allow past event dates for test mode, but require future for live
        if not args.test_data and event_date <= dt.date.today():
            LOGGER.warning(
                "Event date %s is not in the future. Proceeding anyway for testing.",
                event_date,
            )

        cache_only = bool(getattr(args, "cache_only", False))
        cache_spot = getattr(args, "cache_spot", None)
        cache_front_expiry_raw = getattr(args, "cache_front_expiry", None)
        cache_back1_expiry_raw = getattr(args, "cache_back1_expiry", None)
        cache_back2_expiry_raw = getattr(args, "cache_back2_expiry", None)
        cache_front_expiry: dt.date | None = None
        cache_back1_expiry: dt.date | None = None
        cache_back2_expiry: dt.date | None = None
        if cache_front_expiry_raw:
            cache_front_expiry = dt.date.fromisoformat(str(cache_front_expiry_raw))
        if cache_back1_expiry_raw:
            cache_back1_expiry = dt.date.fromisoformat(str(cache_back1_expiry_raw))
        if cache_back2_expiry_raw:
            cache_back2_expiry = dt.date.fromisoformat(str(cache_back2_expiry_raw))

        try:
            if cache_spot is not None:
                spot = float(cache_spot)
            else:
                spot = get_spot_price(ticker)
            div_yield = get_dividend_yield(ticker)
            LOGGER.info("Dividend yield for %s: %.4f", ticker, div_yield)
            if cache_front_expiry is not None:
                front_expiry = cache_front_expiry
                post_event = get_expiries_after([front_expiry], event_date)
                if not post_event:
                    raise ValueError("Cached front expiry is before event date.")
                if cache_back1_expiry is not None:
                    back1_expiry = cache_back1_expiry
                else:
                    back1_expiry = front_expiry
                back2_expiry = cache_back2_expiry
            else:
                expiries = get_option_expiries(ticker)
                front_expiry = select_front_expiry(
                    expiries,
                    event_date,
                    ticker=ticker,
                    event_time_label=_lookup_event_time_label(ticker, event_date),
                )
                post_event = get_expiries_after(expiries, front_expiry)
                if len(post_event) < 2:
                    raise ValueError("Insufficient expiries after event date.")
                back1_expiry = post_event[1]
                back2_expiry = post_event[2] if len(post_event) > 2 else None

            _validate_front_expiry(event_date, front_expiry)

            cache_dir = Path(args.cache_dir)

            # Calibrate liquidity/wing-width params from the raw (unfiltered)
            # front chain before applying any filters.
            raw_front = get_options_chain(
                ticker,
                front_expiry,
                cache_dir=cache_dir if args.use_cache else None,
                use_cache=args.use_cache,
                cache_only=cache_only,
            )
            cal = calibrate_ticker_params(ticker, raw_front, spot)

            front_chain = _load_filtered_chain(
                front_expiry,
                spot,
                cache_dir,
                args.use_cache,
                args.refresh_cache,
                cache_only=cache_only,
                ticker=ticker,
                min_oi=cal["min_oi"],
                max_spread_pct=cal["max_spread_pct"],
            )
            back1_chain = _load_filtered_chain(
                back1_expiry,
                spot,
                cache_dir,
                args.use_cache,
                args.refresh_cache,
                cache_only=cache_only,
                ticker=ticker,
                min_oi=cal["min_oi"],
                max_spread_pct=cal["max_spread_pct"],
            )
            back2_chain = (
                _load_filtered_chain(
                    back2_expiry,
                    spot,
                    cache_dir,
                    args.use_cache,
                    args.refresh_cache,
                    cache_only=cache_only,
                    ticker=ticker,
                    min_oi=cal["min_oi"],
                    max_spread_pct=cal["max_spread_pct"],
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
            history = get_price_history(ticker, config.HISTORY_YEARS)
            earnings_dates = get_earnings_dates(ticker)
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
    aligned_earnings_dates, signed_moves = extract_earnings_moves_with_dates(
        history,
        earnings_dates,
    )
    dist_shape = compute_distribution_shape(signed_moves)
    fat_tail_inputs = calibrate_fat_tail_inputs(signed_moves)
    target_excess_kurtosis = float(fat_tail_inputs["target_excess_kurtosis"])
    historical_sample_size = int(fat_tail_inputs["sample_size"])

    abs_moves = [abs(move) for move in signed_moves]
    conditional_expected = conditional_expected_move(abs_moves)
    timing_splits = split_by_timing(ticker, aligned_earnings_dates, signed_moves)
    resolved_event_timing = _resolve_event_timing_bucket(
        ticker,
        event_date,
        fallback_split=timing_splits,
    )
    if resolved_event_timing in {"amc", "bmo"}:
        split_moves = timing_splits.get(resolved_event_timing, [])
        if len(split_moves) >= 4:
            conditional_expected = conditional_expected_move(
                split_moves,
                timing=resolved_event_timing,
            )
        else:
            LOGGER.warning(
                "Insufficient %s observations (%d) for %s; falling back to combined.",
                resolved_event_timing,
                len(split_moves),
                ticker,
            )
            conditional_expected = conditional_expected_move(
                abs_moves, timing="combined"
            )
    elif resolved_event_timing == "unknown":
        conditional_expected = conditional_expected_move(abs_moves, timing="unknown")

    edge_ratio = compute_edge_ratio(implied_move, conditional_expected)

    atm_iv_history = load_atm_iv_history_from_store(ticker)

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
        float(event_info["front_iv"]) if event_info["front_iv"] is not None else 0.0
    )
    back_iv = float(event_info["back_iv"]) if event_info["back_iv"] is not None else 0.0
    back2_iv = event_info.get("back2_iv")
    event_vol = float(event_info.get("event_vol_daily", 0.0) or 0.0)
    event_vol_ratio = event_vol / max(front_iv, config.TIME_EPSILON)
    simulation_event_vol = _resolve_simulation_event_vol(
        event_vol=event_vol,
        implied_move=implied_move,
    )

    # Calibrate IV scenario magnitudes from event vol structure (live only)
    if not args.test_data and front_iv > 0 and back_iv > 0:
        event_variance_ratio = float(event_info.get("event_variance_ratio", 0.0))
        calibrate_iv_scenarios(front_iv, back_iv, event_variance_ratio)

    # Get term structure note from event_info
    term_structure_note = event_info.get("term_structure_note")

    t_front = business_days(dt.date.today(), front_expiry) / 252.0
    t_front = max(t_front, config.TIME_EPSILON)
    t_back1_gex = business_days(dt.date.today(), back1_expiry) / 252.0
    t_back1_gex = max(t_back1_gex, config.TIME_EPSILON)
    gex = gex_summary(front_chain, spot, t_front, div_yield=div_yield)
    back_gex_result = gex_summary(back1_chain, spot, t_back1_gex, div_yield=div_yield)
    skew = skew_metrics(front_chain, spot, t_front, div_yield=div_yield)

    pc_5d, pc_20d_avg = _estimate_put_call_proxy(front_chain)
    ticker_10d_ret = _compute_recent_return(history, days=10)
    sector_10d_ret = None
    positioning = classify_positioning(
        oi_concentration(front_chain),
        pc_ratio_signal(pc_5d, pc_20d_avg),
        drift_vs_sector(ticker_10d_ret, sector_10d_ret),
        max_pain_distance(front_chain, spot),
    )

    signal_graph = _build_single_ticker_signal_graph(
        ticker=ticker,
        event_date=event_date,
    )

    gex_large_abs = cal.get("gex_large_abs", config.GEX_LARGE_ABS)
    gex_note = None
    if gex["abs_gex"] >= gex_large_abs and abs(gex["net_gex"]) / gex["abs_gex"] < 0.1:
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
    short_delta = abs(
        bsm_delta(
            spot,
            atm_strike,
            t_front,
            config.RISK_FREE_RATE,
            div_yield,
            front_iv,
            "call",
        )
    )

    early_snapshot = {
        "iv_ratio": iv_ratio,
        "event_variance_ratio": event_info.get("event_variance_ratio", 0.0),
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
        shock_vol = max(simulation_event_vol * (1 + shock / 100.0), 0.0)
        seed = None if args.seed is None else args.seed + shock + 1000
        moves_by_shock[shock] = simulate_moves(
            shock_vol,
            config.MC_SIMULATIONS,
            seed=seed,
            model=args.move_model,
            target_excess_kurtosis=target_excess_kurtosis,
            historical_sample_size=historical_sample_size,
        )

    comparison_seed = 0 if args.seed is None else args.seed + 777
    lognormal_moves = simulate_moves(
        simulation_event_vol,
        config.MC_SIMULATIONS,
        seed=comparison_seed,
        model="lognormal",
    )
    fat_tailed_moves = simulate_moves(
        simulation_event_vol,
        config.MC_SIMULATIONS,
        seed=comparison_seed,
        model="fat_tailed",
        target_excess_kurtosis=target_excess_kurtosis,
        historical_sample_size=historical_sample_size,
    )

    simulation_comparison = {
        "lognormal": {
            "mean_abs_move": float(np.mean(np.abs(lognormal_moves))),
            "abs_q10": _safe_abs_quantile(lognormal_moves, 0.10),
            "abs_q50": _safe_abs_quantile(lognormal_moves, 0.50),
            "abs_q90": _safe_abs_quantile(lognormal_moves, 0.90),
            "p95_abs_move": float(np.percentile(np.abs(lognormal_moves), 95)),
            "tail_prob_gt_6pct": float(np.mean(np.abs(lognormal_moves) > 0.06)),
            "tail_prob_gt_10pct": float(np.mean(np.abs(lognormal_moves) > 0.10)),
        },
        "fat_tailed": {
            "mean_abs_move": float(np.mean(np.abs(fat_tailed_moves))),
            "abs_q10": _safe_abs_quantile(fat_tailed_moves, 0.10),
            "abs_q50": _safe_abs_quantile(fat_tailed_moves, 0.50),
            "abs_q90": _safe_abs_quantile(fat_tailed_moves, 0.90),
            "p95_abs_move": float(np.percentile(np.abs(fat_tailed_moves), 95)),
            "tail_prob_gt_6pct": float(np.mean(np.abs(fat_tailed_moves) > 0.06)),
            "tail_prob_gt_10pct": float(np.mean(np.abs(fat_tailed_moves) > 0.10)),
        },
    }

    implied_abs_reference = _implied_abs_move_reference(
        implied_move,
        len(fat_tailed_moves),
        seed=comparison_seed + 911,
    )
    ks_result = stats.ks_2samp(np.abs(fat_tailed_moves), implied_abs_reference)
    simulation_comparison["fat_tailed"]["ks_statistic"] = float(ks_result.statistic)
    simulation_comparison["fat_tailed"]["ks_pvalue"] = float(ks_result.pvalue)

    trust_metrics = _compute_trust_metrics(
        implied_move=implied_move,
        simulation_comparison=simulation_comparison,
    )

    strangle_offset = implied_move * 0.8
    strategies = build_strategies(
        front_chain,
        back1_chain,
        spot,
        strangle_offset_pct=strangle_offset,
    )

    # ── Conditionally add backspreads ─────────────────────────────
    wing_width_pct = cal.get(
        "backspread_min_wing_width_pct",
        config.BACKSPREAD_MIN_WING_WIDTH_PCT,
    )
    front_expiry_ts = pd.Timestamp(front_expiry)
    if should_build_strategy("CALL_BACKSPREAD", early_snapshot):
        call_bs = build_call_backspread(
            front_chain,
            spot,
            front_expiry_ts,
            wing_width_pct=wing_width_pct,
        )
        if call_bs is not None:
            strategies.append(call_bs)
            LOGGER.info("Added call_backspread to strategy pool.")
    if should_build_strategy("PUT_BACKSPREAD", early_snapshot):
        put_bs = build_put_backspread(
            front_chain,
            spot,
            front_expiry_ts,
            wing_width_pct=wing_width_pct,
        )
        if put_bs is not None:
            strategies.append(put_bs)
            LOGGER.info("Added put_backspread to strategy pool.")
    combined_chain = pd.concat([front_chain, back1_chain], ignore_index=True)
    chain_lookup = _build_chain_lookup(combined_chain)

    # Collect conditional strategies that did NOT qualify (for report)
    not_applicable: list[dict] = []
    for cond_name in ("CALL_BACKSPREAD", "PUT_BACKSPREAD", "POST_EVENT_CALENDAR"):
        if not should_build_strategy(cond_name, early_snapshot):
            not_applicable.append(
                {
                    "name": cond_name,
                    "reason": _not_applicable_reason(cond_name, early_snapshot),
                }
            )
    short_vol_dte_weight = _short_vol_dte_weight(front_dte)
    short_vol_evidence = _short_vol_evidence_gate(ticker)
    if not short_vol_evidence["allowed"]:
        evidence_reason = (
            "short-vol evidence gate failed: "
            f"{short_vol_evidence['note']}"
        )
        not_applicable.extend(
            [
                {"name": "IRON_CONDOR", "reason": evidence_reason},
                {"name": "CALENDAR", "reason": evidence_reason},
            ]
        )

    results = []
    for strategy in strategies:
        if (
            strategy.name in _SHORT_VOL_STRATEGY_NAMES
            and not short_vol_evidence["allowed"]
        ):
            LOGGER.info(
                "Skipping short-vol strategy %s due to evidence gate: %s",
                strategy.name,
                short_vol_evidence["note"],
            )
            continue
        try:
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
                div_yield=div_yield,
            )
        except ValueError as exc:
            LOGGER.warning("Skipping strategy %s: %s", strategy.name, exc)
            continue

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
                div_yield=div_yield,
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
                    div_yield=div_yield,
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
            div_yield=div_yield,
        )
        metrics["net_delta"] = net_greeks["delta"]
        metrics["net_gamma"] = net_greeks["gamma"]
        metrics["net_vega"] = net_greeks["vega"]
        metrics["net_theta"] = net_greeks["theta"]
        metrics["risk_weight"] = 1.0
        if strategy.name in _SHORT_VOL_STRATEGY_NAMES:
            metrics["risk_weight"] = short_vol_dte_weight
            metrics["ev"] = float(metrics["ev"]) * short_vol_dte_weight
            metrics["capital_normalized_ev"] = (
                float(metrics["capital_normalized_ev"]) * short_vol_dte_weight
            )
        pnls = base_pnls
        metrics["pnls"] = pnls
        results.append(metrics)

    ranked = score_strategies(results)
    if not ranked:
        LOGGER.error("No viable strategies after liquidity/DTE filtering.")
        return

    trust_gate_failed = trust_metrics.get("status") == "FAIL"
    if trust_gate_failed:
        LOGGER.warning(
            "Trust gate failed (score %.1f, dir=%s): suppressing recommendations.",
            float(trust_metrics.get("trust_score", 0.0)),
            str(trust_metrics.get("mismatch_direction", "matched")),
        )
        not_applicable.append(
            {
                "name": "TRUST_GATE",
                "reason": (
                    "Ranking suppressed due to trust score "
                    f"{float(trust_metrics.get('trust_score', 0.0)):.1f} "
                    f"(direction={str(trust_metrics.get('mismatch_direction', 'matched'))})"
                ),
            }
        )

    top = ranked[0]
    if trust_gate_failed:
        ev_base = 0.0
        ev_2x = 0.0
        pnl_plot = plot_pnl_distribution(
            np.array([0.0]),
            "Trust gate blocked strategy ranking",
        )
    else:
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
        pnl_plot = plot_pnl_distribution(
            top["pnls"],
            f"Top Strategy: {top['strategy']}",
        )

    expected_move_dollar = max(implied_move, hist_p75) * spot * 100
    move_plot = plot_move_comparison(implied_move, hist_p75)
    rr25_raw = skew["rr25"]
    bf25_raw = skew["bf25"]
    rr25_value = f"{skew['rr25']:.4f}" if skew["rr25"] is not None else "N/A"
    bf25_value = f"{skew['bf25']:.4f}" if skew["bf25"] is not None else "N/A"

    # Build comprehensive snapshot (includes early_snapshot fields)
    snapshot = {
        "spot": spot,
        "ticker": ticker,
        "event_date": event_date,
        "front_expiry": front_expiry,
        "back_expiry": back1_expiry,
        "implied_move": implied_move,
        "historical_p75": hist_p75,
        "front_iv": front_iv,
        "back_iv": back_iv,
        "back2_iv": back2_iv,
        "event_vol": event_vol,
        "simulation_event_vol": simulation_event_vol,
        "event_vol_ratio": event_vol_ratio,
        "expected_move_dollar": expected_move_dollar,
        "raw_event_var": event_info["raw_event_var"],
        "event_variance_ratio": event_info.get("event_variance_ratio", 0.0),
        "front_back_spread": event_info.get("front_back_spread", 0.0),
        "back_slope": event_info.get("back_slope"),
        "t_front": event_info.get("t_front", t_front),
        "t_back1": event_info.get("t_back1", t_front + 20 / 252),
        "interpolation_method": event_info.get("interpolation_method", "unknown"),
        "negative_event_var": event_info.get("negative_event_var", False),
        "term_structure_note": term_structure_note,
        "warning_level": event_info["warning_level"],
        "assumption": event_info["assumption"],
        "gex_net": gex["net_gex"],
        "gex_abs": gex["abs_gex"],
        "front_gex": gex["net_gex"],
        "back_gex": back_gex_result["net_gex"],
        "gamma_flip": gex.get("gamma_flip"),
        "flip_distance_pct": gex.get("flip_distance_pct"),
        "top_gamma_strikes": gex.get("top_gamma_strikes", []),
        "gex_by_strike_top": sorted(
            gex.get("gex_by_strike", []),
            key=lambda row: abs(float(row[1])),
            reverse=True,
        )[:15],
        "gex_by_strike": gex.get("gex_by_strike", []),
        "pin_strikes": gex.get("pin_strikes", []),
        "vanna_net": gex.get("vanna_net", 0.0),
        "charm_net": gex.get("charm_net", 0.0),
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
        "atm_iv_history": atm_iv_history,
        "conditional_expected": {
            "median": conditional_expected.median,
            "trimmed_mean": conditional_expected.trimmed_mean,
            "recency_weighted": conditional_expected.recency_weighted,
            "timing_method": conditional_expected.timing_method,
            "n_observations": conditional_expected.n_observations,
            "data_quality": conditional_expected.data_quality,
            "conditioning_applied": conditional_expected.conditioning_applied,
            "primary_estimate": conditional_expected.primary_estimate,
            "peer_conditioned": conditional_expected.peer_conditioned,
        },
        "edge_ratio": {
            "implied": edge_ratio.implied,
            "conditional_expected_primary": edge_ratio.conditional_expected_primary,
            "ratio": edge_ratio.ratio,
            "label": edge_ratio.label,
            "confidence": edge_ratio.confidence,
            "secondary_ratio": edge_ratio.secondary_ratio,
            "label_disagreement": edge_ratio.label_disagreement,
            "note": edge_ratio.note,
            "low_confidence_caveat": EDGE_RATIO_LOW_CONFIDENCE_CAVEAT,
        },
        "positioning": {
            "label": positioning.label,
            "direction": positioning.direction,
            "confidence": positioning.confidence,
            "available_count": positioning.available_count,
            "note": positioning.note,
            "signals": {
                name: {
                    "signal": signal.signal.value,
                    "is_available": signal.is_available,
                    "note": signal.note,
                }
                for name, signal in positioning.signals.items()
            },
        },
        "signal_graph": {
            "edges": [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "revenue_overlap": edge.revenue_overlap,
                    "factor_overlap": edge.factor_overlap,
                    "weight": edge.weight,
                }
                for edge in signal_graph.edges
            ],
            "nodes": {
                symbol: {
                    "ticker": node.ticker,
                    "role": node.role,
                    "event_date": node.event_date.isoformat(),
                    "has_signal": node.has_signal,
                    "signal_decay_status": node.signal_decay_status,
                }
                for symbol, node in signal_graph.nodes.items()
            },
            "tradeable_followers": [
                node.ticker for node in signal_graph.tradeable_followers
            ],
            "absorbed_followers": [
                node.ticker for node in signal_graph.absorbed_followers
            ],
        },
        "timing_splits": {
            "amc": len(timing_splits.get("amc", [])),
            "bmo": len(timing_splits.get("bmo", [])),
            "unknown": len(timing_splits.get("unknown", [])),
        },
        "move_model_selected": args.move_model,
        "move_model_default": config.MOVE_MODEL_DEFAULT,
        "fat_tail_calibration": fat_tail_inputs,
        "simulation_comparison": simulation_comparison,
        "trust_metrics": trust_metrics,
        "short_vol_dte_weight": short_vol_dte_weight,
        "short_vol_evidence": short_vol_evidence,
        "rr25": rr25_value,
        "bf25": bf25_value,
        "rr25_raw": rr25_raw,
        "bf25_raw": bf25_raw,
        "ev_base": ev_base,
        "ev_2x": ev_2x,
    }
    # Merge early snapshot fields used by strategy gates
    snapshot.update(early_snapshot)

    # Classify regime
    regime = classify_regime(snapshot)
    snapshot["regime"] = regime

    event_state = {
        "event_date": event_date,
        "today": today,
        "phase1_category": None,
        "phase1_metrics": {
            "move_vs_implied": None,
        },
    }
    type_classification = classify_type(
        vol_regime=regime,
        edge_ratio=snapshot["edge_ratio"],
        positioning=snapshot["positioning"],
        signal_graph=signal_graph,
        event_state=event_state,
        operator_inputs={
            "falsifier": None,
            "narrative_label": None,
            "has_position": None,
        },
    )
    snapshot["type_classification"] = {
        "type": type_classification.type,
        "rationale": type_classification.rationale,
        "action_guidance": type_classification.action_guidance,
        "phase2_checklist": type_classification.phase2_checklist,
        "confidence": type_classification.confidence,
        "is_no_trade": type_classification.is_no_trade,
        "frequency_warning": type_classification.frequency_warning,
    }

    try:
        store_prediction(
            ticker=ticker,
            event_date=event_date,
            type_classification=snapshot["type_classification"],
            edge_ratio=snapshot["edge_ratio"],
            vol_regime=regime,
            timing=resolved_event_timing.upper(),
        )
    except ValueError as exc:
        LOGGER.info("Outcome prediction not stored (%s): %s", ticker, exc)

    ranking_payload = ranked if not trust_gate_failed else []

    # Compute alignment for all strategies
    compute_all_alignments(ranking_payload, regime)

    # ── Post-event calendar (separate evaluation model) ───────────
    post_event_cal = None
    if (not trust_gate_failed) and should_build_strategy(
        "POST_EVENT_CALENDAR", early_snapshot
    ):
        t_back1 = max(back_dte / 365.0, config.TIME_EPSILON)
        pe_result = build_post_event_calendar(
            spot,
            atm_strike,
            front_iv,
            back_iv,
            t_front,
            t_back1,
            pd.Timestamp(front_expiry),
            pd.Timestamp(back1_expiry),
            div_yield=div_yield,
        )
        pe_scenarios = compute_post_event_calendar_scenarios(
            spot=spot,
            K=atm_strike,
            t_short=t_front,
            t_long=t_back1,
            iv_long=back_iv,
            net_cost=pe_result["net_cost"],
            div_yield=div_yield,
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

    generic_event = snapshot_to_event_spec(ticker, snapshot)
    generic_market_context = snapshot_to_market_context(snapshot)
    generic_playbook = build_playbook_recommendation(
        generic_event,
        generic_market_context,
        ranking_payload,
        rationale_map=STRATEGY_RATIONALE,
        regime=regime,
        not_applicable=not_applicable,
    )

    report_path = Path(args.output)
    write_report(
        report_path,
        {
            "ticker": ticker,
            "snapshot": snapshot,
            "regime": regime,
            "rankings": ranking_payload,
            "move_plot": move_plot,
            "pnl_plot": pnl_plot,
            "post_event_calendar": post_event_cal,
            "not_applicable": not_applicable,
            "strategy_rationale": STRATEGY_RATIONALE,
            "generic_event": generic_event.to_dict(),
            "generic_market_context": generic_market_context.to_dict(),
            "generic_playbook": generic_playbook.to_dict(),
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
        snapshot,
    )

    analysis_summary_path = getattr(args, "analysis_summary_json", None)
    if analysis_summary_path:
        blocking_warnings: list[str] = []
        if snapshot.get("negative_event_var"):
            blocking_warnings.append("negative_event_var")
        if snapshot.get("warning_level"):
            blocking_warnings.append(f"event_var_warning:{snapshot['warning_level']}")
        if snapshot.get("term_structure_note"):
            blocking_warnings.append("term_structure_inversion")
        if snapshot.get("gex_note"):
            blocking_warnings.append("gex_concentration_ambiguous")
        if snapshot.get("trust_metrics", {}).get("status") == "FAIL":
            blocking_warnings.append("trust_gate_failed")

        analysis_summary = {
            "ticker": ticker,
            "event_date": str(event_date),
            "event_date_source": event_date_source,
            "regime": regime.get("composite_regime"),
            "top_structure": None if trust_gate_failed else top.get("name"),
            "score": (
                None
                if trust_gate_failed
                else round(float(top.get("score", 0.0)), 4)
            ),
            "move_model": args.move_model,
            "implied_move": snapshot.get("implied_move"),
            "front_iv": snapshot.get("front_iv"),
            "back_iv": snapshot.get("back_iv"),
            "trust_metrics": snapshot.get("trust_metrics"),
            "blocking_warnings": blocking_warnings,
            # Full TYPE classification for playbook scan
            "vol_regime": {
                "vol_regime": regime.get("vol_regime"),
                "vol_regime_legacy": regime.get("vol_regime_legacy"),
                "ivr": regime.get("ivr"),
                "ivp": regime.get("ivp"),
                "vol_confidence": regime.get("vol_confidence"),
                "vol_confidence_label": regime.get("vol_confidence_label"),
                "event_regime": regime.get("event_regime"),
                "term_structure_regime": regime.get("term_structure_regime"),
                "gamma_regime": regime.get("gamma_regime"),
                "composite_regime": regime.get("composite_regime"),
                "confidence": regime.get("confidence"),
            },
            "edge_ratio": snapshot.get("edge_ratio"),
            "positioning": snapshot.get("positioning"),
            "signal_graph": snapshot.get("signal_graph"),
            "type_classification": snapshot.get("type_classification"),
        }
        summary_path = Path(analysis_summary_path)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(analysis_summary, indent=2),
            encoding="utf-8",
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


def _estimate_put_call_proxy(chain: pd.DataFrame) -> tuple[float | None, float | None]:
    """Estimate put/call proxies from current chain volume when available."""

    if "volume" not in chain.columns or "option_type" not in chain.columns:
        return None, None

    frame = chain.copy()
    frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0)
    frame["option_type"] = frame["option_type"].astype(str).str.lower()
    call_volume = float(frame.loc[frame["option_type"] == "call", "volume"].sum())
    put_volume = float(frame.loc[frame["option_type"] == "put", "volume"].sum())
    if call_volume <= 0.0:
        return None, None

    ratio = put_volume / call_volume
    return ratio, ratio


def _compute_recent_return(history: pd.DataFrame, days: int = 10) -> float | None:
    """Compute simple close-to-close return over trailing N sessions."""

    if history.empty or "Close" not in history.columns:
        return None

    closes = pd.to_numeric(history["Close"], errors="coerce").dropna()
    if len(closes) <= days:
        return None

    start = float(closes.iloc[-(days + 1)])
    end = float(closes.iloc[-1])
    if start <= 0.0:
        return None
    return end / start - 1.0


def _build_single_ticker_signal_graph(
    ticker: str,
    event_date: dt.date,
) -> SignalGraphResult:
    """Build one-name signal graph with config-backed metadata."""

    try:
        sector_map, factor_map = load_signal_graph_config()
    except (FileNotFoundError, ValueError):
        return build_signal_graph_result(
            pd.DataFrame(columns=["ticker", "event_date", "sector", "factors"]),
            {},
            {},
            dt.date.today(),
            {},
        )

    calendar_df = pd.DataFrame(
        [
            {
                "ticker": ticker,
                "event_date": event_date,
                "sector": None,
                "factors": None,
            }
        ]
    )
    return build_signal_graph_result(
        calendar_df,
        sector_map,
        factor_map,
        dt.date.today(),
        price_moves={},
    )


def _load_filtered_chain(
    expiry: dt.date | None,
    spot: float,
    cache_dir: Path,
    use_cache: bool,
    refresh_cache: bool,
    cache_only: bool = False,
    ticker: str | None = None,
    min_oi: int = config.MIN_OI,
    max_spread_pct: float = config.MAX_SPREAD_PCT,
    allow_empty: bool = False,
) -> pd.DataFrame | None:
    if expiry is None:
        return None
    resolved_ticker = (ticker or config.TICKER).upper()
    chain = get_options_chain(
        resolved_ticker,
        expiry,
        cache_dir=cache_dir,
        use_cache=use_cache,
        refresh_cache=refresh_cache,
        cache_only=cache_only,
    )
    LOGGER.info("Options rows pre-filter for %s: %d", expiry, len(chain))
    chain = filter_by_moneyness(
        chain,
        spot,
        config.MONEYNESS_LOW,
        config.MONEYNESS_HIGH,
    )
    chain = filter_by_liquidity(chain, min_oi, max_spread_pct)
    LOGGER.info("Options rows post-filter for %s: %d", expiry, len(chain))
    if chain.empty:
        if allow_empty:
            return None
        raise ValueError(
            f"No options remain after filtering for {expiry} "
            f"(OI>={min_oi}, spread<={max_spread_pct}, "
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
    snapshot: dict | None = None,
) -> None:
    print("\n" + "=" * 60)
    print("VOLATILITY DIAGNOSTICS")
    print("=" * 60)
    print(f"ImpliedMove:        {implied_move:.4f}")
    print(f"Historical P75:       {hist_p75:.4f}")
    implied_ratio = implied_move / max(hist_p75, 1e-9)
    print(f"ImpliedMove / P75:    {implied_ratio:.4f}")
    print(f"EventVol:             {event_vol:.4f}")
    print(f"EventVol / FrontIV:   {event_vol_ratio:.4f}")
    if snapshot and snapshot.get("trust_metrics"):
        trust = snapshot["trust_metrics"]
        print(f"Trust Gate:           {trust['status']}")
        print(f"Trust Score:          {trust.get('trust_score', 0.0):.1f}")
        print(f"Mismatch Ratio:       {trust['mismatch_ratio']:.2f}x")
        print(f"Mismatch Direction:   {trust.get('mismatch_direction', 'matched')}")
        if trust["status"] == "FAIL":
            print("TRUST GATE FAILED: quantile consistency check failed")
    if snapshot and snapshot.get("simulation_event_vol") is not None:
        print(f"Sim Sigma (daily):    {snapshot['simulation_event_vol']:.4f}")

    if regime:
        print("\n" + "=" * 60)
        print("REGIME CLASSIFICATION")
        print("=" * 60)
        print(f"Vol Pricing:          {regime['vol_regime']}")
        if regime.get("vol_regime_legacy"):
            print(f"Vol Pricing (legacy): {regime['vol_regime_legacy']}")
        if regime.get("ivr") is not None and regime.get("ivp") is not None:
            print(f"IVR / IVP:            {regime['ivr']:.1f} / {regime['ivp']:.1f}")
            print(f"Vol Confidence:       {regime.get('vol_confidence_label', 'LOW')}")
        print(f"Event Structure:      {regime['event_regime']}")
        print(f"Term Structure:       {regime['term_structure_regime']}")
        print(f"Gamma Regime:         {regime['gamma_regime']}")
        print(f"Composite Regime:     {regime['composite_regime']}")
        print(f"Composite Confidence: {regime['confidence']:.2f}")

    if snapshot and snapshot.get("edge_ratio"):
        edge = snapshot["edge_ratio"]
        print("\n" + "=" * 60)
        print("EDGE RATIO")
        print("=" * 60)
        print(f"Ratio:                {edge['ratio']:.3f}")
        print(f"Label:                {edge['label']}")
        print(f"Confidence:           {edge['confidence']}")
        if edge.get("confidence") == "LOW":
            print(EDGE_RATIO_LOW_CONFIDENCE_CAVEAT)

    if snapshot and snapshot.get("type_classification"):
        t = snapshot["type_classification"]
        print("\n" + "=" * 60)
        print("TYPE CLASSIFICATION")
        print("=" * 60)
        print(f"TYPE:                 {t['type']}")
        print(f"Confidence:           {t['confidence']}")
        print(f"Action:               {t['action_guidance']}")

    print("\n" + "=" * 60)
    print("MICROSTRUCTURE DIAGNOSTICS")
    print("=" * 60)
    print(f"Slippage sensitivity (EV delta): {ev_2x - ev_base:.2f}")
    print(f"GEX net:  {gex['net_gex']:.2f}")
    print(f"GEX abs:  {gex['abs_gex']:.2f}")
    if gex.get("vanna_net") is not None:
        print(f"Vanna net: {gex['vanna_net']:.2f}")
    if gex.get("charm_net") is not None:
        print(f"Charm net: {gex['charm_net']:.2f}")
    if gex.get("gamma_flip"):
        print(f"Gamma Flip: {gex['gamma_flip']:.2f}")
    if gex.get("pin_strikes"):
        pins = gex["pin_strikes"]
        pin_labels = ", ".join(
            f"{row['strike']:.2f} ({row['abs_pct'] * 100:.1f}%)" for row in pins[:3]
        )
        print(f"Pin strikes: {pin_labels}")
    print("=" * 60)


def _resolve_event_timing_bucket(
    ticker: str,
    event_date: dt.date,
    *,
    fallback_split: dict[str, list[float]],
) -> str:
    """Resolve target timing bucket for conditional expected move.

    Preference order:
    1) exact event_date label from event registry
    2) inferred dominant bucket from historical split counts
    """

    db_path = Path("data/options_intraday.db")
    if db_path.exists():
        try:
            from data.option_data_store import create_store

            store = create_store(db_path)
            registry = store.get_event_registry()
            if not registry.empty:
                mask = (
                    registry["underlying_symbol"].astype(str).str.upper()
                    == ticker.upper()
                ) & (registry["event_date"] == event_date)
                exact = registry[mask]
                if not exact.empty:
                    label = str(exact.iloc[0].get("event_time_label") or "")
                    normalized = label.strip().lower()
                    if normalized in {"ah", "amc", "after close", "after hours"}:
                        return "amc"
                    if normalized in {
                        "am",
                        "bmo",
                        "before open",
                        "pre market",
                        "pre-market",
                    }:
                        return "bmo"
        except Exception:  # pragma: no cover
            LOGGER.debug("Could not resolve event timing from registry.", exc_info=True)

    amc_count = len(fallback_split.get("amc", []))
    bmo_count = len(fallback_split.get("bmo", []))
    if amc_count == 0 and bmo_count == 0:
        return "unknown"
    return "amc" if amc_count >= bmo_count else "bmo"


def _lookup_event_time_label(ticker: str, event_date: dt.date) -> str | None:
    """Return raw event_time_label from local registry when available."""
    db_path = Path("data/options_intraday.db")
    if not db_path.exists():
        return None
    try:
        from data.option_data_store import create_store

        store = create_store(db_path)
        registry = store.get_event_registry()
        if registry.empty:
            return None
        mask = (
            registry["underlying_symbol"].astype(str).str.upper()
            == ticker.upper()
        ) & (registry["event_date"] == event_date)
        exact = registry[mask]
        if exact.empty:
            return None
        value = exact.iloc[0].get("event_time_label")
        if value is None:
            return None
        text = str(value).strip()
        return text or None
    except Exception:
        LOGGER.debug("Could not load event_time_label from registry.", exc_info=True)
        return None


if __name__ == "__main__":
    main()
