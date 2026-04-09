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
"""Public exports for the generic event playbook package."""

from event_option_playbook.backfill import (
    backfill_event_manifest,
    backfill_event_records,
    build_event_id,
    load_event_manifest,
)
from event_option_playbook.bridge import (
    build_playbook_recommendation,
    snapshot_to_event_spec,
    snapshot_to_market_context,
)
from event_option_playbook.context import MarketContext, MarketRegime
from event_option_playbook.events import EventFamily, EventSpec, EventTiming
from event_option_playbook.playbook import (
    PlaybookCandidate,
    PlaybookRecommendation,
    RiskFlag,
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
    "EventSpec",
    "EventTiming",
    "MarketContext",
    "MarketRegime",
    "PlaybookCandidate",
    "PlaybookRecommendation",
    "ReplayAssumptions",
    "RiskFlag",
    "backfill_event_manifest",
    "backfill_event_records",
    "build_event_id",
    "build_playbook_recommendation",
    "load_event_manifest",
    "load_event_replay_context",
    "replay_selection_summary",
    "snapshot_to_event_spec",
    "snapshot_to_market_context",
]
