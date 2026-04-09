"""Foundational event replay primitives built on the additive event storage model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from data.option_data_store import OptionsDataStore


@dataclass(frozen=True)
class ReplayAssumptions:
    """Explicit replay assumptions for standardized event evaluation."""

    entry_snapshot_label: str = "pre_close_d0"
    default_pre_snapshot_label: str = "pre_close_d0"
    default_post_snapshot_label: str = "post_close_d1"
    pricing_model_version: str = "midmark_v1"
    assumptions_version: str = "v1"


@dataclass(frozen=True)
class EventReplayContext:
    """One fully resolved event context ready for replay evaluation."""

    event: dict[str, Any]
    snapshot_bindings: pd.DataFrame
    surface_metrics: pd.DataFrame
    realized_outcomes: pd.DataFrame
    replay_outcomes: pd.DataFrame
    horizons: pd.DataFrame
    assumptions: ReplayAssumptions

    @property
    def event_id(self) -> str:
        """Stable event identifier."""

        return str(self.event["event_id"])

    def binding_for(self, snapshot_label: str) -> dict[str, Any]:
        """Return one binding row for a named snapshot label."""

        rows = self.snapshot_bindings[
            self.snapshot_bindings["snapshot_label"] == snapshot_label
        ]
        if rows.empty:
            raise KeyError(
                f"Snapshot label '{snapshot_label}' is not bound for event '{self.event_id}'."
            )
        return rows.iloc[0].to_dict()

    def primary_pre_event_binding(self) -> dict[str, Any]:
        """Return the primary pre-event binding used as replay anchor."""

        rows = self.snapshot_bindings[
            (self.snapshot_bindings["timing_bucket"] == "pre_event")
            & (self.snapshot_bindings["is_primary"] == 1)
        ]
        if rows.empty:
            raise ValueError(
                f"No primary pre-event snapshot binding found for event '{self.event_id}'."
            )
        return rows.iloc[0].to_dict()

    def outcome_for_horizon(self, horizon_code: str) -> dict[str, Any]:
        """Return one realized outcome row for a horizon code."""

        rows = self.realized_outcomes[
            self.realized_outcomes["horizon_code"] == horizon_code
        ]
        if rows.empty:
            raise KeyError(
                f"No realized outcome stored for horizon '{horizon_code}' on event '{self.event_id}'."
            )
        return rows.iloc[0].to_dict()

    def snapshot_chain(self, store: OptionsDataStore, snapshot_label: str) -> pd.DataFrame:
        """Load the full options surface for one bound snapshot label."""

        binding = self.binding_for(snapshot_label)
        quote_ts = _coerce_timestamp(binding["quote_ts"])
        return store.query_chain(
            ticker=str(binding["ticker"]),
            timestamp=quote_ts,
            min_quality="valid",
        )


def load_event_replay_context(
    store: OptionsDataStore,
    event_id: str,
    *,
    assumptions: ReplayAssumptions | None = None,
) -> EventReplayContext:
    """Resolve a replay-ready event context from the additive storage model."""

    assumptions = assumptions or ReplayAssumptions()

    event_df = store.get_event_registry(event_id)
    if event_df.empty:
        raise KeyError(f"Event '{event_id}' not found in event registry.")
    event = event_df.iloc[0].to_dict()

    bindings = store.get_event_snapshot_bindings(event_id)
    surface_metrics = _read_table(
        store,
        """
        SELECT * FROM event_surface_metrics
        WHERE event_id = ?
        ORDER BY snapshot_label, metric_version
        """,
        [event_id],
    )
    realized_outcomes = _read_table(
        store,
        """
        SELECT * FROM event_realized_outcome
        WHERE event_id = ?
        ORDER BY horizon_code, outcome_version
        """,
        [event_id],
    )
    replay_outcomes = _read_table(
        store,
        """
        SELECT * FROM structure_replay_outcome
        WHERE event_id = ?
        ORDER BY structure_code, exit_horizon_code
        """,
        [event_id],
    )
    horizons = _read_table(
        store,
        """
        SELECT * FROM event_evaluation_horizon
        ORDER BY horizon_days, horizon_code
        """,
        [],
    )

    return EventReplayContext(
        event=event,
        snapshot_bindings=bindings,
        surface_metrics=surface_metrics,
        realized_outcomes=realized_outcomes,
        replay_outcomes=replay_outcomes,
        horizons=horizons,
        assumptions=assumptions,
    )


def replay_selection_summary(context: EventReplayContext) -> dict[str, Any]:
    """Return a compact, explicit summary of replay inputs and available outputs."""

    primary = context.primary_pre_event_binding()
    return {
        "event_id": context.event_id,
        "entry_snapshot_label": context.assumptions.entry_snapshot_label,
        "primary_pre_event_snapshot": primary["snapshot_label"],
        "available_snapshot_labels": sorted(
            context.snapshot_bindings["snapshot_label"].astype(str).unique().tolist()
        ),
        "available_horizons": sorted(
            context.horizons["horizon_code"].astype(str).unique().tolist()
        ),
        "realized_outcome_horizons": sorted(
            context.realized_outcomes["horizon_code"].astype(str).unique().tolist()
        ),
        "stored_structure_replays": sorted(
            context.replay_outcomes["structure_code"].astype(str).unique().tolist()
        ),
        "assumptions_version": context.assumptions.assumptions_version,
        "pricing_model_version": context.assumptions.pricing_model_version,
    }


def _read_table(
    store: OptionsDataStore,
    query: str,
    params: list[Any],
) -> pd.DataFrame:
    """Execute a read-only query against the store and normalize datetime columns."""

    with store._get_connection() as conn:
        frame = pd.read_sql_query(query, conn, params=params)
    for column in ("quote_ts", "event_ts_utc", "created_at", "updated_at"):
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column])
    return frame


def _coerce_timestamp(value: Any) -> datetime:
    """Normalize one bound quote timestamp to a datetime."""

    if isinstance(value, datetime):
        return value
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"Unsupported quote timestamp value: {value!r}")
