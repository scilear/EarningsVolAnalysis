"""Signal-graph helpers for leader/follower earnings propagation."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd


_WEIGHT_ORDER = {
    "LOW": 0,
    "MEDIUM": 1,
    "HIGH": 2,
}


@dataclass(frozen=True)
class SignalEdge:
    """Directed leader->follower relationship with overlap strengths."""

    source: str
    target: str
    revenue_overlap: str
    factor_overlap: str
    weight: str


@dataclass(frozen=True)
class SignalNode:
    """Node metadata for one ticker in the signal graph."""

    ticker: str
    role: str
    event_date: dt.date
    has_signal: bool
    signal_decay_status: str


@dataclass(frozen=True)
class SignalGraphResult:
    """Full graph result with filtered tradeable and absorbed followers."""

    nodes: dict[str, SignalNode]
    edges: list[SignalEdge]
    tradeable_followers: list[SignalNode]
    absorbed_followers: list[SignalNode]


def load_signal_graph_config(
    config_path: str | Path = "config/signal_graph_sectors.json",
) -> tuple[dict, dict]:
    """Load human-maintained sector/factor maps for signal graph edges."""

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(path)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed signal graph config at {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Signal graph config at {path} must be an object.")

    sector_map = payload.get("sector_map")
    factor_map = payload.get("factor_map")
    if not isinstance(sector_map, dict) or not isinstance(factor_map, dict):
        raise ValueError(
            f"Signal graph config at {path} must include sector_map and factor_map."
        )
    return sector_map, factor_map


def build_graph(
    calendar_df: pd.DataFrame,
    sector_map: dict,
    factor_map: dict,
) -> list[SignalEdge]:
    """Build directed edges for time-ordered, mapped ticker pairs."""

    if calendar_df.empty:
        return []

    frame = _normalize_calendar(calendar_df)
    edges: list[SignalEdge] = []
    rows = frame.to_dict("records")
    for source in rows:
        for target in rows:
            if source["ticker"] == target["ticker"]:
                continue
            if source["event_date"] >= target["event_date"]:
                continue

            revenue_overlap = _revenue_overlap(
                source["ticker"],
                target["ticker"],
                sector_map,
            )
            factor_overlap = _factor_overlap(
                source["ticker"],
                target["ticker"],
                factor_map,
            )
            if revenue_overlap == "LOW" and factor_overlap == "LOW":
                continue

            edges.append(
                SignalEdge(
                    source=source["ticker"],
                    target=target["ticker"],
                    revenue_overlap=revenue_overlap,
                    factor_overlap=factor_overlap,
                    weight=_max_weight(revenue_overlap, factor_overlap),
                )
            )

    return edges


def classify_nodes(
    calendar_df: pd.DataFrame,
    today: dt.date,
    edges: list[SignalEdge] | None = None,
) -> dict[str, SignalNode]:
    """Classify LEADER/FOLLOWER node roles relative to today's date."""

    if calendar_df.empty:
        return {}

    frame = _normalize_calendar(calendar_df)
    leaders = {
        row["ticker"] for row in frame.to_dict("records") if row["event_date"] <= today
    }
    by_target: dict[str, list[SignalEdge]] = {}
    for edge in edges or []:
        by_target.setdefault(edge.target, []).append(edge)

    nodes: dict[str, SignalNode] = {}
    for row in frame.to_dict("records"):
        role = "LEADER" if row["event_date"] <= today else "FOLLOWER"
        has_signal = False
        if role == "FOLLOWER":
            has_signal = any(
                upstream.source in leaders
                for upstream in by_target.get(row["ticker"], [])
            )

        nodes[row["ticker"]] = SignalNode(
            ticker=row["ticker"],
            role=role,
            event_date=row["event_date"],
            has_signal=has_signal,
            signal_decay_status="UNKNOWN",
        )
    return nodes


def detect_signal_decay(
    follower_ticker: str,
    upstream_move_pct: float | None,
    follower_move_pct: float | None,
) -> str:
    """Detect whether follower move already absorbed upstream signal."""

    del follower_ticker
    if follower_move_pct is None:
        return "UNKNOWN"
    if upstream_move_pct is None:
        return "UNKNOWN"

    upstream = float(upstream_move_pct)
    follower = float(follower_move_pct)
    if upstream == 0.0:
        return "UNKNOWN"

    same_direction = (upstream > 0 and follower > 0) or (upstream < 0 and follower < 0)
    if same_direction and abs(follower) >= 0.5 * abs(upstream):
        return "ABSORBED"
    return "FRESH"


def get_tradeable_followers(
    nodes: dict[str, SignalNode],
    edges: list[SignalEdge],
    price_moves: dict[str, float],
) -> list[SignalNode]:
    """Return follower nodes with active, non-absorbed upstream signal."""

    del edges
    del price_moves
    return [
        node
        for node in nodes.values()
        if node.role == "FOLLOWER"
        and node.has_signal
        and node.signal_decay_status in {"FRESH", "UNKNOWN"}
    ]


def build_signal_graph_result(
    calendar_df: pd.DataFrame,
    sector_map: dict,
    factor_map: dict,
    today: dt.date,
    price_moves: dict[str, float] | None = None,
) -> SignalGraphResult:
    """Build full signal graph, node roles, and follower decay filters."""

    if calendar_df.empty:
        return SignalGraphResult(
            nodes={},
            edges=[],
            tradeable_followers=[],
            absorbed_followers=[],
        )

    moves = price_moves or {}
    edges = build_graph(calendar_df, sector_map, factor_map)
    nodes = classify_nodes(calendar_df, today, edges=edges)
    nodes = _apply_decay_status(nodes, edges, moves)

    absorbed_followers = [
        node
        for node in nodes.values()
        if node.role == "FOLLOWER" and node.signal_decay_status == "ABSORBED"
    ]
    tradeable_followers = get_tradeable_followers(nodes, edges, moves)
    return SignalGraphResult(
        nodes=nodes,
        edges=edges,
        tradeable_followers=tradeable_followers,
        absorbed_followers=absorbed_followers,
    )


def _normalize_calendar(calendar_df: pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate minimal calendar columns for graph operations."""

    required = {"ticker", "event_date"}
    missing = required.difference(calendar_df.columns)
    if missing:
        raise ValueError(f"calendar_df missing required columns: {sorted(missing)}")

    frame = calendar_df[["ticker", "event_date"]].copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    frame["event_date"] = pd.to_datetime(frame["event_date"], errors="coerce").dt.date
    frame = frame.dropna(subset=["ticker", "event_date"])
    frame = frame.drop_duplicates(subset=["ticker"], keep="last")
    return frame.sort_values("event_date").reset_index(drop=True)


def _revenue_overlap(source: str, target: str, sector_map: dict) -> str:
    """Return configured revenue-overlap tag for directed pair."""

    raw = (
        sector_map.get(source, {}).get(target)
        if isinstance(sector_map.get(source, {}), dict)
        else None
    )
    return _normalize_weight(raw)


def _factor_overlap(source: str, target: str, factor_map: dict) -> str:
    """Infer factor overlap from per-ticker factor metadata."""

    source_meta = factor_map.get(source, {}) if isinstance(factor_map, dict) else {}
    target_meta = factor_map.get(target, {}) if isinstance(factor_map, dict) else {}
    source_primary = _normalized_factor(source_meta.get("primary"))
    target_primary = _normalized_factor(target_meta.get("primary"))
    source_secondary = {
        _normalized_factor(item)
        for item in source_meta.get("secondary", [])
        if _normalized_factor(item)
    }
    target_secondary = {
        _normalized_factor(item)
        for item in target_meta.get("secondary", [])
        if _normalized_factor(item)
    }

    if source_primary and target_primary and source_primary == target_primary:
        return "HIGH"
    if source_primary and source_primary in target_secondary:
        return "MEDIUM"
    if target_primary and target_primary in source_secondary:
        return "MEDIUM"
    if source_secondary.intersection(target_secondary):
        return "MEDIUM"
    return "LOW"


def _max_weight(a: str, b: str) -> str:
    """Return stronger of two LOW/MEDIUM/HIGH weights."""

    return a if _WEIGHT_ORDER[a] >= _WEIGHT_ORDER[b] else b


def _normalize_weight(value: object) -> str:
    """Normalize free-form weight tags to LOW/MEDIUM/HIGH."""

    normalized = str(value or "LOW").strip().upper()
    if normalized not in _WEIGHT_ORDER:
        return "LOW"
    return normalized


def _normalized_factor(value: object) -> str | None:
    """Normalize factor names for overlap matching."""

    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _apply_decay_status(
    nodes: dict[str, SignalNode],
    edges: list[SignalEdge],
    price_moves: dict[str, float],
) -> dict[str, SignalNode]:
    """Fill per-follower signal_decay_status from leader/follower moves."""

    updated = dict(nodes)
    leaders = {ticker for ticker, node in nodes.items() if node.role == "LEADER"}
    edges_by_target: dict[str, list[SignalEdge]] = {}
    for edge in edges:
        if edge.source in leaders:
            edges_by_target.setdefault(edge.target, []).append(edge)

    for ticker, node in nodes.items():
        if node.role != "FOLLOWER" or not node.has_signal:
            continue

        upstream_move = _pick_upstream_move(
            edges_by_target.get(ticker, []), price_moves
        )
        follower_move = price_moves.get(ticker)
        status = detect_signal_decay(ticker, upstream_move, follower_move)
        updated[ticker] = replace(node, signal_decay_status=status)

    return updated


def _pick_upstream_move(
    upstream_edges: list[SignalEdge],
    price_moves: dict[str, float],
) -> float | None:
    """Pick strongest available upstream move by absolute magnitude."""

    candidates: list[float] = []
    for edge in upstream_edges:
        move = price_moves.get(edge.source)
        if move is None:
            continue
        candidates.append(float(move))

    if not candidates:
        return None
    return max(candidates, key=lambda value: abs(value))
