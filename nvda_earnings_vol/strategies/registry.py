"""
Strategy registry: entry-condition gates and builder dispatch.

Every strategy type is registered in two parallel dicts:
    STRATEGY_CONDITIONS — maps name → condition function(snapshot) → bool
    STRATEGY_BUILDERS   — maps name → builder function

A module-level assertion ensures the two dicts are always in sync.
Adding a condition without a matching builder (or vice versa) raises
``AssertionError`` at import time.

Usage
-----
    from nvda_earnings_vol.strategies.registry import should_build_strategy
    if should_build_strategy("CALL_BACKSPREAD", snapshot):
        ...

Raises ``KeyError`` for any name not registered in STRATEGY_CONDITIONS.
"""

from __future__ import annotations

from typing import Any, Callable

from nvda_earnings_vol.strategies.backspreads import (
    backspread_conditions_met,
    build_call_backspread,
    build_put_backspread,
)
from nvda_earnings_vol.strategies.calendar import (
    calendar_conditions_met,
    build_calendar,
)
from nvda_earnings_vol.strategies.post_event_calendar import (
    post_event_calendar_conditions_met,
    build_post_event_calendar,
)


# ── Entry-condition gates ──────────────────────────────────────────────────

STRATEGY_CONDITIONS: dict[str, Callable[[dict[str, Any]], bool]] = {
    "CALL_BACKSPREAD": backspread_conditions_met,
    "PUT_BACKSPREAD": backspread_conditions_met,
    "CALENDAR": calendar_conditions_met,
    "POST_EVENT_CALENDAR": post_event_calendar_conditions_met,
}

# ── Builder functions ──────────────────────────────────────────────────────
# Builders accept (snapshot, chains, ...) and return Strategy / dict.
# Stored here for dispatch; callers pass the appropriate chain arguments.

STRATEGY_BUILDERS: dict[str, Callable] = {
    "CALL_BACKSPREAD": build_call_backspread,
    "PUT_BACKSPREAD": build_put_backspread,
    "CALENDAR": build_calendar,
    "POST_EVENT_CALENDAR": build_post_event_calendar,
}

# Structural invariant: conditions and builders must be registered together.
assert set(STRATEGY_CONDITIONS.keys()) == set(STRATEGY_BUILDERS.keys()), (
    "STRATEGY_CONDITIONS and STRATEGY_BUILDERS have mismatched keys. "
    f"Symmetric difference: "
    f"{set(STRATEGY_CONDITIONS.keys()) ^ set(STRATEGY_BUILDERS.keys())}"
)


def should_build_strategy(name: str, snapshot: dict[str, Any]) -> bool:
    """Check whether a named strategy's entry conditions are satisfied.

    Args:
        name: Strategy name (e.g. ``"CALL_BACKSPREAD"``).  Must be a key
            in ``STRATEGY_CONDITIONS``.
        snapshot: Market snapshot dict.

    Returns:
        True when entry conditions pass for the given snapshot.

    Raises:
        KeyError: If ``name`` is not registered in ``STRATEGY_CONDITIONS``.
    """
    # KeyError propagates naturally for unregistered names
    condition_fn = STRATEGY_CONDITIONS[name]
    return condition_fn(snapshot)


__all__ = [
    "STRATEGY_CONDITIONS",
    "STRATEGY_BUILDERS",
    "should_build_strategy",
]
