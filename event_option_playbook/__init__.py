"""Generic event-based options playbook domain package."""

from event_option_playbook.backfill import (
    backfill_event_manifest,
    backfill_event_records,
    build_event_id,
    load_event_manifest,
)
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
    default_entry_windows,
    normalize_event_family,
    normalize_event_name,
    normalize_event_timing,
)
from event_option_playbook.playbook import (
    PlaybookCandidate,
    PlaybookRecommendation,
    PlaybookRiskNote,
)
from event_option_playbook.replay import (
    EventReplayContext,
    ReplayAssumptions,
    load_event_replay_context,
    replay_selection_summary,
)

__all__ = [
    "EventFamily",
    "EventReplayContext",
    "EventSchedule",
    "EventSpec",
    "EventTiming",
    "EventWindow",
    "LiquidityProfile",
    "MarketContext",
    "PlaybookCandidate",
    "PlaybookRecommendation",
    "PlaybookRiskNote",
    "ReplayAssumptions",
    "backfill_event_manifest",
    "backfill_event_records",
    "build_event_id",
    "build_playbook_recommendation",
    "default_entry_windows",
    "load_event_manifest",
    "load_event_replay_context",
    "normalize_event_family",
    "normalize_event_name",
    "normalize_event_timing",
    "ranked_results_to_candidates",
    "replay_selection_summary",
    "snapshot_to_event_spec",
    "snapshot_to_market_context",
]
