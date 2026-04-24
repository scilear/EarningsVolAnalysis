"""Structure Advisor core for payoff-type structure queries."""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from event_vol_analysis.strategies.payoff_map import (
    PayoffType,
    _resolve_payoff_type,
    get_structures_for_payoff,
)
from event_vol_analysis.strategies.structures import OptionLeg, Strategy

OPTION_CHAIN_TOOL_PATH = Path(
    "/home/fabien/Documents/OptionTrader/tools/option_chain.py"
)
_OPTION_CHAIN_UNSUPPORTED_STRIKES = "unrecognized arguments: --strikes"


@dataclass
class ScoredStructure:
    """One priced structure candidate."""

    structure_name: str
    net_debit: float
    annualized_carry_pct: float
    max_loss: float
    notional_estimate: float
    breakeven: float | None
    loss_zone: tuple[float, float] | None
    rank: int
    note: str | None = None
    assignment_warning: str | None = None
    manually_specified: bool = False


@dataclass
class ExcludedStructure:
    """Excluded structure with explicit reason."""

    structure_name: str
    reason: str


@dataclass
class StructureAdvisorResult:
    """Top-level result payload for a query."""

    payoff_type: str
    ticker: str
    expiry: str
    spot: float
    ranked_structures: list[ScoredStructure] = field(default_factory=list)
    excluded: list[ExcludedStructure] = field(default_factory=list)
    fitness_flags: list[str] = field(default_factory=list)
    vol_regime_summary: str = ""
    data_unavailable: bool = False

    def to_table(self) -> str:
        """Render compact operator table output."""
        lines: list[str] = []
        lines.append(
            "Structure Advisor - "
            f"{self.ticker} | payoff: {self.payoff_type} | "
            f"spot: ${self.spot:.2f} | {self.expiry}"
        )
        if self.vol_regime_summary:
            lines.append(f"Vol fitness: {self.vol_regime_summary}")
        for flag in self.fitness_flags:
            lines.append(f"Fitness flag: {flag}")
        lines.append("")
        lines.append("RANKED CANDIDATES")
        lines.append("-" * 84)
        lines.append(
            "Rank  Structure                 Net debit   Annlzd   "
            "Notional   Max loss   Breakeven   Loss zone"
        )

        for row in self.ranked_structures:
            breakeven = "n/a" if row.breakeven is None else f"{row.breakeven:.2f}"
            if row.loss_zone is None:
                loss_zone = "none"
            else:
                low, high = row.loss_zone
                loss_zone = f"{low:.2f}-{high:.2f}"
            label = " [MANUALLY_SPECIFIED]" if row.manually_specified else ""
            lines.append(
                f"{row.rank:<5} {row.structure_name[:24]:<24} "
                f"${row.net_debit:>8.2f} {row.annualized_carry_pct:>8.2f}% "
                f"${row.notional_estimate:>8.0f} ${row.max_loss:>8.2f} "
                f"{breakeven:>10} {loss_zone:>12}{label}"
            )
            if row.note:
                lines.append(f"      note: {row.note}")
            if row.assignment_warning:
                lines.append(f"      assignment: {row.assignment_warning}")

        if not self.ranked_structures:
            lines.append("(no ranked structures)")

        grouped: dict[str, list[str]] = {}
        for item in self.excluded:
            grouped.setdefault(item.reason, []).append(item.structure_name)
        for reason in sorted(grouped):
            names = ", ".join(sorted(grouped[reason]))
            lines.append(f"EXCLUDED ({reason}): {names}")

        if self.ranked_structures:
            best = self.ranked_structures[0]
            lines.append("")
            lines.append(
                "RECOMMENDATION: "
                f"Rank {best.rank} - {best.structure_name} at "
                f"${best.net_debit:.2f} ({best.annualized_carry_pct:.2f}% annlzd)."
            )

        if len(lines) > 60:
            lines = lines[:59] + ["... output truncated to 60 lines"]
        return "\n".join(lines)

    def to_json(self) -> str:
        """Serialize the result payload."""
        return json.dumps(asdict(self), indent=2)


def query_structures(
    payoff_type: PayoffType | str,
    ticker: str,
    expiry: str,
    spot: float,
    budget: float | None = None,
    max_notional: float | None = None,
    context: dict | None = None,
    validate: str | None = None,
) -> StructureAdvisorResult:
    """Query, price, gate, and rank structures for a payoff type."""
    context = context or {}
    resolved = _resolve_payoff_type(payoff_type)
    expiry_date = dt.date.fromisoformat(expiry)
    dte_hint = int(context.get("dte") or max((expiry_date - dt.date.today()).days, 1))
    back_expiry = expiry_date + dt.timedelta(days=max(21, dte_hint))

    result = StructureAdvisorResult(
        payoff_type=resolved.value,
        ticker=ticker.upper(),
        expiry=expiry,
        spot=float(spot),
    )
    result.vol_regime_summary = _vol_regime_summary(context)
    result.fitness_flags.extend(_fitness_warnings(resolved, context))

    structures = get_structures_for_payoff(
        resolved,
        expiry=expiry_date,
        back_expiry=back_expiry,
        spot=float(spot),
    )
    if validate:
        structures.append(_parse_validate_structure(validate, expiry_date))

    lookup, error = _fetch_targeted_quotes(ticker.upper(), structures)
    if error is not None:
        result.data_unavailable = True
        result.fitness_flags.append(error)
        return result

    scored: list[ScoredStructure] = []
    for structure in structures:
        if structure.requires_naked_short_approval:
            result.excluded.append(
                ExcludedStructure(
                    structure_name=structure.name, reason="CHARTER_BLOCKED"
                )
            )
            continue

        leg_prices = _resolve_leg_prices(structure, lookup)
        if leg_prices is None:
            result.excluded.append(
                ExcludedStructure(
                    structure_name=structure.name,
                    reason="LIQUIDITY_INSUFFICIENT",
                )
            )
            continue

        net_debit = _compute_net_debit(leg_prices)
        notional_estimate = _estimate_notional(structure, float(spot))
        if budget is not None and net_debit > budget:
            result.excluded.append(
                ExcludedStructure(
                    structure_name=structure.name, reason="BUDGET_EXCEEDED"
                )
            )
            continue
        if max_notional is not None and notional_estimate > max_notional:
            result.excluded.append(
                ExcludedStructure(
                    structure_name=structure.name,
                    reason="NOTIONAL_LIMIT",
                )
            )
            continue

        dte = max(
            (min(leg.expiry.date() for leg in structure.legs) - dt.date.today()).days, 1
        )
        annualized = _annualized_carry(net_debit, float(spot), dte)
        spots = _spot_grid(float(spot), structure)
        pnl = [_terminal_pnl(structure, net_debit, x) for x in spots]
        max_loss = max(0.0, -min(pnl))
        breakeven = _estimate_breakeven(spots, pnl, float(spot))
        loss_zone = _loss_zone(structure, spots, pnl, net_debit)

        note = structure.notes
        if "diagonal" in structure.name:
            note = _diagonal_cost_note(structure, net_debit, float(spot))
        assignment_warning = _assignment_warning(structure, float(spot))

        scored.append(
            ScoredStructure(
                structure_name=structure.name,
                net_debit=net_debit,
                annualized_carry_pct=annualized,
                max_loss=max_loss,
                notional_estimate=notional_estimate,
                breakeven=breakeven,
                loss_zone=loss_zone,
                rank=0,
                note=note,
                assignment_warning=assignment_warning,
                manually_specified=structure.name.endswith("manual"),
            )
        )

    scored = sorted(scored, key=_ranking_key)
    for index, item in enumerate(scored, start=1):
        item.rank = index
    result.ranked_structures = scored
    return result


def _fetch_targeted_quotes(
    ticker: str,
    structures: list[Strategy],
) -> tuple[dict[tuple[dt.date, str, float], dict[str, float]], str | None]:
    """Fetch only required strike/expiry quotes and return lookup."""
    needed = _required_contracts(structures)
    lookup: dict[tuple[dt.date, str, float], dict[str, float]] = {}
    for expiry, payload in needed.items():
        rows, error = _fetch_option_chain_rows(
            ticker=ticker,
            expiry=expiry,
            strikes=sorted(payload["strikes"]),
        )
        if error:
            return {}, error
        for row in rows:
            strike = float(row.get("strike") or 0.0)
            right = str(row.get("right") or "").upper()
            option_type = "call" if right == "C" else "put"
            key = (dt.date.fromisoformat(expiry), option_type, strike)
            bid = float(row.get("bid") or 0.0)
            ask = float(row.get("ask") or 0.0)
            mid = float(row.get("mid") or 0.0)
            if mid <= 0.0 and bid > 0.0 and ask > 0.0:
                mid = (bid + ask) / 2.0
            lookup[key] = {
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "iv": float(row.get("iv") or 0.0),
                "delta": float(row.get("delta") or 0.0),
                "vega": float(row.get("vega") or 0.0),
            }
    return lookup, None


def _required_contracts(
    structures: list[Strategy],
) -> dict[str, dict[str, set[float]]]:
    """Return required contracts grouped by expiry."""
    grouped: dict[str, dict[str, set[float]]] = {}
    for structure in structures:
        for leg in structure.legs:
            expiry = leg.expiry.date().isoformat()
            grouped.setdefault(expiry, {"strikes": set()})
            grouped[expiry]["strikes"].add(float(leg.strike))
    return grouped


def _fetch_option_chain_rows(
    ticker: str,
    expiry: str,
    strikes: list[float],
) -> tuple[list[dict], str | None]:
    """Call OptionTrader chain tool and return filtered rows."""
    if not OPTION_CHAIN_TOOL_PATH.exists():
        return [], "DATA UNAVAILABLE: option chain tool not found"

    strike_csv = ",".join(f"{value:.2f}" for value in strikes)
    with_strikes = [
        sys.executable,
        str(OPTION_CHAIN_TOOL_PATH),
        "--ticker",
        ticker,
        "--expiry",
        expiry,
        "--output",
        "json",
        "--strikes",
        strike_csv,
    ]
    result = subprocess.run(
        with_strikes,
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        stderr = result.stderr or ""
        if _OPTION_CHAIN_UNSUPPORTED_STRIKES in stderr:
            without_strikes = with_strikes[:-2]
            result = subprocess.run(
                without_strikes,
                check=False,
                capture_output=True,
                text=True,
            )
        if result.returncode != 0:
            return [], "DATA UNAVAILABLE: option chain fetch failed"

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return [], "DATA UNAVAILABLE: invalid chain response"

    rows = payload.get("rows")
    if not isinstance(rows, list):
        return [], "DATA UNAVAILABLE: malformed chain response"

    wanted = {round(value, 2) for value in strikes}
    filtered = [
        row for row in rows if round(float(row.get("strike") or 0.0), 2) in wanted
    ]
    return filtered, None


def _resolve_leg_prices(
    structure: Strategy,
    lookup: dict[tuple[dt.date, str, float], dict[str, float]],
) -> list[tuple[str, float, int]] | None:
    """Resolve leg prices from lookup."""
    resolved: list[tuple[str, float, int]] = []
    for leg in structure.legs:
        key = (leg.expiry.date(), leg.option_type, float(leg.strike))
        quote = lookup.get(key)
        if quote is None:
            return None
        bid = float(quote.get("bid") or 0.0)
        ask = float(quote.get("ask") or 0.0)
        mid = float(quote.get("mid") or 0.0)
        if bid <= 0.0 or ask <= 0.0 or mid <= 0.0:
            return None
        resolved.append((leg.side, mid, int(leg.qty)))
    return resolved


def _compute_net_debit(leg_prices: list[tuple[str, float, int]]) -> float:
    """Compute net debit in dollars."""
    total = 0.0
    for side, mid, qty in leg_prices:
        cash = mid * qty * 100.0
        if side == "buy":
            total += cash
        else:
            total -= cash
    return total


def _estimate_notional(structure: Strategy, spot: float) -> float:
    """Estimate gross notional exposure in dollars."""
    gross_contracts = float(sum(abs(int(leg.qty)) for leg in structure.legs))
    return gross_contracts * spot * 100.0


def _assignment_warning(structure: Strategy, spot: float) -> str | None:
    """Return assignment-risk note for near-expiry ITM short legs."""
    short_legs = [leg for leg in structure.legs if leg.side == "sell"]
    if not short_legs:
        return None

    nearest_short_expiry = min(leg.expiry.date() for leg in short_legs)
    dte = max((nearest_short_expiry - dt.date.today()).days, 0)
    if dte > 7:
        return None

    warnings: list[str] = []
    for leg in short_legs:
        if leg.option_type == "call":
            itm = spot >= float(leg.strike)
        else:
            itm = spot <= float(leg.strike)
        if not itm:
            continue

        moneyness = abs(spot - float(leg.strike)) / max(spot, 1e-9)
        severity = "HIGH" if moneyness >= 0.01 else "MEDIUM"
        warnings.append(
            f"{severity} assignment risk on short {leg.option_type} "
            f"{leg.strike:.2f} ({dte} DTE)"
        )

    if not warnings:
        return None
    return "; ".join(warnings)


def _annualized_carry(net_debit: float, spot: float, dte: int) -> float:
    """Compute annualized carry percentage from net debit."""
    denominator = max(spot * 100.0 * (dte / 365.0), 1e-9)
    return (net_debit / denominator) * 100.0


def _spot_grid(spot: float, structure: Strategy) -> list[float]:
    """Build deterministic spot grid for payoff diagnostics."""
    strikes = [float(leg.strike) for leg in structure.legs]
    low = min(min(strikes) * 0.75, spot * 0.75)
    high = max(max(strikes) * 1.25, spot * 1.25)
    step = (high - low) / 160.0
    return [low + (idx * step) for idx in range(161)]


def _terminal_pnl(structure: Strategy, net_debit: float, terminal_spot: float) -> float:
    """Approximate terminal PnL by intrinsic settlement."""
    intrinsic_value = 0.0
    for leg in structure.legs:
        if leg.option_type == "call":
            intrinsic = max(terminal_spot - leg.strike, 0.0)
        else:
            intrinsic = max(leg.strike - terminal_spot, 0.0)
        sign = 1.0 if leg.side == "buy" else -1.0
        intrinsic_value += sign * intrinsic * leg.qty * 100.0
    return intrinsic_value - net_debit


def _estimate_breakeven(
    spots: list[float],
    pnls: list[float],
    spot: float,
) -> float | None:
    """Estimate one representative break-even point."""
    roots: list[float] = []
    for index in range(1, len(spots)):
        y0 = pnls[index - 1]
        y1 = pnls[index]
        if y0 == 0.0:
            roots.append(spots[index - 1])
            continue
        if y0 * y1 < 0.0:
            x0 = spots[index - 1]
            x1 = spots[index]
            root = x0 - y0 * (x1 - x0) / (y1 - y0)
            roots.append(root)
    if not roots:
        return None
    return min(roots, key=lambda value: abs(value - spot))


def _loss_zone(
    structure: Strategy,
    spots: list[float],
    pnls: list[float],
    net_debit: float,
) -> tuple[float, float] | None:
    """Return loss zone for ratio/diagonal structures only."""
    has_ratio = any(leg.qty != 1 for leg in structure.legs)
    if not has_ratio and "diagonal" not in structure.name:
        return None
    threshold = -abs(net_debit)
    bad_spots = [x for x, y in zip(spots, pnls) if y < threshold]
    if not bad_spots:
        return None
    return (min(bad_spots), max(bad_spots))


def _diagonal_cost_note(structure: Strategy, net_debit: float, spot: float) -> str:
    """Return conditional cost note for diagonal structures."""
    short_leg = next((leg for leg in structure.legs if leg.side == "sell"), None)
    if short_leg is None:
        return "conditional cost unavailable"
    assignment_extra = max(short_leg.strike - spot, 0.0) * short_leg.qty * 100.0
    assigned_cost = net_debit + assignment_extra
    return (
        "conditional: short expires OTM cost=${:.2f}; "
        "if assigned effective cost=${:.2f}+"
    ).format(net_debit, assigned_cost)


def _ranking_key(item: ScoredStructure) -> tuple[float, float]:
    """Sort key with ratio/diagonal penalty."""
    penalty = 0.0
    if item.loss_zone is not None:
        penalty += 20.0
    if item.note and "conditional" in item.note.lower():
        penalty += 10.0
    return (item.annualized_carry_pct + penalty, item.net_debit)


def _vol_regime_summary(context: dict) -> str:
    """Build volatility context summary."""
    ivp = context.get("iv_percentile")
    if ivp is None:
        return "IV percentile unavailable"
    ivp_value = float(ivp)
    if ivp_value > 80:
        label = "ELEVATED"
    elif ivp_value > 60:
        label = "RICH"
    elif ivp_value < 30:
        label = "CHEAP"
    else:
        label = "NEUTRAL"
    return f"IV percentile {ivp_value:.1f}% - {label}"


def _fitness_warnings(payoff_type: PayoffType, context: dict) -> list[str]:
    """Apply payoff fitness warnings from spec."""
    warnings: list[str] = []
    ivp = context.get("iv_percentile")
    binary_event_within_dte = bool(context.get("binary_event_within_dte"))

    if ivp is not None:
        ivp_value = float(ivp)
        if payoff_type in {PayoffType.CRASH, PayoffType.RALLY} and ivp_value > 80:
            warnings.append("IV percentile >80: long vol expensive")
        if payoff_type is PayoffType.VOL_EXPANSION and ivp_value > 60:
            warnings.append("IV percentile >60: vol expansion entry expensive")

    if payoff_type is PayoffType.SIDEWAYS and binary_event_within_dte:
        warnings.append("Binary event inside DTE for sideways structures")
    return warnings


_MONTH_MAP = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _parse_month_day(token: str, year: int) -> dt.date:
    """Parse month-day token (e.g., May15)."""
    match = re.fullmatch(r"([A-Za-z]{3})(\d{1,2})", token)
    if match is None:
        raise ValueError(f"Invalid date token '{token}'")
    month = _MONTH_MAP.get(match.group(1).lower())
    if month is None:
        raise ValueError(f"Unsupported month in token '{token}'")
    day = int(match.group(2))
    return dt.date(year, month, day)


def _parse_validate_structure(validate: str, base_expiry: dt.date) -> Strategy:
    """Parse --validate structure string into a Strategy."""
    pattern = re.compile(
        r"^diagonal:short-([A-Za-z]{3}\d{1,2})-(\d+(?:\.\d+)?)P/"
        r"long-(\d+)x-([A-Za-z]{3}\d{1,2})-(\d+(?:\.\d+)?)P$"
    )
    match = pattern.fullmatch(validate.strip())
    if match is None:
        raise ValueError(
            "Unsupported --validate format. Use: "
            "diagonal:short-May15-420P/long-2x-Jul17-410P"
        )

    short_date = _parse_month_day(match.group(1), base_expiry.year)
    short_strike = float(match.group(2))
    ratio = int(match.group(3))
    long_date = _parse_month_day(match.group(4), base_expiry.year)
    if long_date <= short_date:
        long_date = dt.date(long_date.year + 1, long_date.month, long_date.day)
    long_strike = float(match.group(5))

    return Strategy(
        name="diagonal_put_backspread_manual",
        legs=(
            OptionLeg(
                "put",
                short_strike,
                1,
                "sell",
                pd.Timestamp(short_date),
            ),
            OptionLeg(
                "put",
                long_strike,
                ratio,
                "buy",
                pd.Timestamp(long_date),
            ),
        ),
        notes="Manual validate structure",
    )


__all__ = [
    "ExcludedStructure",
    "ScoredStructure",
    "StructureAdvisorResult",
    "query_structures",
]
