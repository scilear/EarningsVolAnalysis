"""Generic event-based options playbook domain package."""

from event_option_playbook.bridge import (
    build_playbook_recommendation,
    ranked_results_to_candidates,
    snapshot_to_event_spec,
    snapshot_to_market_context,
)
from event_option_playbook.context import LiquidityProfile, MarketContext
from event_option_playbook.events import (
    EventFamily,
    EventSchedule,
    EventSpec,
    EventTiming,
    EventWindow,
    normalize_event_family,
    normalize_event_name,
    normalize_event_timing,
    default_entry_windows,
)
from event_option_playbook.playbook import (
    PlaybookCandidate,
    PlaybookRiskNote,
    PlaybookRecommendation,
)

__all__ = [
    "build_playbook_recommendation",
    "LiquidityProfile",
    "MarketContext",
    "EventFamily",
    "EventSchedule",
    "EventSpec",
    "EventTiming",
    "EventWindow",
    "PlaybookCandidate",
    "PlaybookRiskNote",
    "PlaybookRecommendation",
    "ranked_results_to_candidates",
    "snapshot_to_event_spec",
    "snapshot_to_market_context",
    "normalize_event_family",
    "normalize_event_name",
    "normalize_event_timing",
    "default_entry_windows",
]
