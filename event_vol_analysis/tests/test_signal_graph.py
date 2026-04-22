"""Unit tests for signal graph leader/follower and decay logic."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from event_vol_analysis.analytics.signal_graph import (
    build_graph,
    build_signal_graph_result,
    classify_nodes,
    detect_signal_decay,
    get_tradeable_followers,
    load_signal_graph_config,
)


def _calendar(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _maps() -> tuple[dict, dict]:
    sector_map = {
        "SYF": {"COF": "HIGH", "AXP": "MEDIUM"},
        "COF": {"AXP": "HIGH"},
    }
    factor_map = {
        "SYF": {"primary": "consumer_credit", "secondary": []},
        "COF": {"primary": "consumer_credit", "secondary": []},
        "AXP": {"primary": "consumer_credit", "secondary": []},
    }
    return sector_map, factor_map


def test_build_graph_two_tickers_same_sector() -> None:
    calendar = _calendar(
        [
            {"ticker": "SYF", "event_date": "2026-04-01"},
            {"ticker": "COF", "event_date": "2026-04-15"},
        ]
    )
    sector_map, factor_map = _maps()
    edges = build_graph(calendar, sector_map, factor_map)
    assert len(edges) == 1
    assert edges[0].source == "SYF"
    assert edges[0].target == "COF"


def test_build_graph_different_sectors_no_shared_factor() -> None:
    calendar = _calendar(
        [
            {"ticker": "AAA", "event_date": "2026-04-01"},
            {"ticker": "BBB", "event_date": "2026-04-15"},
        ]
    )
    edges = build_graph(calendar, {}, {})
    assert edges == []


def test_classify_nodes_leader() -> None:
    calendar = _calendar([{"ticker": "SYF", "event_date": "2026-04-01"}])
    nodes = classify_nodes(calendar, today=dt.date(2026, 4, 1), edges=[])
    assert nodes["SYF"].role == "LEADER"


def test_classify_nodes_follower() -> None:
    calendar = _calendar([{"ticker": "AXP", "event_date": "2026-04-20"}])
    nodes = classify_nodes(calendar, today=dt.date(2026, 4, 1), edges=[])
    assert nodes["AXP"].role == "FOLLOWER"


def test_classify_nodes_has_signal_false() -> None:
    calendar = _calendar([{"ticker": "AXP", "event_date": "2026-04-20"}])
    nodes = classify_nodes(calendar, today=dt.date(2026, 4, 1), edges=[])
    assert nodes["AXP"].has_signal is False


def test_detect_signal_decay_absorbed() -> None:
    status = detect_signal_decay(
        "AXP", upstream_move_pct=-0.10, follower_move_pct=-0.06
    )
    assert status == "ABSORBED"


def test_detect_signal_decay_fresh() -> None:
    status = detect_signal_decay("AXP", upstream_move_pct=0.10, follower_move_pct=0.02)
    assert status == "FRESH"


def test_detect_signal_decay_opposite_direction() -> None:
    status = detect_signal_decay("AXP", upstream_move_pct=-0.10, follower_move_pct=0.06)
    assert status == "FRESH"


def test_detect_signal_decay_unknown() -> None:
    status = detect_signal_decay("AXP", upstream_move_pct=0.10, follower_move_pct=None)
    assert status == "UNKNOWN"


def test_get_tradeable_followers_excludes_absorbed() -> None:
    calendar = _calendar(
        [
            {"ticker": "SYF", "event_date": "2026-04-01"},
            {"ticker": "AXP", "event_date": "2026-04-20"},
        ]
    )
    sector_map, factor_map = _maps()
    result = build_signal_graph_result(
        calendar_df=calendar,
        sector_map=sector_map,
        factor_map=factor_map,
        today=dt.date(2026, 4, 10),
        price_moves={"SYF": -0.10, "AXP": -0.06},
    )
    followers = get_tradeable_followers(result.nodes, result.edges, {})
    assert followers == []


def test_get_tradeable_followers_includes_unknown() -> None:
    calendar = _calendar(
        [
            {"ticker": "SYF", "event_date": "2026-04-01"},
            {"ticker": "AXP", "event_date": "2026-04-20"},
        ]
    )
    sector_map, factor_map = _maps()
    result = build_signal_graph_result(
        calendar_df=calendar,
        sector_map=sector_map,
        factor_map=factor_map,
        today=dt.date(2026, 4, 10),
        price_moves={"SYF": -0.10},
    )
    followers = get_tradeable_followers(result.nodes, result.edges, {})
    assert [node.ticker for node in followers] == ["AXP"]


def test_empty_calendar() -> None:
    result = build_signal_graph_result(
        calendar_df=pd.DataFrame(columns=["ticker", "event_date"]),
        sector_map={},
        factor_map={},
        today=dt.date(2026, 4, 1),
        price_moves={},
    )
    assert result.edges == []
    assert result.nodes == {}


def test_single_ticker_no_edges() -> None:
    calendar = _calendar([{"ticker": "NVDA", "event_date": "2026-04-01"}])
    result = build_signal_graph_result(
        calendar_df=calendar,
        sector_map={},
        factor_map={},
        today=dt.date(2026, 4, 1),
        price_moves={},
    )
    assert result.edges == []


def test_config_loads_without_error() -> None:
    sector_map, factor_map = load_signal_graph_config()
    assert isinstance(sector_map, dict)
    assert isinstance(factor_map, dict)


def test_integration_credit_chain_tradeable_follower() -> None:
    calendar = _calendar(
        [
            {"ticker": "SYF", "event_date": "2026-04-01"},
            {"ticker": "COF", "event_date": "2026-04-05"},
            {"ticker": "AXP", "event_date": "2026-04-20"},
        ]
    )
    sector_map, factor_map = _maps()
    result = build_signal_graph_result(
        calendar_df=calendar,
        sector_map=sector_map,
        factor_map=factor_map,
        today=dt.date(2026, 4, 10),
        price_moves={"SYF": -0.10, "COF": -0.08, "AXP": -0.03},
    )
    assert "AXP" in [node.ticker for node in result.tradeable_followers]


def test_integration_credit_chain_absorbed_follower() -> None:
    calendar = _calendar(
        [
            {"ticker": "SYF", "event_date": "2026-04-01"},
            {"ticker": "COF", "event_date": "2026-04-05"},
            {"ticker": "AXP", "event_date": "2026-04-20"},
        ]
    )
    sector_map, factor_map = _maps()
    result = build_signal_graph_result(
        calendar_df=calendar,
        sector_map=sector_map,
        factor_map=factor_map,
        today=dt.date(2026, 4, 10),
        price_moves={"SYF": -0.10, "COF": -0.08, "AXP": -0.06},
    )
    assert "AXP" in [node.ticker for node in result.absorbed_followers]
    assert "AXP" not in [node.ticker for node in result.tradeable_followers]
