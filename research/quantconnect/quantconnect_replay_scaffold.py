"""QuantConnect-oriented export scaffold built on the event replay store."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from data.option_data_store import create_store


@dataclass(frozen=True)
class QCScaffoldConfig:
    """Configuration for exporting replay-ready event payloads to QuantConnect research."""

    db_path: str = "data/options_intraday.db"
    event_family: str = "earnings"
    event_name: str | None = None
    underlying_symbol: str | None = None
    proxy_symbol: str | None = None
    horizon_code: str = "h1_close"
    assumptions_version: str = "v1"
    limit: int = 50


def load_qc_event_dataset(config: QCScaffoldConfig) -> dict[str, pd.DataFrame]:
    """Load the event sample required for the QC scaffold."""

    store = create_store(config.db_path)
    with store._get_connection() as conn:
        events = pd.read_sql_query(
            """
            SELECT *
            FROM event_registry
            WHERE event_family = ?
              AND (? IS NULL OR event_name = ?)
              AND (? IS NULL OR underlying_symbol = ?)
              AND (? IS NULL OR proxy_symbol = ?)
            ORDER BY event_date DESC, underlying_symbol
            LIMIT ?
            """,
            conn,
            params=[
                config.event_family,
                config.event_name,
                config.event_name,
                _upper_or_none(config.underlying_symbol),
                _upper_or_none(config.underlying_symbol),
                _upper_or_none(config.proxy_symbol),
                _upper_or_none(config.proxy_symbol),
                config.limit,
            ],
        )
        bindings = pd.read_sql_query(
            """
            SELECT esb.*, er.event_date, er.event_name
            FROM event_snapshot_binding esb
            JOIN event_registry er ON er.event_id = esb.event_id
            WHERE er.event_family = ?
              AND (? IS NULL OR er.event_name = ?)
              AND (? IS NULL OR er.underlying_symbol = ?)
              AND (? IS NULL OR er.proxy_symbol = ?)
            ORDER BY er.event_date DESC, esb.snapshot_label
            """,
            conn,
            params=[
                config.event_family,
                config.event_name,
                config.event_name,
                _upper_or_none(config.underlying_symbol),
                _upper_or_none(config.underlying_symbol),
                _upper_or_none(config.proxy_symbol),
                _upper_or_none(config.proxy_symbol),
            ],
        )
        outcomes = pd.read_sql_query(
            """
            SELECT ero.*
            FROM event_realized_outcome ero
            JOIN event_registry er ON er.event_id = ero.event_id
            WHERE er.event_family = ?
              AND ero.horizon_code = ?
              AND ero.outcome_version = 'v1'
              AND (? IS NULL OR er.event_name = ?)
              AND (? IS NULL OR er.underlying_symbol = ?)
              AND (? IS NULL OR er.proxy_symbol = ?)
            ORDER BY er.event_date DESC
            """,
            conn,
            params=[
                config.event_family,
                config.horizon_code,
                config.event_name,
                config.event_name,
                _upper_or_none(config.underlying_symbol),
                _upper_or_none(config.underlying_symbol),
                _upper_or_none(config.proxy_symbol),
                _upper_or_none(config.proxy_symbol),
            ],
        )
        replays = pd.read_sql_query(
            """
            SELECT sro.*
            FROM structure_replay_outcome sro
            JOIN event_registry er ON er.event_id = sro.event_id
            WHERE er.event_family = ?
              AND sro.exit_horizon_code = ?
              AND sro.assumptions_version = ?
              AND (? IS NULL OR er.event_name = ?)
              AND (? IS NULL OR er.underlying_symbol = ?)
              AND (? IS NULL OR er.proxy_symbol = ?)
            ORDER BY er.event_date DESC, sro.structure_code
            """,
            conn,
            params=[
                config.event_family,
                config.horizon_code,
                config.assumptions_version,
                config.event_name,
                config.event_name,
                _upper_or_none(config.underlying_symbol),
                _upper_or_none(config.underlying_symbol),
                _upper_or_none(config.proxy_symbol),
                _upper_or_none(config.proxy_symbol),
            ],
        )
    return {
        "events": events,
        "bindings": bindings,
        "outcomes": outcomes,
        "replays": replays,
    }


def build_qc_scaffold(config: QCScaffoldConfig) -> dict[str, Any]:
    """Build an export bundle that QC research code can consume directly."""

    dataset = load_qc_event_dataset(config)
    events: list[dict[str, Any]] = []

    for _, row in dataset["events"].iterrows():
        event_id = str(row["event_id"])
        event_bindings = dataset["bindings"][dataset["bindings"]["event_id"] == event_id]
        event_outcomes = dataset["outcomes"][dataset["outcomes"]["event_id"] == event_id]
        event_replays = dataset["replays"][dataset["replays"]["event_id"] == event_id]
        events.append(
            {
                "event_id": event_id,
                "event_name": row["event_name"],
                "event_family": row["event_family"],
                "underlying_symbol": row["underlying_symbol"],
                "proxy_symbol": row["proxy_symbol"],
                "event_date": row["event_date"],
                "event_time_label": row["event_time_label"],
                "snapshot_labels": (
                    sorted(event_bindings["snapshot_label"].astype(str).unique().tolist())
                    if not event_bindings.empty
                    else []
                ),
                "primary_pre_event_snapshot": _primary_snapshot_label(event_bindings),
                "realized_move_abs_pct": _first_value(event_outcomes, "realized_move_abs_pct"),
                "realized_move_signed_pct": _first_value(event_outcomes, "realized_move_signed_pct"),
                "iv_crush_pct": _first_value(event_outcomes, "iv_crush_pct"),
                "top_structure": _best_structure(event_replays),
                "structures": _structure_rankings(event_replays),
            }
        )

    return {
        "config": asdict(config),
        "coverage": {
            "events": int(len(dataset["events"])),
            "bindings": int(len(dataset["bindings"])),
            "outcomes": int(len(dataset["outcomes"])),
            "replays": int(len(dataset["replays"])),
        },
        "events": events,
        "algorithm_stub": render_algorithm_stub(config),
        "research_template": render_research_template(config),
        "limitations": [
            "This scaffold exports store-backed event samples; it does not fetch live data.",
            "Replay rows remain dependent on the assumptions_version and horizon_code filters.",
            "QuantConnect integration still needs custom data plumbing or notebook payload ingestion.",
        ],
    }


def render_algorithm_stub(config: QCScaffoldConfig) -> str:
    """Render a minimal QC algorithm skeleton for event replay research."""

    symbol_hint = config.underlying_symbol or "SPY"
    return f"""from AlgorithmImports import *


class EventReplayScaffoldAlgorithm(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2024, 1, 1)
        self.SetEndDate(2024, 12, 31)
        self.SetCash(100000)
        self.symbol = self.AddEquity("{symbol_hint}", Resolution.Minute).Symbol
        self.horizon_code = "{config.horizon_code}"
        self.assumptions_version = "{config.assumptions_version}"

        # Load exported event payload from Object Store or Research notebook input.
        self.Debug("Inject event payload generated by quantconnect_replay_scaffold.py")

    def OnData(self, data: Slice):
        pass
"""


def render_research_template(config: QCScaffoldConfig) -> str:
    """Render a QuantConnect Research notebook-style Python template."""

    symbol_hint = config.underlying_symbol or "SPY"
    family = config.event_family
    return f"""# QuantConnect Research Template
# Generated from EarningsVolAnalysis event replay scaffold.

import json
import pandas as pd

payload_path = "event_replay_payload.json"
with open(payload_path, "r", encoding="utf-8") as handle:
    payload = json.load(handle)

events = pd.DataFrame(payload["events"])
events

# Suggested QC research bootstrap
qb = QuantBook()
symbol = qb.add_equity("{symbol_hint}").symbol

# Example filters aligned to the exported scaffold
target_family = "{family}"
target_horizon = "{config.horizon_code}"
target_assumptions = "{config.assumptions_version}"

events["event_date"] = pd.to_datetime(events["event_date"])
events = events.sort_values("event_date")

# Quick orientation view
events[[
    "event_id",
    "event_name",
    "underlying_symbol",
    "event_date",
    "realized_move_abs_pct",
    "iv_crush_pct",
]]

# Expand structure rankings for cross-event comparison
structures = pd.json_normalize(
    [
        {{"event_id": row["event_id"], **structure}}
        for row in payload["events"]
        for structure in row.get("structures", [])
    ]
)
structures
"""


def main() -> None:
    """CLI entry point."""

    parser = argparse.ArgumentParser(description="Export a QC replay scaffold payload.")
    parser.add_argument("--db", default="data/options_intraday.db")
    parser.add_argument("--event-family", default="earnings")
    parser.add_argument("--event-name")
    parser.add_argument("--underlying-symbol")
    parser.add_argument("--proxy-symbol")
    parser.add_argument("--horizon-code", default="h1_close")
    parser.add_argument("--assumptions-version", default="v1")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--format",
        choices=("json", "stub", "research"),
        default="json",
        help="Emit the export bundle, the LEAN algorithm stub, or the research template.",
    )
    args = parser.parse_args()

    config = QCScaffoldConfig(
        db_path=args.db,
        event_family=args.event_family,
        event_name=args.event_name,
        underlying_symbol=args.underlying_symbol,
        proxy_symbol=args.proxy_symbol,
        horizon_code=args.horizon_code,
        assumptions_version=args.assumptions_version,
        limit=args.limit,
    )
    scaffold = build_qc_scaffold(config)
    if args.format == "stub":
        print(scaffold["algorithm_stub"])
        return
    if args.format == "research":
        print(scaffold["research_template"])
        return
    print(json.dumps(scaffold, indent=2, sort_keys=True))


def _upper_or_none(value: str | None) -> str | None:
    """Normalize optional symbol filters."""

    if value is None:
        return None
    return value.upper()


def _primary_snapshot_label(bindings: pd.DataFrame) -> str | None:
    """Extract the primary pre-event snapshot label when present."""

    if bindings.empty:
        return None
    primary = bindings[
        (bindings["timing_bucket"] == "pre_event") & (bindings["is_primary"] == 1)
    ]
    if primary.empty:
        return None
    return str(primary.iloc[0]["snapshot_label"])


def _first_value(frame: pd.DataFrame, column: str) -> float | None:
    """Extract one numeric value when present."""

    if frame.empty or column not in frame.columns:
        return None
    value = frame.iloc[0][column]
    if pd.isna(value):
        return None
    return float(value)


def _best_structure(frame: pd.DataFrame) -> dict[str, Any] | None:
    """Return the best replayed structure for one event by realized PnL."""

    if frame.empty:
        return None
    ranked = frame.sort_values("realized_pnl", ascending=False).iloc[0]
    return {
        "structure_code": str(ranked["structure_code"]),
        "realized_pnl": float(ranked["realized_pnl"]),
        "realized_pnl_pct": (
            None if pd.isna(ranked["realized_pnl_pct"]) else float(ranked["realized_pnl_pct"])
        ),
    }


def _structure_rankings(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Return all replayed structures for one event sorted by realized PnL."""

    if frame.empty:
        return []
    ordered = frame.sort_values("realized_pnl", ascending=False)
    return [
        {
            "structure_code": str(row["structure_code"]),
            "realized_pnl": float(row["realized_pnl"]),
            "realized_pnl_pct": (
                None if pd.isna(row["realized_pnl_pct"]) else float(row["realized_pnl_pct"])
            ),
        }
        for _, row in ordered.iterrows()
    ]
