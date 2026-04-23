"""Macro binary-event outcomes store and query helpers.

Provides a file-based store for macro-event outcomes used by activation
filters that require event-type tail-rate evidence.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_MACRO_OUTCOMES_DIR = Path("data/macro_event_outcomes")
ALLOWED_EVENT_TYPES = {
    "geopolitical",
    "fomc",
    "election",
    "regulatory",
}


@dataclass(frozen=True)
class MacroEventOutcomeRecord:
    """One macro-event outcome row persisted as JSON."""

    event_type: str
    event_date: dt.date
    underlying: str
    implied_move_pct: float
    realized_move_pct: float
    move_vs_implied_ratio: float
    vix_at_entry: float
    vvix_percentile_at_entry: float
    gex_zone: str
    vol_crush: float
    notes: str = ""
    vix_quartile: int | None = None


def store_macro_event_outcome(
    event_type: str,
    event_date: dt.date | dt.datetime | str,
    underlying: str,
    implied_move_pct: float,
    realized_move_pct: float,
    *,
    move_vs_implied_ratio: float | None = None,
    vix_at_entry: float,
    vvix_percentile_at_entry: float,
    gex_zone: str,
    vol_crush: float,
    notes: str = "",
    vix_quartile: int | None = None,
    data_dir: Path | str = DEFAULT_MACRO_OUTCOMES_DIR,
) -> Path:
    """Upsert one macro-event outcome JSON record.

    Args:
        event_type: One of geopolitical/fomc/election/regulatory.
        event_date: Event date (ISO string or date-like).
        underlying: Primary traded vehicle (e.g., SPY, XOP).
        implied_move_pct: Implied move as decimal.
        realized_move_pct: Realized move as decimal.
        move_vs_implied_ratio: Explicit realized/implied ratio. If None,
            computed from implied_move_pct and realized_move_pct.
        vix_at_entry: VIX level at entry.
        vvix_percentile_at_entry: VVIX percentile at entry (0-100).
        gex_zone: GEX zone label.
        vol_crush: IV change from entry to +1 session.
        notes: Optional operator notes.
        vix_quartile: Optional quartile bucket (1-4).
        data_dir: Store directory for JSON files.

    Returns:
        Path to the written record file.
    """
    normalized_event_type = _normalize_event_type(event_type)
    normalized_date = _as_date(event_date)
    normalized_underlying = str(underlying).upper().strip()
    if not normalized_underlying:
        raise ValueError("underlying is required")

    implied = float(implied_move_pct)
    realized = float(realized_move_pct)
    ratio = _resolve_ratio(implied, realized, move_vs_implied_ratio)
    quartile = _normalize_vix_quartile(vix_quartile)

    record = MacroEventOutcomeRecord(
        event_type=normalized_event_type,
        event_date=normalized_date,
        underlying=normalized_underlying,
        implied_move_pct=implied,
        realized_move_pct=realized,
        move_vs_implied_ratio=ratio,
        vix_at_entry=float(vix_at_entry),
        vvix_percentile_at_entry=float(vvix_percentile_at_entry),
        gex_zone=str(gex_zone),
        vol_crush=float(vol_crush),
        notes=str(notes),
        vix_quartile=quartile,
    )

    target_dir = Path(data_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / _record_filename(record)
    payload = asdict(record)
    payload["event_date"] = record.event_date.isoformat()
    file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return file_path


def load_macro_event_outcomes(
    data_dir: Path | str = DEFAULT_MACRO_OUTCOMES_DIR,
) -> list[MacroEventOutcomeRecord]:
    """Load all macro-event outcome records from JSON files."""
    source_dir = Path(data_dir)
    if not source_dir.exists():
        return []

    records: list[MacroEventOutcomeRecord] = []
    for file_path in sorted(source_dir.glob("*.json")):
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        records.append(_record_from_payload(payload))
    return records


def query_event_type_tail_rate(
    event_type: str,
    threshold_sd: float = 1.0,
    *,
    vix_quartile: int | None = None,
    data_dir: Path | str = DEFAULT_MACRO_OUTCOMES_DIR,
) -> dict[str, Any]:
    """Return tail-rate summary for one event type.

    Tail events are records where move_vs_implied_ratio > threshold_sd.
    """
    normalized_event_type = _normalize_event_type(event_type)
    quartile = _normalize_vix_quartile(vix_quartile)
    threshold = float(threshold_sd)

    records = [
        record
        for record in load_macro_event_outcomes(data_dir)
        if record.event_type == normalized_event_type
    ]
    if quartile is not None:
        records = [
            record
            for record in records
            if (
                record.vix_quartile is not None
                and record.vix_quartile == quartile
            )
        ]

    tail_events = [
        record
        for record in records
        if float(record.move_vs_implied_ratio) > threshold
    ]
    total_events = len(records)
    tail_count = len(tail_events)

    return {
        "event_type": normalized_event_type,
        "threshold_sd": threshold,
        "vix_quartile": quartile,
        "tail_event_count": tail_count,
        "total_events": total_events,
        "tail_rate": (
            float(tail_count / total_events)
            if total_events > 0
            else 0.0
        ),
        "has_min_2_tail_events": tail_count >= 2,
    }


def _record_filename(record: MacroEventOutcomeRecord) -> str:
    """Build deterministic file name for one record."""
    return (
        f"{record.event_type}_"
        f"{record.event_date.isoformat()}_"
        f"{record.underlying}.json"
    )


def _record_from_payload(payload: dict[str, Any]) -> MacroEventOutcomeRecord:
    """Convert JSON payload into MacroEventOutcomeRecord."""
    normalized_event_type = _normalize_event_type(payload["event_type"])
    event_date = _as_date(payload["event_date"])
    implied = float(payload["implied_move_pct"])
    realized = float(payload["realized_move_pct"])
    ratio = _resolve_ratio(
        implied,
        realized,
        payload.get("move_vs_implied_ratio"),
    )
    quartile = _normalize_vix_quartile(payload.get("vix_quartile"))

    return MacroEventOutcomeRecord(
        event_type=normalized_event_type,
        event_date=event_date,
        underlying=str(payload["underlying"]).upper(),
        implied_move_pct=implied,
        realized_move_pct=realized,
        move_vs_implied_ratio=ratio,
        vix_at_entry=float(payload["vix_at_entry"]),
        vvix_percentile_at_entry=float(payload["vvix_percentile_at_entry"]),
        gex_zone=str(payload["gex_zone"]),
        vol_crush=float(payload["vol_crush"]),
        notes=str(payload.get("notes", "")),
        vix_quartile=quartile,
    )


def _normalize_event_type(value: str) -> str:
    """Normalize event type and validate against supported values."""
    normalized = str(value).strip().lower()
    if normalized not in ALLOWED_EVENT_TYPES:
        allowed = ", ".join(sorted(ALLOWED_EVENT_TYPES))
        raise ValueError(f"event_type must be one of: {allowed}")
    return normalized


def _normalize_vix_quartile(value: int | str | None) -> int | None:
    """Validate optional VIX quartile value."""
    if value is None:
        return None
    quartile = int(value)
    if quartile < 1 or quartile > 4:
        raise ValueError("vix_quartile must be between 1 and 4")
    return quartile


def _resolve_ratio(
    implied_move_pct: float,
    realized_move_pct: float,
    ratio: float | None,
) -> float:
    """Resolve move-vs-implied ratio with safe fallback."""
    if ratio is not None:
        return float(ratio)
    implied = float(implied_move_pct)
    if implied <= 0.0:
        raise ValueError("implied_move_pct must be > 0 when ratio is missing")
    return float(realized_move_pct) / implied


def _as_date(value: dt.date | dt.datetime | str) -> dt.date:
    """Normalize date-like values to date."""
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))
